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
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from synapse_api.domain.enums import DEFAULT_AI_MODEL, MessageKind, TaskStatus, TaskType
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
    # Signalement structuré d'un Bugfix (écran 6), voir schemas.BugReport.
    bug_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # État du cycle de vie, miroir de domain.lifecycle.TaskState.
    status: Mapped[TaskStatus] = mapped_column(
        _enum(TaskStatus, "ck_tasks_status"), default=TaskStatus.BACKLOG
    )
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

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    # Verrou optimiste : deux décisions concurrentes sur la même tâche ne s'écrasent pas.
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    project: Mapped[Project] = relationship(back_populates="tasks")
    events: Mapped[list["TaskEvent"]] = relationship(back_populates="task", order_by="TaskEvent.created_at")
    messages: Mapped[list["TaskMessage"]] = relationship(
        back_populates="task", order_by="TaskMessage.created_at"
    )

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
    plan_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    task: Mapped[Task] = relationship(back_populates="messages")
