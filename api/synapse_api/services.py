"""Opérations sur les tâches, partagées par l'API (humains) et l'orchestrateur (agents)."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from synapse_api.db.models import Project, Task, TaskEvent, TaskMessage
from synapse_api.domain.enums import DEFAULT_AI_MODEL, MessageKind, TaskType
from synapse_api.domain.lifecycle import Actor, ActorKind, Command, TaskState, apply


def create_task(
    session: Session,
    project: Project,
    *,
    type: TaskType,
    title: str,
    description: str,
    author: Actor,
    author_subject: str,
    ai_model: str = DEFAULT_AI_MODEL,
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
        created_by=author_subject,
        ai_model=ai_model,
    )
    session.add(task)
    session.flush()
    # La demande ouvre le fil de la tâche.
    add_message(
        session,
        task,
        kind=MessageKind.MESSAGE,
        author=author,
        author_subject=author_subject,
        body=description or title,
    )
    return task


def add_message(
    session: Session,
    task: Task,
    *,
    kind: MessageKind,
    author: Actor,
    body: str,
    author_subject: str | None = None,
    payload: dict | None = None,
    plan_version: int | None = None,
    ai_model: str | None = None,
) -> TaskMessage:
    if kind is not MessageKind.MESSAGE and author.kind is not ActorKind.AGENT:
        raise ValueError("Seule une casquette propose un plan, un résultat ou une question.")
    message = TaskMessage(
        task_id=task.id,
        kind=kind,
        author_kind=author.kind,
        author_name=author.name,
        author_subject=author_subject,
        casquette=author.casquette.value if author.casquette else None,
        ai_model=ai_model,
        body=body,
        payload=payload,
        plan_version=plan_version,
    )
    session.add(message)
    session.flush()
    return message


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
    before = task.lifecycle_state()
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
