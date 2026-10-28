"""task activity

Revision ID: 6f2ac4387cc9
Revises: 5e9cf904612b
Create Date: 2026-10-28 12:55:00.000000

Ce qu'une casquette fait en ce moment sur une tâche (indicateur de travail dans l'interface),
et son dernier échec. Table à part pour ne pas toucher au verrou de version de la tâche.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6f2ac4387cc9"
down_revision: str | None = "5e9cf904612b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_activities",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("casquette", sa.String(length=32), nullable=False),
        sa.Column("step", sa.String(length=200), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], name=op.f("fk_task_activities_task_id_tasks")),
        sa.PrimaryKeyConstraint("task_id", name=op.f("pk_task_activities")),
    )


def downgrade() -> None:
    op.drop_table("task_activities")
