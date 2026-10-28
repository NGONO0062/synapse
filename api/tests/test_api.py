import uuid

from synapse_api.db.models import Task
from synapse_api.domain.enums import Casquette
from synapse_api.domain.lifecycle import Actor, Command
from synapse_api.services import execute, propose_report

from .conftest import ADMIN, AUTRE_TESTEUR, PO, TESTEUR


def new_project(clients) -> str:
    res = clients.as_(PO).post("/projects", json={"name": "Gestion des feuilles de temps"})
    assert res.status_code == 201
    return res.json()["id"]


def new_task(clients, project_id: str, type_: str = "FEATURE", user=PO) -> dict:
    res = clients.as_(user).post(f"/projects/{project_id}/tasks", json={"type": type_, "title": "Export PDF"})
    assert res.status_code == 201, res.text
    return res.json()


def agent(session_factory, task_id: str, command: Command, casquette=Casquette.ORCHESTRATEUR) -> None:
    """Simule l'orchestrateur : les agents ne passent pas par l'API HTTP."""
    with session_factory() as session:
        task = session.get(Task, uuid.UUID(task_id))
        execute(session, task, command, Actor.agent(casquette), ai_model="claude-sonnet")
        session.commit()


def command(clients, user, task_id: str, cmd: str, comment: str | None = None):
    return clients.as_(user).post(f"/tasks/{task_id}/commands", json={"command": cmd, "comment": comment})


def test_health(clients):
    assert clients.as_(PO).get("/health").json() == {"status": "ok"}


def test_tasks_are_numbered_per_type(clients):
    project = new_project(clients)
    assert new_task(clients, project)["code"] == "FEAT-001"
    assert new_task(clients, project)["code"] == "FEAT-002"
    assert new_task(clients, project, "BUGFIX")["code"] == "BUG-001"
    assert new_task(clients, project, "DOC")["status"] == "BACKLOG"


def test_only_po_creates_projects_and_features(clients):
    assert clients.as_(TESTEUR).post("/projects", json={"name": "x"}).status_code == 403
    project = new_project(clients)
    res = clients.as_(TESTEUR).post(f"/projects/{project}/tasks", json={"type": "FEATURE", "title": "x"})
    assert res.status_code == 403
    assert new_task(clients, project, "BUGFIX", user=TESTEUR)["code"] == "BUG-001"


def test_admin_has_no_access_to_projects_in_v1(clients):
    assert clients.as_(ADMIN).get("/projects").status_code == 403


def test_tester_sees_only_own_bugs(clients):
    project = new_project(clients)
    new_task(clients, project)
    mine = new_task(clients, project, "BUGFIX", user=TESTEUR)
    new_task(clients, project, "BUGFIX", user=AUTRE_TESTEUR)

    listed = clients.as_(TESTEUR).get(f"/projects/{project}/tasks").json()
    assert [t["id"] for t in listed] == [mine["id"]]
    assert len(clients.as_(PO).get(f"/projects/{project}/tasks").json()) == 3
    assert clients.as_(AUTRE_TESTEUR).get(f"/tasks/{mine['id']}").status_code == 404


def test_full_bugfix_cycle_with_traceability(clients, session_factory):
    project = new_project(clients)
    bug = new_task(clients, project, "BUGFIX", user=TESTEUR)["id"]

    assert command(clients, PO, bug, "PRIORITIZE").json()["status"] == "TODO"
    agent(session_factory, bug, Command.PROPOSE_PLAN, Casquette.DEBOGUEUR)
    assert command(clients, PO, bug, "VALIDATE_PLAN").json()["status"] == "IN_PROGRESS"
    agent(session_factory, bug, Command.SUBMIT_FOR_REVIEW)

    res = command(clients, PO, bug, "VALIDATE_RESULT")
    assert res.json()["status"] == "REVIEW"  # attend la confirmation du testeur
    res = command(clients, TESTEUR, bug, "CONFIRM_FIX")
    assert res.json()["status"] == "DONE"

    events = clients.as_(PO).get(f"/tasks/{bug}/events").json()
    assert [e["command"] for e in events] == [
        "PRIORITIZE",
        "PROPOSE_PLAN",
        "VALIDATE_PLAN",
        "SUBMIT_FOR_REVIEW",
        "VALIDATE_RESULT",
        "CONFIRM_FIX",
    ]
    assert events[1]["casquette"] == "DEBOGUEUR" and events[1]["ai_model"] == "claude-sonnet"
    assert events[2]["actor_name"] == "Aline Mbarga"


def test_agent_commands_are_not_exposed_over_http(clients):
    project = new_project(clients)
    task = new_task(clients, project)["id"]
    assert command(clients, PO, task, "SUBMIT_FOR_REVIEW").status_code == 422
    assert command(clients, PO, task, "PROPOSE_PLAN").status_code == 422


