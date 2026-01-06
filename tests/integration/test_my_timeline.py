"""Integration tests for my-timeline query."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

import pytest

from cl.ledger.models import Offering, Term, UserEnrollment
from cl.ledger.queries import TimelineEntry, get_my_timeline
from cl.ledger.store import get_session, reset_engine, run_migrations


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Generator[Path]:
    """Create a temporary database with migrations applied."""
    db_path = tmp_path / "test_ledger.db"
    run_migrations(db_path, backup=False)
    yield db_path
    reset_engine()


def seed_test_data(db_path: Path) -> None:
    """Seed the database with test data for timeline queries."""
    now = datetime.now(UTC)

    with get_session(db_path) as session:
        # Create terms
        fall_2024 = Term(
            canvas_term_id=1,
            name="Fall 2024",
            start_date=datetime(2024, 8, 15, tzinfo=UTC),
            end_date=datetime(2024, 12, 15, tzinfo=UTC),
            observed_at=now,
            last_seen_at=now,
        )
        spring_2024 = Term(
            canvas_term_id=2,
            name="Spring 2024",
            start_date=datetime(2024, 1, 10, tzinfo=UTC),
            end_date=datetime(2024, 5, 15, tzinfo=UTC),
            observed_at=now,
            last_seen_at=now,
        )
        session.add(fall_2024)
        session.add(spring_2024)
        session.commit()
        session.refresh(fall_2024)
        session.refresh(spring_2024)

        # Create offerings
        course1 = Offering(
            canvas_course_id=101,
            name="Introduction to Testing",
            code="TST101",
            term_id=fall_2024.id,
            workflow_state="available",
            observed_at=now,
            last_seen_at=now,
        )
        course2 = Offering(
            canvas_course_id=102,
            name="Advanced Testing",
            code="TST201",
            term_id=spring_2024.id,
            workflow_state="available",
            observed_at=now,
            last_seen_at=now,
        )
        course3 = Offering(
            canvas_course_id=103,
            name="Testing Without Term",
            code="TST000",
            term_id=None,
            workflow_state="completed",
            observed_at=now,
            last_seen_at=now,
        )
        session.add(course1)
        session.add(course2)
        session.add(course3)
        session.commit()
        session.refresh(course1)
        session.refresh(course2)
        session.refresh(course3)

        # Create user enrollments
        enrollments = [
            UserEnrollment(
                canvas_enrollment_id=1001,
                offering_id=course1.id,
                role="teacher",
                enrollment_state="active",
                observed_at=now,
                last_seen_at=now,
            ),
            UserEnrollment(
                canvas_enrollment_id=1002,
                offering_id=course2.id,
                role="ta",
                enrollment_state="active",
                observed_at=now,
                last_seen_at=now,
            ),
            UserEnrollment(
                canvas_enrollment_id=1003,
                offering_id=course3.id,
                role="student",
                enrollment_state="completed",
                observed_at=now,
                last_seen_at=now,
            ),
            # Multiple roles in same course
            UserEnrollment(
                canvas_enrollment_id=1004,
                offering_id=course1.id,
                role="designer",
                enrollment_state="active",
                observed_at=now,
                last_seen_at=now,
            ),
        ]
        for e in enrollments:
            session.add(e)
        session.commit()


class TestGetMyTimeline:
    """Tests for get_my_timeline query."""

    def test_empty_database_returns_empty(self, temp_db_path: Path) -> None:
        """Should return empty list when no data exists."""
        entries = get_my_timeline(temp_db_path)
        assert entries == []

    def test_returns_all_offerings_with_enrollments(self, temp_db_path: Path) -> None:
        """Should return all offerings the user has enrollments in."""
        seed_test_data(temp_db_path)

        entries = get_my_timeline(temp_db_path)

        assert len(entries) == 3
        course_ids = {e.canvas_course_id for e in entries}
        assert course_ids == {101, 102, 103}

    def test_sorted_by_term_date_descending(self, temp_db_path: Path) -> None:
        """Entries should be sorted by term start date, most recent first."""
        seed_test_data(temp_db_path)

        entries = get_my_timeline(temp_db_path)

        # Fall 2024 (August) should come before Spring 2024 (January)
        # Courses without terms should be last
        assert entries[0].term_name == "Fall 2024"
        assert entries[1].term_name == "Spring 2024"
        assert entries[2].term_name is None

    def test_aggregates_multiple_roles(self, temp_db_path: Path) -> None:
        """Should aggregate multiple roles for same offering."""
        seed_test_data(temp_db_path)

        entries = get_my_timeline(temp_db_path)

        # Find the course with multiple roles
        course1_entry = next(e for e in entries if e.canvas_course_id == 101)

        assert len(course1_entry.roles) == 2
        assert set(course1_entry.roles) == {"teacher", "designer"}

    def test_filter_by_term(self, temp_db_path: Path) -> None:
        """Should filter by term name."""
        seed_test_data(temp_db_path)

        entries = get_my_timeline(temp_db_path, term_filter="Fall")

        assert len(entries) == 1
        assert entries[0].term_name == "Fall 2024"

    def test_filter_by_role(self, temp_db_path: Path) -> None:
        """Should filter by role."""
        seed_test_data(temp_db_path)

        entries = get_my_timeline(temp_db_path, role_filter="ta")

        assert len(entries) == 1
        assert "ta" in entries[0].roles

    def test_filter_by_term_case_insensitive(self, temp_db_path: Path) -> None:
        """Term filter should be case-insensitive."""
        seed_test_data(temp_db_path)

        entries = get_my_timeline(temp_db_path, term_filter="SPRING")

        assert len(entries) == 1
        assert entries[0].term_name == "Spring 2024"


class TestTimelineEntry:
    """Tests for TimelineEntry dataclass."""

    def test_to_dict(self) -> None:
        """to_dict should include all fields."""
        entry = TimelineEntry(
            canvas_course_id=123,
            offering_name="Test Course",
            offering_code="TST101",
            workflow_state="available",
            term_name="Fall 2024",
            term_start_date=datetime(2024, 8, 15, tzinfo=UTC),
            roles=["teacher", "designer"],
            enrollment_states=["active", "active"],
            observed_at=datetime(2024, 1, 1, tzinfo=UTC),
            last_seen_at=datetime(2024, 1, 2, tzinfo=UTC),
        )

        data = entry.to_dict()

        assert data["canvas_course_id"] == 123
        assert data["offering_name"] == "Test Course"
        assert data["offering_code"] == "TST101"
        assert data["workflow_state"] == "available"
        assert data["term_name"] == "Fall 2024"
        assert data["roles"] == ["teacher", "designer"]
        assert "term_start_date" in data
        assert "observed_at" in data
        assert "last_seen_at" in data


class TestOutputFormats:
    """Tests for output formatting of timeline data."""

    def test_json_output(self, temp_db_path: Path) -> None:
        """Timeline should be exportable as JSON."""
        import json

        from cl.export.formatters import to_json

        seed_test_data(temp_db_path)

        entries = get_my_timeline(temp_db_path)
        data = [e.to_dict() for e in entries]

        output = StringIO()
        to_json(data, output=output)

        # Should be valid JSON
        output.seek(0)
        parsed = json.load(output)

        assert isinstance(parsed, list)
        assert len(parsed) == 3

    def test_csv_output(self, temp_db_path: Path) -> None:
        """Timeline should be exportable as CSV."""
        import csv

        from cl.export.formatters import to_csv

        seed_test_data(temp_db_path)

        entries = get_my_timeline(temp_db_path)
        data = [e.to_dict() for e in entries]

        output = StringIO()
        to_csv(data, output=output)

        # Should be valid CSV
        output.seek(0)
        reader = csv.DictReader(output)
        rows = list(reader)

        assert len(rows) == 3
        assert "canvas_course_id" in reader.fieldnames

    def test_table_output(self, temp_db_path: Path) -> None:
        """Timeline should be exportable as table."""
        from cl.export.formatters import to_table

        seed_test_data(temp_db_path)

        entries = get_my_timeline(temp_db_path)
        data = [e.to_dict() for e in entries]

        output = StringIO()
        to_table(data, output=output)

        output.seek(0)
        table = output.read()

        # Should have header and separator
        assert "canvas_course_id" in table
        assert "---" in table
