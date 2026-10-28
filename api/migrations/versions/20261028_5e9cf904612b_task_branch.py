"""task branch

Revision ID: 5e9cf904612b
Revises: b448d0ea95b2
Create Date: 2026-10-28 11:19:35.162535

Exécution par les casquettes (lot 3b) : branche Git de chaque tâche, et commit de sa
fusion dans main une fois la tâche en Done.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5e9cf904612b"
down_revision: str | None = "b448d0ea95b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("branch", sa.String(length=100), nullable=True))
    op.add_column("tasks", sa.Column("merged_commit", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "merged_commit")
    op.drop_column("tasks", "branch")
