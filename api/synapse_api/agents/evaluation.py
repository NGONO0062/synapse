"""Cas de référence des casquettes, rejoués automatiquement (section 3, section 11).

Chaque casquette a ses cas, versionnés dans `cas_reference/<casquette>.json` : un dossier
d'entrée et ce que la réponse doit tenir. Un cas passe par exactement la même consigne que le
travail réel (référentiel, mission, format de réponse) ; seule la réponse est vérifiée, rien
n'est publié ni exécuté.

Les cas sont rejoués dès que l'empreinte change : modèle réel derrière le nom de la
passerelle, consignes (référentiel compris), cas eux-mêmes. Un cas réussi au rejeu
précédent et échoué à celui-ci est une régression : seule elle alerte l'humain.

    python -m synapse_api.agents.evaluation                       # ce qui est dû
    python -m synapse_api.agents.evaluation --casquette debogueur --model gemini   # forcer
"""

import argparse
import hashlib
import json
import logging
from datetime import UTC, datetime
from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from synapse_api.agents.casquettes import LABELS, referentiel, system_prompt
from synapse_api.agents.execution import (
    ESCAPES,
    IMPLEMENT,
    REPRODUCE,
    Implementation,
    RequirementsDraft,
    ScenariosDraft,
    check_requirements,
    check_scenarios,
    implementation_prompt,
    requirements_prompt,
    scenarios_prompt,
)
from synapse_api.agents.gateway import GatewayError
from synapse_api.agents.graph import draft_prompt, review_prompt
from synapse_api.agents.jobs import JOBS, Job, PlanDraft, ReportDraft, Review
from synapse_api.agents.state import Deps
from synapse_api.agents.usage import ask_model
from synapse_api.config import get_settings
from synapse_api.db.models import EvaluationResult, EvaluationRun, Task
from synapse_api.domain.enums import DEFAULT_AI_MODEL, Casquette, EvaluationStatus, TaskType

CASES_DIR = Path(__file__).parent / "cas_reference"
log = logging.getLogger("synapse.evaluation")


class CaseKind(StrEnum):
    REPORT = "REPORT"  # reformuler un bug écrit en langage naturel
    PLAN = "PLAN"  # proposer un plan
    REVIEW = "REVIEW"  # relire la proposition d'une autre casquette
    IMPLEMENT = "IMPLEMENT"  # réaliser un plan validé (fichiers proposés, rien n'est exécuté)
    REPRODUCE = "REPRODUCE"  # écrire le test qui reproduit un bug
    REQUIREMENTS = "REQUIREMENTS"  # mettre à jour les exigences de la mémoire (Business Analyst)
    SCENARIOS = "SCENARIOS"  # écrire les scénarios de test à partir des exigences (Analyste de test)


SCHEMAS: dict[CaseKind, type[BaseModel]] = {
    CaseKind.REPORT: ReportDraft,
    CaseKind.PLAN: PlanDraft,
    CaseKind.REVIEW: Review,
    CaseKind.IMPLEMENT: Implementation,
    CaseKind.REPRODUCE: Implementation,
    CaseKind.REQUIREMENTS: RequirementsDraft,
    CaseKind.SCENARIOS: ScenariosDraft,
}
DONE_KINDS = {CaseKind.REPORT, CaseKind.PLAN, CaseKind.REQUIREMENTS, CaseKind.SCENARIOS}


class Expect(BaseModel):
    """Ce que la réponse doit tenir. Chaque attente non tenue devient une raison d'échec."""

    done: bool = Field(default=False, description="La définition de « terminé » de la casquette passe.")
    values: dict[str, list[Any]] = Field(default={}, description="Champ → valeurs acceptées.")
    mentions: dict[str, list[str]] = Field(default={}, description="Champ → un de ces mots au moins.")
    approved: bool | None = None  # relecture : approuvée ou non
    writes: list[str] = Field(default=[], description="Fichiers que la réponse doit écrire.")
    asks: bool | None = None  # réalisation : pose une question au lieu d'écrire
    min_items: dict[str, int] = Field(default={}, description="Champ liste → nombre minimal d'éléments.")


