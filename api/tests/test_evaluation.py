"""Cas de référence rejoués et régressions (lot 3c, sections 3 et 11)."""

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select

from synapse_api.agents import evaluation
from synapse_api.agents.evaluation import (
    Case,
    all_cases,
    due_evaluations,
    evaluate,
    fingerprint,
    judge,
    regressions,
)
from synapse_api.agents.gateway import GatewayError, ModelInfo, Usage
from synapse_api.agents.graph import Deps, build_orchestrator
from synapse_api.agents.jobs import AUTHORS, REVIEWERS, PlanDraft, Review
from synapse_api.agents.worker import run_once
from synapse_api.db.models import EvaluationRun, ModelUsage
from synapse_api.domain.enums import Casquette, EvaluationStatus

from .conftest import ADMIN, PO
from .test_api import new_project, new_task
from .test_orchestrator import ScriptedModel

REFUSED = {"approved": False, "corrections": ["Pas de test qui reproduit le bug."]}
APPROVED = {"approved": True}


def served(model: str = "anthropic/claude-sonnet-5-5"):
    return lambda: {
        "claude-sonnet": ModelInfo("claude-sonnet", model, 3e-06, 1.5e-05),
        "gemini": ModelInfo("gemini", "gemini/gemini-2.5-flash", None, None),
    }


SERVED = served()


@pytest.fixture
def deps(session_factory):
    def make(model: ScriptedModel, catalog=SERVED):
        return Deps(sessions=session_factory, model=model, catalog=catalog)

    return make


def reviewer_model(*answers: dict) -> ScriptedModel:
    model = ScriptedModel(Review=list(answers))
    model.last_usage = Usage(500, 50)
    return model


def test_every_casquette_that_writes_or_reviews_has_reference_cases():
    cases = all_cases()
    for casquette in {*AUTHORS.values(), *REVIEWERS.values()}:
        assert cases.get(casquette), f"{casquette} sans cas de référence"
    ids = [c.id for group in cases.values() for c in group]
    assert len(ids) == len(set(ids))


def test_a_case_uses_the_prompt_of_the_real_work():
    [plan, *_] = [c for c in all_cases()[Casquette.DEBOGUEUR] if c.kind == "PLAN"]
    prompt = plan.prompt()
    assert prompt.startswith(plan.brief)
    assert "Commence par le test qui reproduit le bug" in prompt  # consigne propre au Bugfix


def test_fingerprint_changes_with_the_model_and_the_instructions(monkeypatch):
    base = fingerprint(Casquette.REVIEWER, "anthropic/claude-sonnet-5-5")
    assert base == fingerprint(Casquette.REVIEWER, "anthropic/claude-sonnet-5-5")
    assert base != fingerprint(Casquette.REVIEWER, "anthropic/claude-sonnet-6")
    monkeypatch.setattr(evaluation, "system_prompt", lambda c: "référentiel modifié")
    assert base != fingerprint(Casquette.REVIEWER, "anthropic/claude-sonnet-5-5")


def case(**expect) -> Case:
    return Case(id="c", title="Cas", kind="PLAN", task_type="BUGFIX", brief="Projet : x", expect=expect)


def test_judge_lists_each_expectation_not_met():
    plan = PlanDraft(
        message="Plan.", changes=["~ src/total.js"], failing_test="Total du samedi = 44", tests="1 test"
    )
    assert judge(case(done=True, mentions={"failing_test": ["samedi"]}), plan) == []

    bad = plan.model_copy(update={"failing_test": None, "changes": ["corriger le total"]})
    failures = judge(case(done=True, mentions={"failing_test": ["samedi"]}), bad)
    assert any("« + », « ~ » ou « - »" in f for f in failures)
    assert any("test qui reproduit le bug" in f for f in failures)
    assert "failing_test ne parle pas de : samedi." in failures

    review = Case(id="r", title="R", kind="REVIEW", task_type="BUGFIX", brief="x", author="DEBOGUEUR",
                  proposal={}, expect={"approved": False})  # fmt: skip
    assert judge(review, Review(approved=True)) == ["Proposition approuvée à tort."]


def test_judge_checks_files_and_questions():
    from synapse_api.agents.execution import Implementation

    impl = Case(id="i", title="I", kind="IMPLEMENT", task_type="FEATURE", brief="x",
                expect={"writes": ["src/total.js"], "asks": False})  # fmt: skip
    written = Implementation(message="Fait.", edits=[{"path": "src/total.js", "content": "x"}])
    assert judge(impl, written) == []
    asked = Implementation(message="Question.", question="Quel taux ?")
    assert judge(impl, asked) == [
        "Le fichier src/total.js n'est pas écrit.",
        "Question posée au lieu de réaliser.",
    ]


def test_only_a_case_that_passed_before_can_regress():
    before = {"a": True, "b": False}
    assert regressions(before, {"a": False, "b": False, "c": False}) == ["a"]
    assert regressions({}, {"a": False}) == []


def test_a_replay_records_results_and_its_cost_outside_projects(deps, session_factory):
    run = evaluate(deps(reviewer_model(REFUSED, APPROVED)), Casquette.REVIEWER, "claude-sonnet")
    assert (run.status, run.passed, run.total, run.regressed_cases) == (EvaluationStatus.DONE, 2, 2, [])
    assert run.served_model == "anthropic/claude-sonnet-5-5"
    assert run.referentiel_version.startswith("reviewer@")
    with session_factory() as session:
        calls = session.scalars(select(ModelUsage)).all()
    assert len(calls) == 2
    assert all(c.project_id is None and c.evaluation_run_id == run.id for c in calls)
    assert all(c.casquette == "REVIEWER" and c.cost_usd == pytest.approx(0.00225) for c in calls)


