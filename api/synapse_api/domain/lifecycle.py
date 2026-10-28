"""Cycle de vie d'une tâche (dossier de développement, section 5).

Module pur : aucune dépendance à la base ni au web. Chaque commande prend un état,
un acteur et renvoie le nouvel état, ou lève `LifecycleError`. Les règles :

- BACKLOG → TODO : le PO priorise. Un bug écrit en langage naturel doit d'abord voir sa
  reformulation validée par son auteur.
- TODO → IN_PROGRESS : le PO valide le plan proposé par un agent.
- IN_PROGRESS → REVIEW : l'orchestrateur soumet un livrable contrôlé.
- REVIEW → DONE : le PO valide le résultat ; pour un Bugfix, le testeur confirme aussi.
- REVIEW → IN_PROGRESS : le PO refuse, avec un commentaire.

Une tâche qui attend un humain reste IN_PROGRESS avec `awaiting_human`. Un agent qui
doit s'écarter du plan validé propose une nouvelle version et s'arrête jusqu'à validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum

from .enums import Casquette, Role, TaskStatus, TaskType
from .rules import MAX_QA_ROUND_TRIPS, MAX_TASK_EXECUTION


class ActorKind(StrEnum):
    HUMAN = "HUMAN"
    AGENT = "AGENT"


@dataclass(frozen=True)
class Actor:
    kind: ActorKind
    name: str
    roles: frozenset[Role] = field(default_factory=frozenset)
    casquette: Casquette | None = None

    @classmethod
    def human(cls, name: str, *roles: Role) -> Actor:
        return cls(ActorKind.HUMAN, name, frozenset(roles))

    @classmethod
    def agent(cls, casquette: Casquette) -> Actor:
        return cls(ActorKind.AGENT, casquette.value, casquette=casquette)


class AwaitingReason(StrEnum):
    QUESTION = "QUESTION"  # l'agent pose une question au PO
    PLAN_CHANGE = "PLAN_CHANGE"  # l'agent doit s'écarter du plan validé
    QA_LIMIT = "QA_LIMIT"  # allers-retours QA/Débogueur épuisés
    TIMEOUT = "TIMEOUT"  # durée maximale d'exécution atteinte


class Command(StrEnum):
    PROPOSE_REPORT = "PROPOSE_REPORT"
    REQUEST_REPORT_CHANGES = "REQUEST_REPORT_CHANGES"
    VALIDATE_REPORT = "VALIDATE_REPORT"
    PRIORITIZE = "PRIORITIZE"
    PROPOSE_PLAN = "PROPOSE_PLAN"
    REQUEST_PLAN_CHANGES = "REQUEST_PLAN_CHANGES"
    VALIDATE_PLAN = "VALIDATE_PLAN"
    ASK_HUMAN = "ASK_HUMAN"
    ANSWER_HUMAN = "ANSWER_HUMAN"
    RECORD_QA_FAILURE = "RECORD_QA_FAILURE"
    ESCALATE_TIMEOUT = "ESCALATE_TIMEOUT"
    SUBMIT_FOR_REVIEW = "SUBMIT_FOR_REVIEW"
    VALIDATE_RESULT = "VALIDATE_RESULT"
    CONFIRM_FIX = "CONFIRM_FIX"
    REJECT_RESULT = "REJECT_RESULT"


_PO = frozenset({Role.PO})
# L'auteur d'un bug, PO ou testeur, valide sa reformulation (l'API vérifie qu'il en est l'auteur).
_REPORTER = frozenset({Role.PO, Role.TESTEUR})

HUMAN_COMMANDS: dict[Command, frozenset[Role]] = {
    Command.REQUEST_REPORT_CHANGES: _REPORTER,
    Command.VALIDATE_REPORT: _REPORTER,
    Command.PRIORITIZE: _PO,
    Command.REQUEST_PLAN_CHANGES: _PO,
    Command.VALIDATE_PLAN: _PO,
    Command.ANSWER_HUMAN: _PO,
    Command.VALIDATE_RESULT: _PO,
    Command.REJECT_RESULT: _PO,
    Command.CONFIRM_FIX: frozenset({Role.TESTEUR}),
}

# Commandes d'agent réservées à une casquette ; les autres sont ouvertes à toutes.
AGENT_COMMANDS: dict[Command, Casquette | None] = {
    Command.PROPOSE_REPORT: None,
    Command.PROPOSE_PLAN: None,
    Command.ASK_HUMAN: None,
    Command.RECORD_QA_FAILURE: None,
    Command.ESCALATE_TIMEOUT: Casquette.ORCHESTRATEUR,
    Command.SUBMIT_FOR_REVIEW: Casquette.ORCHESTRATEUR,
}

COMMENT_REQUIRED = {
    Command.REQUEST_REPORT_CHANGES,
    Command.REQUEST_PLAN_CHANGES,
    Command.ASK_HUMAN,
    Command.ANSWER_HUMAN,
    Command.REJECT_RESULT,
}


class LifecycleError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class TaskState:
    type: TaskType
    status: TaskStatus = TaskStatus.BACKLOG
    # Bug écrit en langage naturel : sa reformulation doit être validée avant la priorisation.
    report_required: bool = False
    report_version: int = 0  # dernière reformulation proposée
    validated_report_version: int = 0
    rejected_report_version: int = 0
    plan_version: int = 0  # dernière version proposée ; 0 = aucun plan
    validated_plan_version: int = 0
    rejected_plan_version: int = 0
    awaiting_human: bool = False
    awaiting_reason: AwaitingReason | None = None
    qa_round_trips: int = 0
    execution_started_at: datetime | None = None
    result_validated: bool = False
    tester_confirmed: bool = False

    @property
    def has_pending_plan(self) -> bool:
        return self.plan_version > max(self.validated_plan_version, self.rejected_plan_version)

    @property
    def has_pending_report(self) -> bool:
        return self.report_version > max(self.validated_report_version, self.rejected_report_version)

    @property
    def report_ready(self) -> bool:
        return not self.report_required or self.validated_report_version > 0


def apply(
    state: TaskState,
    command: Command,
    actor: Actor,
    *,
    now: datetime,
    comment: str | None = None,
) -> TaskState:
    _check_actor(command, actor)
    if command in COMMENT_REQUIRED and not (comment and comment.strip()):
        raise LifecycleError("comment_required", "Un commentaire est obligatoire.")
    if state.status is TaskStatus.DONE:
        raise LifecycleError("task_done", "La tâche est terminée.")
    return _HANDLERS[command](state, now)


class PendingDecision(StrEnum):
    """Ce que la tâche attend d'un humain (accueil : « En attente de ta validation »)."""

    REPORT = "REPORT"  # l'auteur d'un bug valide ou fait corriger sa reformulation
    PLAN = "PLAN"  # le PO valide ou fait modifier un plan
    QUESTION = "QUESTION"  # le PO répond à un agent
    ESCALATION = "ESCALATION"  # limite QA ou durée atteinte, le PO tranche
    RESULT = "RESULT"  # le PO valide ou refuse un résultat
    TESTER_CONFIRMATION = "TESTER_CONFIRMATION"  # le testeur confirme un correctif


