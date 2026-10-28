"""Travaux des casquettes : qui fait quoi, avec quel dossier, et quand c'est « terminé ».

L'orchestrateur lit l'état du cycle de vie pour savoir ce qui est dû (section 5) :
- un bug écrit en langage naturel attend sa reformulation (Débogueur) ;
- une tâche en To do sans plan à valider attend son plan (Architecte, Débogueur ou Rédacteur) ;
- une tâche en In progress qui n'attend pas l'humain s'exécute (Développeur ou Rédacteur, voir
  execution.py).
"""

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from synapse_api.agents.casquettes import LABELS
from synapse_api.db.models import Task
from synapse_api.domain.enums import Casquette, TaskStatus, TaskType
from synapse_api.domain.lifecycle import Actor, ActorKind, Command
from synapse_api.schemas import ReformulatedReport
from synapse_api.services import propose_plan, propose_report


class Job(StrEnum):
    REPORT = "REPORT"  # reformuler un bug écrit en langage naturel
    PLAN = "PLAN"  # proposer le plan d'une tâche en To do
    EXECUTE = "EXECUTE"  # réaliser le plan validé, jusqu'au livrable en Review


# Chaîne de casquettes (section 5) : qui rédige, qui relit avant l'humain.
AUTHORS = {
    (Job.REPORT, TaskType.BUGFIX): Casquette.DEBOGUEUR,
    (Job.PLAN, TaskType.FEATURE): Casquette.ARCHITECTE,
    (Job.PLAN, TaskType.BUGFIX): Casquette.DEBOGUEUR,
    (Job.PLAN, TaskType.DOC): Casquette.REDACTEUR,
    (Job.EXECUTE, TaskType.FEATURE): Casquette.DEVELOPPEUR,
    (Job.EXECUTE, TaskType.BUGFIX): Casquette.DEVELOPPEUR,
    (Job.EXECUTE, TaskType.DOC): Casquette.REDACTEUR,
}
REVIEWERS = {
    (Job.REPORT, TaskType.BUGFIX): Casquette.ANALYSTE_TEST,
    (Job.PLAN, TaskType.FEATURE): Casquette.BUSINESS_ANALYST,
    (Job.PLAN, TaskType.BUGFIX): Casquette.REVIEWER,
    (Job.PLAN, TaskType.DOC): Casquette.BUSINESS_ANALYST,
    (Job.EXECUTE, TaskType.FEATURE): Casquette.REVIEWER,
    (Job.EXECUTE, TaskType.BUGFIX): Casquette.REVIEWER,
    (Job.EXECUTE, TaskType.DOC): Casquette.BUSINESS_ANALYST,
}

# Décisions humaines qui (re)lancent l'exécution : chacune ouvre un nouveau fil LangGraph.
EXECUTION_TRIGGERS = {Command.VALIDATE_PLAN, Command.ANSWER_HUMAN, Command.REJECT_RESULT}


@dataclass(frozen=True)
class Assignment:
    """Travail dû à une casquette, choisi par l'orchestrateur."""

    task_id: uuid.UUID
    code: str
    job: Job
    version: int  # version de la proposition à produire, ou rang de l'exécution
    task_type: TaskType

    @property
    def author(self) -> Casquette:
        return AUTHORS[(self.job, self.task_type)]

    @property
    def reviewer(self) -> Casquette:
        return REVIEWERS[(self.job, self.task_type)]

    @classmethod
    def from_state(cls, state: dict) -> "Assignment":
        return cls(
            uuid.UUID(state["task_id"]),
            state["code"],
            Job(state["job"]),
            state["version"],
            TaskType(state["task_type"]),
        )

    def to_state(self) -> dict:
        return {
            "task_id": str(self.task_id),
            "code": self.code,
            "job": self.job.value,
            "version": self.version,
            "task_type": self.task_type.value,
        }

    @property
    def thread_id(self) -> str:
        # Un fil LangGraph par proposition : une reprise après interruption retrouve son état.
        return f"{self.task_id}:{self.job.lower()}:{self.version}"


def assignment_for(task: Task) -> Assignment | None:
    state = task.lifecycle_state()
    if (
        state.status is TaskStatus.BACKLOG
        and state.report_required
        and not state.validated_report_version
        and not state.has_pending_report
    ):
        return Assignment(task.id, task.code, Job.REPORT, state.report_version + 1, task.type)
    if state.status is TaskStatus.TODO and not state.has_pending_plan:
        return Assignment(task.id, task.code, Job.PLAN, state.plan_version + 1, task.type)
    if state.status is TaskStatus.IN_PROGRESS and not state.awaiting_human:
        runs = sum(1 for e in task.events if e.command in EXECUTION_TRIGGERS)
        return Assignment(task.id, task.code, Job.EXECUTE, runs, task.type)
    return None


