import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from synapse_api.auth import User, require_any
from synapse_api.db.models import Project, Task
from synapse_api.db.session import get_session
from synapse_api.domain.enums import Role, TaskType
from synapse_api.schemas import ProjectIn, ProjectOut, TaskIn, TaskOut
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


@router.get("", response_model=list[ProjectOut])
def list_projects(user: User, session: DB) -> list[Project]:
    require_any(user, Role.PO, Role.TESTEUR)
    return list(session.scalars(select(Project).order_by(Project.created_at)))


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
        created_by=user.subject,
    )
    session.commit()
    return task


@router.get("/{project_id}/tasks", response_model=list[TaskOut])
def list_project_tasks(project_id: uuid.UUID, user: User, session: DB) -> list[Task]:
    require_any(user, Role.PO, Role.TESTEUR)
    load_project(session, project_id)
    query = select(Task).where(Task.project_id == project_id)
    if not user.has(Role.PO):
        # Le testeur ne voit que ses bugs.
        query = query.where(Task.type == TaskType.BUGFIX, Task.created_by == user.subject)
    return list(session.scalars(query.order_by(Task.created_at)))
