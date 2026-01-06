"""Annotation tables: LeadInstructorAnnotation, InvolvementAnnotation.

Revision ID: 003
Revises: 002
Create Date: 2026-01-06

These tables store declared truth (user annotations) that coexist with
observed Canvas data. Annotations reference Canvas IDs rather than
internal FKs so they survive re-ingestion.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # LeadInstructorAnnotation table
    op.create_table(
        "lead_instructor_annotation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("offering_canvas_id", sa.Integer(), nullable=False),
        sa.Column("person_canvas_id", sa.Integer(), nullable=False),
        sa.Column("designation", sa.VARCHAR(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_lead_instructor_annotation_offering_canvas_id",
        "lead_instructor_annotation",
        ["offering_canvas_id"],
        unique=False,
    )
    op.create_index(
        "ix_lead_instructor_annotation_person_canvas_id",
        "lead_instructor_annotation",
        ["person_canvas_id"],
        unique=False,
    )

    # InvolvementAnnotation table
    op.create_table(
        "involvement_annotation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("offering_canvas_id", sa.Integer(), nullable=False),
        sa.Column("classification", sa.VARCHAR(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_involvement_annotation_offering_canvas_id",
        "involvement_annotation",
        ["offering_canvas_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_involvement_annotation_offering_canvas_id",
        table_name="involvement_annotation",
    )
    op.drop_table("involvement_annotation")

    op.drop_index(
        "ix_lead_instructor_annotation_person_canvas_id",
        table_name="lead_instructor_annotation",
    )
    op.drop_index(
        "ix_lead_instructor_annotation_offering_canvas_id",
        table_name="lead_instructor_annotation",
    )
    op.drop_table("lead_instructor_annotation")
