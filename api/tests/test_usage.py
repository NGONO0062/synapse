"""Consommation des modèles IA et quotas (lot 3c, section 11)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select

from synapse_api.agents.gateway import ModelInfo, Usage
from synapse_api.agents.graph import Deps, build_orchestrator
from synapse_api.agents.usage import month_start
from synapse_api.agents.worker import run_once
from synapse_api.db.models import ModelUsage, TaskActivity
from synapse_api.routes.usage import month_bounds

from .conftest import ADMIN, PO, TESTEUR
from .test_api import command, new_project, new_task
from .test_orchestrator import APPROVED, PLAN, ScriptedModel

SONNET = ModelInfo("claude-sonnet", "anthropic/claude-sonnet-5-5", 3e-06, 1.5e-05)


def catalog():
    return {"claude-sonnet": SONNET}


@pytest.fixture
def tick(session_factory):
    def make(model: ScriptedModel, prices=catalog):
        deps = Deps(sessions=session_factory, model=model, catalog=prices)
        graph = build_orchestrator(deps, InMemorySaver())
        return lambda: run_once(graph, deps)

    return make


def planned_task(clients) -> tuple[str, str]:
    project = new_project(clients)
    task = new_task(clients, project)["id"]
    command(clients, PO, task, "PRIORITIZE")
    return project, task


def set_budget(clients, user, project: str, amount: float | None):
    return clients.as_(user).put(f"/projects/{project}/budget", json={"monthly_budget_usd": amount})


def counted_model() -> ScriptedModel:
    model = ScriptedModel(PlanDraft=[PLAN], Review=[APPROVED])
    model.last_usage = Usage(1000, 100)
    return model


def test_every_call_is_counted_with_its_casquette_and_cost(clients, session_factory, tick):
    project, task = planned_task(clients)
    assert list(tick(counted_model())().values()) == ["published"]

    with session_factory() as session:
        calls = session.scalars(select(ModelUsage).order_by(ModelUsage.casquette)).all()
    # L'Architecte rédige, le Business Analyst relit : deux appels, chacun à sa casquette.
    assert [c.casquette for c in calls] == ["ARCHITECTE", "BUSINESS_ANALYST"]
    for call in calls:
        assert str(call.project_id) == project and str(call.task_id) == task
        assert call.ai_model == "claude-sonnet" and call.served_model == "anthropic/claude-sonnet-5-5"
        assert (call.input_tokens, call.output_tokens) == (1000, 100)
        assert call.cost_usd == pytest.approx(0.0045)


def test_unknown_price_is_kept_unknown(clients, session_factory, tick):
    planned_task(clients)
    tick(counted_model(), prices=lambda: None)()  # passerelle sans catalogue
    with session_factory() as session:
        calls = session.scalars(select(ModelUsage)).all()
    assert len(calls) == 2 and all(c.cost_usd is None and c.input_tokens == 1000 for c in calls)


def test_a_project_over_its_quota_stops_calling_models(clients, session_factory, tick):
    project, task = planned_task(clients)
    assert (
        clients.as_(ADMIN).put(f"/projects/{project}/budget", json={"monthly_budget_usd": 0.005}).status_code
        == 200
    )
    model = counted_model()
    run = tick(model)
    run()  # 0,009 $ consommés : le quota de 0,005 $ est dépassé
    command(clients, PO, task, "REQUEST_PLAN_CHANGES", "Ajoute l'export Excel.")

    assert list(run().values()) == ["error"]
    assert len(model.calls) == 2  # aucun nouvel appel
    with session_factory() as session:
        activity = session.scalar(select(TaskActivity))
    assert "Quota IA du projet atteint" in activity.error and "0,01 $" in activity.error


def test_quota_counts_only_the_current_month(clients, session_factory, tick):
    project, task = planned_task(clients)
    with session_factory() as session:
        last_month = month_start(datetime.now(UTC)) - timedelta(days=2)
        session.add(
            ModelUsage(
                project_id=uuid.UUID(project),
                casquette="ARCHITECTE",
                ai_model="claude-sonnet",
                cost_usd=50,
                created_at=last_month,
            )
        )
        session.commit()
    set_budget(clients, ADMIN, project, 10)
    assert list(tick(counted_model())().values()) == ["published"]


def test_po_follows_project_usage_by_model_and_casquette(clients, tick):
    project, _ = planned_task(clients)
    tick(counted_model())()

    usage = clients.as_(PO).get(f"/projects/{project}/usage").json()
    assert usage["month"] == month_bounds(None)[0]
    assert usage["cost_usd"] == pytest.approx(0.009)
    assert usage["budget_usd"] is None and usage["budget_is_default"]
    [sonnet] = usage["by_model"]
    assert sonnet == {
        "key": "claude-sonnet", "calls": 2, "input_tokens": 2000, "output_tokens": 200,
        "cost_usd": pytest.approx(0.009), "unpriced_calls": 0,
    }  # fmt: skip
    assert {line["key"] for line in usage["by_casquette"]} == {"ARCHITECTE", "BUSINESS_ANALYST"}
    # Un autre mois : rien.
    assert clients.as_(PO).get(f"/projects/{project}/usage?month=2020-01").json()["by_model"] == []
    assert clients.as_(PO).get(f"/projects/{project}/usage?month=2020-13").status_code == 422
    assert clients.as_(TESTEUR).get(f"/projects/{project}/usage").status_code == 403


def test_admin_sees_the_workspace_and_sets_quotas(clients, tick):
    project, _ = planned_task(clients)
    idle = new_project(clients)
    tick(counted_model())()

    assert clients.as_(PO).get("/usage").status_code == 403
    assert (
        clients.as_(PO).put(f"/projects/{project}/budget", json={"monthly_budget_usd": 5}).status_code == 403
    )
    assert (
        clients.as_(ADMIN).put(f"/projects/{project}/budget", json={"monthly_budget_usd": -1}).status_code
        == 422
    )

    row = set_budget(clients, ADMIN, project, 25).json()
    assert row["budget_usd"] == 25 and not row["budget_is_default"] and row["calls"] == 2

    usage = clients.as_(ADMIN).get("/usage").json()
    assert [p["project_id"] for p in usage["projects"]] == [project, idle]  # le plus coûteux d'abord
    assert usage["projects"][1]["cost_usd"] == 0 and usage["projects"][1]["budget_is_default"]
    assert usage["by_model"][0]["key"] == "claude-sonnet"
    assert usage["evaluations"]["calls"] == 0

    # Quota retiré : le projet revient au quota par défaut de l'espace.
    row = set_budget(clients, ADMIN, project, None).json()
    assert row["budget_usd"] is None and row["budget_is_default"]


def test_month_bounds_cross_the_year():
    label, start, end = month_bounds("2026-12")
    assert label == "2026-12" and start == datetime(2026, 12, 1, tzinfo=UTC)
    assert end == datetime(2027, 1, 1, tzinfo=UTC)
