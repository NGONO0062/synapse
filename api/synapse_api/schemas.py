import uuid
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from synapse_api.domain.enums import AI_MODELS, DEFAULT_AI_MODEL, MessageKind, TaskStatus, TaskType
from synapse_api.domain.lifecycle import (
    HUMAN_COMMANDS,
    ActorKind,
    AwaitingReason,
    Command,
    PendingDecision,
)

# Seules les décisions humaines passent par l'API ; les agents passent par l'orchestrateur.
HumanCommand = StrEnum("HumanCommand", {c.value: c.value for c in HUMAN_COMMANDS})


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    created_at: datetime


class ProjectSummaryOut(ProjectOut):
    status_counts: dict[TaskStatus, int]
    pending_decisions: int


def known_model(value: str) -> str:
    if value not in AI_MODELS:
        raise ValueError(f"Modèle inconnu. Modèles disponibles : {', '.join(AI_MODELS)}.")
    return value


class TaskIn(BaseModel):
    type: TaskType
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=20_000)
    ai_model: str = DEFAULT_AI_MODEL

    _check_model = field_validator("ai_model")(known_model)


class BugReport(BaseModel):
    """Formulaire de signalement du testeur (écran 6)."""

    environment: Literal["STAGING", "PREPROD"]
    device: str = Field(default="", max_length=200)
    steps: str = Field(min_length=1, max_length=10_000)
    expected: str = Field(min_length=1, max_length=5_000)
    actual: str = Field(min_length=1, max_length=5_000)
    severity: Literal["BLOQUANT", "MAJEUR", "MINEUR"] = "MAJEUR"


class BugIn(BugReport):
    title: str = Field(min_length=1, max_length=300)
    ai_model: str = DEFAULT_AI_MODEL

    _check_model = field_validator("ai_model")(known_model)


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    code: str
    type: TaskType
    title: str
    description: str
    status: TaskStatus
    ai_model: str
    bug_report: BugReport | None
    pending_decision: PendingDecision | None
    awaiting_human: bool
    awaiting_reason: AwaitingReason | None
    plan_version: int
    validated_plan_version: int
    rejected_plan_version: int
    qa_round_trips: int
    result_validated: bool
    tester_confirmed: bool
    created_at: datetime
    updated_at: datetime


class CommandIn(BaseModel):
    command: HumanCommand  # type: ignore[valid-type]
    comment: str | None = Field(default=None, max_length=10_000)


class TaskEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    command: Command
    actor_kind: ActorKind
    actor_name: str
    casquette: str | None
    ai_model: str | None
    from_status: TaskStatus
    to_status: TaskStatus
    comment: str | None
    created_at: datetime


class FileChange(BaseModel):
    path: str
    additions: int = 0
    deletions: int = 0
    diff: list[str] = []  # lignes préfixées par « + », « - » ou une espace
    note: str | None = None


class Check(BaseModel):
    label: str
    ok: bool
    value: str  # ex. « Passe », « Échoue », « Aucun »


class ProposalPayload(BaseModel):
    """Contenu d'un plan ou d'un résultat. Chaque proposition dit ce dont l'agent
    n'est pas sûr, ce qu'il a supposé et ce qu'il n'a pas pu vérifier (section 1).
    Un résultat peut porter un livrable consultable dans le panneau droit."""

    changes: list[str] = []
    failing_test: str | None = None  # Bugfix : le test qui reproduit le bug
    files: list[FileChange] = []
    checks: list[Check] = []
    note: str | None = None
    warnings: list[str] = []
    tests: str | None = None
    uncertainties: list[str] = []
    assumptions: list[str] = []
    unverified: list[str] = []


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=20_000)


class TaskMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: MessageKind
    author_kind: ActorKind
    author_name: str
    casquette: str | None
    ai_model: str | None
    body: str
    payload: ProposalPayload | None
    plan_version: int | None
    created_at: datetime


class DecisionOut(BaseModel):
    kind: PendingDecision
    task: TaskOut
    project_id: uuid.UUID
    project_name: str
    casquette: str | None  # casquette à l'origine de la proposition
    since: datetime


class MeOut(BaseModel):
    subject: str
    name: str
    email: str | None
    roles: list[str]
