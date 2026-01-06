"""SQLModel models for the canvas-ledger database.

Phase 0: IngestRun for tracking ingestion runs.
Additional models will be added in later phases.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(UTC)


class IngestScope(str, Enum):
    """Scope of an ingestion run."""

    CATALOG = "catalog"  # All visible courses
    OFFERING = "offering"  # Deep ingest for specific offering(s)


class IngestStatus(str, Enum):
    """Status of an ingestion run."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class IngestRun(SQLModel, table=True):
    """Track individual ingestion runs with metadata.

    Each run captures when data was fetched from Canvas,
    what scope was ingested, and summary counts.
    """

    __tablename__ = "ingest_run"

    id: int | None = Field(default=None, primary_key=True)
    started_at: datetime = Field(default_factory=_utcnow)
    completed_at: datetime | None = Field(default=None)
    scope: IngestScope = Field(default=IngestScope.CATALOG)
    scope_detail: str | None = Field(
        default=None,
        description="Additional scope info, e.g., offering canvas_id for deep ingest",
    )
    status: IngestStatus = Field(default=IngestStatus.RUNNING)
    error_message: str | None = Field(default=None)

    # Summary counts
    new_count: int = Field(default=0)
    updated_count: int = Field(default=0)
    unchanged_count: int = Field(default=0)

    def mark_completed(
        self,
        new_count: int = 0,
        updated_count: int = 0,
        unchanged_count: int = 0,
    ) -> None:
        """Mark the ingestion run as completed with counts."""
        self.completed_at = _utcnow()
        self.status = IngestStatus.COMPLETED
        self.new_count = new_count
        self.updated_count = updated_count
        self.unchanged_count = unchanged_count

    def mark_failed(self, error_message: str) -> None:
        """Mark the ingestion run as failed with error message."""
        self.completed_at = _utcnow()
        self.status = IngestStatus.FAILED
        self.error_message = error_message

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "scope": self.scope.value,
            "scope_detail": self.scope_detail,
            "status": self.status.value,
            "error_message": self.error_message,
            "new_count": self.new_count,
            "updated_count": self.updated_count,
            "unchanged_count": self.unchanged_count,
        }
