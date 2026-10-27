import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from synapse_api.access import can_see
from synapse_api.auth import CurrentUser, User, require_any
from synapse_api.db.models import Task, TaskEvent, TaskMessage
from synapse_api.db.session import get_session
from synapse_api.domain.enums import MessageKind, Role
from synapse_api.domain.lifecycle import Command, LifecycleError
from synapse_api.schemas import CommandIn, MessageIn, TaskEventOut, TaskMessageOut, TaskOut
from synapse_api.services import add_message, execute

router = APIRouter(prefix="/tasks", tags=["tâches"])
DB = Annotated[Session, Depends(get_session)]

_FORBIDDEN_CODES = {"forbidden", "human_only", "agent_only"}


def load_visible_task(session: Session, task_id: uuid.UUID, user: CurrentUser) -> Task:
    require_any(user, Role.PO, Role.TESTEUR)
    task = session.get(Task, task_id)
    if task is None or not can_see(task, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tâche introuvable.")
    return task


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: uuid.UUID, user: User, session: DB) -> Task:
    return load_visible_task(session, task_id, user)


@router.get("/{task_id}/events", response_model=list[TaskEventOut])
def list_task_events(task_id: uuid.UUID, user: User, session: DB) -> list[TaskEvent]:
    return load_visible_task(session, task_id, user).events


@router.get("/{task_id}/messages", response_model=list[TaskMessageOut])
def list_task_messages(task_id: uuid.UUID, user: User, session: DB) -> list[TaskMessage]:
    return load_visible_task(session, task_id, user).messages


@router.post("/{task_id}/messages", response_model=TaskMessageOut, status_code=status.HTTP_201_CREATED)
def post_task_message(task_id: uuid.UUID, body: MessageIn, user: User, session: DB) -> TaskMessage:
    """Message libre dans le fil. Les décisions passent par /commands, avec leur commentaire."""
    task = load_visible_task(session, task_id, user)
    message = add_message(
        session,
        task,
        kind=MessageKind.MESSAGE,
        author=user.as_actor(),
        author_subject=user.subject,
        body=body.body,
    )
    session.commit()
    return message


@router.post("/{task_id}/commands", response_model=TaskOut)
def run_command(task_id: uuid.UUID, body: CommandIn, user: User, session: DB) -> Task:
    task = load_visible_task(session, task_id, user)
    try:
        execute(session, task, Command(body.command), user.as_actor(), comment=body.comment)
        session.commit()
    except LifecycleError as exc:
        session.rollback()
        code = status.HTTP_403_FORBIDDEN if exc.code in _FORBIDDEN_CODES else status.HTTP_409_CONFLICT
        raise HTTPException(code, {"code": exc.code, "message": exc.message}) from exc
    except StaleDataError as exc:
        session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"code": "concurrent_update", "message": "La tâche a changé entre-temps. Recharge-la."},
        ) from exc
    return task
