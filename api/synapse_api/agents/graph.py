"""Graphe de l'orchestrateur (LangGraph) : un sous-graphe par casquette (section 12).

    orchestrateur : préparer le dossier → sous-graphe de la casquette qui rédige
    casquette     : brouillon → définition de « terminé » → relecture → publication
                       ↑________ corrections (3 brouillons au plus) ________|

Chaque étape est sauvegardée par le checkpointer : une tâche interrompue reprend là où
elle s'est arrêtée, sans refaire les appels déjà faits (section 11, robustesse).
"""

import json
import uuid
from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session, sessionmaker

from synapse_api.agents.casquettes import LABELS, referentiel, system_prompt
from synapse_api.agents.gateway import ModelFactory
from synapse_api.agents.jobs import AUTHORS, JOBS, Assignment, Job, Review, assignment_for, brief
from synapse_api.db.models import Task
from synapse_api.domain.enums import Casquette, TaskType
from synapse_api.domain.lifecycle import Actor

# Au-delà, la proposition part quand même, avec les points non résolus en avertissement :
# c'est l'humain qui tranche.
MAX_DRAFTS = 3


class WorkState(TypedDict, total=False):
    task_id: str
    code: str
    job: str
    version: int
    task_type: str
    ai_model: str
    brief: str
    draft: dict[str, Any]
    drafts: int
    feedback: list[str]  # corrections à reprendre, ou avertissements si la limite est atteinte
    outcome: str  # « published », ou « obsolete » si la tâche a changé entre-temps


@dataclass(frozen=True)
class Deps:
    sessions: sessionmaker[Session]
    model: ModelFactory


def initial_state(assignment: Assignment) -> WorkState:
    return {
        "task_id": str(assignment.task_id),
        "code": assignment.code,
        "job": assignment.job.value,
        "version": assignment.version,
        "task_type": assignment.task_type.value,
    }


def _assignment(state: WorkState) -> Assignment:
    return Assignment(
        uuid.UUID(state["task_id"]),
        state["code"],
        Job(state["job"]),
        state["version"],
        TaskType(state["task_type"]),
    )


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def casquette_graph(casquette: Casquette, deps: Deps):
    """Sous-graphe d'une casquette : elle rédige, vérifie, se fait relire, puis publie."""

    def draft(state: WorkState) -> WorkState:
        a = _assignment(state)
        spec = JOBS[a.job]
        prompt = f"{state['brief']}\n\nTa mission : {spec.instruction(a.job, a.task_type)}"
        if state.get("feedback"):
            prompt += (
                f"\n\nTa proposition précédente :\n{json.dumps(state['draft'], ensure_ascii=False)}"
                f"\n\nCorrige-la :\n{_bullets(state['feedback'])}"
            )
        answer = deps.model(state["ai_model"]).structured(
            spec.schema, system=system_prompt(casquette), prompt=prompt
        )
        return {"draft": answer.model_dump(mode="json"), "drafts": state.get("drafts", 0) + 1, "feedback": []}

    def check(state: WorkState) -> WorkState:
        a = _assignment(state)
        spec = JOBS[a.job]
        problems = spec.check(spec.schema.model_validate(state["draft"]), a.task_type)
        return {"feedback": [f"Définition de « terminé » : {p}" for p in problems]}

    def review(state: WorkState) -> WorkState:
        a = _assignment(state)
        prompt = (
            f"{state['brief']}\n\nProposition du {LABELS[casquette]} :\n"
            f"{json.dumps(state['draft'], ensure_ascii=False, indent=2)}\n\n"
            "Relis-la avec ton référentiel. Approuve-la si elle peut être soumise à l'humain telle quelle ; "
            "sinon, liste des corrections précises. Ne la réécris pas."
        )
        verdict = deps.model(state["ai_model"]).structured(
            Review, system=system_prompt(a.reviewer), prompt=prompt
        )
        if verdict.approved:
            return {}
        corrections = verdict.corrections or ["Proposition refusée sans motif précis."]
        return {
            "feedback": state.get("feedback", [])
            + [f"Relecture ({LABELS[a.reviewer]}) : {c}" for c in corrections]
        }

    def publish(state: WorkState) -> WorkState:
        a = _assignment(state)
        spec = JOBS[a.job]
        with deps.sessions() as session:
            task = session.get(Task, a.task_id)
            current = assignment_for(task) if task else None
            if current is None or (current.job, current.version) != (a.job, a.version):
                return {"outcome": "obsolete"}
            spec.publish(
                session,
                task,
                Actor.agent(casquette),
                spec.schema.model_validate(state["draft"]),
                state.get("feedback", []),
                referentiel(casquette).version,
            )
            session.commit()
        return {"outcome": "published"}

    def after_check(state: WorkState) -> str:
        return "draft" if state["feedback"] and state["drafts"] < MAX_DRAFTS else "review"

    def after_review(state: WorkState) -> str:
        return "draft" if state.get("feedback") and state["drafts"] < MAX_DRAFTS else "publish"

    graph = StateGraph(WorkState)
    graph.add_node("draft", draft)
    graph.add_node("check", check)
    graph.add_node("review", review)
    graph.add_node("publish", publish)
    graph.add_edge(START, "draft")
    graph.add_edge("draft", "check")
    graph.add_conditional_edges("check", after_check, ["draft", "review"])
    graph.add_conditional_edges("review", after_review, ["draft", "publish"])
    graph.add_edge("publish", END)
    # Sans checkpointer propre : il hérite de celui de l'orchestrateur.
    return graph.compile(name=casquette.value.lower())


def build_orchestrator(deps: Deps, checkpointer=None):
    def prepare(state: WorkState) -> WorkState:
        with deps.sessions() as session:
            task = session.get(Task, uuid.UUID(state["task_id"]))
            return {"brief": brief(task), "ai_model": task.ai_model, "drafts": 0, "feedback": []}

    def route(state: WorkState) -> str:
        return _assignment(state).author.value.lower()

    authors = sorted(set(AUTHORS.values()))
    graph = StateGraph(WorkState)
    graph.add_node("prepare", prepare)
    for casquette in authors:
        graph.add_node(casquette.value.lower(), casquette_graph(casquette, deps))
        graph.add_edge(casquette.value.lower(), END)
    graph.add_edge(START, "prepare")
    graph.add_conditional_edges("prepare", route, [c.value.lower() for c in authors])
    return graph.compile(checkpointer=checkpointer, name="orchestrateur")


def run(orchestrator, assignment: Assignment) -> str:
    """Fait avancer un travail ; reprend au point d'arrêt s'il a été interrompu."""
    config = {"configurable": {"thread_id": assignment.thread_id}}
    if orchestrator.get_state(config).next:
        result = orchestrator.invoke(None, config)
    else:
        result = orchestrator.invoke(initial_state(assignment), config)
    return result["outcome"]
