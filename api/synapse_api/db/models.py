import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from synapse_api.domain.enums import (
    DEFAULT_AI_MODEL,
    EvaluationStatus,
    MessageKind,
    TaskStatus,
    TaskType,
)
from synapse_api.domain.lifecycle import (
    ActorKind,
    AwaitingReason,
    Command,
    PendingDecision,
    TaskState,
    pending_decision,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def _enum(enum_cls: type, check_name: str) -> Enum:
    # Stocké en texte contrôlé par CHECK : portable et sans type natif à migrer.
    # Le nom est explicite car Alembic ne passe pas les enums par la convention de nommage.
    return Enum(
        enum_cls,
        name=check_name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
    )


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(column_0_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Quota mensuel de consommation IA (dollars), fixé par l'administrateur. Vide : le quota
    # par défaut de l'espace (SYNAPSE_PROJECT_MONTHLY_BUDGET_USD), ou aucun.
    monthly_budget_usd: Mapped[float | None] = mapped_column(Numeric(10, 2, asdecimal=False), nullable=True)

    tasks: Mapped[list["Task"]] = relationship(back_populates="project")


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (UniqueConstraint("project_id", "type", "number"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    type: Mapped[TaskType] = mapped_column(_enum(TaskType, "ck_tasks_type"))
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(255), index=True)
    # Modèle IA choisi dans la barre de saisie ; la casquette, elle, est choisie par l'orchestrateur.
    ai_model: Mapped[str] = mapped_column(String(100), default=DEFAULT_AI_MODEL)
    # Signalement structuré d'un Bugfix (écran 6), voir schemas.BugReport. Pour un bug écrit
    # en langage naturel, il est rempli quand l'auteur valide la reformulation.
    bug_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # État du cycle de vie, miroir de domain.lifecycle.TaskState.
    status: Mapped[TaskStatus] = mapped_column(
        _enum(TaskStatus, "ck_tasks_status"), default=TaskStatus.BACKLOG
    )
    report_required: Mapped[bool] = mapped_column(Boolean, default=False)
    report_version: Mapped[int] = mapped_column(Integer, default=0)
    validated_report_version: Mapped[int] = mapped_column(Integer, default=0)
    rejected_report_version: Mapped[int] = mapped_column(Integer, default=0)
    plan_version: Mapped[int] = mapped_column(Integer, default=0)
    validated_plan_version: Mapped[int] = mapped_column(Integer, default=0)
    rejected_plan_version: Mapped[int] = mapped_column(Integer, default=0)
    awaiting_human: Mapped[bool] = mapped_column(Boolean, default=False)
    awaiting_reason: Mapped[AwaitingReason | None] = mapped_column(
        _enum(AwaitingReason, "ck_tasks_awaiting_reason"), nullable=True
    )
    qa_round_trips: Mapped[int] = mapped_column(Integer, default=0)
    execution_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_validated: Mapped[bool] = mapped_column(Boolean, default=False)
    tester_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Branche Git où les casquettes travaillent (synapse/feat-001), et commit de sa fusion
    # dans main, faite seulement quand la tâche est en Done.
    branch: Mapped[str | None] = mapped_column(String(100), nullable=True)
    merged_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    # Verrou optimiste : deux décisions concurrentes sur la même tâche ne s'écrasent pas.
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    project: Mapped[Project] = relationship(back_populates="tasks")
    events: Mapped[list["TaskEvent"]] = relationship(back_populates="task", order_by="TaskEvent.created_at")
    messages: Mapped[list["TaskMessage"]] = relationship(
        back_populates="task", order_by="TaskMessage.created_at"
    )
    activity: Mapped["TaskActivity | None"] = relationship(back_populates="task", lazy="selectin")

    __mapper_args__ = {"version_id_col": row_version}

    @property
    def code(self) -> str:
        return f"{self.type.prefix}-{self.number:03d}"

    def lifecycle_state(self) -> TaskState:
        started = self.execution_started_at
        if started is not None and started.tzinfo is None:
            started = started.replace(tzinfo=UTC)  # SQLite perd le fuseau
        return TaskState(
            type=self.type,
            status=self.status,
            report_required=self.report_required,
            report_version=self.report_version,
            validated_report_version=self.validated_report_version,
            rejected_report_version=self.rejected_report_version,
            plan_version=self.plan_version,
            validated_plan_version=self.validated_plan_version,
            rejected_plan_version=self.rejected_plan_version,
            awaiting_human=self.awaiting_human,
            awaiting_reason=self.awaiting_reason,
            qa_round_trips=self.qa_round_trips,
            execution_started_at=started,
            result_validated=self.result_validated,
            tester_confirmed=self.tester_confirmed,
        )

    @property
    def pending_decision(self) -> PendingDecision | None:
        return pending_decision(self.lifecycle_state())


class TaskEvent(Base):
    """Journal de traçabilité : chaque proposition et chaque décision (section 11)."""

    __tablename__ = "task_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"), index=True)
    command: Mapped[Command] = mapped_column(_enum(Command, "ck_task_events_command"))
    actor_kind: Mapped[ActorKind] = mapped_column(_enum(ActorKind, "ck_task_events_actor_kind"))
    actor_name: Mapped[str] = mapped_column(String(255))
    actor_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    casquette: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ai_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    referentiel_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    from_status: Mapped[TaskStatus] = mapped_column(_enum(TaskStatus, "ck_task_events_from_status"))
    to_status: Mapped[TaskStatus] = mapped_column(_enum(TaskStatus, "ck_task_events_to_status"))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    task: Mapped[Task] = relationship(back_populates="events")


class TaskMessage(Base):
    """Fil de la tâche : messages humains, réponses et propositions des casquettes."""

    __tablename__ = "task_messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"), index=True)
    kind: Mapped[MessageKind] = mapped_column(_enum(MessageKind, "ck_task_messages_kind"))
    author_kind: Mapped[ActorKind] = mapped_column(_enum(ActorKind, "ck_task_messages_author_kind"))
    author_name: Mapped[str] = mapped_column(String(255))
    author_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    casquette: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ai_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    body: Mapped[str] = mapped_column(Text, default="")
    # Contenu structuré d'une proposition (plan ou résultat), voir schemas.ProposalPayload.
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Version du plan (PLAN) ou de la reformulation (REPORT) que porte le message.
    plan_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    task: Mapped[Task] = relationship(back_populates="messages")


