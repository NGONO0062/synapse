"""Worker de l'orchestrateur : cherche ce qui est dû aux casquettes et le fait avancer.

    python -m synapse_api.agents.worker          # en continu
    python -m synapse_api.agents.worker --once   # un seul tour

L'état des graphes est sauvegardé dans PostgreSQL (tables du checkpointer LangGraph).
"""

import argparse
import logging
import time
from datetime import UTC, datetime, timedelta

from langgraph.checkpoint.postgres import PostgresSaver
from sqlalchemy import select

from synapse_api import memory
from synapse_api.agents import activity, evaluation
from synapse_api.agents.casquettes import LABELS
from synapse_api.agents.gateway import LiteLLMModel, gateway_catalog
from synapse_api.agents.graph import Deps, build_orchestrator, run
from synapse_api.agents.jobs import Job, due_assignments
from synapse_api.agents.sandbox import Workspace
from synapse_api.agents.usage import QuotaExceeded
from synapse_api.config import get_settings
from synapse_api.db.models import MemoryVersion, Task
from synapse_api.db.session import _session_factory
from synapse_api.domain.enums import Casquette, MessageKind, TaskStatus
from synapse_api.domain.lifecycle import Actor, Command, is_execution_overdue
from synapse_api.services import add_message, execute

log = logging.getLogger("synapse.orchestrateur")

JOB_LABELS = {Job.REPORT: "reformulation", Job.PLAN: "plan", Job.EXECUTE: "exécution"}


def describe(exc: Exception) -> str:
    """Raison d'un échec, lisible par le PO dans l'interface."""
    text = str(exc)
    lowered = text.lower()
    if isinstance(exc, QuotaExceeded):
        return text
    if any(k in lowered for k in ("api_key", "api key", "authentication", "401", "403")):
        return "Le fournisseur de ce modèle refuse l'accès : clé absente ou invalide dans infra/.env."
    if "connection error" in lowered or isinstance(exc, ConnectionError):
        return "La passerelle IA (LiteLLM) ne répond pas."
    first = text.strip().splitlines()[0] if text.strip() else type(exc).__name__
    return first[:300]


def escalate_overdue(deps: Deps, now: datetime | None = None) -> list[str]:
    """Durée maximale d'exécution atteinte (2 h) : la tâche remonte au PO."""
    now = now or datetime.now(UTC)
    escalated = []
    with deps.sessions() as session:
        running = select(Task).where(Task.status == TaskStatus.IN_PROGRESS, Task.awaiting_human.is_(False))
        for task in session.scalars(running):
            if is_execution_overdue(task.lifecycle_state(), now):
                execute(
                    session, task, Command.ESCALATE_TIMEOUT, Actor.agent(Casquette.ORCHESTRATEUR), now=now
                )
                escalated.append(task.code)
        session.commit()
    return escalated


def merge_done(deps: Deps, retry_at: dict[str, float]) -> list[str]:
    """Tâche en Done : le DevOps fusionne sa branche dans main."""
    merged = []
    with deps.sessions() as session:
        done = select(Task).where(
            Task.status == TaskStatus.DONE, Task.branch.is_not(None), Task.merged_commit.is_(None)
        )
        for task in session.scalars(done).all():
            key = f"merge:{task.id}"
            if retry_at.get(key, 0) > time.monotonic():
                continue
            ws = Workspace(deps.git_dir, task.project_id, task.id, task.branch)
            try:
                ws.ensure()
                task.merged_commit = ws.merge_into_main(f"{task.code} : {task.title}")
            except Exception as exc:  # noqa: BLE001 : réessayé plus tard, sans bloquer les autres
                retry_at[key] = time.monotonic() + get_settings().orchestrator_retry_delay
                log.warning("%s · fusion dans main impossible : %s", task.code, exc)
                continue
            add_message(
                session,
                task,
                kind=MessageKind.MESSAGE,
                author=Actor.agent(Casquette.DEVOPS),
                body=f"Branche {task.branch} fusionnée dans main (commit {task.merged_commit[:8]}).",
            )
            session.commit()
            merged.append(task.code)
    return merged