def branch_name(code: str) -> str:
    return f"synapse/{code.lower()}"


def due_assignments(session: Session) -> list[Assignment]:
    query = (
        select(Task)
        .where(Task.status.in_([TaskStatus.BACKLOG, TaskStatus.TODO, TaskStatus.IN_PROGRESS]))
        .order_by(Task.updated_at)
    )
    return [a for task in session.scalars(query) if (a := assignment_for(task))]


TYPE_LABELS = {TaskType.FEATURE: "Feature", TaskType.BUGFIX: "Bugfix", TaskType.DOC: "Doc"}

COMMAND_LABELS = {
    "REQUEST_REPORT_CHANGES": "a demandé une correction de la reformulation",
    "VALIDATE_REPORT": "a validé la reformulation",
    "PRIORITIZE": "a priorisé la tâche",
    "REQUEST_PLAN_CHANGES": "a demandé des modifications du plan",
    "VALIDATE_PLAN": "a validé le plan",
    "ANSWER_HUMAN": "a répondu",
    "REJECT_RESULT": "a refusé le résultat",
    "VALIDATE_RESULT": "a validé le résultat",
}


def brief(task: Task) -> str:
    """Dossier remis à la casquette : le projet, la tâche et tout le fil, décisions comprises."""
    project = task.project
    lines = [f"Projet : {project.name}"]
    if project.description:
        lines += ["", project.description]
    lines += ["", f"Tâche {task.code} ({TYPE_LABELS[task.type]}) : {task.title}"]
    if task.bug_report:
        lines += ["", "Signalement structuré :", json.dumps(task.bug_report, ensure_ascii=False, indent=2)]

    items: list[tuple[object, str]] = []
    for m in task.messages:
        if m.author_kind is ActorKind.HUMAN:
            who = m.author_name
        else:
            who = LABELS[Casquette(m.casquette)] if m.casquette else "Agent"
        text = f"{who} ({m.kind.lower()}) : {m.body}"
        if m.payload:
            text += "\n" + json.dumps(_essential(m.payload), ensure_ascii=False)
        items.append((m.created_at, text))
    for e in task.events:
        if e.actor_kind is ActorKind.HUMAN and e.command in COMMAND_LABELS:
            text = f"{e.actor_name} {COMMAND_LABELS[e.command]}"
            items.append((e.created_at, text + (f" : « {e.comment} »" if e.comment else ".")))
    lines += ["", "Fil de la tâche, du plus ancien au plus récent :"]
    lines += [f"- {text}" for _, text in sorted(items, key=lambda item: item[0])]

    validated = next(
        (m for m in task.messages if m.kind == "PLAN" and m.plan_version == task.validated_plan_version),
        None,
    )
    if task.validated_plan_version and validated:
        plan = json.dumps(_essential(validated.payload or {}), ensure_ascii=False, indent=2)
        lines += ["", f"Plan validé par le PO (version {task.validated_plan_version}) :", plan]
    return "\n".join(lines)


def _essential(payload: dict) -> dict:
    kept = {k: v for k, v in payload.items() if v not in (None, [], "")}
    if "files" in kept:  # le diff complet est dans le dépôt, pas dans le dossier
        kept["files"] = [f["path"] for f in kept["files"]]
    return kept


# Réponses attendues des modèles.


class ReportDraft(BaseModel):
    message: str = Field(description="Une ou deux phrases à l'auteur du bug : il valide ou fait corriger.")
    report: ReformulatedReport
    uncertainties: list[str] = Field(default=[], description="Ce qui manque ou reste flou dans le texte.")
    assumptions: list[str] = Field(default=[], description="Ce que tu as déduit sans que l'auteur le dise.")


class PlanDraft(BaseModel):
    message: str = Field(description="Une ou deux phrases au PO : ce que propose le plan.")
    changes: list[str] = Field(
        description="Ce qui change, une ligne par changement, préfixée par « + », « ~ » ou « - »."
    )
    failing_test: str | None = Field(
        default=None,
        description="Bugfix seulement : le test qui reproduit le bug et échoue avant correction.",
    )
    tests: str = Field(description="Les tests prévus, en une phrase.")
    uncertainties: list[str] = []
    assumptions: list[str] = []
    unverified: list[str] = Field(default=[], description="Ce que tu n'as pas pu vérifier.")


