import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from synapse_api.agents.execution import REPRO_MARKER
from synapse_api.agents.graph import Deps, build_orchestrator
from synapse_api.agents.sandbox import DockerSandbox, RunResult, SandboxError, safe_path
from synapse_api.agents.worker import escalate_overdue, run_once

from .conftest import PO, TESTEUR
from .test_api import BUG, command, new_project, new_task
from .test_orchestrator import APPROVED, PLAN, ScriptedModel, last_message

CONFIG = {"path": "synapse.json", "content": '{"test": "python -m pytest -q"}'}
CODE = {
    "message": "L'export PDF est en place, avec son test.",
    "edits": [
        CONFIG,
        {"path": "app/export.py", "content": "def export_pdf(week):\n    return b'%PDF'\n"},
        {"path": "tests/test_export.py", "content": "from app.export import export_pdf\n"},
    ],
}
REPRO = {
    "message": "Le test reproduit le bug.",
    "edits": [CONFIG, {"path": "tests/test_total.py", "content": "def test_samedi():\n    assert False\n"}],
}
FIX = {
    "message": "Le samedi compte.",
    "edits": [{"path": "app/total.py", "content": "def total(h):\n    return sum(h)\n"}],
}


class FakeSandbox:
    """Bac à sable factice : rejoue des issues de commande (la dernière se répète), sans conteneur."""

    def __init__(self, *results: bool) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, bool]] = []

    def run(self, workspace: Path, command: str, *, image: str, network: bool, label: str) -> RunResult:
        self.calls.append((command, network))
        ok = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        return RunResult(
            command, 0 if ok else 1, "1 passed" if ok else "FAILED tests/test_total.py::test_samedi"
        )


@pytest.fixture
def team(session_factory, tmp_path):
    """`team(model, sandbox)` renvoie (un tour de worker, les dépendances)."""

    def make(model: ScriptedModel, sandbox: FakeSandbox):
        deps = Deps(sessions=session_factory, model=model, sandbox=sandbox, git_dir=tmp_path)
        graph = build_orchestrator(deps, InMemorySaver())
        return (lambda: run_once(graph, deps)), deps

    return make


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8").stdout


def bare_repo(tmp_path: Path) -> Path:
    [repo] = (tmp_path / "repos").glob("*.git")
    return repo


def in_progress(clients, tick, task: str) -> None:
    """Priorise, laisse la casquette proposer son plan, et le valide."""
    command(clients, PO, task, "PRIORITIZE")
    tick()
    assert command(clients, PO, task, "VALIDATE_PLAN").json()["status"] == "IN_PROGRESS"


def get(clients, task: str) -> dict:
    return clients.as_(PO).get(f"/tasks/{task}").json()


def test_feature_is_built_reviewed_tested_then_submitted(clients, team, tmp_path):
    task = new_task(clients, new_project(clients))["id"]
    model = ScriptedModel(PlanDraft=[PLAN], Review=[APPROVED], Implementation=[CODE])
    sandbox = FakeSandbox(True)
    tick, _ = team(model, sandbox)
    in_progress(clients, tick, task)

    assert list(tick().values()) == ["published"]
    assert get(clients, task)["status"] == "REVIEW" and get(clients, task)["pending_decision"] == "RESULT"
    result = last_message(clients, PO, task)
    assert result["kind"] == "RESULT" and result["casquette"] == "DEVELOPPEUR"
    files = {f["path"]: f for f in result["payload"]["files"]}
    assert (
        files["app/export.py"]["additions"] == 2
        and "+def export_pdf(week):" in files["app/export.py"]["diff"]
    )
    assert {c["label"]: c["value"] for c in result["payload"]["checks"]}["Relecture du code"] == "Approuvée"
    assert (
        result["payload"]["note"] == "Branche synapse/feat-001 prête ; fusion dans main après ta validation."
    )
    # Le Développeur part du plan validé ; le Reviewer de code relit le diff ; les tests tournent sans réseau.
    assert "Plan validé par le PO (version 1)" in model.prompts("Implementation")[0]
    assert "« Reviewer de code »" in model.systems("Review")[-1]
    assert "+def export_pdf(week):" in model.prompts("Review")[-1]
    assert sandbox.calls == [("python -m pytest -q", False)]
    # Le travail est sur la branche de la tâche ; main n'a pas bougé.
    repo = bare_repo(tmp_path)
    assert "app/export.py" in git(repo, "ls-tree", "-r", "--name-only", "synapse/feat-001")
    assert git(repo, "ls-tree", "-r", "--name-only", "main") == ""


