"""Tableau de bord des cas de référence, pour l'administrateur (section 11, évaluation continue).

Dernier rejeu de chaque casquette avec chaque modèle, régressions d'abord. Ne montre rien des
projets : les cas de référence sont des dossiers d'exemple versionnés avec Synapse.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from synapse_api.auth import User, require_any
from synapse_api.db.models import EvaluationRun, ModelUsage
from synapse_api.db.session import get_session
from synapse_api.domain.enums import EvaluationStatus, Role
from synapse_api.schemas import EvaluationResultOut, EvaluationRunDetailOut, EvaluationRunOut

router = APIRouter(prefix="/evaluations", tags=["cas de référence"])
DB = Annotated[Session, Depends(get_session)]


def _costs(session: Session, run_ids: list[uuid.UUID]) -> dict[uuid.UUID, float]:
    if not run_ids:
        return {}
    query = (
        select(ModelUsage.evaluation_run_id, func.coalesce(func.sum(ModelUsage.cost_usd), 0))
        .where(ModelUsage.evaluation_run_id.in_(run_ids))
        .group_by(ModelUsage.evaluation_run_id)
    )
    return {run_id: float(cost) for run_id, cost in session.execute(query)}


def _out(runs: list[EvaluationRun], session: Session) -> list[EvaluationRunOut]:
    costs = _costs(session, [r.id for r in runs])
    return [
        EvaluationRunOut.model_validate(run).model_copy(update={"cost_usd": costs.get(run.id, 0)})
        for run in runs
    ]


def _rank(run: EvaluationRunOut) -> tuple:
    # Régressions, puis rejeux en échec, puis le reste par casquette.
    return (not run.regressed_cases, run.status is not EvaluationStatus.ERROR, run.casquette, run.ai_model)


@router.get("", response_model=list[EvaluationRunOut])
def latest_runs(user: User, session: DB) -> list[EvaluationRunOut]:
    require_any(user, Role.ADMIN)
    # Le dernier rejeu terminé fait foi : un rejeu en cours ou interrompu ne cache pas une
    # régression déjà constatée. Sans rejeu terminé, le plus récent est montré.
    latest: dict[tuple[str, str], EvaluationRun] = {}
    for run in session.scalars(select(EvaluationRun).order_by(EvaluationRun.started_at)):
        key = (run.casquette, run.ai_model)
        kept = latest.get(key)
        if kept is None or run.status is EvaluationStatus.DONE or kept.status is not EvaluationStatus.DONE:
            latest[key] = run
    return sorted(_out(list(latest.values()), session), key=_rank)


@router.get("/{run_id}", response_model=EvaluationRunDetailOut)
def run_detail(run_id: uuid.UUID, user: User, session: DB) -> EvaluationRunDetailOut:
    require_any(user, Role.ADMIN)
    run = session.get(EvaluationRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rejeu introuvable.")
    history = session.scalars(
        select(EvaluationRun)
        .where(
            EvaluationRun.casquette == run.casquette,
            EvaluationRun.ai_model == run.ai_model,
            # « <= » et non « < » : sous Windows, deux rejeux enchaînés peuvent avoir la même heure.
            EvaluationRun.started_at <= run.started_at,
            EvaluationRun.id != run.id,
        )
        .order_by(EvaluationRun.started_at.desc())
        .limit(10)
    ).all()
    [summary] = _out([run], session)
    return EvaluationRunDetailOut(
        **summary.model_dump(),
        results=[EvaluationResultOut.model_validate(r) for r in run.results],
        history=_out(list(history), session),
    )
