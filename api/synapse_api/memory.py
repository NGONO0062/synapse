"""Mémoire du projet (section 7) : tout ce que l'humain a validé, en six documents.

    Exigences · Maquettes · Architecture · Scénarios · Tests E2E · Décisions

- Seul ce qui est validé entre dans la mémoire :
  · une décision, quand le PO répond à la question d'une casquette (datée, avec son auteur) ;
  · les mises à jour proposées avec le livrable d'une tâche (exigences du Business Analyst,
    scénarios de l'Analyste de test), quand la tâche passe en Done : le PO les a validées
    avec le résultat.
- Chaque version garde le document entier (table memory_versions). L'orchestrateur l'écrit
  ensuite dans le dépôt du projet, dossier `memoire/`, sur main (worker.write_memory).
- Les casquettes relisent la mémoire avant chaque travail : elle est dans leur dossier
  (jobs.brief), jamais modifiable par elles. Un fichier de `memoire/` écrit par un agent est
  ignoré.
"""

import io
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from synapse_api.db.models import MemoryVersion, Task, TaskEvent, TaskMessage
from synapse_api.domain.enums import SCENARIO_COLUMNS, MemoryDocument, MessageKind, ScenarioPlatformStatus
from synapse_api.domain.lifecycle import AwaitingReason, Command
from synapse_api.domain.rules import MAX_QA_ROUND_TRIPS

MEMORY_DIR = "memoire"
AGENT_BUDGET = 40_000  # caractères de mémoire remis à une casquette avec son dossier

LABELS = {
    MemoryDocument.EXIGENCES: "Exigences",
    MemoryDocument.MAQUETTES: "Maquettes",
    MemoryDocument.ARCHITECTURE: "Architecture",
    MemoryDocument.SCENARIOS: "Scénarios",
    MemoryDocument.TESTS_E2E: "Tests E2E",
    MemoryDocument.DECISIONS: "Décisions",
}
FILES = {
    MemoryDocument.EXIGENCES: "exigences.md",
    MemoryDocument.MAQUETTES: "maquettes.md",
    MemoryDocument.ARCHITECTURE: "architecture.md",
    MemoryDocument.SCENARIOS: "scenarios.md",
    MemoryDocument.TESTS_E2E: "tests-e2e.md",
    MemoryDocument.DECISIONS: "decisions.md",
}
# Unité comptée sur la carte du document (« 24 exigences »).
UNITS = {
    MemoryDocument.EXIGENCES: ("exigence", "exigences"),
    MemoryDocument.MAQUETTES: ("écran", "écrans"),
    MemoryDocument.ARCHITECTURE: ("section", "sections"),
    MemoryDocument.SCENARIOS: ("scénario", "scénarios"),
    MemoryDocument.TESTS_E2E: ("parcours critique", "parcours critiques"),
    MemoryDocument.DECISIONS: ("décision", "décisions"),
}


def count_label(document: MemoryDocument, count: int) -> str:
    one, many = UNITS[document]
    return f"{count} {one if count <= 1 else many}"


# Contenu des documents : une liste d'éléments, chacun repéré par une clé.


class Requirement(BaseModel):
    id: str = Field(pattern=r"^EX-\d{3,}$", description="Identifiant stable : EX-001, EX-002…")
    module: str = Field(min_length=1, max_length=120, description="Partie de l'application concernée.")
    title: str = Field(min_length=1, max_length=200)
    statement: str = Field(min_length=1, description="La règle : qui, quoi et pourquoi.")
    acceptance: list[str] = Field(description="Critères d'acceptation, un par ligne, chacun testable.")


