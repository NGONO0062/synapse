import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from synapse_api.auth import CurrentUser, User, require_any
from synapse_api.db.models import Task, TaskEvent
from synapse_api.db.session import get_session
from synapse_api.domain.enums import Role, TaskType
from synapse_api.domain.lifecycle import Command, LifecycleError
from synapse_api.schemas import CommandIn, TaskEventOut, TaskOut
from synapse_api.services import execute

router = APIRouter(prefix="/tasks", tags=["tâches"])
DB = Annotated[Session, Depends(get_session)]

_FORBIDDEN_CODES = {"forbidden", "human_only", "agent_only"}


def load_visible_task(session: Session, task_id: uuid.UUID, user: CurrentUser) -> Task:
    require_any(user, Role.PO, Role.TESTEUR)
    task = session.get(Task, task_id)
    visible = task is not None and (
        user.has(Role.PO) or (task.type is TaskType.BUGFIX and task.created_by == user.subject)
    )
    if not visible:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tâche introuvable.")
    return task


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: uuid.UUID, user: User, session: DB) -> Task:
    return load_visible_task(session, task_id, user)


@router.get("/{task_id}/events", response_model=list[TaskEventOut])
def list_task_events(task_id: uuid.UUID, user: User, session: DB) -> list[TaskEvent]:
    return load_visible_task(session, task_id, user).events


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
