"""usage and evaluations

Revision ID: 3c7a91d2e4b5
Revises: 6f2ac4387cc9
Create Date: 2026-11-10 10:00:00.000000

Lot 3c : consommation des modèles IA par appel (projet, tâche, casquette, modèle, jetons, coût),
quota mensuel par projet, et rejeux des cas de référence des casquettes avec leurs résultats.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3c7a91d2e4b5"
down_revision: str | None = "6f2ac4387cc9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("monthly_budget_usd", sa.Numeric(precision=10, scale=2), nullable=True))

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("casquette", sa.String(length=32), nullable=False),
        sa.Column("ai_model", sa.String(length=100), nullable=False),
        sa.Column("served_model", sa.String(length=200), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("referentiel_version", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "RUNNING",
                "DONE",
                "ERROR",
                name="ck_evaluation_runs_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("passed", sa.Integer(), nullable=False),
        sa.Column("regressed_cases", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_runs")),
    )
    op.create_index(op.f("ix_evaluation_runs_casquette"), "evaluation_runs", ["casquette"])
    op.create_index(op.f("ix_evaluation_runs_fingerprint"), "evaluation_runs", ["fingerprint"])

    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("failures", sa.JSON(), nullable=False),
        sa.Column("answer", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"], ["evaluation_runs.id"], name=op.f("fk_evaluation_results_run_id_evaluation_runs")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_results")),
    )
    op.create_index(op.f("ix_evaluation_results_run_id"), "evaluation_results", ["run_id"])

    op.create_table(
        "model_usages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("evaluation_run_id", sa.Uuid(), nullable=True),
        sa.Column("casquette", sa.String(length=32), nullable=False),
        sa.Column("ai_model", sa.String(length=100), nullable=False),
        sa.Column("served_model", sa.String(length=200), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=14, scale=6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["evaluation_run_id"],
            ["evaluation_runs.id"],
            name=op.f("fk_model_usages_evaluation_run_id_evaluation_runs"),
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_model_usages_project_id_projects")),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], name=op.f("fk_model_usages_task_id_tasks")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_usages")),
    )
    op.create_index(op.f("ix_model_usages_project_id"), "model_usages", ["project_id"])
    op.create_index(op.f("ix_model_usages_evaluation_run_id"), "model_usages", ["evaluation_run_id"])
    op.create_index(op.f("ix_model_usages_created_at"), "model_usages", ["created_at"])


def downgrade() -> None:
    op.drop_table("model_usages")
    op.drop_table("evaluation_results")
    op.drop_table("evaluation_runs")
    op.drop_column("projects", "monthly_budget_usd")