class TaskActivity(Base):
    """Ce qu'une casquette fait en ce moment sur la tâche, écrit par l'orchestrateur.

    Table à part : la tâche porte un verrou de version, et l'activité change sans cesse
    pendant que l'humain peut décider."""

    __tablename__ = "task_activities"

    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"), primary_key=True)
    casquette: Mapped[str] = mapped_column(String(32))
    step: Mapped[str] = mapped_column(String(200))  # « rédige le plan », « lance les tests »…
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    # Dernier échec (modèle injoignable, clé absente…) et heure du prochain essai.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped[Task] = relationship(back_populates="activity")


class ModelUsage(Base):
    """Un appel à un modèle par la passerelle : qui l'a fait, pour quoi, et combien il a coûté
    (section 11, coûts). Écrit par l'orchestrateur, jamais modifié."""

    __tablename__ = "model_usages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Un appel sert un projet (travail sur une tâche) ou une évaluation (cas de référence).
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    evaluation_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evaluation_runs.id"), nullable=True, index=True
    )
    casquette: Mapped[str] = mapped_column(String(32))
    ai_model: Mapped[str] = mapped_column(String(100))  # nom dans la passerelle (claude-sonnet…)
    served_model: Mapped[str | None] = mapped_column(String(200), nullable=True)  # modèle réel derrière
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    # Prix de la passerelle au moment de l'appel ; vide si elle ne le connaît pas.
    cost_usd: Mapped[float | None] = mapped_column(Numeric(14, 6, asdecimal=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class EvaluationRun(Base):
    """Rejeu des cas de référence d'une casquette avec un modèle (section 3, section 11).

    L'empreinte couvre le modèle réel derrière le nom de la passerelle, les consignes
    (référentiel compris) et les cas : dès que l'un change, les cas sont rejoués."""

    __tablename__ = "evaluation_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    casquette: Mapped[str] = mapped_column(String(32), index=True)
    ai_model: Mapped[str] = mapped_column(String(100))
    served_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    referentiel_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[EvaluationStatus] = mapped_column(
        _enum(EvaluationStatus, "ck_evaluation_runs_status"), default=EvaluationStatus.RUNNING
    )
    total: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    # Cas réussis au rejeu précédent (même casquette, même modèle) et échoués à celui-ci.
    regressed_cases: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    results: Mapped[list["EvaluationResult"]] = relationship(
        back_populates="run", order_by="EvaluationResult.case_id"
    )

    @property
    def regressed(self) -> bool:
        return bool(self.regressed_cases)


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evaluation_runs.id"), index=True)
    case_id: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(300))
    passed: Mapped[bool] = mapped_column(Boolean)
    failures: Mapped[list] = mapped_column(JSON, default=list)  # attentes non tenues, en clair
    answer: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # réponse du modèle

    run: Mapped[EvaluationRun] = relationship(back_populates="results")