def pending_decision(state: TaskState) -> PendingDecision | None:
    if state.status is TaskStatus.BACKLOG and state.has_pending_report:
        return PendingDecision.REPORT
    if state.status is TaskStatus.TODO and state.has_pending_plan:
        return PendingDecision.PLAN
    if state.status is TaskStatus.IN_PROGRESS and state.awaiting_human:
        return {
            AwaitingReason.PLAN_CHANGE: PendingDecision.PLAN,
            AwaitingReason.QUESTION: PendingDecision.QUESTION,
        }.get(state.awaiting_reason, PendingDecision.ESCALATION)  # type: ignore[arg-type]
    if state.status is TaskStatus.REVIEW:
        if not state.result_validated:
            return PendingDecision.RESULT
        if state.type is TaskType.BUGFIX and not state.tester_confirmed:
            return PendingDecision.TESTER_CONFIRMATION
    return None


def is_execution_overdue(state: TaskState, now: datetime) -> bool:
    return (
        state.status is TaskStatus.IN_PROGRESS
        and not state.awaiting_human
        and state.execution_started_at is not None
        and now - state.execution_started_at >= MAX_TASK_EXECUTION
    )


def _check_actor(command: Command, actor: Actor) -> None:
    if command in HUMAN_COMMANDS:
        if actor.kind is not ActorKind.HUMAN:
            raise LifecycleError("human_only", "Cette décision revient à un humain.")
        allowed = HUMAN_COMMANDS[command]
        if not allowed & actor.roles:
            raise LifecycleError("forbidden", f"Rôle {' ou '.join(sorted(allowed))} requis.")
        return
    if actor.kind is not ActorKind.AGENT:
        raise LifecycleError("agent_only", "Cette action est réservée aux agents.")
    required = AGENT_COMMANDS[command]
    if required is not None and actor.casquette is not required:
        raise LifecycleError("forbidden", f"Casquette {required} requise.")


