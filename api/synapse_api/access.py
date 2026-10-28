"""Qui voit quoi, qui décide quoi (CLAUDE.md, Domaine › Visibilité)."""

from sqlalchemy import Select

from synapse_api.auth import CurrentUser
from synapse_api.db.models import Task
from synapse_api.domain.enums import Role, TaskType
from synapse_api.domain.lifecycle import Command, PendingDecision

PO_DECISIONS = {
    PendingDecision.PLAN,
    PendingDecision.QUESTION,
    PendingDecision.ESCALATION,
    PendingDecision.RESULT,
}


# Décisions réservées à l'auteur du signalement, quel que soit son rôle.
REPORTER_COMMANDS = {Command.VALIDATE_REPORT, Command.REQUEST_REPORT_CHANGES}


def visible_tasks(query: Select, user: CurrentUser) -> Select:
    if user.has(Role.PO):
        return query
    # Le testeur ne voit que les bugs qu'il a signalés.
    return query.where(Task.type == TaskType.BUGFIX, Task.created_by == user.subject)


def can_see(task: Task, user: CurrentUser) -> bool:
    return user.has(Role.PO) or (task.type is TaskType.BUGFIX and task.created_by == user.subject)


def decision_for(task: Task, user: CurrentUser) -> PendingDecision | None:
    """La décision que la tâche attend de cet utilisateur, s'il y en a une."""
    decision = task.pending_decision
    if decision in PO_DECISIONS and user.has(Role.PO):
        return decision
    if decision is PendingDecision.REPORT and task.created_by == user.subject:
        return decision
    if (
        decision is PendingDecision.TESTER_CONFIRMATION
        and user.has(Role.TESTEUR)
        and task.created_by == user.subject
    ):
        return decision
    return None
