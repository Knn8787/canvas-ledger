"""SQLModel models for annotations (declared truth).

Annotations store user-declared facts that coexist with observed Canvas data.
Key design principle: Annotations reference Canvas IDs (not internal FKs)
so they survive offering re-ingestion.

Phase 2: LeadInstructorAnnotation, InvolvementAnnotation
Phase 6: CourseAlias, CourseAliasOffering (deferred)
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(UTC)


class AnnotationType(str, Enum):
    """Type of annotation."""

    LEAD_INSTRUCTOR = "lead_instructor"
    INVOLVEMENT = "involvement"


class LeadDesignation(str, Enum):
    """Designation for lead instructor annotation.

    Both values represent the same concept (the person primarily
    responsible for the course), but users may prefer different terms.
    """

    LEAD = "lead"
    GRADE_RESPONSIBLE = "grade_responsible"


class LeadInstructorAnnotation(SQLModel, table=True):
    """Declare who is the lead/grade-responsible instructor for an offering.

    This annotation allows users to clarify who is primarily responsible
    when Canvas data shows multiple instructors or when the Canvas-reported
    role doesn't accurately reflect reality.

    References offerings and persons by Canvas IDs (not internal FKs) so
    annotations survive re-ingestion. The person_canvas_id may reference
    a user not yet in the local ledger (will be populated during deep ingestion).
    """

    __tablename__ = "lead_instructor_annotation"

    id: int | None = Field(default=None, primary_key=True)
    offering_canvas_id: int = Field(index=True)
    person_canvas_id: int = Field(index=True)
    designation: LeadDesignation = Field(default=LeadDesignation.LEAD)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "annotation_type": AnnotationType.LEAD_INSTRUCTOR.value,
            "offering_canvas_id": self.offering_canvas_id,
            "person_canvas_id": self.person_canvas_id,
            "designation": self.designation.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class InvolvementAnnotation(SQLModel, table=True):
    """Classify the user's involvement in an offering.

    This annotation allows users to describe their actual involvement
    when the Canvas role doesn't tell the full story. For example:
    - "developed course" for a course you created but aren't listed as instructor
    - "guest lecturer" for a one-time teaching contribution
    - "co-instructor" to clarify shared teaching responsibility
    - "course coordinator" for administrative roles

    The classification field is free text to support any involvement type
    the user needs to record.

    References offerings by Canvas ID (not internal FK) so annotations
    survive re-ingestion.
    """

    __tablename__ = "involvement_annotation"

    id: int | None = Field(default=None, primary_key=True)
    offering_canvas_id: int = Field(index=True)
    classification: str  # Free text: "developed course", "guest lecturer", etc.
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "annotation_type": AnnotationType.INVOLVEMENT.value,
            "offering_canvas_id": self.offering_canvas_id,
            "classification": self.classification,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
