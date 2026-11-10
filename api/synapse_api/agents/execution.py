"""Exécution d'une tâche en In progress, jusqu'au livrable en Review (lots 3b et 4a).

    préparer la branche → [Bugfix] test qui reproduit le bug (Débogueur, doit échouer)
        → réaliser (Développeur ou Rédacteur) → relecture du code → QA dans le bac à sable
        → [Feature] exigences (Business Analyst) → [Feature, Bugfix] scénarios (Analyste de test)
        → livrable en Review

La réalisation peut aussi s'arrêter sur une question au PO ou sur un nouveau plan à valider.
Un échec QA repart en réalisation ; au 3e, la tâche remonte au PO (cycle de vie).

Exigences et scénarios sont des mises à jour de la mémoire du projet proposées avec le livrable :
écrites à partir de la demande, du plan validé, des réponses du PO et du signalement, jamais à
partir du code. Le PO les valide avec le résultat ; elles sont versées au Done (memory.pour).
"""

import json
import uuid
from collections.abc import Callable
from pathlib import PurePosixPath

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from synapse_api import memory
from synapse_api.agents import activity
from synapse_api.agents.casquettes import LABELS, referentiel, system_prompt
from synapse_api.agents.jobs import (
    Assignment,
    PlanDraft,
    Review,
    assignment_for,
    branch_name,
    review_prompt,
)
from synapse_api.agents.sandbox import CONFIG_FILE, RunResult, Workspace, safe_path
from synapse_api.agents.state import Deps, WorkState
from synapse_api.agents.usage import ask_model
from synapse_api.db.models import Task
from synapse_api.domain.enums import Casquette, MemoryDocument, MessageKind, TaskType
from synapse_api.domain.lifecycle import Actor, Command
from synapse_api.domain.rules import MAX_QA_ROUND_TRIPS
from synapse_api.memory import MemoryChange, MemoryContentError, Requirement, ScenarioRow
from synapse_api.schemas import Check
from synapse_api.services import add_message, execute, propose_plan

MAX_ROUNDS = 3  # brouillons de code, ou essais de reproduction, avant de s'arrêter
REPRO_MARKER = "[synapse:reproduction]"
CONTEXT_BUDGET = 120_000  # caractères de fichiers remis au modèle
FILE_LIMIT = 40_000
SKIPPED = ("node_modules/", ".venv/", "venv/", "dist/", "build/", "__pycache__/", ".next/")
BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz", ".woff", ".woff2",
    ".ttf", ".mp4", ".mp3", ".xlsx", ".docx", ".pptx", ".jar", ".exe", ".dll", ".so", ".lock",
}  # fmt: skip


class FileEdit(BaseModel):
    path: str = Field(description="Chemin relatif dans le dépôt, avec des « / ».")
    content: str | None = Field(
        default=None, description="Contenu complet du fichier ; absent pour le supprimer."
    )


class Implementation(BaseModel):
    message: str = Field(description="Une ou deux phrases au PO : ce qui a été fait.")
    edits: list[FileEdit] = Field(default=[], description="Fichiers à écrire en entier ou à supprimer.")
    question: str | None = Field(
        default=None, description="Si une règle manque pour avancer : la question au PO, sans fichier."
    )
    new_plan: PlanDraft | None = Field(
        default=None,
        description="Si le plan validé ne peut pas être suivi : le nouveau plan à valider, sans fichier.",
    )


REPRODUCE = (
    "Écris seulement le test automatisé qui reproduit ce bug : il doit échouer tant que le bug est là. "
    f"Ne corrige pas le bug. Si {CONFIG_FILE} n'existe pas, crée-le avec la commande « test »."
)
IMPLEMENT = {
    TaskType.FEATURE: (
        "Réalise le plan validé, et seulement lui. Donne chaque fichier modifié en entier. Ajoute les "
        f"tests qui prouvent la demande ; ils passent avec la commande « test » de {CONFIG_FILE} "
        "(crée-le si besoin)."
    ),
    TaskType.BUGFIX: (
        "Corrige le bug selon le plan validé. Le test qui le reproduit est déjà dans le dépôt : ne le "
        "modifie pas, corrige le code pour qu'il passe sans casser les autres tests. Donne chaque "
        "fichier modifié en entier."
    ),
    TaskType.DOC: "Écris la documentation prévue par le plan validé. Donne chaque fichier en entier.",
}
ESCAPES = (
    " Si une règle manque, pose une question au lieu d'écrire des fichiers. Si le plan validé ne peut "
    "pas être suivi, propose un nouveau plan au lieu d'écrire des fichiers."
)