def test_lifecycle_errors_map_to_http(clients):
    project = new_project(clients)
    task = new_task(clients, project)["id"]

    res = command(clients, PO, task, "VALIDATE_RESULT")
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "invalid_status"

    bug = new_task(clients, project, "BUGFIX", user=TESTEUR)["id"]
    res = command(clients, TESTEUR, bug, "PRIORITIZE")
    assert res.status_code == 403

    # Aucun événement n'est journalisé pour une commande refusée.
    assert clients.as_(PO).get(f"/tasks/{task}/events").json() == []


def test_project_summaries_count_statuses_and_decisions(clients, session_factory):
    project = new_project(clients)
    task = new_task(clients, project)["id"]
    new_task(clients, project, "DOC")
    command(clients, PO, task, "PRIORITIZE")
    agent(session_factory, task, Command.PROPOSE_PLAN, Casquette.ARCHITECTE)

    [summary] = clients.as_(PO).get("/projects").json()
    assert summary["status_counts"]["TODO"] == 1 and summary["status_counts"]["BACKLOG"] == 1
    assert summary["pending_decisions"] == 1


def test_decisions_list_what_waits_for_each_role(clients, session_factory):
    project = new_project(clients)
    bug = new_task(clients, project, "BUGFIX", user=TESTEUR)["id"]
    command(clients, PO, bug, "PRIORITIZE")
    agent(session_factory, bug, Command.PROPOSE_PLAN, Casquette.DEBOGUEUR)

    [decision] = clients.as_(PO).get("/decisions").json()
    assert decision["kind"] == "PLAN" and decision["project_name"] == "Gestion des feuilles de temps"
    assert clients.as_(TESTEUR).get("/decisions").json() == []

    command(clients, PO, bug, "VALIDATE_PLAN")
    agent(session_factory, bug, Command.SUBMIT_FOR_REVIEW)
    command(clients, PO, bug, "VALIDATE_RESULT")
    assert clients.as_(PO).get("/decisions").json() == []
    [mine] = clients.as_(TESTEUR).get("/decisions").json()
    assert mine["kind"] == "TESTER_CONFIRMATION"
    assert clients.as_(AUTRE_TESTEUR).get("/decisions").json() == []


def test_task_by_code_respects_visibility(clients):
    project = new_project(clients)
    bug = new_task(clients, project, "BUGFIX", user=TESTEUR)
    assert clients.as_(PO).get(f"/projects/{project}/tasks/by-code/bug-001").json()["id"] == bug["id"]
    assert clients.as_(AUTRE_TESTEUR).get(f"/projects/{project}/tasks/by-code/BUG-001").status_code == 404
    assert clients.as_(PO).get(f"/projects/{project}/tasks/by-code/XYZ-1").status_code == 404


def test_request_opens_the_thread_and_messages_follow(clients):
    project = new_project(clients)
    res = clients.as_(PO).post(
        f"/projects/{project}/tasks",
        json={
            "type": "FEATURE",
            "title": "Export PDF",
            "description": "Seulement les feuilles validées.",
            "ai_model": "claude-opus",
        },
    )
    task = res.json()
    assert task["ai_model"] == "claude-opus"
    clients.as_(PO).post(f"/tasks/{task['id']}/messages", json={"body": "Précision : format A4."})
    thread = clients.as_(PO).get(f"/tasks/{task['id']}/messages").json()
    assert [(m["author_name"], m["body"]) for m in thread] == [
        ("Aline Mbarga", "Seulement les feuilles validées."),
        ("Aline Mbarga", "Précision : format A4."),
    ]


def test_unknown_ai_model_is_rejected(clients):
    project = new_project(clients)
    res = clients.as_(PO).post(
        f"/projects/{project}/tasks", json={"type": "DOC", "title": "x", "ai_model": "gpt-99"}
    )
    assert res.status_code == 422


BUG = {
    "title": "Le total de la semaine ne compte pas le samedi",
    "environment": "STAGING",
    "device": "Chrome, Android",
    "steps": "1. Saisir 8 h du lundi au vendredi\n2. Saisir 2 h le samedi",
    "expected": "42 h",
    "actual": "40 h",
    "severity": "MAJEUR",
}


def test_tester_reports_a_structured_bug(clients):
    project = new_project(clients)
    res = clients.as_(TESTEUR).post(f"/projects/{project}/bugs", json=BUG)
    assert res.status_code == 201, res.text
    bug = res.json()
    assert bug["code"] == "BUG-001" and bug["status"] == "BACKLOG"
    assert bug["bug_report"]["severity"] == "MAJEUR" and bug["bug_report"]["environment"] == "STAGING"
    [opening] = clients.as_(TESTEUR).get(f"/tasks/{bug['id']}/messages").json()
    assert opening["author_name"] == "Brice Nkoulou" and "Attendu : 42 h" in opening["body"]


