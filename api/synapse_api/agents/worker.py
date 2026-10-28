"""Worker de l'orchestrateur : cherche ce qui est dû aux casquettes et le fait avancer.

    python -m synapse_api.agents.worker          # en continu
    python -m synapse_api.agents.worker --once   # un seul tour

L'état des graphes est sauvegardé dans PostgreSQL (tables du checkpointer LangGraph).
"""

import argparse
import logging
import time

from langgraph.checkpoint.postgres import PostgresSaver

from synapse_api.agents.casquettes import LABELS
from synapse_api.agents.gateway import LiteLLMModel
from synapse_api.agents.graph import Deps, build_orchestrator, run
from synapse_api.agents.jobs import Job, due_assignments
from synapse_api.config import get_settings
from synapse_api.db.session import _session_factory

log = logging.getLogger("synapse.orchestrateur")

JOB_LABELS = {Job.REPORT: "reformulation", Job.PLAN: "plan"}


def run_once(orchestrator, deps: Deps, retry_at: dict[str, float] | None = None) -> dict[str, str]:
    """Un tour : chaque travail dû avance d'un coup. Renvoie l'issue par fil LangGraph."""
    retry_at = retry_at if retry_at is not None else {}
    with deps.sessions() as session:
        assignments = due_assignments(session)
    outcomes = {}
    for a in assignments:
        if retry_at.get(a.thread_id, 0) > time.monotonic():
            continue
        what = f"{a.code} · {JOB_LABELS[a.job]} v{a.version} · {LABELS[a.author]}"
        try:
            outcomes[a.thread_id] = run(orchestrator, a)
            retry_at.pop(a.thread_id, None)
            log.info("%s · %s", what, outcomes[a.thread_id])
        except Exception as exc:  # noqa: BLE001 : un échec n'arrête pas les autres tâches
            outcomes[a.thread_id] = "error"
            retry_at[a.thread_id] = time.monotonic() + get_settings().orchestrator_retry_delay
            log.warning("%s · échec, nouvel essai plus tard : %s", what, exc)
    return outcomes


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--once", action="store_true", help="un seul tour, puis s'arrêter")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    settings = get_settings()
    deps = Deps(sessions=_session_factory(), model=LiteLLMModel)
    conn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    with PostgresSaver.from_conn_string(conn) as checkpointer:
        checkpointer.setup()
        orchestrator = build_orchestrator(deps, checkpointer)
        retry_at: dict[str, float] = {}
        log.info("Orchestrateur prêt (passerelle %s).", settings.litellm_url)
        while True:
            run_once(orchestrator, deps, retry_at)
            if args.once:
                break
            time.sleep(settings.orchestrator_interval)


if __name__ == "__main__":
    main()
