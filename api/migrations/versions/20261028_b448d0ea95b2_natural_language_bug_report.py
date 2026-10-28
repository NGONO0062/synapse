"""natural language bug report

Revision ID: b448d0ea95b2
Revises: c0ec2b5379e4
Create Date: 2026-10-28 10:21:27.042715

Un bug écrit en langage naturel est reformulé par une casquette et validé par son auteur :
colonnes de suivi de la reformulation, nouvelles commandes et nouveau type de message.
Les énumérations sont des CHECK (voir db.models._enum), qu'Alembic ne compare pas.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b448d0ea95b2"
down_revision: str | None = "c0ec2b5379e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_COMMANDS = (
    "PRIORITIZE",
    "PROPOSE_PLAN",
    "REQUEST_PLAN_CHANGES",
    "VALIDATE_PLAN",
    "ASK_HUMAN",
    "ANSWER_HUMAN",
    "RECORD_QA_FAILURE",
    "ESCALATE_TIMEOUT",
    "SUBMIT_FOR_REVIEW",
    "VALIDATE_RESULT",
    "CONFIRM_FIX",
    "REJECT_RESULT",
)
NEW_COMMANDS = ("PROPOSE_REPORT", "REQUEST_REPORT_CHANGES", "VALIDATE_REPORT", *OLD_COMMANDS)
OLD_KINDS = ("MESSAGE", "PLAN", "RESULT", "QUESTION")
NEW_KINDS = (*OLD_KINDS, "REPORT")
REPORT_COLUMNS = ("report_version", "validated_report_version", "rejected_report_version")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _replace_checks(commands: tuple[str, ...], kinds: tuple[str, ...]) -> None:
    op.drop_constraint(op.f("ck_task_events_command"), "task_events", type_="check")
    op.create_check_constraint(op.f("ck_task_events_command"), "task_events", _in("command", commands))
    op.drop_constraint(op.f("ck_task_messages_kind"), "task_messages", type_="check")
    op.create_check_constraint(op.f("ck_task_messages_kind"), "task_messages", _in("kind", kinds))


def upgrade() -> None:
    op.add_column("tasks", sa.Column("report_required", sa.Boolean(), nullable=False, server_default=sa.false()))
    for column in REPORT_COLUMNS:
        op.add_column("tasks", sa.Column(column, sa.Integer(), nullable=False, server_default="0"))
    _replace_checks(NEW_COMMANDS, NEW_KINDS)


def downgrade() -> None:
    # Les reformulations n'existent pas dans le schéma précédent.
    op.execute(f"DELETE FROM task_events WHERE NOT ({_in('command', OLD_COMMANDS)})")
    op.execute(f"DELETE FROM task_messages WHERE NOT ({_in('kind', OLD_KINDS)})")
    _replace_checks(OLD_COMMANDS, OLD_KINDS)
    for column in ("report_required", *REPORT_COLUMNS):
        op.drop_column("tasks", column)
