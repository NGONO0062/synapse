"""Mémoire du projet (lot 4a, section 7) : ce que l'humain a validé, relu par les casquettes."""

import io

import pytest
from openpyxl import load_workbook

from synapse_api.domain.enums import SCENARIO_COLUMNS, MemoryDocument
from synapse_api.memory import MemoryChange, MemoryContentError, apply_change, next_id

from .conftest import ADMIN, PO, TESTEUR
from .test_api import BUG, command, new_project, new_task
from .test_execution import (
    BUG_MEMORY,
    CODE,
    FIX,
    MEMORY,
    REPRO,
    REQUIREMENTS,
    SCENARIO,
    FakeSandbox,
    bare_repo,
    get,
    git,
    in_progress,
)
from .test_orchestrator import APPROVED, PLAN, ScriptedModel, last_message

EXIGENCE = REQUIREMENTS["requirements"][0]


def memory_of(clients, project: str) -> dict[str, dict]:
    cards = clients.as_(PO).get(f"/projects/{project}/memory").json()["documents"]
    return {card["document"]: card for card in cards}


def document(clients, project: str, name: str, **params) -> dict:
    return clients.as_(PO).get(f"/projects/{project}/memory/{name}", params=params).json()


# Contenu des documents.


def test_a_change_replaces_in_place_adds_at_the_end_and_removes():
    first = EXIGENCE | {"id": "EX-001"}
    second = EXIGENCE | {"id": "EX-002", "title": "Deuxième"}
    change = MemoryChange(
        document=MemoryDocument.EXIGENCES,
        upserts=[first | {"title": "Renommée"}, EXIGENCE | {"id": "EX-003"}],
        removals=["EX-002"],
    )
    items = apply_change([first, second], change)
    assert [(i["id"], i["title"]) for i in items] == [("EX-001", "Renommée"), ("EX-003", EXIGENCE["title"])]
    assert next_id(items, "EX") == "EX-004" and next_id([], "SC") == "SC-001"


def test_an_agent_never_sets_a_scenario_status():
    passed = SCENARIO | {"chrome": "Passed", "firefox": "Failed"}
    same = apply_change([passed], MemoryChange(document=MemoryDocument.SCENARIOS, upserts=[SCENARIO]))
    assert (same[0]["chrome"], same[0]["firefox"]) == ("Passed", "Failed")  # repris à l'identique

    changed = SCENARIO | {"expected": "Autre résultat", "chrome": "Passed"}
    [row] = apply_change([passed], MemoryChange(document=MemoryDocument.SCENARIOS, upserts=[changed]))
    assert {row[p] for p in ("chrome", "firefox", "ios", "android")} == {"Not started"}


def test_invalid_or_forbidden_changes_are_refused():
    with pytest.raises(MemoryContentError):
        apply_change([], MemoryChange(document=MemoryDocument.EXIGENCES, upserts=[{"id": "X"}]))
    with pytest.raises(MemoryContentError):  # les décisions viennent seulement des réponses du PO
        apply_change([], MemoryChange(document=MemoryDocument.DECISIONS, upserts=[{}]))


# Décisions : les réponses du PO aux casquettes.


def test_po_answer_becomes_a_dated_decision(clients, team):
    project = new_project(clients)
    task = new_task(clients, project)["id"]
    question = {"message": "", "question": "Faut-il arrondir au quart d'heure ?"}
    model = ScriptedModel(PlanDraft=[PLAN], Review=[APPROVED], Implementation=[question])
    tick, _ = team(model, FakeSandbox(True))
    in_progress(clients, tick, task)
    tick()
    assert memory_of(clients, project)["DECISIONS"]["latest"] is None

    command(clients, PO, task, "ANSWER_HUMAN", "Oui, au quart d'heure supérieur.")
    decisions = document(clients, project, "DECISIONS")
    [decision] = decisions["items"]
    assert decision["question"] == "Faut-il arrondir au quart d'heure ?"
    assert decision["answer"] == "Oui, au quart d'heure supérieur."
    who = (decision["author"], decision["task"], decision["casquette"])
    assert who == ("Aline Mbarga", "FEAT-001", "DEVELOPPEUR")
    assert decisions["count_label"] == "1 décision" and decisions["version"]["source_task"] == "FEAT-001"