def test_bug_report_is_validated(clients):
    project = new_project(clients)
    for field, value in [("environment", "PROD"), ("severity", "URGENT"), ("steps", "")]:
        res = clients.as_(TESTEUR).post(f"/projects/{project}/bugs", json=BUG | {field: value})
        assert res.status_code == 422, field
    assert clients.as_(ADMIN).post(f"/projects/{project}/bugs", json=BUG).status_code == 403


TEXT = (
    "Quand je saisis 2 h le samedi, le total de la semaine reste à 40 h au lieu de 42 h. "
    "Vu sur Chrome Android, en staging."
)


def free_text_bug(clients, project: str) -> dict:
    res = clients.as_(TESTEUR).post(f"/projects/{project}/bugs/text", json={"text": TEXT})
    assert res.status_code == 201, res.text
    return res.json()


def reformulate(session_factory, task_id: str, **changes) -> None:
    with session_factory() as session:
        task = session.get(Task, uuid.UUID(task_id))
        propose_report(
            session,
            task,
            Actor.agent(Casquette.DEBOGUEUR),
            body="Voici comment je comprends le bug.",
            payload={"report": BUG | changes, "uncertainties": ["Appareil exact non précisé."]},
        )
        session.commit()


def test_tester_describes_a_bug_in_natural_language(clients):
    project = new_project(clients)
    bug = free_text_bug(clients, project)
    assert bug["code"] == "BUG-001" and bug["status"] == "BACKLOG"
    assert bug["report_required"] and bug["bug_report"] is None
    assert bug["created_by"] == TESTEUR.subject
    assert bug["title"].startswith("Quand je saisis 2 h le samedi") and len(bug["title"]) <= 80
    [opening] = clients.as_(TESTEUR).get(f"/tasks/{bug['id']}/messages").json()
    assert opening["body"] == TEXT
    res = command(clients, PO, bug["id"], "PRIORITIZE")
    assert res.status_code == 409 and res.json()["detail"]["code"] == "report_not_validated"


def test_free_text_bug_must_say_something(clients):
    project = new_project(clients)
    assert clients.as_(TESTEUR).post(f"/projects/{project}/bugs/text", json={"text": "  "}).status_code == 422
    assert clients.as_(ADMIN).post(f"/projects/{project}/bugs/text", json={"text": TEXT}).status_code == 403


def test_author_validates_the_reformulation_before_prioritization(clients, session_factory):
    project = new_project(clients)
    bug = free_text_bug(clients, project)["id"]
    reformulate(session_factory, bug, title="Total hebdomadaire sans le samedi")

    [decision] = clients.as_(TESTEUR).get("/decisions").json()
    assert decision["kind"] == "REPORT" and decision["casquette"] == "DEBOGUEUR"
    assert clients.as_(PO).get("/decisions").json() == []
    # Seul l'auteur valide la reformulation de son signalement.
    assert command(clients, PO, bug, "VALIDATE_REPORT").status_code == 403
    assert command(clients, AUTRE_TESTEUR, bug, "VALIDATE_REPORT").status_code == 404

    res = command(clients, TESTEUR, bug, "REQUEST_REPORT_CHANGES", "C'est sur Firefox, pas Chrome.")
    assert res.status_code == 200 and res.json()["pending_decision"] is None
    assert res.json()["rejected_report_version"] == 1
    reformulate(session_factory, bug, title="Total hebdomadaire sans le samedi (Firefox)", device="Firefox")
    messages = clients.as_(TESTEUR).get(f"/tasks/{bug}/messages").json()
    [proposal_v2] = [m for m in messages if m["plan_version"] == 2]
    assert proposal_v2["kind"] == "REPORT" and proposal_v2["payload"]["report"]["device"] == "Firefox"

    res = command(clients, TESTEUR, bug, "VALIDATE_REPORT")
    assert res.status_code == 200, res.text
    validated = res.json()
    assert validated["title"] == "Total hebdomadaire sans le samedi (Firefox)"
    assert validated["bug_report"]["device"] == "Firefox" and validated["bug_report"]["expected"] == "42 h"
    assert command(clients, PO, bug, "PRIORITIZE").json()["status"] == "TODO"


def test_reformulation_is_checked(clients, session_factory):
    project = new_project(clients)
    bug = free_text_bug(clients, project)["id"]
    try:
        reformulate(session_factory, bug, environment="PROD")
    except ValueError:
        pass
    else:
        raise AssertionError("Une reformulation invalide doit être refusée.")