def test_a_case_that_fails_after_passing_is_a_regression(deps):
    evaluate(deps(reviewer_model(REFUSED, APPROVED)), Casquette.REVIEWER, "claude-sonnet")
    run = evaluate(deps(reviewer_model(APPROVED, APPROVED)), Casquette.REVIEWER, "claude-sonnet")
    assert run.passed == 1 and run.regressed_cases == ["relecture-plan-bugfix-sans-test"]


def test_a_model_that_cannot_answer_fails_the_case_not_the_replay(deps):
    run = evaluate(
        deps(reviewer_model(GatewayError("Pas de réponse structurée."))), Casquette.REVIEWER, "claude-sonnet"
    )
    assert run.status is EvaluationStatus.DONE and run.passed == 0


def test_an_unreachable_gateway_stops_the_replay_until_later(deps, session_factory):
    with pytest.raises(ConnectionError):
        evaluate(
            deps(reviewer_model(ConnectionError("Connection error."))), Casquette.REVIEWER, "claude-sonnet"
        )
    with session_factory() as session:
        run = session.scalar(select(EvaluationRun))
    assert run.status is EvaluationStatus.ERROR and "Connection error" in run.error


def test_replays_are_due_when_the_served_model_changes(deps, clients):
    assert due_evaluations(deps(reviewer_model(APPROVED), catalog=lambda: None)) == []
    due = due_evaluations(deps(reviewer_model(APPROVED)))
    assert {d.casquette for d in due} == set(all_cases()) and {d.ai_model for d in due} == {"claude-sonnet"}

    evaluate(deps(reviewer_model(REFUSED, APPROVED)), Casquette.REVIEWER, "claude-sonnet")
    assert Casquette.REVIEWER not in {d.casquette for d in due_evaluations(deps(reviewer_model(APPROVED)))}
    moved = due_evaluations(deps(reviewer_model(APPROVED), catalog=served("anthropic/claude-sonnet-6")))
    assert Casquette.REVIEWER in {d.casquette for d in moved}

    # Un modèle choisi pour une tâche entre dans les rejeux s'il est dans la passerelle.
    project = new_project(clients)
    for ai_model in ("gemini", "mistral"):
        body = {"type": "FEATURE", "title": "Export", "ai_model": ai_model}
        assert clients.as_(PO).post(f"/projects/{project}/tasks", json=body).status_code == 201
    in_use = {d.ai_model for d in due_evaluations(deps(reviewer_model(APPROVED)))}
    assert in_use == {"claude-sonnet", "gemini"}  # mistral n'est pas dans la passerelle


def test_the_worker_replays_only_when_no_task_is_due(deps, clients, monkeypatch):
    monkeypatch.setattr(
        evaluation, "all_cases", lambda: {Casquette.REVIEWER: all_cases()[Casquette.REVIEWER]}
    )
    model = ScriptedModel(PlanDraft=[{"message": "m", "changes": ["+ x"], "tests": "t"}], Review=[APPROVED])
    d = deps(model)
    tick = lambda: run_once(build_orchestrator(d, InMemorySaver()), d)  # noqa: E731

    task = new_task(clients, new_project(clients))["id"]
    clients.as_(PO).post(f"/tasks/{task}/commands", json={"command": "PRIORITIZE"})
    assert "evaluation" not in tick()  # le plan d'abord
    assert tick()["evaluation"] == "done"
    assert "evaluation" not in tick()  # rien n'a changé : pas de nouveau rejeu


def test_admin_dashboard_shows_regressions_first(deps, clients):
    analyst = ScriptedModel(Review=[APPROVED], ScenariosDraft=[{"message": "m", "scenarios": []}])
    evaluate(deps(analyst), Casquette.ANALYSTE_TEST, "claude-sonnet")
    evaluate(deps(reviewer_model(REFUSED, APPROVED)), Casquette.REVIEWER, "claude-sonnet")
    regressed = evaluate(deps(reviewer_model(APPROVED, APPROVED)), Casquette.REVIEWER, "claude-sonnet")

    assert clients.as_(PO).get("/evaluations").status_code == 403
    runs = clients.as_(ADMIN).get("/evaluations").json()
    assert [(r["casquette"], r["regressed_cases"]) for r in runs] == [
        ("REVIEWER", ["relecture-plan-bugfix-sans-test"]),
        ("ANALYSTE_TEST", []),
    ]
    assert runs[0]["cost_usd"] == pytest.approx(0.00225 * 2)

    detail = clients.as_(ADMIN).get(f"/evaluations/{regressed.id}").json()
    failed = next(r for r in detail["results"] if not r["passed"])
    assert failed["failures"] == ["Proposition approuvée à tort."] and failed["answer"] == APPROVED | {
        "corrections": []
    }
    assert [h["passed"] for h in detail["history"]] == [2]
    assert clients.as_(ADMIN).get("/evaluations/00000000-0000-0000-0000-000000000000").status_code == 404


def test_a_replay_in_progress_does_not_hide_a_regression(deps, clients, session_factory):
    evaluate(deps(reviewer_model(REFUSED, APPROVED)), Casquette.REVIEWER, "claude-sonnet")
    regressed = evaluate(deps(reviewer_model(APPROVED, APPROVED)), Casquette.REVIEWER, "claude-sonnet")
    with session_factory() as session:
        session.add(EvaluationRun(casquette="REVIEWER", ai_model="claude-sonnet", fingerprint="f",
                                  referentiel_version="r", regressed_cases=[]))  # fmt: skip
        session.commit()
    [shown] = clients.as_(ADMIN).get("/evaluations").json()
    assert shown["id"] == str(regressed.id) and shown["regressed_cases"]
