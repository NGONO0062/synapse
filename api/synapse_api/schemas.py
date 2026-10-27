import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from synapse_api.domain.enums import TaskStatus, TaskType
from synapse_api.domain.lifecycle import HUMAN_COMMANDS, ActorKind, AwaitingReason, Command

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


class TaskIn(BaseModel):
    type: TaskType
    title: str = Field(min_length=1, max_length=300)
    description: str = ""


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    code: str
    type: TaskType
    title: str
    description: str
    status: TaskStatus
    awaiting_human: bool
    awaiting_reason: AwaitingReason | None
    plan_version: int
    validated_plan_version: int
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


class MeOut(BaseModel):
    subject: str
    name: str
    email: str | None
    roles: list[str]
