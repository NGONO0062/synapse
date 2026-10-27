"""Opérations sur les tâches, partagées par l'API (humains) et l'orchestrateur (agents)."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from synapse_api.db.models import Project, Task, TaskEvent
from synapse_api.domain.enums import TaskType
from synapse_api.domain.lifecycle import Actor, Command, TaskState, apply


def create_task(
    session: Session,
    project: Project,
    *,
    type: TaskType,
    title: str,
    description: str,
    created_by: str,
) -> Task:
    # Numérotation par projet et par type : FEAT-001, BUG-001, DOC-001…
    # La contrainte d'unicité (project_id, type, number) protège des créations concurrentes.
    last = session.scalar(
        select(func.max(Task.number)).where(Task.project_id == project.id, Task.type == type)
    )
    task = Task(
        project_id=project.id,
        type=type,
        number=(last or 0) + 1,
        title=title,
        description=description,
        created_by=created_by,
    )
    session.add(task)
    session.flush()
    return task


def to_state(task: Task) -> TaskState:
    started = task.execution_started_at
    if started is not None and started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    return TaskState(
        type=task.type,
        status=task.status,
        plan_version=task.plan_version,
        validated_plan_version=task.validated_plan_version,
        rejected_plan_version=task.rejected_plan_version,
        awaiting_human=task.awaiting_human,
        awaiting_reason=task.awaiting_reason,
        qa_round_trips=task.qa_round_trips,
        execution_started_at=started,
        result_validated=task.result_validated,
        tester_confirmed=task.tester_confirmed,
    )


def execute(
    session: Session,
    task: Task,
    command: Command,
    actor: Actor,
    *,
    comment: str | None = None,
    ai_model: str | None = None,
    referentiel_version: str | None = None,
    now: datetime | None = None,
) -> TaskEvent:
    """Applique une commande du cycle de vie et la journalise. Lève LifecycleError."""
    now = now or datetime.now(UTC)
    before = to_state(task)
    after = apply(before, command, actor, now=now, comment=comment)

    for field in TaskState.__dataclass_fields__:
        if field != "type":
            setattr(task, field, getattr(after, field))

    event = TaskEvent(
        task_id=task.id,
        command=command,
        actor_kind=actor.kind,
        actor_name=actor.name,
        actor_role=",".join(sorted(actor.roles)) or None,
        casquette=actor.casquette.value if actor.casquette else None,
        ai_model=ai_model,
        referentiel_version=referentiel_version,
        from_status=before.status,
        to_status=after.status,
        comment=comment,
        created_at=now,
    )
    session.add(event)
    session.flush()
    return event