def test_bug_is_reproduced_by_a_failing_test_before_the_fix(clients, team, tmp_path):
    bug = clients.as_(TESTEUR).post(f"/projects/{new_project(clients)}/bugs", json=BUG).json()["id"]
    failing = PLAN | {"failing_test": "✕ le samedi n'est pas compté"}
    model = ScriptedModel(PlanDraft=[failing], Review=[APPROVED], Implementation=[REPRO, FIX])
    tick, _ = team(model, FakeSandbox(False, True))
    in_progress(clients, tick, bug)

    assert list(tick().values()) == ["published"]
    systems = model.systems("Implementation")
    assert "« Débogueur »" in systems[0] and "« Développeur »" in systems[1]
    log = git(bare_repo(tmp_path), "log", "--format=%s", "synapse/bug-001").splitlines()
    assert REPRO_MARKER in log[1] and log[0].startswith("BUG-001 : ")
    checks = {c["label"]: c["value"] for c in last_message(clients, PO, bug)["payload"]["checks"]}
    assert checks["Test qui reproduisait le bug"] == "Échouait, passe"


def test_a_test_that_passes_does_not_reproduce_the_bug(clients, team):
    bug = clients.as_(TESTEUR).post(f"/projects/{new_project(clients)}/bugs", json=BUG).json()["id"]
    model = ScriptedModel(
        PlanDraft=[PLAN | {"failing_test": "✕ samedi"}], Review=[APPROVED], Implementation=[REPRO, REPRO, FIX]
    )
    tick, _ = team(model, FakeSandbox(True, False, True))
    in_progress(clients, tick, bug)

    assert list(tick().values()) == ["published"]
    assert "Le test passe : il ne reproduit pas le bug." in model.prompts("Implementation")[1]


def test_qa_failures_go_back_to_development_then_up_to_the_po(clients, team):
    task = new_task(clients, new_project(clients))["id"]
    model = ScriptedModel(PlanDraft=[PLAN], Review=[APPROVED], Implementation=[CODE])
    tick, _ = team(model, FakeSandbox(False))
    in_progress(clients, tick, task)

    assert list(tick().values()) == ["escalated"]
    state = get(clients, task)
    assert state["awaiting_reason"] == "QA_LIMIT" and state["pending_decision"] == "ESCALATION"
    assert len(model.prompts("Implementation")) == 3
    assert "Les tests échouent dans le bac à sable" in model.prompts("Implementation")[1]
    qa = [
        m for m in clients.as_(PO).get(f"/tasks/{task}/messages").json() if m["casquette"] == "ANALYSTE_TEST"
    ]
    assert [m["body"].splitlines()[0] for m in qa][-1] == "Les tests échouent (essai 3 sur 3) :"


def test_developer_asks_instead_of_guessing(clients, team):
    task = new_task(clients, new_project(clients))["id"]
    question = {"message": "", "question": "Faut-il arrondir au quart d'heure ?"}
    model = ScriptedModel(PlanDraft=[PLAN], Review=[APPROVED], Implementation=[question, CODE])
    tick, _ = team(model, FakeSandbox(True))
    in_progress(clients, tick, task)

    assert list(tick().values()) == ["question"]
    assert get(clients, task)["pending_decision"] == "QUESTION"
    assert last_message(clients, PO, task)["kind"] == "QUESTION"
    assert tick() == {}  # rien ne bouge tant que le PO n'a pas répondu

    command(clients, PO, task, "ANSWER_HUMAN", "Oui, au quart d'heure supérieur.")
    assert list(tick().values()) == ["published"]
    assert "Oui, au quart d'heure supérieur." in model.prompts("Implementation")[1]


def test_developer_proposes_a_new_plan_instead_of_deviating(clients, team):
    task = new_task(clients, new_project(clients))["id"]
    deviation = {"message": "", "new_plan": PLAN | {"message": "Il faut aussi une table d'historique."}}
    model = ScriptedModel(PlanDraft=[PLAN], Review=[APPROVED], Implementation=[deviation])
    tick, _ = team(model, FakeSandbox(True))
    in_progress(clients, tick, task)

    assert list(tick().values()) == ["plan_change"]
    state = get(clients, task)
    assert state["pending_decision"] == "PLAN" and state["awaiting_reason"] == "PLAN_CHANGE"
    assert state["plan_version"] == 2