def write_memory(deps: Deps, retry_at: dict[str, float]) -> list[str]:
    """Versions validées de la mémoire pas encore dans le dépôt : écrites dans memoire/ sur main."""
    written = []
    with deps.sessions() as session:
        pending = session.scalars(select(MemoryVersion).where(MemoryVersion.commit.is_(None))).all()
        for project_id in sorted({v.project_id for v in pending}, key=str):
            key = f"memory:{project_id}"
            if retry_at.get(key, 0) > time.monotonic():
                continue
            versions = [v for v in pending if v.project_id == project_id]
            ws = Workspace.main_of(deps.git_dir, project_id)
            try:
                ws.sync_main()
                for document, version in memory.current(session, project_id).items():
                    if version is not None:
                        path = f"{memory.MEMORY_DIR}/{memory.FILES[document]}"
                        ws.write(path, memory.render_markdown(version))
                summary = "; ".join(f"{memory.LABELS[v.document]} v{v.version}" for v in versions)
                commit = ws.commit(f"Mémoire du projet : {summary}") or ws.head()
            except Exception as exc:  # noqa: BLE001 : réessayé plus tard, sans bloquer les autres
                retry_at[key] = time.monotonic() + get_settings().orchestrator_retry_delay
                log.warning("Mémoire du projet %s · écriture dans le dépôt impossible : %s", project_id, exc)
                continue
            for version in versions:
                version.commit = commit
            session.commit()
            written.append(str(project_id))
    return written


def replay_reference_cases(deps: Deps, retry_at: dict[str, float]) -> str | None:
    """Rejoue les cas de référence d'une casquette dont l'empreinte a changé (un rejeu par tour)."""
    for due in evaluation.due_evaluations(deps):
        key = f"evaluation:{due.ai_model}:{due.fingerprint}"
        if retry_at.get(key, 0) > time.monotonic():
            continue
        what = f"Cas de référence · {LABELS[due.casquette]} · {due.ai_model}"
        try:
            run = evaluation.evaluate(deps, due.casquette, due.ai_model, due.served_model)
        except Exception as exc:  # noqa: BLE001 : repris plus tard, sans bloquer les tâches
            retry_at[key] = time.monotonic() + get_settings().orchestrator_retry_delay
            log.warning("%s · échec, nouvel essai plus tard : %s", what, exc)
            return "error"
        log.info("%s · %d/%d cas réussis", what, run.passed, run.total)
        return "regression" if run.regressed_cases else "done"
    return None


def run_once(orchestrator, deps: Deps, retry_at: dict[str, float] | None = None) -> dict[str, str]:
    """Un tour : chaque travail dû avance d'un coup. Renvoie l'issue par fil LangGraph."""
    retry_at = retry_at if retry_at is not None else {}
    for code in escalate_overdue(deps):
        log.info("%s · 2 h d'exécution atteintes : remontée au PO", code)
    for code in merge_done(deps, retry_at):
        log.info("%s · branche fusionnée dans main", code)
    for project_id in write_memory(deps, retry_at):
        log.info("Mémoire du projet %s · écrite dans memoire/ sur main", project_id)
    with deps.sessions() as session:
        assignments = due_assignments(session)
    outcomes = {}
    for a in assignments:
        activity.queue(deps.sessions, a.task_id, a.author)
    for a in assignments:
        if retry_at.get(a.thread_id, 0) > time.monotonic():
            continue
        what = f"{a.code} · {JOB_LABELS[a.job]} v{a.version} · {LABELS[a.author]}"
        activity.report(deps.sessions, a.task_id, a.author, "prépare son travail")
        try:
            outcomes[a.thread_id] = run(orchestrator, a)
            retry_at.pop(a.thread_id, None)
            activity.clear(deps.sessions, a.task_id)
            log.info("%s · %s", what, outcomes[a.thread_id])
        except Exception as exc:  # noqa: BLE001 : un échec n'arrête pas les autres tâches
            outcomes[a.thread_id] = "error"
            delay = get_settings().orchestrator_retry_delay
            retry_at[a.thread_id] = time.monotonic() + delay
            activity.fail(
                deps.sessions, a.task_id, describe(exc), datetime.now(UTC) + timedelta(seconds=delay)
            )
            log.warning("%s · échec, nouvel essai plus tard : %s", what, exc)
    # Les tâches passent d'abord : les cas de référence se rejouent quand rien d'autre n'est dû.
    if not assignments and get_settings().evaluations:
        replayed = replay_reference_cases(deps, retry_at)
        if replayed:
            outcomes["evaluation"] = replayed
    return outcomes


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--once", action="store_true", help="un seul tour, puis s'arrêter")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    settings = get_settings()
    deps = Deps(sessions=_session_factory(), model=LiteLLMModel, catalog=gateway_catalog)
    conn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    with PostgresSaver.from_conn_string(conn) as checkpointer:
        checkpointer.setup()
        orchestrator = build_orchestrator(deps, checkpointer)
        retry_at: dict[str, float] = {}
        activity.clear(deps.sessions)  # une activité restée d'un arrêt précédent n'est plus vraie
        evaluation.interrupted(deps)
        log.info("Orchestrateur prêt (passerelle %s).", settings.litellm_url)
        while True:
            run_once(orchestrator, deps, retry_at)
            if args.once:
                break
            time.sleep(settings.orchestrator_interval)


if __name__ == "__main__":
    main()