def _require(state: TaskState, *statuses: TaskStatus) -> None:
    if state.status not in statuses:
        raise LifecycleError(
            "invalid_status",
            f"Action impossible au statut {state.status}.",
        )


def _require_running(state: TaskState) -> None:
    _require(state, TaskStatus.IN_PROGRESS)
    if state.awaiting_human:
        raise LifecycleError("awaiting_human", "La tâche attend une réponse humaine.")


def _wait(state: TaskState, reason: AwaitingReason) -> TaskState:
    return replace(state, awaiting_human=True, awaiting_reason=reason, execution_started_at=None)


def _resume(state: TaskState, now: datetime) -> TaskState:
    return replace(state, awaiting_human=False, awaiting_reason=None, execution_started_at=now)


def _propose_report(state: TaskState, now: datetime) -> TaskState:
    _require(state, TaskStatus.BACKLOG)
    if not state.report_required:
        raise LifecycleError("no_report_needed", "Ce bug a été signalé par le formulaire détaillé.")
    if state.validated_report_version:
        raise LifecycleError("report_validated", "Le signalement est déjà validé.")
    return replace(state, report_version=state.report_version + 1)


def _require_pending_report(state: TaskState) -> None:
    _require(state, TaskStatus.BACKLOG)
    if not state.has_pending_report:
        raise LifecycleError("no_pending_report", "Aucune reformulation à valider.")


def _request_report_changes(state: TaskState, now: datetime) -> TaskState:
    _require_pending_report(state)
    return replace(state, rejected_report_version=state.report_version)


def _validate_report(state: TaskState, now: datetime) -> TaskState:
    _require_pending_report(state)
    return replace(state, validated_report_version=state.report_version)


def _prioritize(state: TaskState, now: datetime) -> TaskState:
    _require(state, TaskStatus.BACKLOG)
    if not state.report_ready:
        raise LifecycleError(
            "report_not_validated", "Le signalement doit d'abord être validé par son auteur."
        )
    return replace(state, status=TaskStatus.TODO)


def _propose_plan(state: TaskState, now: datetime) -> TaskState:
    _require(state, TaskStatus.TODO, TaskStatus.IN_PROGRESS)
    proposed = replace(state, plan_version=state.plan_version + 1)
    if state.status is TaskStatus.IN_PROGRESS:
        # Écart au plan validé : l'agent s'arrête et redemande une validation.
        return _wait(proposed, AwaitingReason.PLAN_CHANGE)
    return proposed


def _require_pending_plan(state: TaskState) -> None:
    if state.status is TaskStatus.IN_PROGRESS and state.awaiting_reason is not AwaitingReason.PLAN_CHANGE:
        raise LifecycleError("no_pending_plan", "Aucun nouveau plan à valider.")
    _require(state, TaskStatus.TODO, TaskStatus.IN_PROGRESS)
    if not state.has_pending_plan:
        raise LifecycleError("no_pending_plan", "Aucun nouveau plan à valider.")


def _request_plan_changes(state: TaskState, now: datetime) -> TaskState:
    _require_pending_plan(state)
    return replace(state, rejected_plan_version=state.plan_version)