def test_memory_is_for_the_po_only(clients):
    project = new_project(clients)
    assert clients.as_(PO).get(f"/projects/{project}/memory").status_code == 200
    for user in (TESTEUR, ADMIN):
        assert clients.as_(user).get(f"/projects/{project}/memory").status_code == 403
        assert clients.as_(user).get(f"/projects/{project}/memory/scenarios.xlsx").status_code == 403
    cards = memory_of(clients, project)
    assert list(cards) == [d.value for d in MemoryDocument]
    assert cards["EXIGENCES"] == {
        "document": "EXIGENCES",
        "label": "Exigences",
        "file": "memoire/exigences.md",
        "count_label": "0 exigence",
        "latest": None,
    }


# Livrable : exigences et scénarios proposés, versés au Done.


def test_feature_result_proposes_memory_updates_poured_when_done(clients, team, tmp_path):
    project = new_project(clients)
    task = new_task(clients, project)["id"]
    model = ScriptedModel(PlanDraft=[PLAN], Review=[APPROVED], Implementation=[CODE], **MEMORY)
    tick, _ = team(model, FakeSandbox(True))
    in_progress(clients, tick, task)
    tick()

    # Le Business Analyst écrit les exigences, l'Analyste de test les scénarios à partir d'elles.
    assert "« Business Analyst »" in model.systems("RequirementsDraft")[0]
    assert "Prochain identifiant libre : EX-001" in model.prompts("RequirementsDraft")[0]
    scenarios_prompt = model.prompts("ScenariosDraft")[0]
    assert "« Analyste de test »" in model.systems("ScenariosDraft")[0] and "EX-001" in scenarios_prompt
    assert "Diff de la branche" not in scenarios_prompt  # jamais à partir du code
    result = last_message(clients, PO, task)["payload"]
    assert [c["document"] for c in result["memory"]] == ["EXIGENCES", "SCENARIOS"]
    checks = {c["label"]: c["value"] for c in result["checks"]}
    assert checks["Mémoire du projet"] == "1 exigence, 1 scénario à verser au Done"
    assert memory_of(clients, project)["EXIGENCES"]["latest"] is None  # rien tant que le PO n'a pas validé

    command(clients, PO, task, "VALIDATE_RESULT")
    cards = memory_of(clients, project)
    assert cards["EXIGENCES"]["count_label"] == "1 exigence"
    assert cards["EXIGENCES"]["latest"]["summary"] == "FEAT-001 : 1 exigence ajoutée"
    assert cards["EXIGENCES"]["latest"]["validated_by"] == "Aline Mbarga"
    [row] = document(clients, project, "SCENARIOS")["items"]
    assert row["id"] == "SC-001" and row["chrome"] == "Not started"

    # Le worker l'écrit dans le dépôt, dossier memoire/ sur main, à côté du code.
    tick()
    repo = bare_repo(tmp_path)
    exigences = git(repo, "show", "main:memoire/exigences.md")
    assert exigences.startswith("# Exigences") and "## EX-001 · Exporter la semaine en PDF" in exigences
    assert "app/export.py" in git(repo, "ls-tree", "-r", "--name-only", "main")
    assert memory_of(clients, project)["EXIGENCES"]["latest"]["commit"]

    # La tâche suivante part de la mémoire : identifiants suivants, exigence existante dans le dossier.
    second = new_task(clients, project)["id"]
    in_progress(clients, tick, second)
    tick()
    assert "EX-001 · Exporter la semaine en PDF" in model.prompts("Implementation")[-1]
    assert "Prochain identifiant libre : EX-002" in model.prompts("RequirementsDraft")[-1]


