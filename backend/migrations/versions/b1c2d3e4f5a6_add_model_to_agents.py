"""Add model column to agents table."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "a9b1c2d3e4f7"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("model", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "model")
