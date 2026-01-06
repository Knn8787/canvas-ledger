"""Query implementations for canvas-ledger.

Provides read-only queries against the local ledger database.
Queries merge observed data with declared annotations where applicable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlmodel import Session, select

from cl.ledger.models import Offering, Term, UserEnrollment
from cl.ledger.store import get_session

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class TimelineEntry:
    """A single entry in the user's involvement timeline."""

    canvas_course_id: int
    offering_name: str
    offering_code: str | None
    workflow_state: str
    term_name: str | None
    term_start_date: datetime | None
    roles: list[str]  # User's roles in this offering
    enrollment_states: list[str]  # States for each enrollment
    observed_at: datetime
    last_seen_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "canvas_course_id": self.canvas_course_id,
            "offering_name": self.offering_name,
            "offering_code": self.offering_code,
            "workflow_state": self.workflow_state,
            "term_name": self.term_name,
            "term_start_date": (self.term_start_date.isoformat() if self.term_start_date else None),
            "roles": self.roles,
            "enrollment_states": self.enrollment_states,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
        }


def get_my_timeline(
    db_path: Path | str,
    term_filter: str | None = None,
    role_filter: str | None = None,
) -> list[TimelineEntry]:
    """Get the user's involvement timeline.

    Returns all offerings the user has enrollments in, sorted by term
    (most recent first) then by offering name.

    Args:
        db_path: Path to the SQLite database.
        term_filter: Optional filter by term name (case-insensitive contains).
        role_filter: Optional filter by role (exact match).

    Returns:
        List of TimelineEntry objects representing the user's involvement.
    """
    with get_session(db_path) as session:
        return _get_my_timeline_impl(session, term_filter, role_filter)


def _get_my_timeline_impl(
    session: Session,
    term_filter: str | None = None,
    role_filter: str | None = None,
) -> list[TimelineEntry]:
    """Implementation of get_my_timeline that takes an existing session."""
    # Get all user enrollments with their offerings
    stmt = (
        select(UserEnrollment, Offering, Term)
        .join(Offering, UserEnrollment.offering_id == Offering.id)  # type: ignore[arg-type]
        .outerjoin(Term, Offering.term_id == Term.id)  # type: ignore[arg-type]
    )

    if role_filter:
        stmt = stmt.where(UserEnrollment.role == role_filter)

    if term_filter:
        # Case-insensitive contains match on term name
        stmt = stmt.where(Term.name.icontains(term_filter))  # type: ignore[attr-defined]

    results = session.exec(stmt).all()

    # Group enrollments by offering
    offerings_map: dict[int, dict[str, Any]] = {}

    for enrollment, offering, term in results:
        course_id = offering.canvas_course_id

        if course_id not in offerings_map:
            offerings_map[course_id] = {
                "offering": offering,
                "term": term,
                "roles": [],
                "enrollment_states": [],
            }

        offerings_map[course_id]["roles"].append(enrollment.role)
        offerings_map[course_id]["enrollment_states"].append(enrollment.enrollment_state)

    # Convert to TimelineEntry objects
    entries: list[TimelineEntry] = []

    for course_id, data in offerings_map.items():
        offering = data["offering"]
        term = data["term"]

        entries.append(
            TimelineEntry(
                canvas_course_id=course_id,
                offering_name=offering.name,
                offering_code=offering.code,
                workflow_state=offering.workflow_state,
                term_name=term.name if term else None,
                term_start_date=term.start_date if term else None,
                roles=data["roles"],
                enrollment_states=data["enrollment_states"],
                observed_at=offering.observed_at,
                last_seen_at=offering.last_seen_at,
            )
        )

    # Sort by term start date (descending, nulls last), then by name
    def sort_key(entry: TimelineEntry) -> tuple[float, str]:
        # Use a very old date for None to push to end
        date = entry.term_start_date or datetime.min.replace(tzinfo=None)
        if hasattr(date, "tzinfo") and date.tzinfo:
            date = date.replace(tzinfo=None)
        return (-date.timestamp() if date != datetime.min else float("inf"), entry.offering_name)

    entries.sort(key=sort_key)

    return entries


def get_all_offerings(
    db_path: Path | str,
    include_inactive: bool = False,
) -> list[Offering]:
    """Get all offerings in the ledger.

    Args:
        db_path: Path to the SQLite database.
        include_inactive: If True, include offerings with non-available states.

    Returns:
        List of Offering objects.
    """
    with get_session(db_path) as session:
        stmt = select(Offering)

        if not include_inactive:
            stmt = stmt.where(Offering.workflow_state == "available")

        stmt = stmt.order_by(Offering.name)
        return list(session.exec(stmt).all())


def get_offering_by_canvas_id(
    db_path: Path | str,
    canvas_course_id: int,
) -> Offering | None:
    """Get an offering by its Canvas course ID.

    Args:
        db_path: Path to the SQLite database.
        canvas_course_id: Canvas course ID.

    Returns:
        Offering object or None if not found.
    """
    with get_session(db_path) as session:
        stmt = select(Offering).where(Offering.canvas_course_id == canvas_course_id)
        return session.exec(stmt).first()


def get_offerings_with_terms(db_path: Path | str) -> list[dict[str, Any]]:
    """Get all offerings with their term information.

    Returns offering data suitable for export.

    Args:
        db_path: Path to the SQLite database.

    Returns:
        List of dictionaries with offering and term data.
    """
    with get_session(db_path) as session:
        stmt = (
            select(Offering, Term)
            .outerjoin(Term, Offering.term_id == Term.id)  # type: ignore[arg-type]
            .order_by(Offering.name)
        )

        results = session.exec(stmt).all()

        return [
            {
                "canvas_course_id": offering.canvas_course_id,
                "name": offering.name,
                "code": offering.code,
                "workflow_state": offering.workflow_state,
                "term_name": term.name if term else None,
                "term_start_date": (
                    term.start_date.isoformat() if term and term.start_date else None
                ),
                "term_end_date": (term.end_date.isoformat() if term and term.end_date else None),
                "observed_at": (offering.observed_at.isoformat() if offering.observed_at else None),
                "last_seen_at": (
                    offering.last_seen_at.isoformat() if offering.last_seen_at else None
                ),
            }
            for offering, term in results
        ]
