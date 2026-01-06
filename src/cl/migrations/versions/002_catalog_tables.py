"""Catalog tables: Term, Offering, UserEnrollment.

Revision ID: 002
Revises: 001
Create Date: 2026-01-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Term table
    op.create_table(
        "term",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("canvas_term_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.VARCHAR(), nullable=False),
        sa.Column("start_date", sa.DateTime(), nullable=True),
        sa.Column("end_date", sa.DateTime(), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_term_canvas_term_id", "term", ["canvas_term_id"], unique=True)

    # Offering table
    op.create_table(
        "offering",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("canvas_course_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.VARCHAR(), nullable=False),
        sa.Column("code", sa.VARCHAR(), nullable=True),
        sa.Column("term_id", sa.Integer(), nullable=True),
        sa.Column("workflow_state", sa.VARCHAR(), nullable=False),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["term_id"], ["term.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_offering_canvas_course_id", "offering", ["canvas_course_id"], unique=True)
    op.create_index("ix_offering_term_id", "offering", ["term_id"], unique=False)

    # UserEnrollment table
    op.create_table(
        "user_enrollment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("canvas_enrollment_id", sa.Integer(), nullable=False),
        sa.Column("offering_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.VARCHAR(), nullable=False),
        sa.Column("enrollment_state", sa.VARCHAR(), nullable=False),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["offering_id"], ["offering.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_user_enrollment_canvas_enrollment_id",
        "user_enrollment",
        ["canvas_enrollment_id"],
        unique=True,
    )
    op.create_index(
        "ix_user_enrollment_offering_id",
        "user_enrollment",
        ["offering_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_enrollment_offering_id", table_name="user_enrollment")
    op.drop_index("ix_user_enrollment_canvas_enrollment_id", table_name="user_enrollment")
    op.drop_table("user_enrollment")

    op.drop_index("ix_offering_term_id", table_name="offering")
    op.drop_index("ix_offering_canvas_course_id", table_name="offering")
    op.drop_table("offering")

    op.drop_index("ix_term_canvas_term_id", table_name="term")
    op.drop_table("term")