class Review(BaseModel):
    approved: bool = Field(description="Vrai si la proposition peut être soumise à l'humain telle quelle.")
    corrections: list[str] = Field(
        default=[], description="Corrections précises demandées ; vide si approuvé."
    )


# Définition de « terminé », vérifiée avant la relecture.


def check_report(draft: ReportDraft, task_type: TaskType) -> list[str]:
    report = draft.report
    problems = []
    if report.expected.strip().casefold() == report.actual.strip().casefold():
        problems.append("Le résultat attendu et le résultat obtenu sont identiques.")
    if len(report.title) > 80:
        problems.append("Le titre dépasse 80 caractères.")
    if not draft.message.strip():
        problems.append("Le message à l'auteur est vide.")
    return problems


def check_plan(draft: PlanDraft, task_type: TaskType) -> list[str]:
    problems = []
    if not draft.changes:
        problems.append("Le plan ne dit pas ce qui change.")
    if any(not change.lstrip().startswith(("+", "~", "-")) for change in draft.changes):
        problems.append("Chaque changement commence par « + », « ~ » ou « - ».")
    if task_type is TaskType.BUGFIX and not (draft.failing_test or "").strip():
        problems.append(
            "Un plan de Bugfix commence par le test qui reproduit le bug et échoue avant correction."
        )
    if not draft.tests.strip():
        problems.append("Le plan ne dit pas quels tests sont prévus.")
    if not draft.message.strip():
        problems.append("Le message au PO est vide.")
    return problems


# Publication : par les services, donc par les règles du cycle de vie.


def publish_report(
    session: Session, task: Task, actor: Actor, draft: ReportDraft, warnings: list[str], ref: str
):
    propose_report(
        session,
        task,
        actor,
        body=draft.message,
        ai_model=task.ai_model,
        referentiel_version=ref,
        payload={
            "report": draft.report.model_dump(),
            "warnings": warnings,
            "uncertainties": draft.uncertainties,
            "assumptions": draft.assumptions,
        },
    )


def publish_plan(session: Session, task: Task, actor: Actor, draft: PlanDraft, warnings: list[str], ref: str):
    propose_plan(
        session,
        task,
        actor,
        body=draft.message,
        ai_model=task.ai_model,
        referentiel_version=ref,
        payload={
            "changes": draft.changes,
            "failing_test": draft.failing_test if task.type is TaskType.BUGFIX else None,
            "tests": draft.tests,
            "warnings": warnings,
            "uncertainties": draft.uncertainties,
            "assumptions": draft.assumptions,
            "unverified": draft.unverified,
        },
    )


INSTRUCTIONS = {
    Job.REPORT: (
        "Reformule ce bug, écrit en langage naturel par son auteur, en signalement structuré : titre court, "
        "étapes numérotées pour reproduire, résultat attendu, résultat obtenu, environnement (STAGING ou "
        "PREPROD), navigateur ou appareil, gravité (BLOQUANT, MAJEUR ou MINEUR). Si l'auteur a demandé une "
        "correction d'une reformulation précédente, applique-la. Le message s'adresse à l'auteur."
    ),
    Job.PLAN: (
        "Propose le plan de cette tâche. Le PO le validera avant toute exécution. Si le PO a demandé des "
        "modifications d'un plan précédent, applique-les et dis-le dans le message."
    ),
}

PLAN_FOCUS = {
    TaskType.FEATURE: "Pars de l'analyse d'impact : écrans, API, données, droits et tests touchés.",
    TaskType.BUGFIX: (
        "Commence par le test qui reproduit le bug et échoue, puis la correction et la non-régression."
    ),
    TaskType.DOC: "Dis quels documents sont créés ou modifiés, pour quel lecteur.",
}


@dataclass(frozen=True)
class JobSpec:
    schema: type[BaseModel]
    check: Callable[[BaseModel, TaskType], list[str]]
    publish: Callable[[Session, Task, Actor, BaseModel, list[str], str], None]

    def instruction(self, job: Job, task_type: TaskType) -> str:
        return INSTRUCTIONS[job] + (f" {PLAN_FOCUS[task_type]}" if job is Job.PLAN else "")


JOBS: dict[Job, JobSpec] = {
    Job.REPORT: JobSpec(ReportDraft, check_report, publish_report),  # type: ignore[arg-type]
    Job.PLAN: JobSpec(PlanDraft, check_plan, publish_plan),  # type: ignore[arg-type]
}
