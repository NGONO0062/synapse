"""project memory

Revision ID: 8d41e6b0a2f7
Revises: 3c7a91d2e4b5
Create Date: 2026-11-10 16:00:00.000000

Lot 4a : mémoire du projet. Chaque version validée d'un des six documents (exigences, maquettes,
architecture, scénarios, tests E2E, décisions), avec la tâche d'origine, l'humain qui l'a validée
et le commit qui l'a écrite dans le dépôt du projet.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8d41e6b0a2f7"
down_revision: str | None = "3c7a91d2e4b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memory_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column(
            "document",
            sa.Enum(
                "EXIGENCES",
                "MAQUETTES",
                "ARCHITECTURE",
                "SCENARIOS",
                "TESTS_E2E",
                "DECISIONS",
                name="ck_memory_versions_document",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source_task_id", sa.Uuid(), nullable=True),
        sa.Column("validated_by", sa.String(length=255), nullable=False),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("commit", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_memory_versions_project_id_projects")),
        sa.ForeignKeyConstraint(["source_task_id"], ["tasks.id"], name=op.f("fk_memory_versions_source_task_id_tasks")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memory_versions")),
        sa.UniqueConstraint(
            "project_id", "document", "version", name=op.f("uq_memory_versions_project_id_document_version")
        ),
    )
    op.create_index(op.f("ix_memory_versions_project_id"), "memory_versions", ["project_id"])


def downgrade() -> None:
    op.drop_table("memory_versions")
