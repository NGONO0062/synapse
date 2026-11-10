"""Consommation des modèles IA (section 11, coûts).

Chaque appel d’une casquette passe par `ask_model` : le quota mensuel du projet est vérifié avant,
les jetons et le coût sont enregistrés après, même quand la réponse est inexploitable
(un appel refusé est payé quand même).
"""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from synapse_api.agents.gateway import usage_of
from synapse_api.agents.state import Deps
from synapse_api.config import get_settings
from synapse_api.db.models import ModelUsage, Project, Task
from synapse_api.domain.enums import Casquette


class QuotaExceeded(Exception):
    """Le projet a atteint son quota du mois : plus aucun appel jusqu'au mois suivant,
    ou jusqu'à ce que l'administrateur relève le quota."""


def month_start(now: datetime) -> datetime:
    return now.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def budget_of(project: Project) -> float | None:
    if project.monthly_budget_usd is not None:
        return project.monthly_budget_usd
    return get_settings().project_monthly_budget_usd


def month_cost(session: Session, project_id: uuid.UUID, now: datetime) -> float:
    query = select(func.coalesce(func.sum(ModelUsage.cost_usd), 0)).where(
        ModelUsage.project_id == project_id, ModelUsage.created_at >= month_start(now)
    )
    return float(session.scalar(query) or 0)


def dollars(amount: float) -> str:
    return f"{amount:,.2f} $".replace(",", " ").replace(".", ",")


def check_quota(session: Session, project: Project, now: datetime) -> None:
    budget = budget_of(project)
    if budget is None:
        return
    spent = month_cost(session, project.id, now)
    if spent >= budget:
        raise QuotaExceeded(
            f"Quota IA du projet atteint : {dollars(spent)} consommés ce mois-ci pour {dollars(budget)} "
            "autorisés. L'administrateur peut relever le quota."
        )


def ask_model[T: BaseModel](
    deps: Deps,
    schema: type[T],
    *,
    casquette: Casquette,
    ai_model: str,
    system: str,
    prompt: str,
    task_id: uuid.UUID | str | None = None,
    evaluation_run_id: uuid.UUID | None = None,
) -> T:
    """Appelle le modèle pour une casquette, dans les limites du quota, et compte l'appel."""
    project_id = None
    if task_id is not None:
        task_id = uuid.UUID(str(task_id))
        with deps.sessions() as session:
            task = session.get(Task, task_id)
            if task is not None:
                project_id = task.project_id
                check_quota(session, task.project, datetime.now(UTC))

    model = deps.model(ai_model)
    answered = False
    try:
        answer = model.structured(schema, system=system, prompt=prompt)
        answered = True
        return answer
    finally:
        usage = usage_of(model)
        if answered or usage.input_tokens or usage.output_tokens:
            catalog = deps.catalog() or {}
            info = catalog.get(ai_model)
            with deps.sessions() as session:
                session.add(
                    ModelUsage(
                        project_id=project_id,
                        task_id=task_id,
                        evaluation_run_id=evaluation_run_id,
                        casquette=casquette.value,
                        ai_model=ai_model,
                        served_model=info.served_model if info else None,
                        input_tokens=usage.input_tokens,
                        output_tokens=usage.output_tokens,
                        cost_usd=info.cost(usage) if info else None,
                    )
                )
                session.commit()
