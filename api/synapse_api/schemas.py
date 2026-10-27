import uuid
from datetime import datetime
from enum import StrEnum

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


class TaskIn(BaseModel):
    type: TaskType
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=20_000)
    ai_model: str = DEFAULT_AI_MODEL

    @field_validator("ai_model")
    @classmethod
    def known_model(cls, value: str) -> str:
        if value not in AI_MODELS:
            raise ValueError(f"Modèle inconnu. Modèles disponibles : {', '.join(AI_MODELS)}.")
        return value


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


class ProposalPayload(BaseModel):
    """Contenu d'un plan ou d'un résultat. Chaque proposition dit ce dont l'agent
    n'est pas sûr, ce qu'il a supposé et ce qu'il n'a pas pu vérifier (section 1)."""

    changes: list[str] = []
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