# Mémoire du projet : exigences (Business Analyst) et scénarios (Analyste de test).


class RequirementsDraft(BaseModel):
    message: str = Field(description="Une phrase au PO : ce qui change dans les exigences.")
    requirements: list[Requirement] = Field(
        default=[], description="Exigences ajoutées, ou modifiées et données en entier (même identifiant)."
    )
    removed: list[str] = Field(default=[], description="Identifiants des exigences que la demande supprime.")
    uncertainties: list[str] = []
    assumptions: list[str] = []


class ScenariosDraft(BaseModel):
    message: str = Field(description="Une phrase au PO : ce que couvrent les scénarios.")
    scenarios: list[ScenarioRow] = Field(
        default=[], description="Scénarios ajoutés, ou modifiés et donnés en entier (même identifiant)."
    )
    uncertainties: list[str] = []
    assumptions: list[str] = []


REQUIREMENTS = (
    "Mets à jour les exigences de la mémoire du projet pour cette Feature, à partir de la demande, du "
    "plan validé et des réponses du PO, jamais à partir du code. Ajoute les exigences nouvelles ; reprends "
    "en entier, avec leur identifiant, celles que la demande change ; retire celles qu'elle supprime. "
    "Chaque exigence dit qui, quoi et pourquoi, avec des critères d'acceptation testables. Ne touche pas "
    "aux exigences que la demande ne concerne pas."
)
SCENARIOS = {
    TaskType.FEATURE: (
        "Écris les scénarios de test de cette Feature dans le modèle Excel du projet, à partir des "
        "exigences ci-dessous, jamais à partir du code. Couvre chaque critère d'acceptation (partitions, "
        "valeurs limites, cas d'erreur et de droits). Chaque scénario cite les exigences qu'il couvre."
    ),
    TaskType.BUGFIX: (
        "Écris le scénario de non-régression de ce bug dans le modèle Excel du projet, à partir du "
        "signalement validé, jamais à partir du code : les étapes du signalement, et le résultat attendu "
        "comme résultat attendu. Cite l'exigence concernée si la mémoire en a une."
    ),
}
SCENARIO_FORMAT = (
    " Un scénario par ligne : module, scénario en une phrase, préconditions, étapes numérotées (une par "
    "ligne : « 1. … »), résultat attendu observable. Ne donne aucun statut d'exécution."
)


def requirements_prompt(brief: str, next_id: str) -> str:
    """Consigne du Business Analyst, partagée avec les cas de référence (evaluation.py)."""
    return f"{brief}\n\nTa mission : {REQUIREMENTS} Prochain identifiant libre : {next_id}."


def scenarios_prompt(brief: str, task_type: TaskType, requirements: list[dict], next_id: str) -> str:
    """Consigne de l'Analyste de test, partagée avec les cas de référence (evaluation.py)."""
    prompt = brief
    if requirements:
        prompt += (
            "\n\nExigences de cette tâche, proposées par le Business Analyst et validées avec le résultat :\n"
            + json.dumps(requirements, ensure_ascii=False, indent=2)
        )
    mission = f"{SCENARIOS[task_type]}{SCENARIO_FORMAT} Prochain identifiant libre : {next_id}."
    return f"{prompt}\n\nTa mission : {mission}"


def memory_summary(changes: list[MemoryChange]) -> str:
    """« 2 exigences, 3 scénarios proposés » : ce que le livrable versera dans la mémoire."""
    parts = []
    for c in changes:
        removed = f" ({len(c.removals)} retirée(s))" if c.removals else ""
        parts.append(memory.count_label(c.document, len(c.upserts)) + removed)
    return (", ".join(parts) + " à verser au Done") if parts else "Rien à verser"


def _duplicates(keys: list[str]) -> list[str]:
    return sorted({k for k in keys if keys.count(k) > 1})


def check_requirements(draft: RequirementsDraft, task_type: TaskType = TaskType.FEATURE) -> list[str]:
    """Définition de « terminé » du Business Analyst."""
    problems = []
    if not draft.requirements and not draft.removed:
        problems.append("Aucune exigence ajoutée, modifiée ou retirée : une Feature en change au moins une.")
    for r in draft.requirements:
        if not [c for c in r.acceptance if c.strip()]:
            problems.append(f"{r.id} n'a pas de critère d'acceptation.")
    for key in _duplicates([r.id for r in draft.requirements]):
        problems.append(f"{key} est proposée deux fois.")
    if not draft.message.strip():
        problems.append("Le message au PO est vide.")
    return problems


