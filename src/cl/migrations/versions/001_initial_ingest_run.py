"""Initial schema with ingest_run table.

Revision ID: 001
Revises:
Create Date: 2026-01-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingest_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("scope", sa.VARCHAR(length=20), nullable=False),
        sa.Column("scope_detail", sa.VARCHAR(), nullable=True),
        sa.Column("status", sa.VARCHAR(length=20), nullable=False),
        sa.Column("error_message", sa.VARCHAR(), nullable=True),
        sa.Column("new_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unchanged_count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    # Index for querying recent runs
    op.create_index(
        "ix_ingest_run_started_at",
        "ingest_run",
        ["started_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ingest_run_started_at", table_name="ingest_run")
    op.drop_table("ingest_run")
