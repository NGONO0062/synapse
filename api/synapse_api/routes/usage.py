"""Consommation des modèles IA par projet et par modèle, quotas (section 11, coûts).

Le PO suit la consommation de ses projets. L'administrateur voit celle de tout l'espace
(noms des projets et chiffres seulement, jamais leur contenu) et fixe les quotas.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import ColumnElement, case, func, select
from sqlalchemy.orm import Session

from synapse_api.agents.usage import budget_of
from synapse_api.auth import User, require_any
from synapse_api.config import get_settings
from synapse_api.db.models import ModelUsage, Project
from synapse_api.db.session import get_session
from synapse_api.domain.enums import Role
from synapse_api.routes.projects import load_project
from synapse_api.schemas import (
    BudgetIn,
    ProjectBudgetRow,
    ProjectUsageOut,
    UsageLine,
    WorkspaceUsageOut,
)

router = APIRouter(tags=["consommation"])
DB = Annotated[Session, Depends(get_session)]
Month = Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="AAAA-MM")]


def month_bounds(month: str | None, now: datetime | None = None) -> tuple[str, datetime, datetime]:
    now = now or datetime.now(UTC)
    year, number = (int(p) for p in month.split("-")) if month else (now.year, now.month)
    start = datetime(year, number, 1, tzinfo=UTC)
    end = datetime(year + number // 12, number % 12 + 1, 1, tzinfo=UTC)
    return f"{year:04d}-{number:02d}", start, end


def _lines(session: Session, key: ColumnElement, *where: ColumnElement) -> list[UsageLine]:
    query = (
        select(
            key,
            func.count(),
            func.coalesce(func.sum(ModelUsage.input_tokens), 0),
            func.coalesce(func.sum(ModelUsage.output_tokens), 0),
            func.coalesce(func.sum(ModelUsage.cost_usd), 0),
            func.sum(case((ModelUsage.cost_usd.is_(None), 1), else_=0)),
        )
        .where(*where)
        .group_by(key)
    )
    lines = [
        UsageLine(
            key=str(k),
            calls=calls,
            input_tokens=int(tin),
            output_tokens=int(tout),
            cost_usd=float(cost),
            unpriced_calls=int(unpriced or 0),
        )
        for k, calls, tin, tout, cost, unpriced in session.execute(query)
    ]
    return sorted(lines, key=lambda line: (-line.cost_usd, -line.calls, line.key))


def _total(lines: list[UsageLine], key: str) -> UsageLine:
    return UsageLine(
        key=key,
        calls=sum(line.calls for line in lines),
        input_tokens=sum(line.input_tokens for line in lines),
        output_tokens=sum(line.output_tokens for line in lines),
        cost_usd=sum(line.cost_usd for line in lines),
        unpriced_calls=sum(line.unpriced_calls for line in lines),
    )


@router.get("/projects/{project_id}/usage", response_model=ProjectUsageOut)
def project_usage(project_id: uuid.UUID, user: User, session: DB, month: Month = None) -> ProjectUsageOut:
    require_any(user, Role.PO, Role.ADMIN)
    project = load_project(session, project_id)
    label, start, end = month_bounds(month)
    where = (ModelUsage.project_id == project.id, ModelUsage.created_at >= start, ModelUsage.created_at < end)
    by_model = _lines(session, ModelUsage.ai_model, *where)
    return ProjectUsageOut(
        project_id=project.id,
        project_name=project.name,
        month=label,
        cost_usd=_total(by_model, "total").cost_usd,
        budget_usd=budget_of(project),
        budget_is_default=project.monthly_budget_usd is None,
        by_model=by_model,
        by_casquette=_lines(session, ModelUsage.casquette, *where),
    )


@router.get("/usage", response_model=WorkspaceUsageOut)
def workspace_usage(user: User, session: DB, month: Month = None) -> WorkspaceUsageOut:
    require_any(user, Role.ADMIN)
    label, start, end = month_bounds(month)
    period = (ModelUsage.created_at >= start, ModelUsage.created_at < end)
    used = _lines(session, ModelUsage.project_id, ModelUsage.project_id.is_not(None), *period)
    per_project = {line.key: line for line in used}
    rows = [
        _budget_row(project, per_project.get(str(project.id)))
        for project in session.scalars(select(Project).order_by(Project.name))
    ]
    by_model = _lines(session, ModelUsage.ai_model, *period)
    evaluations = _lines(session, ModelUsage.ai_model, ModelUsage.evaluation_run_id.is_not(None), *period)
    return WorkspaceUsageOut(
        month=label,
        cost_usd=_total(by_model, "total").cost_usd,
        default_budget_usd=get_settings().project_monthly_budget_usd,
        projects=sorted(rows, key=lambda r: (-r.cost_usd, r.project_name)),
        by_model=by_model,
        evaluations=_total(evaluations, "evaluations"),
    )


@router.put("/projects/{project_id}/budget", response_model=ProjectBudgetRow)
def set_budget(project_id: uuid.UUID, body: BudgetIn, user: User, session: DB) -> ProjectBudgetRow:
    """Quota mensuel d'un projet, fixé par l'administrateur."""
    require_any(user, Role.ADMIN)
    project = load_project(session, project_id)
    project.monthly_budget_usd = body.monthly_budget_usd
    session.commit()
    _, start, end = month_bounds(None)
    lines = _lines(
        session,
        ModelUsage.project_id,
        ModelUsage.project_id == project.id,
        ModelUsage.created_at >= start,
        ModelUsage.created_at < end,
    )
    return _budget_row(project, lines[0] if lines else None)


def _budget_row(project: Project, line: UsageLine | None) -> ProjectBudgetRow:
    return ProjectBudgetRow(
        project_id=project.id,
        project_name=project.name,
        calls=line.calls if line else 0,
        cost_usd=line.cost_usd if line else 0,
        budget_usd=budget_of(project),
        budget_is_default=project.monthly_budget_usd is None,
    )
