"""Exécution d'une tâche en In progress, jusqu'au livrable en Review (lot 3b).

    préparer la branche → [Bugfix] test qui reproduit le bug (Débogueur, doit échouer)
        → réaliser (Développeur ou Rédacteur) → relecture du code → QA dans le bac à sable
        → livrable en Review

La réalisation peut aussi s'arrêter sur une question au PO ou sur un nouveau plan à valider.
Un échec QA repart en réalisation ; au 3e, la tâche remonte au PO (cycle de vie).
"""

import uuid
from pathlib import PurePosixPath

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from synapse_api.agents.casquettes import LABELS, referentiel, system_prompt
from synapse_api.agents.jobs import Assignment, PlanDraft, Review, assignment_for, branch_name
from synapse_api.agents.sandbox import CONFIG_FILE, RunResult, Workspace
from synapse_api.agents.state import Deps, WorkState
from synapse_api.db.models import Task
from synapse_api.domain.enums import Casquette, MessageKind, TaskType
from synapse_api.domain.lifecycle import Actor, Command
from synapse_api.domain.rules import MAX_QA_ROUND_TRIPS
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
        prompt = f"{state['brief']}\n\n{repo_context(workspace(state))}\n\nTa mission : {instruction}"
        if state.get("feedback"):
            prompt += "\n\nÀ corriger d'abord :\n" + "\n".join(f"- {f}" for f in state["feedback"])
        model = deps.model(state["ai_model"])
        return model.structured(Implementation, system=system_prompt(casquette), prompt=prompt)

    def write(ws: Workspace, answer: Implementation) -> None:
        for edit in answer.edits:
            if edit.content is None:
                ws.delete(edit.path)
            else:
                ws.write(edit.path, edit.content)

    # Nœuds

    def setup(state: WorkState) -> WorkState:
        a = Assignment.from_state(state)
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
        }

    def reproduce(state: WorkState) -> WorkState:
        a = Assignment.from_state(state)
        answer = propose(state, Casquette.DEBOGUEUR, REPRODUCE)
        if answer.question:
            return ask(state, Casquette.DEBOGUEUR, answer.question)
        attempts = state["attempts"] + 1
        problem = "Aucun test écrit."
        if answer.edits:
            ws = workspace(state)
            write(ws, answer)
            run = run_tests(deps, ws, a.code.lower())
            if not run.ok:
                ws.commit(f"{a.code} : test qui reproduit le bug, en échec avant correction {REPRO_MARKER}")
                return {"attempts": attempts, "feedback": [], "reproduced": True}
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
        write(workspace(state), answer)
        return {"drafts": drafts, "feedback": [], "message": answer.message}

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
        prompt = (
            f"{state['brief']}\n\nDiff de la branche par rapport à main :\n{workspace(state).diff()[:60_000]}"
            f"\n\nRelis ce changement du {LABELS[a.author]} avec ton référentiel, au regard du plan validé. "
            "Approuve-le s'il peut partir en tests ; sinon, liste des corrections précises."
        )
        verdict = deps.model(state["ai_model"]).structured(
            Review, system=system_prompt(a.reviewer), prompt=prompt
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

    def submit(state: WorkState) -> WorkState:
        a = Assignment.from_state(state)
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
                    "warnings": points,
                    "unverified": [
                        "Scénarios de l'Analyste de test et E2E Playwright : pas encore automatisés."
                    ],
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
        return "implement" if state["feedback"] else "submit"

    graph = StateGraph(WorkState)
    for node in (setup, reproduce, implement, code_review, qa, submit):
        graph.add_node(node.__name__, node)
    graph.add_edge(START, "setup")
    graph.add_conditional_edges("setup", after_setup, ["reproduce", "implement"])
    graph.add_conditional_edges("reproduce", after_reproduce, ["reproduce", "implement", END])
    graph.add_conditional_edges("implement", after_implement, ["implement", "code_review", END])
    graph.add_conditional_edges("code_review", after_review, ["implement", "qa"])
    graph.add_conditional_edges("qa", after_qa, ["implement", "submit", END])
    graph.add_edge("submit", END)
    return graph.compile(name="execution")