class Screen(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    journey: str = Field(default="", description="Parcours dont l'écran fait partie.")
    description: str = ""


class ArchitectureSection(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = ""


class ScenarioRow(BaseModel):
    """Une ligne du modèle Excel des scénarios, telle que l'Analyste de test la propose."""

    id: str = Field(pattern=r"^SC-\d{3,}$", description="Identifiant stable : SC-001, SC-002…")
    module: str = Field(min_length=1, max_length=120)
    scenario: str = Field(min_length=1, description="Ce qui est testé, en une phrase.")
    preconditions: str = Field(default="", description="État nécessaire avant de commencer.")
    steps: str = Field(min_length=1, description="Actions numérotées, une par ligne.")
    expected: str = Field(min_length=1, description="Ce qui doit se produire si l'application fonctionne.")
    requirements: list[str] = Field(default=[], description="Exigences couvertes (EX-…).")


class Scenario(ScenarioRow):
    """Ligne de la mémoire : avec le statut d'exécution par plateforme."""

    chrome: ScenarioPlatformStatus = ScenarioPlatformStatus.NOT_STARTED
    firefox: ScenarioPlatformStatus = ScenarioPlatformStatus.NOT_STARTED
    ios: ScenarioPlatformStatus = ScenarioPlatformStatus.NOT_STARTED
    android: ScenarioPlatformStatus = ScenarioPlatformStatus.NOT_STARTED


PLATFORMS = ("chrome", "firefox", "ios", "android")


class E2ETest(BaseModel):
    journey: str = Field(min_length=1, max_length=200, description="Parcours critique automatisé.")
    justification: str = Field(default="", description="Pourquoi ce parcours, par le risque.")
    file: str | None = None


class Decision(BaseModel):
    date: datetime
    question: str
    answer: str
    author: str  # le PO qui a répondu
    task: str | None = None  # code de la tâche (FEAT-003)
    casquette: str | None = None  # casquette qui a posé la question


ITEM_SCHEMAS: dict[MemoryDocument, type[BaseModel]] = {
    MemoryDocument.EXIGENCES: Requirement,
    MemoryDocument.MAQUETTES: Screen,
    MemoryDocument.ARCHITECTURE: ArchitectureSection,
    MemoryDocument.SCENARIOS: Scenario,
    MemoryDocument.TESTS_E2E: E2ETest,
    MemoryDocument.DECISIONS: Decision,
}
KEYS = {
    MemoryDocument.EXIGENCES: "id",
    MemoryDocument.MAQUETTES: "name",
    MemoryDocument.ARCHITECTURE: "title",
    MemoryDocument.SCENARIOS: "id",
    MemoryDocument.TESTS_E2E: "journey",
}
# Documents que les casquettes peuvent proposer de mettre à jour avec un livrable. Les décisions
# viennent seulement des réponses du PO.
PROPOSABLE = tuple(KEYS)


class MemoryChange(BaseModel):
    """Mise à jour d'un document proposée avec un livrable ; versée au Done de la tâche."""

    document: MemoryDocument
    upserts: list[dict[str, Any]] = Field(default=[], description="Éléments ajoutés ou remplacés (même clé).")
    removals: list[str] = Field(default=[], description="Clés des éléments retirés.")
    summary: str = ""


class MemoryContentError(ValueError):
    pass


def _validated(document: MemoryDocument, items: list[dict]) -> list[dict]:
    schema = ITEM_SCHEMAS[document]
    try:
        return [schema.model_validate(item).model_dump(mode="json") for item in items]
    except ValidationError as exc:
        reason = exc.errors()[0]["msg"]
        raise MemoryContentError(f"{LABELS[document]} : contenu invalide ({reason}).") from exc


def apply_change(items: list[dict], change: MemoryChange) -> list[dict]:
    """Nouveau contenu du document : éléments remplacés à leur place, nouveaux à la fin, retirés ôtés.

    Un scénario nouveau ou modifié repart à « Not started » sur les quatre plateformes ; un
    scénario repris à l'identique garde ses statuts. Une casquette ne fixe jamais un statut."""
    if change.document not in KEYS:
        raise MemoryContentError(f"{LABELS[change.document]} : document non modifiable par un livrable.")
    key = KEYS[change.document]
    result = [dict(item) for item in items]
    index = {item[key]: i for i, item in enumerate(result)}
    for raw in change.upserts:
        item = dict(raw)
        if change.document is MemoryDocument.SCENARIOS:
            item = _scenario_statuses(item, result[index[item.get(key)]] if item.get(key) in index else None)
        [item] = _validated(change.document, [item])
        if item[key] in index:
            result[index[item[key]]] = item
        else:
            index[item[key]] = len(result)
            result.append(item)
    removed = set(change.removals)
    return [item for item in result if item[key] not in removed]


def _scenario_statuses(item: dict, before: dict | None) -> dict:
    row = {k: v for k, v in item.items() if k not in PLATFORMS}
    if before is not None:
        try:
            unchanged = ScenarioRow.model_validate(row) == ScenarioRow.model_validate(before)
        except ValidationError:
            unchanged = False  # la ligne proposée est invalide : _validated le dira
        if unchanged:
            return row | {p: before.get(p, ScenarioPlatformStatus.NOT_STARTED) for p in PLATFORMS}
    return row | {p: ScenarioPlatformStatus.NOT_STARTED for p in PLATFORMS}


def describe_change(document: MemoryDocument, before: list[dict], after: list[dict]) -> str:
    """« 2 exigences ajoutées, 1 modifiée » : ce que la version change, pour l'historique."""
    key = KEYS[document]
    old = {item[key]: item for item in before}
    new = {item[key]: item for item in after}
    added = sum(1 for k in new if k not in old)
    changed = sum(1 for k in new if k in old and new[k] != old[k])
    removed = sum(1 for k in old if k not in new)
    one, many = UNITS[document]
    parts = []
    for n, verb in ((added, "ajouté"), (changed, "modifié"), (removed, "retiré")):
        if n:
            agreement = "e" if document in (MemoryDocument.EXIGENCES, MemoryDocument.ARCHITECTURE) else ""
            noun = one if n == 1 else many
            parts.append(f"{n} {noun} {verb}{agreement}{'' if n == 1 else 's'}")
    return ", ".join(parts) or "Aucun changement."


# Lecture.


def latest(session: Session, project_id: uuid.UUID, document: MemoryDocument) -> MemoryVersion | None:
    query = (
        select(MemoryVersion)
        .where(MemoryVersion.project_id == project_id, MemoryVersion.document == document)
        .order_by(MemoryVersion.version.desc())
        .limit(1)
    )
    return session.scalar(query)


def current(session: Session, project_id: uuid.UUID) -> dict[MemoryDocument, MemoryVersion | None]:
    return {document: latest(session, project_id, document) for document in MemoryDocument}


def history(session: Session, project_id: uuid.UUID, document: MemoryDocument) -> list[MemoryVersion]:
    query = (
        select(MemoryVersion)
        .where(MemoryVersion.project_id == project_id, MemoryVersion.document == document)
        .order_by(MemoryVersion.version.desc())
    )
    return list(session.scalars(query))


def next_id(items: list[dict], prefix: str) -> str:
    """Prochain identifiant libre (EX-007, SC-012), donné à la casquette qui en crée."""
    numbers = [
        int(item["id"].split("-", 1)[1]) for item in items if str(item.get("id", "")).startswith(f"{prefix}-")
    ]
    return f"{prefix}-{max(numbers, default=0) + 1:03d}"


def items_of(session: Session, project_id: uuid.UUID, document: MemoryDocument) -> list[dict]:
    version = latest(session, project_id, document)
    return list(version.items) if version else []


# Écriture : toujours une version complète, validée par un humain.


def add_version(
    session: Session,
    project_id: uuid.UUID,
    document: MemoryDocument,
    items: list[dict],
    *,
    summary: str,
    validated_by: str,
    source_task_id: uuid.UUID | None = None,
    at: datetime | None = None,
) -> MemoryVersion:
    last = session.scalar(
        select(func.max(MemoryVersion.version)).where(
            MemoryVersion.project_id == project_id, MemoryVersion.document == document
        )
    )
    version = MemoryVersion(
        project_id=project_id,
        document=document,
        version=(last or 0) + 1,
        items=_validated(document, items),
        summary=summary,
        validated_by=validated_by,
        source_task_id=source_task_id,
        validated_at=at or datetime.now(UTC),
    )
    session.add(version)
    session.flush()
    return version


ESCALATION_QUESTIONS = {
    AwaitingReason.QA_LIMIT: (
        f"Les tests échouent encore après {MAX_QA_ROUND_TRIPS} allers-retours : que faire ?"
    ),
    AwaitingReason.TIMEOUT: "L'exécution a dépassé la durée maximale : que faire ?",
}


def record_decision(
    session: Session, task: Task, reason: AwaitingReason | None, *, answer: str, author: str, at: datetime
) -> MemoryVersion:
    """Le PO a répondu à une casquette : sa réponse rejoint les décisions du projet, datée."""
    question, casquette = ESCALATION_QUESTIONS.get(reason, ""), None  # type: ignore[arg-type]
    if reason is AwaitingReason.QUESTION:
        asked = session.scalar(
            select(TaskMessage)
            .where(TaskMessage.task_id == task.id, TaskMessage.kind == MessageKind.QUESTION)
            .order_by(TaskMessage.created_at.desc())
            .limit(1)
        )
        if asked is not None:
            question, casquette = asked.body, asked.casquette
    decision = Decision(
        date=at, question=question or "Question de la casquette", answer=answer, author=author,
        task=task.code, casquette=casquette,
    )  # fmt: skip
    items = items_of(session, task.project_id, MemoryDocument.DECISIONS)
    return add_version(
        session,
        task.project_id,
        MemoryDocument.DECISIONS,
        [*items, decision.model_dump(mode="json")],
        summary=f"Réponse du PO sur {task.code}",
        validated_by=author,
        source_task_id=task.id,
        at=at,
    )


def proposed_changes(task: Task) -> list[MemoryChange]:
    """Mises à jour de la mémoire portées par le dernier résultat de la tâche."""
    result = next((m for m in reversed(task.messages) if m.kind is MessageKind.RESULT), None)
    if result is None or not result.payload:
        return []
    return [MemoryChange.model_validate(c) for c in result.payload.get("memory") or []]


def pour(session: Session, task: Task, at: datetime) -> list[MemoryVersion]:
    """Tâche en Done : les mises à jour validées avec son résultat sont versées dans la mémoire."""
    validated = session.scalar(
        select(TaskEvent)
        .where(TaskEvent.task_id == task.id, TaskEvent.command == Command.VALIDATE_RESULT)
        .order_by(TaskEvent.created_at.desc())
        .limit(1)
    )
    by = validated.actor_name if validated else "PO"
    versions = []
    for change in proposed_changes(task):
        before = items_of(session, task.project_id, change.document)
        items = apply_change(before, change)
        if items == before:
            continue  # repris à l'identique : pas de nouvelle version
        summary = change.summary.strip() or describe_change(change.document, before, items)
        versions.append(
            add_version(
                session,
                task.project_id,
                change.document,
                items,
                summary=f"{task.code} : {summary}",
                validated_by=by,
                source_task_id=task.id,
                at=at,
            )
        )
    return versions


# Rendu : Markdown pour le dépôt et pour les casquettes, Excel pour les scénarios.


def _date(value: datetime | str) -> str:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.strftime("%d/%m/%Y")


def render_items(document: MemoryDocument, items: list[dict]) -> str:
    blocks: list[str] = []
    for item in items:
        if document is MemoryDocument.EXIGENCES:
            criteria = "\n".join(f"- {c}" for c in item["acceptance"])
            blocks.append(
                f"## {item['id']} · {item['title']}\n\nModule : {item['module']}\n\n{item['statement']}"
                f"\n\nCritères d'acceptation :\n{criteria}"
            )
        elif document is MemoryDocument.MAQUETTES:
            journey = f"Parcours : {item['journey']}\n\n" if item.get("journey") else ""
            blocks.append(f"## {item['name']}\n\n{journey}{item.get('description', '')}".rstrip())
        elif document is MemoryDocument.ARCHITECTURE:
            blocks.append(f"## {item['title']}\n\n{item.get('body', '')}".rstrip())
        elif document is MemoryDocument.SCENARIOS:
            platforms = zip(SCENARIO_COLUMNS[5:], PLATFORMS, strict=True)
            statuses = " · ".join(f"{column} : {item[p]}" for column, p in platforms)
            covered = ", ".join(item.get("requirements") or [])
            covers = f"\nExigences couvertes : {covered}" if covered else ""
            blocks.append(
                f"## {item['id']} · {item['module']} · {item['scenario']}\n\n"
                f"Préconditions : {item.get('preconditions') or '—'}\n\nÉtapes :\n{item['steps']}\n\n"
                f"Résultat attendu : {item['expected']}{covers}\n\n{statuses}"
            )
        elif document is MemoryDocument.TESTS_E2E:
            file = f"\n\nFichier : `{item['file']}`" if item.get("file") else ""
            blocks.append(f"## {item['journey']}\n\n{item.get('justification', '')}{file}".rstrip())
        else:
            where = f" ({item['task']})" if item.get("task") else ""
            blocks.append(
                f"## {_date(item['date'])} · {item['author']}{where}\n\n"
                f"Question : {item['question']}\n\nRéponse : {item['answer']}"
            )
    return "\n\n".join(blocks)


def render_markdown(version: MemoryVersion) -> str:
    """Fichier `memoire/<document>.md` du dépôt."""
    head = (
        f"# {LABELS[version.document]}\n\n"
        f"Version {version.version}, validée le {_date(version.validated_at)} par {version.validated_by}. "
        "Fichier écrit par Synapse : il change par une tâche validée, pas à la main.\n"
    )
    body = render_items(version.document, list(version.items))
    return f"{head}\n{body}\n" if body else head


def for_agents(session: Session, project_id: uuid.UUID, budget: int = AGENT_BUDGET) -> str:
    """Mémoire remise aux casquettes avec leur dossier. Vide si le projet n'a encore rien validé."""
    parts: list[str] = []
    left = budget
    for document, version in current(session, project_id).items():
        if version is None or not version.items:
            continue
        text = f"### {LABELS[document]} (version {version.version})\n\n" + render_items(
            document, list(version.items)
        )
        if len(text) > left:
            text = text[: max(left, 0)].rsplit("\n", 1)[0] + (
                f"\n\n(… {LABELS[document]} tronqué : la mémoire dépasse ce qui peut être remis en une fois.)"
            )
        parts.append(text)
        left -= len(text)
        if left <= 0:
            break
    return "\n\n".join(parts)


def scenarios_xlsx(items: list[dict], project_name: str) -> bytes:
    """Modèle Excel des scénarios (section 12) : les colonnes dans l'ordre imposé."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    from openpyxl.worksheet.datavalidation import DataValidation

    book = Workbook()
    sheet = book.active
    sheet.title = "Scénarios"
    sheet.append(list(SCENARIO_COLUMNS))
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for item in items:
        sheet.append(
            [
                item["module"],
                item["scenario"],
                item.get("preconditions", ""),
                item["steps"],
                item["expected"],
                *(item[p] for p in PLATFORMS),
            ]
        )
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for column, width in zip("ABCDEFGHI", (18, 36, 30, 40, 36, 13, 13, 13, 13), strict=True):
        sheet.column_dimensions[column].width = width
    statuses = ",".join(s.value for s in ScenarioPlatformStatus)
    validation = DataValidation(type="list", formula1=f'"{statuses}"', allow_blank=False)
    sheet.add_data_validation(validation)
    validation.add(f"F2:I{max(len(items) + 1, 2) + 500}")
    sheet.freeze_panes = "A2"
    book.properties.title = f"Scénarios · {project_name}"
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()
