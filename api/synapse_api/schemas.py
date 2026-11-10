import uuid
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from synapse_api.domain.enums import (
    AI_MODELS,
    DEFAULT_AI_MODEL,
    EvaluationStatus,
    MessageKind,
    TaskStatus,
    TaskType,
)
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


class BugTextIn(BaseModel):
    """Bug décrit en langage naturel : une casquette le reformule, son auteur valide."""

    text: str = Field(max_length=20_000)
    ai_model: str = DEFAULT_AI_MODEL

    _check_model = field_validator("ai_model")(known_model)

    @field_validator("text")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Décris le bug.")
        return value.strip()


class ReformulatedReport(BugReport):
    """Signalement proposé par une casquette à partir du texte de l'auteur."""

    title: str = Field(min_length=1, max_length=300)


class ActivityOut(BaseModel):
    """Ce qu'une casquette fait en ce moment sur la tâche (indicateur de travail)."""

    model_config = ConfigDict(from_attributes=True)

    casquette: str
    step: str
    started_at: datetime
    updated_at: datetime
    error: str | None
    retry_at: datetime | None


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
    created_by: str  # sujet OIDC de l'auteur : lui seul valide la reformulation de son bug
    report_required: bool
    report_version: int
    validated_report_version: int
    rejected_report_version: int
    pending_decision: PendingDecision | None
    activity: ActivityOut | None
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
    report: ReformulatedReport | None = None  # reformulation d'un bug (message REPORT)
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


# Consommation des modèles IA (section 11, coûts).


class UsageLine(BaseModel):
    """Consommation regroupée par modèle, par casquette ou par projet."""

    key: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    unpriced_calls: int  # appels dont la passerelle ne connaissait pas le prix


class ProjectUsageOut(BaseModel):
    project_id: uuid.UUID
    project_name: str
    month: str  # « 2026-11 »
    cost_usd: float
    budget_usd: float | None  # quota du mois ; vide : pas de quota
    budget_is_default: bool  # quota de l'espace, pas fixé pour ce projet
    by_model: list[UsageLine]
    by_casquette: list[UsageLine]


class ProjectBudgetRow(BaseModel):
    project_id: uuid.UUID
    project_name: str
    calls: int
    cost_usd: float
    budget_usd: float | None
    budget_is_default: bool


class WorkspaceUsageOut(BaseModel):
    month: str
    cost_usd: float
    default_budget_usd: float | None
    projects: list[ProjectBudgetRow]
    by_model: list[UsageLine]
    evaluations: UsageLine  # rejeu des cas de référence, hors projets


class BudgetIn(BaseModel):
    # Vide : le projet revient au quota par défaut de l'espace.
    monthly_budget_usd: float | None = Field(default=None, ge=0, le=1_000_000)


# Cas de référence des casquettes (section 3, section 11).


class EvaluationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    casquette: str
    ai_model: str
    served_model: str | None
    referentiel_version: str
    status: EvaluationStatus
    total: int
    passed: int
    regressed_cases: list[str]
    error: str | None
    started_at: datetime
    finished_at: datetime | None
    cost_usd: float = 0


class EvaluationResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    case_id: str
    title: str
    passed: bool
    failures: list[str]
    answer: dict | None


class EvaluationRunDetailOut(EvaluationRunOut):
    results: list[EvaluationResultOut]
    history: list[EvaluationRunOut]  # rejeux précédents, même casquette et même modèle
