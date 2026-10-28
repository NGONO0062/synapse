import pytest
from langgraph.checkpoint.memory import InMemorySaver

from synapse_api.agents.casquettes import referentiel
from synapse_api.agents.graph import MAX_DRAFTS, Deps, build_orchestrator
from synapse_api.agents.jobs import AUTHORS, REVIEWERS
from synapse_api.agents.worker import run_once

from .conftest import PO, TESTEUR
from .test_api import BUG, TEXT, command, free_text_bug, new_project, new_task

REPORT = {
    "message": "Voici comment je comprends le bug. Valide-le ou corrige-moi.",
    "report": BUG | {"title": "Total hebdomadaire sans le samedi"},
    "uncertainties": ["Compte utilisé non précisé."],
}
PLAN = {
    "message": "Voici le plan de l'export PDF.",
    "changes": ["+ Export PDF de la semaine", "~ Bouton « Exporter » dans l'écran semaine"],
    "tests": "1 test d'API, 1 E2E sur l'export",
    "uncertainties": ["Mise en page attendue inconnue."],
}
APPROVED = {"approved": True}


class ScriptedModel:
    """Modèle factice : rejoue des réponses écrites d'avance, par format de réponse.
    La dernière réponse d'une liste se répète ; une exception est levée telle quelle."""

    def __init__(self, **answers: list) -> None:
        self.answers = answers
        self.calls: list[tuple[str, str, str]] = []
        self.models: list[str] = []

    def __call__(self, name: str) -> "ScriptedModel":
        self.models.append(name)
        return self

    def structured(self, schema, *, system: str, prompt: str):
        self.calls.append((schema.__name__, system, prompt))
        queue = self.answers[schema.__name__]
        answer = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(answer, Exception):
            raise answer
        return schema.model_validate(answer)

    def prompts(self, schema: str) -> list[str]:
        return [prompt for name, _, prompt in self.calls if name == schema]

    def systems(self, schema: str) -> list[str]:
        return [system for name, system, _ in self.calls if name == schema]


@pytest.fixture
def orchestrator(session_factory):
    """`orchestrator(model)` renvoie un tour de worker, avec un état LangGraph gardé en mémoire."""

    def make(model: ScriptedModel):
        deps = Deps(sessions=session_factory, model=model)
        graph = build_orchestrator(deps, InMemorySaver())
        return lambda: run_once(graph, deps)

    return make


def last_message(clients, user, task_id: str) -> dict:
    return clients.as_(user).get(f"/tasks/{task_id}/messages").json()[-1]


def events(clients, user, task_id: str, cmd: str) -> list[dict]:
    return [e for e in clients.as_(user).get(f"/tasks/{task_id}/events").json() if e["command"] == cmd]


def test_every_casquette_has_its_referentiel():
    for casquette in {*AUTHORS.values(), *REVIEWERS.values()}:
        assert referentiel(casquette).version.startswith(casquette.value.lower() + "@")


def test_debogueur_reformulates_a_bug_written_in_words(clients, orchestrator):
    bug = free_text_bug(clients, new_project(clients))["id"]
    model = ScriptedModel(ReportDraft=[REPORT], Review=[APPROVED])
    tick = orchestrator(model)

    assert list(tick().values()) == ["published"]
    message = last_message(clients, TESTEUR, bug)
    assert message["kind"] == "REPORT" and message["casquette"] == "DEBOGUEUR"
    assert message["body"] == REPORT["message"] and message["plan_version"] == 1
    assert message["payload"]["report"]["title"] == "Total hebdomadaire sans le samedi"
    [decision] = clients.as_(TESTEUR).get("/decisions").json()
    assert decision["kind"] == "REPORT"
    # Traçabilité : modèle IA et version du référentiel journalisés.
    [event] = events(clients, TESTEUR, bug, "PROPOSE_REPORT")
    assert event["ai_model"] == "claude-sonnet" and event["casquette"] == "DEBOGUEUR"
    assert model.models == ["claude-sonnet", "claude-sonnet"]
    # Le Débogueur lit le texte de l'auteur ; l'Analyste de test relit avant l'humain.
    assert TEXT in model.prompts("ReportDraft")[0]
    assert "« Débogueur »" in model.systems("ReportDraft")[0]
    assert "« Analyste de test »" in model.systems("Review")[0]
    assert tick() == {}