def _validate_plan(state: TaskState, now: datetime) -> TaskState:
    _require_pending_plan(state)
    validated = replace(state, validated_plan_version=state.plan_version, status=TaskStatus.IN_PROGRESS)
    return _resume(validated, now)


def _ask_human(state: TaskState, now: datetime) -> TaskState:
    _require_running(state)
    return _wait(state, AwaitingReason.QUESTION)


def _answer_human(state: TaskState, now: datetime) -> TaskState:
    _require(state, TaskStatus.IN_PROGRESS)
    if not state.awaiting_human or state.awaiting_reason is AwaitingReason.PLAN_CHANGE:
        raise LifecycleError("nothing_to_answer", "Aucune question en attente.")
    resumed = _resume(state, now)
    if state.awaiting_reason is AwaitingReason.QA_LIMIT:
        # Le PO a tranché : la boucle QA repart avec un nouveau budget.
        resumed = replace(resumed, qa_round_trips=0)
    return resumed


def _record_qa_failure(state: TaskState, now: datetime) -> TaskState:
    _require_running(state)
    counted = replace(state, qa_round_trips=state.qa_round_trips + 1)
    if counted.qa_round_trips >= MAX_QA_ROUND_TRIPS:
        return _wait(counted, AwaitingReason.QA_LIMIT)
    return counted


def _escalate_timeout(state: TaskState, now: datetime) -> TaskState:
    _require_running(state)
    if not is_execution_overdue(state, now):
        raise LifecycleError("not_overdue", "La durée maximale n'est pas atteinte.")
    return _wait(state, AwaitingReason.TIMEOUT)


def _submit_for_review(state: TaskState, now: datetime) -> TaskState:
    _require_running(state)
    return replace(
        state,
        status=TaskStatus.REVIEW,
        execution_started_at=None,
        result_validated=False,
        tester_confirmed=False,
    )


def _done_if_complete(state: TaskState) -> TaskState:
    needs_tester = state.type is TaskType.BUGFIX
    if state.result_validated and (state.tester_confirmed or not needs_tester):
        return replace(state, status=TaskStatus.DONE)
    return state


def _validate_result(state: TaskState, now: datetime) -> TaskState:
    _require(state, TaskStatus.REVIEW)
    if state.result_validated:
        raise LifecycleError("already_validated", "Résultat déjà validé.")
    return _done_if_complete(replace(state, result_validated=True))


def _confirm_fix(state: TaskState, now: datetime) -> TaskState:
    _require(state, TaskStatus.REVIEW)
    if state.type is not TaskType.BUGFIX:
        raise LifecycleError("not_a_bugfix", "Seul un Bugfix se confirme par le testeur.")
    if state.tester_confirmed:
        raise LifecycleError("already_confirmed", "Correction déjà confirmée.")
    return _done_if_complete(replace(state, tester_confirmed=True))


def _reject_result(state: TaskState, now: datetime) -> TaskState:
    _require(state, TaskStatus.REVIEW)
    rejected = replace(
        state,
        status=TaskStatus.IN_PROGRESS,
        result_validated=False,
        tester_confirmed=False,
    )
    return _resume(rejected, now)


_HANDLERS = {
    Command.PROPOSE_REPORT: _propose_report,
    Command.REQUEST_REPORT_CHANGES: _request_report_changes,
    Command.VALIDATE_REPORT: _validate_report,
    Command.PRIORITIZE: _prioritize,
    Command.PROPOSE_PLAN: _propose_plan,
    Command.REQUEST_PLAN_CHANGES: _request_plan_changes,
    Command.VALIDATE_PLAN: _validate_plan,
    Command.ASK_HUMAN: _ask_human,
    Command.ANSWER_HUMAN: _answer_human,
    Command.RECORD_QA_FAILURE: _record_qa_failure,
    Command.ESCALATE_TIMEOUT: _escalate_timeout,
    Command.SUBMIT_FOR_REVIEW: _submit_for_review,
    Command.VALIDATE_RESULT: _validate_result,
    Command.CONFIRM_FIX: _confirm_fix,
    Command.REJECT_RESULT: _reject_result,
}