def check_scenarios(
    draft: ScenariosDraft,
    task_type: TaskType = TaskType.FEATURE,
    known: set[str] | None = None,
    to_cover: set[str] | None = None,
) -> list[str]:
    """Définition de « terminé » de l'Analyste de test. `known` : exigences existantes ou proposées ;
    `to_cover` : exigences de la tâche, chacune couverte par un scénario au moins."""
    problems = []
    if not draft.scenarios:
        problems.append("Aucun scénario écrit.")
    for s in draft.scenarios:
        if not s.steps.lstrip().startswith("1"):
            problems.append(f"{s.id} : les étapes ne sont pas numérotées (« 1. … »).")
        if task_type is TaskType.FEATURE and not s.requirements:
            problems.append(f"{s.id} ne cite aucune exigence couverte.")
        unknown = sorted(set(s.requirements) - known) if known is not None else []
        if unknown:
            problems.append(f"{s.id} cite une exigence inconnue : {', '.join(unknown)}.")
    covered = {r for s in draft.scenarios for r in s.requirements}
    for key in sorted((to_cover or set()) - covered):
        problems.append(f"{key} n'est couverte par aucun scénario.")
    for key in _duplicates([s.id for s in draft.scenarios]):
        problems.append(f"{key} est proposé deux fois.")
    if not draft.message.strip():
        problems.append("Le message au PO est vide.")
    return problems


def repo_context(ws: Workspace) -> str:
    """Fichiers remis au modèle : la liste complète, et le contenu tant que le budget le permet."""
    files = [f for f in ws.files() if not f.startswith(SKIPPED)]
    parts = [f"Dépôt du projet, branche {ws.branch} ({len(files)} fichiers) :"]
    parts += [f"- {f}" for f in files] or ["(dépôt vide)"]
    budget = CONTEXT_BUDGET
    for path in files:
        if PurePosixPath(path).suffix.lower() in BINARY_SUFFIXES:
            continue
        content = ws.read(path)
        if len(content) > min(FILE_LIMIT, budget):
            parts.append(f"\n=== {path} === (contenu non montré : {len(content)} caractères)")
            continue
        parts.append(f"\n=== {path} ===\n{content}")
        budget -= len(content)
    return "\n".join(parts)


def implementation_prompt(brief: str, repo: str, instruction: str, feedback: list[str]) -> str:
    """Consigne de réalisation, partagée avec les cas de référence (evaluation.py)."""
    prompt = f"{brief}\n\n{repo}\n\nTa mission : {instruction}"
    if feedback:
        prompt += "\n\nÀ corriger d'abord :\n" + "\n".join(f"- {f}" for f in feedback)
    return prompt


def run_tests(deps: Deps, ws: Workspace, label: str) -> RunResult:
    """Installe les dépendances (réseau ouvert) puis lance tous les tests (sans réseau)."""
    config = ws.config()
    if not config.test:
        return RunResult("", 1, f"Aucune commande de test : déclarer « test » dans {CONFIG_FILE}.")
    image = config.image or deps.sandbox_image
    if config.install:
        installed = deps.sandbox.run(ws.path, config.install, image=image, network=True, label=label)
        if not installed.ok:
            return RunResult(config.install, installed.exit_code, "Installation : " + installed.output)
    return deps.sandbox.run(ws.path, config.test, image=image, network=False, label=label)


def _tail(text: str, lines: int = 40) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