def test_author_correction_reaches_the_debogueur(clients, orchestrator):
    bug = free_text_bug(clients, new_project(clients))["id"]
    model = ScriptedModel(ReportDraft=[REPORT, REPORT | {"message": "Corrigé : Firefox."}], Review=[APPROVED])
    tick = orchestrator(model)
    tick()

    assert (
        command(clients, TESTEUR, bug, "REQUEST_REPORT_CHANGES", "C'est sur Firefox, pas Chrome.").status_code
        == 200
    )
    assert list(tick().values()) == ["published"]
    assert "C'est sur Firefox, pas Chrome." in model.prompts("ReportDraft")[1]
    message = last_message(clients, TESTEUR, bug)
    assert message["plan_version"] == 2 and message["body"] == "Corrigé : Firefox."


def test_feature_plan_is_reviewed_before_the_po_sees_it(clients, orchestrator):
    task = new_task(clients, new_project(clients))["id"]
    review = {"approved": False, "corrections": ["Le critère d'acceptation n'est couvert par aucun test."]}
    model = ScriptedModel(PlanDraft=[PLAN, PLAN | {"message": "Plan corrigé."}], Review=[review, APPROVED])
    tick = orchestrator(model)
    assert tick() == {}  # au Backlog, rien n'est dû aux casquettes

    command(clients, PO, task, "PRIORITIZE")
    assert list(tick().values()) == ["published"]
    assert "Le critère d'acceptation n'est couvert par aucun test." in model.prompts("PlanDraft")[1]
    assert "« Business Analyst »" in model.systems("Review")[0]
    message = last_message(clients, PO, task)
    assert message["kind"] == "PLAN" and message["casquette"] == "ARCHITECTE"
    assert message["body"] == "Plan corrigé." and message["payload"]["warnings"] == []
    [event] = events(clients, PO, task, "PROPOSE_PLAN")
    assert event["to_status"] == "TODO"
    assert clients.as_(PO).get(f"/tasks/{task}").json()["pending_decision"] == "PLAN"


def test_bugfix_plan_starts_with_a_failing_test(clients, orchestrator):
    project = new_project(clients)
    bug = clients.as_(TESTEUR).post(f"/projects/{project}/bugs", json=BUG).json()["id"]
    command(clients, PO, bug, "PRIORITIZE")
    failing = PLAN | {"failing_test": "✕ le total de la semaine compte le samedi"}
    model = ScriptedModel(PlanDraft=[PLAN, failing], Review=[APPROVED])
    orchestrator(model)()

    # Sans test en échec, le brouillon repart au Débogueur avant toute relecture.
    assert len(model.prompts("PlanDraft")) == 2 and len(model.prompts("Review")) == 1
    assert "Définition de « terminé »" in model.prompts("PlanDraft")[1]
    assert "« Reviewer de code »" in model.systems("Review")[0]
    message = last_message(clients, PO, bug)
    assert (
        message["casquette"] == "DEBOGUEUR" and message["payload"]["failing_test"] == failing["failing_test"]
    )


def test_unresolved_points_reach_the_human_as_warnings(clients, orchestrator):
    task = new_task(clients, new_project(clients))["id"]
    command(clients, PO, task, "PRIORITIZE")
    model = ScriptedModel(
        PlanDraft=[PLAN], Review=[{"approved": False, "corrections": ["Impact sur les droits ?"]}]
    )
    assert list(orchestrator(model)().values()) == ["published"]

    assert len(model.prompts("PlanDraft")) == MAX_DRAFTS
    warnings = last_message(clients, PO, task)["payload"]["warnings"]
    assert warnings == ["Relecture (Business Analyst) : Impact sur les droits ?"]


def test_interrupted_work_resumes_where_it_stopped(clients, orchestrator):
    task = new_task(clients, new_project(clients))["id"]
    command(clients, PO, task, "PRIORITIZE")
    model = ScriptedModel(PlanDraft=[PLAN], Review=[ConnectionError("passerelle injoignable"), APPROVED])
    tick = orchestrator(model)

    assert list(tick().values()) == ["error"]
    assert clients.as_(PO).get(f"/tasks/{task}").json()["plan_version"] == 0
    assert list(tick().values()) == ["published"]
    # Le brouillon déjà écrit n'est pas refait : seule la relecture est rejouée.
    assert len(model.prompts("PlanDraft")) == 1 and len(model.prompts("Review")) == 2
