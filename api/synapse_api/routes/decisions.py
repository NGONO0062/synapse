from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from synapse_api.access import decision_for, visible_tasks
from synapse_api.auth import User, require_any
from synapse_api.db.models import Task
from synapse_api.db.session import get_session
from synapse_api.domain.enums import Role, TaskStatus
from synapse_api.domain.lifecycle import ActorKind
from synapse_api.schemas import DecisionOut, TaskOut

router = APIRouter(prefix="/decisions", tags=["décisions"])
DB = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[DecisionOut])
def list_my_decisions(user: User, session: DB) -> list[DecisionOut]:
    """Accueil : « En attente de ta validation », sur tous les projets visibles."""
    require_any(user, Role.PO, Role.TESTEUR)
    query = visible_tasks(select(Task).where(Task.status != TaskStatus.DONE), user)
    decisions = []
    for task in session.scalars(query):
        kind = decision_for(task, user)
        if kind is None:
            continue
        last_agent = next((m for m in reversed(task.messages) if m.author_kind is ActorKind.AGENT), None)
        decisions.append(
            DecisionOut(
                kind=kind,
                task=TaskOut.model_validate(task),
                project_id=task.project_id,
                project_name=task.project.name,
                casquette=last_agent.casquette if last_agent else None,
                since=last_agent.created_at if last_agent else task.updated_at,
            )
        )
    return sorted(decisions, key=lambda d: d.since, reverse=True)