def execution_graph(deps: Deps):
    def workspace(state: WorkState) -> Workspace:
        return Workspace(
            deps.git_dir, uuid.UUID(state["project_id"]), uuid.UUID(state["task_id"]), state["branch"]
        )

    def still_due(session: Session, a: Assignment) -> Task | None:
        # La tâche a pu changer pendant le travail (décision humaine) : ne rien publier alors.
        task = session.get(Task, a.task_id)
        return task if task is not None and assignment_for(task) == a else None

    def ask(state: WorkState, casquette: Casquette, question: str) -> WorkState:
        with deps.sessions() as session:
            task = still_due(session, Assignment.from_state(state))
            if task is None:
                return {"outcome": "obsolete"}
            actor = Actor.agent(casquette)
            execute(session, task, Command.ASK_HUMAN, actor, comment=question, ai_model=task.ai_model)
            add_message(
                session, task, kind=MessageKind.QUESTION, author=actor, ai_model=task.ai_model, body=question
            )
            session.commit()
        return {"outcome": "question"}

    def propose(state: WorkState, casquette: Casquette, instruction: str) -> "Implementation":
        prompt = implementation_prompt(
            state["brief"], repo_context(workspace(state)), instruction, state.get("feedback", [])
        )
        return ask_model(
            deps,
            Implementation,
            casquette=casquette,
            ai_model=state["ai_model"],
            system=system_prompt(casquette),
            prompt=prompt,
            task_id=state["task_id"],
        )

    def write(state: WorkState, ws: Workspace, answer: Implementation) -> list[str]:
        """Écrit les fichiers proposés. Ceux de memoire/ sont ignorés : la mémoire ne change
        qu'après validation humaine. Renvoie la liste des fichiers ignorés jusqu'ici."""
        ignored = list(state.get("ignored", []))
        for edit in answer.edits:
            path = safe_path(edit.path)
            if PurePosixPath(path).parts[0] == memory.MEMORY_DIR:
                ignored += [path] if path not in ignored else []
            elif edit.content is None:
                ws.delete(path)
            else:
                ws.write(path, edit.content)
        return ignored

    def contribute(
        state: WorkState,
        author: Casquette,
        reviewer: Casquette,
        schema: type[BaseModel],
        prompt: str,
        check: Callable[[BaseModel], list[str]],
    ) -> tuple[BaseModel, list[str]]:
        """Brouillon → définition de « terminé » → relecture par une autre casquette, 3 fois au plus.
        Renvoie la proposition et les points non résolus (l'humain tranchera)."""
        draft: BaseModel | None = None
        feedback: list[str] = []
        for _ in range(MAX_ROUNDS):
            text = prompt
            if draft is not None:
                text += (
                    f"\n\nTa proposition précédente :\n{draft.model_dump_json()}\n\nCorrige-la :\n"
                    + "\n".join(f"- {f}" for f in feedback)
                )
            draft = ask_model(
                deps,
                schema,
                casquette=author,
                ai_model=state["ai_model"],
                system=system_prompt(author),
                prompt=text,
                task_id=state["task_id"],
            )
            feedback = [f"Définition de « terminé » : {p}" for p in check(draft)]
            if feedback:
                continue
            verdict = ask_model(
                deps,
                Review,
                casquette=reviewer,
                ai_model=state["ai_model"],
                system=system_prompt(reviewer),
                prompt=review_prompt(state["brief"], author, draft.model_dump(mode="json")),
                task_id=state["task_id"],
            )
            if verdict.approved:
                return draft, []
            feedback = [
                f"Relecture ({LABELS[reviewer]}) : {c}"
                for c in verdict.corrections or ["Proposition refusée sans motif précis."]
            ]
        return draft, feedback

    def memory_items(state: WorkState, document: MemoryDocument) -> list[dict]:
        with deps.sessions() as session:
            return memory.items_of(session, uuid.UUID(state["project_id"]), document)

    def notes(label: str, draft: BaseModel) -> list[str]:
        said = [*draft.uncertainties, *draft.assumptions]  # type: ignore[attr-defined]
        return [f"{label} : {n}" for n in said]

    def proposed(change: MemoryChange, before: list[dict]) -> tuple[list[dict], list[str]]:
        """Vérifie que la mise à jour s'applique à la mémoire actuelle avant de la proposer."""
        if not change.upserts and not change.removals:
            return [], []
        try:
            memory.apply_change(before, change)
        except MemoryContentError as exc:
            return [], [f"Mémoire : {exc}"]
        return [change.model_dump(mode="json")], []

    # Nœuds

    def setup(state: WorkState) -> WorkState:
        a = Assignment.from_state(state)
        activity.report(deps.sessions, a.task_id, Casquette.ORCHESTRATEUR, "prépare la branche de la tâche")
        with deps.sessions() as session:
            task = session.get(Task, a.task_id)
            if task.branch is None:
                task.branch = branch_name(task.code)
                session.commit()
            branch, project_id = task.branch, str(task.project_id)
        ws = Workspace(deps.git_dir, uuid.UUID(project_id), a.task_id, branch)
        ws.ensure()
        return {
            "project_id": project_id,
            "branch": branch,
            "reproduced": a.task_type is not TaskType.BUGFIX or ws.has_commit(REPRO_MARKER),
            "drafts": 0,
            "attempts": 0,
            "feedback": [],
            "open_points": [],
            "qa": None,
            "ignored": [],
            "proposed_requirements": [],
            "memory": [],
            "memory_points": [],
            "memory_notes": [],
        }

    def reproduce(state: WorkState) -> WorkState:
        a = Assignment.from_state(state)
        activity.report(deps.sessions, a.task_id, Casquette.DEBOGUEUR, "écrit le test qui reproduit le bug")
        answer = propose(state, Casquette.DEBOGUEUR, REPRODUCE)
        if answer.question:
            return ask(state, Casquette.DEBOGUEUR, answer.question)
        attempts = state["attempts"] + 1
        problem = "Aucun test écrit."
        if answer.edits:
            ws = workspace(state)
            ignored = write(state, ws, answer)
            run = run_tests(deps, ws, a.code.lower())
            if not run.ok:
                ws.commit(f"{a.code} : test qui reproduit le bug, en échec avant correction {REPRO_MARKER}")
                return {"attempts": attempts, "feedback": [], "reproduced": True, "ignored": ignored}
            problem = "Le test passe : il ne reproduit pas le bug."
        if attempts >= MAX_ROUNDS:
            return ask(
                state,
                Casquette.DEBOGUEUR,
                f"Je n'arrive pas à écrire un test qui reproduit le bug ({attempts} essais). "
                "Peux-tu préciser les étapes ou les données qui le déclenchent ?",
            )
        return {"attempts": attempts, "feedback": [problem]}

    def implement(state: WorkState) -> WorkState:
        a = Assignment.from_state(state)
        step = "écrit la documentation" if a.task_type is TaskType.DOC else "écrit le code"
        activity.report(deps.sessions, a.task_id, a.author, step)
        answer = propose(state, a.author, IMPLEMENT[a.task_type] + ESCAPES)
        if answer.question:
            return ask(state, a.author, answer.question)
        if answer.new_plan:
            return replan(state, answer.new_plan)
        drafts = state["drafts"] + 1
        if not answer.edits:
            if drafts >= MAX_ROUNDS:
                return ask(
                    state,
                    a.author,
                    "Je ne trouve rien à modifier pour réaliser le plan : que faut-il changer ?",
                )
            return {
                "drafts": drafts,
                "feedback": ["Aucun fichier modifié : le plan validé n'est pas réalisé."],
            }
        ignored = write(state, workspace(state), answer)
        return {"drafts": drafts, "feedback": [], "message": answer.message, "ignored": ignored}

    def replan(state: WorkState, plan: PlanDraft) -> WorkState:
        # Écart au plan validé : l'agent s'arrête et redemande une validation (règle produit).
        a = Assignment.from_state(state)
        with deps.sessions() as session:
            task = still_due(session, a)
            if task is None:
                return {"outcome": "obsolete"}
            payload = plan.model_dump(exclude={"message"})
            if a.task_type is not TaskType.BUGFIX:
                payload["failing_test"] = None
            propose_plan(
                session,
                task,
                Actor.agent(a.author),
                body=plan.message,
                payload=payload,
                ai_model=task.ai_model,
                referentiel_version=referentiel(a.author).version,
            )
            session.commit()
        return {"outcome": "plan_change"}

    def code_review(state: WorkState) -> WorkState:
        a = Assignment.from_state(state)
        activity.report(deps.sessions, a.task_id, a.reviewer, "relit le changement")
        prompt = (
            f"{state['brief']}\n\nDiff de la branche par rapport à main :\n{workspace(state).diff()[:60_000]}"
            f"\n\nRelis ce changement du {LABELS[a.author]} avec ton référentiel, au regard du plan validé. "
            "Approuve-le s'il peut partir en tests ; sinon, liste des corrections précises."
        )
        verdict = ask_model(
            deps,
            Review,
            casquette=a.reviewer,
            ai_model=state["ai_model"],
            system=system_prompt(a.reviewer),
            prompt=prompt,
            task_id=a.task_id,
        )
        if verdict.approved:
            return {"feedback": [], "open_points": []}
        points = [
            f"Relecture ({LABELS[a.reviewer]}) : {c}" for c in verdict.corrections or ["Changement refusé."]
        ]
        if state["drafts"] < MAX_ROUNDS:
            return {"feedback": points, "open_points": points}
        return {"feedback": [], "open_points": points}  # l'humain tranchera : points en avertissement

    def qa(state: WorkState) -> WorkState:
        a = Assignment.from_state(state)
        activity.report(
            deps.sessions, a.task_id, Casquette.ANALYSTE_TEST, "lance les tests dans le bac à sable"
        )
        ws = workspace(state)
        if a.task_type is TaskType.DOC and not ws.config().test:
            return {"feedback": [], "qa": None}
        run = run_tests(deps, ws, a.code.lower())
        if run.ok:
            return {"feedback": [], "qa": run.command}
        with deps.sessions() as session:
            task = still_due(session, a)
            if task is None:
                return {"outcome": "obsolete"}
            actor = Actor.agent(Casquette.ANALYSTE_TEST)
            execute(session, task, Command.RECORD_QA_FAILURE, actor, ai_model=task.ai_model)
            trial = f"essai {task.qa_round_trips} sur {MAX_QA_ROUND_TRIPS}"
            body = f"Les tests échouent ({trial}) :\n{_tail(run.output, 15)}"
            add_message(
                session, task, kind=MessageKind.MESSAGE, author=actor, ai_model=task.ai_model, body=body
            )
            escalated = task.awaiting_human
            session.commit()
        if escalated:
            return {"outcome": "escalated"}
        return {"feedback": [f"Les tests échouent dans le bac à sable :\n{_tail(run.output)}"], "drafts": 0}

    def requirements(state: WorkState) -> WorkState:
        """Feature : le Business Analyst met à jour les exigences ; l'Analyste de test relit."""
        a = Assignment.from_state(state)
        activity.report(deps.sessions, a.task_id, Casquette.BUSINESS_ANALYST, "met à jour les exigences")
        before = memory_items(state, MemoryDocument.EXIGENCES)
        draft, points = contribute(
            state,
            Casquette.BUSINESS_ANALYST,
            Casquette.ANALYSTE_TEST,
            RequirementsDraft,
            requirements_prompt(state["brief"], memory.next_id(before, "EX")),
            lambda d: check_requirements(d, a.task_type),
        )
        known = {r["id"] for r in before}
        change = MemoryChange(
            document=MemoryDocument.EXIGENCES,
            upserts=[r.model_dump() for r in draft.requirements],
            removals=[key for key in draft.removed if key in known],
        )
        changes, problems = proposed(change, before)
        return {
            "proposed_requirements": [r.model_dump() for r in draft.requirements],
            "memory": changes,
            "memory_points": points + problems,
            "memory_notes": notes("Exigences", draft),
        }

    def scenarios(state: WorkState) -> WorkState:
        """Feature ou Bugfix : l'Analyste de test écrit les scénarios ; le Business Analyst relit."""
        a = Assignment.from_state(state)
        activity.report(deps.sessions, a.task_id, Casquette.ANALYSTE_TEST, "écrit les scénarios de test")
        before = memory_items(state, MemoryDocument.SCENARIOS)
        proposed_requirements = state.get("proposed_requirements", [])
        known = {r["id"] for r in memory_items(state, MemoryDocument.EXIGENCES)} | {
            r["id"] for r in proposed_requirements
        }
        to_cover = {r["id"] for r in proposed_requirements}
        draft, points = contribute(
            state,
            Casquette.ANALYSTE_TEST,
            Casquette.BUSINESS_ANALYST,
            ScenariosDraft,
            scenarios_prompt(
                state["brief"], a.task_type, proposed_requirements, memory.next_id(before, "SC")
            ),
            lambda d: check_scenarios(d, a.task_type, known, to_cover),
        )
        change = MemoryChange(
            document=MemoryDocument.SCENARIOS, upserts=[s.model_dump() for s in draft.scenarios]
        )
        changes, problems = proposed(change, before)
        return {
            "memory": state.get("memory", []) + changes,
            "memory_points": state.get("memory_points", []) + points + problems,
            "memory_notes": state.get("memory_notes", []) + notes("Scénarios", draft),
        }

    def submit(state: WorkState) -> WorkState:
        a = Assignment.from_state(state)
        activity.report(deps.sessions, a.task_id, Casquette.ORCHESTRATEUR, "prépare le livrable")
        ws = workspace(state)
        with deps.sessions() as session:
            task = still_due(session, a)
            if task is None:
                return {"outcome": "obsolete"}
            ws.commit(f"{task.code} : {task.title}")
            points = state.get("open_points", [])
            checks = [
                Check(
                    label="Tests du projet", ok=True, value="Passent" if state.get("qa") else "Aucun déclaré"
                ),
                Check(
                    label="Relecture du code",
                    ok=not points,
                    value=f"{len(points)} point(s) ouvert(s)" if points else "Approuvée",
                ),
                Check(label="Écart avec le plan validé", ok=True, value="Aucun"),
                Check(
                    label="Allers-retours QA",
                    ok=True,
                    value=f"{task.qa_round_trips} sur {MAX_QA_ROUND_TRIPS}",
                ),
            ]
            if a.task_type is TaskType.BUGFIX:
                checks.insert(
                    0, Check(label="Test qui reproduisait le bug", ok=True, value="Échouait, passe")
                )
            changes = [MemoryChange.model_validate(c) for c in state.get("memory", [])]
            memory_points = state.get("memory_points", [])
            if a.task_type is not TaskType.DOC:
                value = memory_summary(changes)
                if memory_points:
                    value += f", {len(memory_points)} point(s) ouvert(s)"
                checks.append(Check(label="Mémoire du projet", ok=not memory_points, value=value))
            warnings = points + memory_points
            if state.get("ignored"):
                warnings.append(
                    "Fichiers de memoire/ ignorés : la mémoire ne change qu'après ta validation. "
                    + ", ".join(state["ignored"])
                )
            execute(session, task, Command.SUBMIT_FOR_REVIEW, Actor.agent(Casquette.ORCHESTRATEUR))
            add_message(
                session,
                task,
                kind=MessageKind.RESULT,
                author=Actor.agent(a.author),
                ai_model=task.ai_model,
                body=state.get("message") or "C'est fait, conforme au plan validé.",
                payload={
                    "files": [f.model_dump() for f in ws.changes()],
                    "checks": [c.model_dump() for c in checks],
                    "note": f"Branche {ws.branch} prête ; fusion dans main après ta validation.",
                    "tests": f"Commande de test : {state['qa']}" if state.get("qa") else None,
                    "warnings": warnings,
                    "uncertainties": state.get("memory_notes", []),
                    "unverified": [
                        "Scénarios : pas encore exécutés sur Chrome, Firefox, iOS et Android.",
                        "Tests E2E Playwright : pas encore automatisés.",
                    ],
                    "memory": [c.model_dump(mode="json") for c in changes],
                },
            )
            session.commit()
        return {"outcome": "published"}

    # Aiguillages : une issue (question, nouveau plan, remontée, tâche changée) arrête le graphe.

    def after_setup(state: WorkState) -> str:
        return "implement" if state["reproduced"] else "reproduce"

    def after_reproduce(state: WorkState) -> str:
        if state.get("outcome"):
            return END
        return "implement" if state["reproduced"] else "reproduce"

    def after_implement(state: WorkState) -> str:
        if state.get("outcome"):
            return END
        return "implement" if state["feedback"] else "code_review"

    def after_review(state: WorkState) -> str:
        return "implement" if state["feedback"] else "qa"

    def after_qa(state: WorkState) -> str:
        if state.get("outcome"):
            return END
        if state["feedback"]:
            return "implement"
        task_type = Assignment.from_state(state).task_type
        return {TaskType.FEATURE: "requirements", TaskType.BUGFIX: "scenarios"}.get(task_type, "submit")

    graph = StateGraph(WorkState)
    for node in (setup, reproduce, implement, code_review, qa, requirements, scenarios, submit):
        graph.add_node(node.__name__, node)
    graph.add_edge(START, "setup")
    graph.add_conditional_edges("setup", after_setup, ["reproduce", "implement"])
    graph.add_conditional_edges("reproduce", after_reproduce, ["reproduce", "implement", END])
    graph.add_conditional_edges("implement", after_implement, ["implement", "code_review", END])
    graph.add_conditional_edges("code_review", after_review, ["implement", "qa"])
    graph.add_conditional_edges("qa", after_qa, ["implement", "requirements", "scenarios", "submit", END])
    graph.add_edge("requirements", "scenarios")
    graph.add_edge("scenarios", "submit")
    graph.add_edge("submit", END)
    return graph.compile(name="execution")
