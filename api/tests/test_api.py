import uuid

from synapse_api.db.models import Task
from synapse_api.domain.enums import Casquette
from synapse_api.domain.lifecycle import Actor, Command
from synapse_api.services import execute

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
