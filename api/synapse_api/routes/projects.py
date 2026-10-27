import uuid
from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from synapse_api.access import decision_for, visible_tasks
from synapse_api.auth import User, require_any
from synapse_api.db.models import Project, Task
from synapse_api.db.session import get_session
from synapse_api.domain.enums import Role, TaskStatus, TaskType
from synapse_api.schemas import ProjectIn, ProjectOut, ProjectSummaryOut, TaskIn, TaskOut
from synapse_api.services import create_task

router = APIRouter(prefix="/projects", tags=["projets"])
DB = Annotated[Session, Depends(get_session)]


def load_project(session: Session, project_id: uuid.UUID) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Projet introuvable.")
    return project


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectIn, user: User, session: DB) -> Project:
    require_any(user, Role.PO)
    project = Project(name=body.name, description=body.description, created_by=user.subject)
    session.add(project)
    session.commit()
    return project


@router.get("", response_model=list[ProjectSummaryOut])
def list_projects(user: User, session: DB) -> list[ProjectSummaryOut]:
    require_any(user, Role.PO, Role.TESTEUR)
    projects = list(session.scalars(select(Project).order_by(Project.created_at)))
    # Volume v1 modeste : agrégation en mémoire sur les tâches visibles.
    tasks = list(session.scalars(visible_tasks(select(Task), user)))
    summaries = []
    for project in projects:
        own = [t for t in tasks if t.project_id == project.id]
        counts = Counter(t.status for t in own)
        summaries.append(
            ProjectSummaryOut(
                **ProjectOut.model_validate(project).model_dump(),
                status_counts={s: counts.get(s, 0) for s in TaskStatus},
                pending_decisions=sum(1 for t in own if decision_for(t, user)),
            )
        )
    return summaries


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: uuid.UUID, user: User, session: DB) -> Project:
    require_any(user, Role.PO, Role.TESTEUR)
    return load_project(session, project_id)


@router.post("/{project_id}/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_project_task(project_id: uuid.UUID, body: TaskIn, user: User, session: DB) -> Task:
    # Le PO lance toute demande ; le testeur ne signale que des bugs.
    if body.type is TaskType.BUGFIX:
        require_any(user, Role.PO, Role.TESTEUR)
    else:
        require_any(user, Role.PO)
    project = load_project(session, project_id)
    task = create_task(
        session,
        project,
        type=body.type,
        title=body.title,
        description=body.description,
        author=user.as_actor(),
        author_subject=user.subject,
        ai_model=body.ai_model,
    )
    session.commit()
    return task


@router.get("/{project_id}/tasks", response_model=list[TaskOut])
def list_project_tasks(project_id: uuid.UUID, user: User, session: DB) -> list[Task]:
    require_any(user, Role.PO, Role.TESTEUR)
    load_project(session, project_id)
    query = visible_tasks(select(Task).where(Task.project_id == project_id), user)
    return list(session.scalars(query.order_by(Task.created_at)))


@router.get("/{project_id}/tasks/by-code/{code}", response_model=TaskOut)
def get_task_by_code(project_id: uuid.UUID, code: str, user: User, session: DB) -> Task:
    require_any(user, Role.PO, Role.TESTEUR)
    prefix, _, number = code.upper().partition("-")
    task_type = next((t for t in TaskType if t.prefix == prefix), None)
    task = None
    if task_type and number.isdigit():
        query = select(Task).where(
            Task.project_id == project_id, Task.type == task_type, Task.number == int(number)
        )
        task = session.scalar(visible_tasks(query, user))
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tâche introuvable.")
    return task