class Case(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    title: str
    kind: CaseKind
    task_type: TaskType
    brief: str  # dossier remis à la casquette, comme jobs.brief() le compose
    author: Casquette | None = None  # relecture : casquette qui a rédigé la proposition
    proposal: dict[str, Any] | None = None  # relecture : la proposition à relire
    repo: str = ""  # réalisation : le dépôt tel que repo_context() le montre
    # Scénarios : exigences de la tâche à couvrir ; exigences et scénarios : prochain identifiant libre.
    requirements: list[dict[str, Any]] = []
    next_id: str | None = None
    expect: Expect

    @model_validator(mode="after")
    def _complete(self) -> "Case":
        if self.kind is CaseKind.REVIEW and (self.author is None or self.proposal is None):
            raise ValueError(f"{self.id} : une relecture précise l'auteur et la proposition.")
        if self.expect.done and self.kind not in DONE_KINDS:
            raise ValueError(f"{self.id} : « done » ne vaut pas pour une relecture.")
        return self

    @property
    def schema(self) -> type[BaseModel]:
        return SCHEMAS[self.kind]

    def prompt(self) -> str:
        """La consigne du travail réel, appliquée au dossier du cas."""
        if self.kind is CaseKind.REPORT:
            return draft_prompt(self.brief, Job.REPORT, self.task_type)
        if self.kind is CaseKind.PLAN:
            return draft_prompt(self.brief, Job.PLAN, self.task_type)
        if self.kind is CaseKind.REVIEW:
            return review_prompt(self.brief, self.author, self.proposal)
        if self.kind is CaseKind.REQUIREMENTS:
            return requirements_prompt(self.brief, self.next_id or "EX-001")
        if self.kind is CaseKind.SCENARIOS:
            return scenarios_prompt(self.brief, self.task_type, self.requirements, self.next_id or "SC-001")
        instruction = REPRODUCE if self.kind is CaseKind.REPRODUCE else IMPLEMENT[self.task_type] + ESCAPES
        return implementation_prompt(self.brief, self.repo or "(dépôt vide)", instruction, [])


class CaseFile(BaseModel):
    casquette: Casquette
    cases: list[Case] = Field(min_length=1)


@cache
def all_cases() -> dict[Casquette, tuple[Case, ...]]:
    found: dict[Casquette, tuple[Case, ...]] = {}
    for path in sorted(CASES_DIR.glob("*.json")):
        data = CaseFile.model_validate_json(path.read_text(encoding="utf-8"))
        if path.stem != data.casquette.value.lower():
            raise ValueError(f"{path.name} : le fichier porte le nom de sa casquette.")
        found[data.casquette] = tuple(data.cases)
    return found


def cases_of(casquette: Casquette) -> tuple[Case, ...]:
    return all_cases().get(casquette, ())


# Vérification d'une réponse.


def _lookup(data: Any, path: str) -> Any:
    for part in path.split("."):
        data = data.get(part) if isinstance(data, dict) else None
    return data


def _text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def done_problems(case: Case, answer: BaseModel) -> list[str]:
    """La définition de « terminé » du travail réel, appliquée à la réponse du cas."""
    if case.kind is CaseKind.REQUIREMENTS:
        return check_requirements(answer, case.task_type)  # type: ignore[arg-type]
    if case.kind is CaseKind.SCENARIOS:
        to_cover = {r["id"] for r in case.requirements if "id" in r}
        return check_scenarios(answer, case.task_type, None, to_cover)  # type: ignore[arg-type]
    job = Job.REPORT if case.kind is CaseKind.REPORT else Job.PLAN
    return JOBS[job].check(answer, case.task_type)


def judge(case: Case, answer: BaseModel) -> list[str]:
    """Attentes non tenues par la réponse, en clair ; vide si le cas passe."""
    data = answer.model_dump(mode="json")
    expect = case.expect
    failures: list[str] = []
    if expect.done:
        failures += [f"Définition de « terminé » : {p}" for p in done_problems(case, answer)]
    for path, minimum in expect.min_items.items():
        value = _lookup(data, path)
        found = len(value) if isinstance(value, list) else 0
        if found < minimum:
            failures.append(f"{path} : {found} élément(s), {minimum} au moins attendu(s).")
    for path, accepted in expect.values.items():
        value = _lookup(data, path)
        if value not in accepted:
            wanted = " ou ".join(f"« {v} »" for v in accepted)
            failures.append(f"{path} vaut « {value} », attendu {wanted}.")
    for path, words in expect.mentions.items():
        text = _text(_lookup(data, path) or "").casefold()
        if not any(word.casefold() in text for word in words):
            failures.append(f"{path} ne parle pas de : {', '.join(words)}.")
    if expect.approved is not None and data.get("approved") is not expect.approved:
        failures.append(
            "Proposition approuvée à tort." if data.get("approved") else "Proposition refusée à tort."
        )
    if case.kind in (CaseKind.IMPLEMENT, CaseKind.REPRODUCE):
        written = {e["path"] for e in data.get("edits", []) if e.get("content") is not None}
        failures += [f"Le fichier {path} n'est pas écrit." for path in expect.writes if path not in written]
        asked = bool((data.get("question") or "").strip())
        if expect.asks is not None and asked is not expect.asks:
            failures.append(
                "Question posée au lieu de réaliser."
                if asked
                else "Aucune question posée alors qu'une règle manque."
            )
    return failures


# Empreinte : ce qui, en changeant, oblige à rejouer les cas.


def fingerprint(casquette: Casquette, served_model: str) -> str:
    cases = cases_of(casquette)
    material = {
        "model": served_model,
        "system": system_prompt(casquette),
        "cases": [
            {"prompt": c.prompt(), "schema": c.schema.model_json_schema(), "expect": c.expect.model_dump()}
            for c in cases
        ],
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Due(BaseModel):
    casquette: Casquette
    ai_model: str
    served_model: str
    fingerprint: str


def models_in_use(session: Session) -> list[str]:
    used = set(session.scalars(select(Task.ai_model).distinct()))
    return sorted(used | {DEFAULT_AI_MODEL})


def due_evaluations(deps: Deps) -> list[Due]:
    """Couples casquette × modèle en usage dont l'empreinte n'a pas encore de rejeu terminé."""
    catalog = deps.catalog()
    if not catalog:  # passerelle injoignable : ni le modèle réel ni l'appel ne sont possibles
        return []
    due = []
    with deps.sessions() as session:
        for ai_model in models_in_use(session):
            info = catalog.get(ai_model)
            if info is None:
                continue
            for casquette in all_cases():
                fp = fingerprint(casquette, info.served_model)
                done = select(EvaluationRun.id).where(
                    EvaluationRun.fingerprint == fp,
                    EvaluationRun.ai_model == ai_model,
                    EvaluationRun.status == EvaluationStatus.DONE,
                )
                if session.scalar(done.limit(1)) is None:
                    due.append(
                        Due(
                            casquette=casquette,
                            ai_model=ai_model,
                            served_model=info.served_model,
                            fingerprint=fp,
                        )
                    )
    return due


# Rejeu.


def previous_run(session: Session, run: EvaluationRun) -> EvaluationRun | None:
    query = (
        select(EvaluationRun)
        .where(
            EvaluationRun.casquette == run.casquette,
            EvaluationRun.ai_model == run.ai_model,
            EvaluationRun.status == EvaluationStatus.DONE,
            EvaluationRun.id != run.id,
        )
        .order_by(EvaluationRun.finished_at.desc())
        .limit(1)
    )
    return session.scalar(query)


def regressions(before: dict[str, bool], after: dict[str, bool]) -> list[str]:
    """Cas réussis avant et échoués maintenant (un cas nouveau ne régresse pas)."""
    return sorted(case for case, passed in after.items() if not passed and before.get(case))


def evaluate(
    deps: Deps, casquette: Casquette, ai_model: str, served_model: str | None = None
) -> EvaluationRun:
    """Rejoue tous les cas d'une casquette avec un modèle. Une passerelle injoignable arrête le
    rejeu (statut ERROR, il sera repris) ; un modèle qui ne sait pas répondre échoue le cas."""
    cases = cases_of(casquette)
    if served_model is None:
        info = (deps.catalog() or {}).get(ai_model)
        served_model = info.served_model if info else ai_model
    with deps.sessions() as session:
        run = EvaluationRun(
            casquette=casquette.value,
            ai_model=ai_model,
            served_model=served_model,
            fingerprint=fingerprint(casquette, served_model),
            referentiel_version=referentiel(casquette).version,
            total=len(cases),
            regressed_cases=[],
        )
        session.add(run)
        session.commit()
        run_id = run.id

    outcomes: dict[str, bool] = {}
    try:
        for case in cases:
            answer, failures = None, []
            try:
                answer = ask_model(
                    deps,
                    case.schema,
                    casquette=casquette,
                    ai_model=ai_model,
                    system=system_prompt(casquette),
                    prompt=case.prompt(),
                    evaluation_run_id=run_id,
                )
                failures = judge(case, answer)
            except GatewayError as exc:
                failures = [str(exc)]
            outcomes[case.id] = not failures
            with deps.sessions() as session:
                session.add(
                    EvaluationResult(
                        run_id=run_id,
                        case_id=case.id,
                        title=case.title,
                        passed=not failures,
                        failures=failures,
                        answer=answer.model_dump(mode="json") if answer else None,
                    )
                )
                session.commit()
    except Exception as exc:
        with deps.sessions() as session:
            run = session.get(EvaluationRun, run_id)
            run.status, run.error, run.finished_at = (
                EvaluationStatus.ERROR,
                str(exc)[:1000],
                datetime.now(UTC),
            )
            session.commit()
        raise

    with deps.sessions() as session:
        run = session.get(EvaluationRun, run_id)
        before = previous_run(session, run)
        previous = {r.case_id: r.passed for r in before.results} if before else {}
        run.passed = sum(outcomes.values())
        run.regressed_cases = regressions(previous, outcomes)
        run.status, run.finished_at = EvaluationStatus.DONE, datetime.now(UTC)
        session.commit()
        if run.regressed_cases:
            log.warning(
                "Régression : %s avec %s, cas %s",
                LABELS[casquette],
                ai_model,
                ", ".join(run.regressed_cases),
            )
        return run


def interrupted(deps: Deps) -> None:
    """Au démarrage du worker : un rejeu resté en cours a été coupé, il sera repris."""
    with deps.sessions() as session:
        session.execute(
            update(EvaluationRun)
            .where(EvaluationRun.status == EvaluationStatus.RUNNING)
            .values(status=EvaluationStatus.ERROR, error="Rejeu interrompu (arrêt de l'orchestrateur).")
        )
        session.commit()


def main() -> None:
    from synapse_api.agents.gateway import LiteLLMModel, gateway_catalog
    from synapse_api.db.session import _session_factory

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--casquette", help="rejouer cette casquette (ex. debogueur), même sans changement")
    parser.add_argument("--model", help="avec ce modèle de la passerelle (par défaut : celui des tâches)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    deps = Deps(sessions=_session_factory(), model=LiteLLMModel, catalog=gateway_catalog)

    if args.casquette:
        casquette = Casquette(args.casquette.upper())
        targets = [(casquette, args.model or get_settings().default_ai_model)]
    else:
        targets = [
            (d.casquette, d.ai_model)
            for d in due_evaluations(deps)
            if not args.model or d.ai_model == args.model
        ]
    if not targets:
        log.info("Aucun rejeu dû.")
    for casquette, ai_model in targets:
        run = evaluate(deps, casquette, ai_model)
        log.info("%s · %s : %d/%d cas réussis", LABELS[casquette], ai_model, run.passed, run.total)


if __name__ == "__main__":
    main()