def test_done_task_is_merged_into_main(clients, team, tmp_path):
    task = new_task(clients, new_project(clients))["id"]
    model = ScriptedModel(PlanDraft=[PLAN], Review=[APPROVED], Implementation=[CODE])
    tick, _ = team(model, FakeSandbox(True))
    in_progress(clients, tick, task)
    tick()
    assert git(bare_repo(tmp_path), "ls-tree", "-r", "--name-only", "main") == ""

    assert command(clients, PO, task, "VALIDATE_RESULT").json()["status"] == "DONE"
    tick()
    assert "app/export.py" in git(bare_repo(tmp_path), "ls-tree", "-r", "--name-only", "main")
    message = last_message(clients, PO, task)
    assert message["casquette"] == "DEVOPS" and "fusionnée dans main" in message["body"]


def test_execution_over_two_hours_goes_up_to_the_po(clients, team):
    task = new_task(clients, new_project(clients))["id"]
    tick, deps = team(ScriptedModel(PlanDraft=[PLAN], Review=[APPROVED]), FakeSandbox(True))
    in_progress(clients, tick, task)

    assert escalate_overdue(deps, now=datetime.now(UTC) + timedelta(hours=1)) == []
    assert escalate_overdue(deps, now=datetime.now(UTC) + timedelta(hours=2, minutes=1)) == ["FEAT-001"]
    assert get(clients, task)["awaiting_reason"] == "TIMEOUT"


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd", ".git/hooks/pre-commit", "C:/Windows/x", ""])
def test_files_outside_the_repository_are_refused(path):
    with pytest.raises(SandboxError):
        safe_path(path)


docker_only = pytest.mark.skipif(
    not (shutil.which("docker") and os.environ.get("SYNAPSE_DOCKER_TESTS")),
    reason="bac à sable réel : SYNAPSE_DOCKER_TESTS=1 et Docker requis",
)


@docker_only
def test_real_sandbox_runs_code_without_network(tmp_path):
    (tmp_path / "hello.py").write_text("print('bonjour')\n", encoding="utf-8")
    sandbox = DockerSandbox()
    ran = sandbox.run(tmp_path, "python hello.py", image="python:3.12-slim", network=False, label="test")
    assert ran.ok and "bonjour" in ran.output
    offline = "python -c \"import socket; socket.create_connection(('1.1.1.1', 53), 3)\""
    assert not sandbox.run(tmp_path, offline, image="python:3.12-slim", network=False, label="test").ok


@docker_only
def test_real_sandbox_runs_the_feature_tests(clients, session_factory, tmp_path):
    unittest_config = '{"image": "python:3.12-slim", "test": "python -m unittest discover -s tests -t ."}'
    code = {
        "message": "Le total compte le samedi.",
        "edits": [
            {"path": "synapse.json", "content": unittest_config},
            {"path": "app/__init__.py", "content": ""},
            {"path": "app/total.py", "content": "def total(heures):\n    return sum(heures)\n"},
            {"path": "tests/__init__.py", "content": ""},
            {
                "path": "tests/test_total.py",
                "content": (
                    "import unittest\n\nfrom app.total import total\n\n\n"
                    "class Total(unittest.TestCase):\n"
                    "    def test_samedi(self):\n"
                    "        self.assertEqual(total([8, 8, 8, 8, 8, 2]), 42)\n"
                ),
            },
        ],
    }
    model = ScriptedModel(PlanDraft=[PLAN], Review=[APPROVED], Implementation=[code])
    git_dir = tmp_path / "dossier avec espaces"
    deps = Deps(sessions=session_factory, model=model, sandbox=DockerSandbox(), git_dir=git_dir)
    graph = build_orchestrator(deps, InMemorySaver())
    task = new_task(clients, new_project(clients))["id"]
    in_progress(clients, lambda: run_once(graph, deps), task)

    assert list(run_once(graph, deps).values()) == ["published"]
    checks = {c["label"]: c["value"] for c in last_message(clients, PO, task)["payload"]["checks"]}
    assert checks["Tests du projet"] == "Passent"
