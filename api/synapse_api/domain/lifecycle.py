"""Cycle de vie d'une tâche (dossier de développement, section 5).

Module pur : aucune dépendance à la base ni au web. Chaque commande prend un état,
un acteur et renvoie le nouvel état, ou lève `LifecycleError`. Les règles :

- BACKLOG → TODO : le PO priorise.
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


HUMAN_COMMANDS: dict[Command, Role] = {
    Command.PRIORITIZE: Role.PO,
    Command.REQUEST_PLAN_CHANGES: Role.PO,
    Command.VALIDATE_PLAN: Role.PO,
    Command.ANSWER_HUMAN: Role.PO,
    Command.VALIDATE_RESULT: Role.PO,
    Command.REJECT_RESULT: Role.PO,
    Command.CONFIRM_FIX: Role.TESTEUR,
}

# Commandes d'agent réservées à une casquette ; les autres sont ouvertes à toutes.
AGENT_COMMANDS: dict[Command, Casquette | None] = {
    Command.PROPOSE_PLAN: None,
    Command.ASK_HUMAN: None,
    Command.RECORD_QA_FAILURE: None,
    Command.ESCALATE_TIMEOUT: Casquette.ORCHESTRATEUR,
    Command.SUBMIT_FOR_REVIEW: Casquette.ORCHESTRATEUR,
}

COMMENT_REQUIRED = {
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
        if HUMAN_COMMANDS[command] not in actor.roles:
            raise LifecycleError("forbidden", f"Rôle {HUMAN_COMMANDS[command]} requis.")
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


def _prioritize(state: TaskState, now: datetime) -> TaskState:
    _require(state, TaskStatus.BACKLOG)
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