def test_memory_history_keeps_every_version(clients, team):
    project = new_project(clients)
    renamed = REQUIREMENTS | {"requirements": [EXIGENCE | {"title": "Exporter une semaine validée en PDF"}]}
    model = ScriptedModel(
        PlanDraft=[PLAN],
        Review=[APPROVED],
        Implementation=[CODE],
        RequirementsDraft=[REQUIREMENTS, renamed],
        ScenariosDraft=MEMORY["ScenariosDraft"],
    )
    tick, _ = team(model, FakeSandbox(True))
    for _ in range(2):
        task = new_task(clients, project)["id"]
        in_progress(clients, tick, task)
        tick()
        command(clients, PO, task, "VALIDATE_RESULT")

    latest = document(clients, project, "EXIGENCES")
    assert [h["version"] for h in latest["history"]] == [2, 1]
    assert latest["history"][0]["summary"] == "FEAT-002 : 1 exigence modifiée"
    assert document(clients, project, "EXIGENCES", version=1)["version"]["source_task"] == "FEAT-001"
    # Scénario repris à l'identique par la seconde tâche : pas de nouvelle version.
    assert [h["version"] for h in document(clients, project, "SCENARIOS")["history"]] == [1]
    missing = clients.as_(PO).get(f"/projects/{project}/memory/EXIGENCES", params={"version": 9})
    assert missing.status_code == 404


def test_bugfix_scenario_is_poured_after_the_tester_confirms(clients, team):
    project = new_project(clients)
    bug = clients.as_(TESTEUR).post(f"/projects/{project}/bugs", json=BUG).json()["id"]
    failing = PLAN | {"failing_test": "✕ le samedi n'est pas compté"}
    model = ScriptedModel(PlanDraft=[failing], Review=[APPROVED], Implementation=[REPRO, FIX], **BUG_MEMORY)
    tick, _ = team(model, FakeSandbox(False, True))
    in_progress(clients, tick, bug)
    tick()
    assert "RequirementsDraft" not in {name for name, _, _ in model.calls}  # pas d'exigence pour un bug

    command(clients, PO, bug, "VALIDATE_RESULT")
    assert memory_of(clients, project)["SCENARIOS"]["latest"] is None
    command(clients, TESTEUR, bug, "CONFIRM_FIX")
    assert get(clients, bug)["status"] == "DONE"
    assert document(clients, project, "SCENARIOS")["items"][0]["scenario"] == "Total avec un samedi travaillé"


def test_agents_cannot_write_the_memory_files(clients, team, tmp_path):
    project = new_project(clients)
    task = new_task(clients, project)["id"]
    sneaky = CODE | {"edits": [*CODE["edits"], {"path": "memoire/exigences.md", "content": "# Faux"}]}
    model = ScriptedModel(PlanDraft=[PLAN], Review=[APPROVED], Implementation=[sneaky], **MEMORY)
    tick, _ = team(model, FakeSandbox(True))
    in_progress(clients, tick, task)
    tick()

    result = last_message(clients, PO, task)["payload"]
    assert "memoire/exigences.md" not in [f["path"] for f in result["files"]]
    assert any("memoire/exigences.md" in w for w in result["warnings"])
    assert "memoire/" not in git(bare_repo(tmp_path), "ls-tree", "-r", "--name-only", "synapse/feat-001")


def test_scenarios_export_follows_the_excel_model(clients, team):
    project = new_project(clients)
    task = new_task(clients, project)["id"]
    tick, _ = team(
        ScriptedModel(PlanDraft=[PLAN], Review=[APPROVED], Implementation=[CODE], **MEMORY), FakeSandbox(True)
    )
    in_progress(clients, tick, task)
    tick()
    command(clients, PO, task, "VALIDATE_RESULT")

    response = clients.as_(PO).get(f"/projects/{project}/memory/scenarios.xlsx")
    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith('attachment; filename="scenarios-')
    sheet = load_workbook(io.BytesIO(response.content)).active
    rows = [[cell.value for cell in row] for row in sheet.iter_rows()]
    assert rows[0] == list(SCENARIO_COLUMNS)
    assert rows[1] == [
        "Export PDF",
        "Exporter une semaine validée",
        "Consultant connecté",
        "1. Ouvrir la semaine\n2. Cliquer sur Exporter en PDF",
        "Le PDF reprend le détail par jour et le total",
        "Not started",
        "Not started",
        "Not started",
        "Not started",
    ]
