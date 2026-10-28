"""Simulateur d'agent, pour le développement uniquement, en attendant l'orchestrateur (lot 3).

Joue le rôle d'une casquette sur une tâche : propose un plan, pose une question, livre
un résultat ou signale un échec QA. Passe par les mêmes services que l'orchestrateur,
donc par les mêmes règles du cycle de vie. Les messages sont marqués « [Simulation] ».

    python -m synapse_api.dev.simulate FEAT-001 plan
    python -m synapse_api.dev.simulate BUG-002 result --project "Gestion des congés"
"""

import argparse
import sys

from sqlalchemy import String, cast, select
from sqlalchemy.orm import Session

from synapse_api.db.models import Project, Task
from synapse_api.db.session import _session_factory
from synapse_api.domain.enums import Casquette, MessageKind, TaskType
from synapse_api.domain.lifecycle import Actor, Command, LifecycleError
from synapse_api.services import add_message, execute

PLANNERS = {
    TaskType.FEATURE: Casquette.ARCHITECTE,
    TaskType.BUGFIX: Casquette.DEBOGUEUR,
    TaskType.DOC: Casquette.REDACTEUR,
}
MAKERS = {
    TaskType.FEATURE: Casquette.DEVELOPPEUR,
    TaskType.BUGFIX: Casquette.DEBOGUEUR,
    TaskType.DOC: Casquette.REDACTEUR,
}
TAG = "[Simulation] "


def find_task(session: Session, code: str, project: str | None) -> Task:
    prefix, _, number = code.upper().partition("-")
    task_type = next((t for t in TaskType if t.prefix == prefix), None)
    if task_type is None or not number.isdigit():
        sys.exit(f"Code de tâche invalide : {code}")
    query = select(Task).join(Project).where(Task.type == task_type, Task.number == int(number))
    if project:
        query = query.where((Project.name == project) | (cast(Project.id, String) == project))
    tasks = list(session.scalars(query))
    if not tasks:
        sys.exit(f"Aucune tâche {code}.")
    if len(tasks) > 1:
        names = ", ".join(sorted(t.project.name for t in tasks))
        sys.exit(f"{code} existe dans plusieurs projets ({names}) : préciser --project.")
    return tasks[0]


def plan(session: Session, task: Task) -> None:
    actor = Actor.agent(PLANNERS[task.type])
    execute(session, task, Command.PROPOSE_PLAN, actor, ai_model=task.ai_model)
    add_message(
        session,
        task,
        kind=MessageKind.PLAN,
        author=actor,
        ai_model=task.ai_model,
        plan_version=task.plan_version,
        body=TAG + "Voici le plan. Rien ne sera fait tant que tu ne l’as pas validé.",
        payload={
            "changes": [
                f"+ Mise en œuvre de « {task.title} »",
                "~ Adaptation de l’écran concerné",
                "~ Mise à jour de la documentation utilisateur",
            ],
            "warnings": ["Plan généré par le simulateur : aucune analyse réelle du dépôt."],
            "failing_test": "✕ le scénario du testeur échoue" if task.type is TaskType.BUGFIX else None,
            "tests": "3 tests prévus : 1 E2E, 1 API, 1 unitaire",
            "uncertainties": ["Volume de données en production inconnu."],
            "assumptions": ["Les droits existants suffisent."],
            "unverified": ["Compatibilité mobile."],
        },
    )


def question(session: Session, task: Task) -> None:
    actor = Actor.agent(MAKERS[task.type])
    body = TAG + "Une règle reste à trancher : le comportement attendu en cas de données incomplètes ?"
    execute(session, task, Command.ASK_HUMAN, actor, comment=body, ai_model=task.ai_model)
    add_message(session, task, kind=MessageKind.QUESTION, author=actor, ai_model=task.ai_model, body=body)


def result(session: Session, task: Task) -> None:
    actor = Actor.agent(MAKERS[task.type])
    execute(session, task, Command.SUBMIT_FOR_REVIEW, Actor.agent(Casquette.ORCHESTRATEUR))
    add_message(
        session,
        task,
        kind=MessageKind.RESULT,
        author=actor,
        ai_model=task.ai_model,
        body=TAG + "C’est fait, conforme au plan validé. Les changements sont dans le livrable.",
        payload={
            "changes": [],
            "warnings": [],
            "files": [
                {
                    "path": "services/calcul.ts",
                    "additions": 1,
                    "deletions": 2,
                    "diff": [
                        "  export function calcul(valeurs) {",
                        "-   const retenues = valeurs.slice(0, 5);",
                        "-   return somme(retenues);",
                        "+   return somme(valeurs);",
                        "  }",
                    ],
                },
                {
                    "path": "tests/calcul.spec.ts",
                    "additions": 18,
                    "deletions": 0,
                    "note": "Nouveau test : scénario de la demande, plus cas limites.",
                },
            ],
            "checks": [
                {"label": "Test de la demande", "ok": True, "value": "Passe"},
                {"label": "Non-régression", "ok": True, "value": "Passe"},
                {"label": "E2E parcours critique", "ok": True, "value": "Passe"},
                {"label": "Écart avec le plan validé", "ok": True, "value": "Aucun"},
            ],
            "note": "Résultat simulé : aucun code exécuté. Branche prête, fusion après ta validation.",
            "unverified": ["Aucune exécution réelle : résultat simulé."],
        },
    )


def qa_failure(session: Session, task: Task) -> None:
    actor = Actor.agent(Casquette.ANALYSTE_TEST)
    execute(session, task, Command.RECORD_QA_FAILURE, actor, ai_model=task.ai_model)
    add_message(
        session,
        task,
        kind=MessageKind.MESSAGE,
        author=actor,
        ai_model=task.ai_model,
        body=TAG + f"Un scénario échoue ; retour au développement (essai {task.qa_round_trips}).",
    )


ACTIONS = {"plan": plan, "question": question, "result": result, "qa-failure": qa_failure}


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("code", help="code de la tâche, ex. FEAT-001")
    parser.add_argument("action", choices=ACTIONS)
    parser.add_argument("--project", help="nom ou identifiant du projet si le code est ambigu")
    args = parser.parse_args()

    with _session_factory()() as session:
        task = find_task(session, args.code, args.project)
        try:
            ACTIONS[args.action](session, task)
        except LifecycleError as exc:
            sys.exit(f"Refusé par le cycle de vie : {exc.message}")
        session.commit()
        print(f"{task.code} · {task.status} · décision attendue : {task.pending_decision or 'aucune'}")


if __name__ == "__main__":
    main()
