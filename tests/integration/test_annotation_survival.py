"""Integration tests for annotation survival across re-ingestion.

Verifies that annotations persist and remain unaffected when catalog
ingestion is run multiple times.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from cl.annotations.manager import (
    add_involvement,
    add_lead_instructor,
    get_involvement_annotations,
    get_lead_instructor_annotations,
    list_annotations,
)
from cl.ledger.ingest import ingest_catalog
from cl.ledger.models import Offering, Term, UserEnrollment
from cl.ledger.queries import get_my_timeline, get_offering_responsibility
from cl.ledger.store import get_session, reset_engine, run_migrations


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Generator[Path]:
    """Create a temporary database with migrations applied."""
    db_path = tmp_path / "test_ledger.db"
    run_migrations(db_path, backup=False)
    yield db_path
    reset_engine()


def seed_initial_data(db_path: Path) -> None:
    """Seed the database with initial offering and enrollment data."""
    now = datetime.now(UTC)

    with get_session(db_path) as session:
        # Create a term
        fall_2025 = Term(
            canvas_term_id=100,
            name="Fall 2025",
            start_date=datetime(2025, 8, 15, tzinfo=UTC),
            end_date=datetime(2025, 12, 15, tzinfo=UTC),
            observed_at=now,
            last_seen_at=now,
        )
        session.add(fall_2025)
        session.commit()
        session.refresh(fall_2025)

        # Create offerings
        course1 = Offering(
            canvas_course_id=1001,
            name="Software Engineering",
            code="SE501",
            term_id=fall_2025.id,
            workflow_state="available",
            observed_at=now,
            last_seen_at=now,
        )
        course2 = Offering(
            canvas_course_id=1002,
            name="Data Structures",
            code="DS101",
            term_id=fall_2025.id,
            workflow_state="available",
            observed_at=now,
            last_seen_at=now,
        )
        session.add(course1)
        session.add(course2)
        session.commit()
        session.refresh(course1)
        session.refresh(course2)

        # Create user enrollments
        enrollments = [
            UserEnrollment(
                canvas_enrollment_id=5001,
                offering_id=course1.id,
                role="teacher",
                enrollment_state="active",
                observed_at=now,
                last_seen_at=now,
            ),
            UserEnrollment(
                canvas_enrollment_id=5002,
                offering_id=course2.id,
                role="ta",
                enrollment_state="active",
                observed_at=now,
                last_seen_at=now,
            ),
        ]
        for e in enrollments:
            session.add(e)
        session.commit()


def create_mock_canvas_client() -> Mock:
    """Create a mock Canvas client that returns updated course data.

    Returns CourseData and TermData objects as expected by ingest_catalog.
    """
    from cl.canvas.client import CourseData, EnrollmentData, TermData

    client = Mock()

    # Mock term data
    mock_term = TermData(
        canvas_term_id=100,
        name="Fall 2025",
        start_date=datetime(2025, 8, 15, tzinfo=UTC),
        end_date=datetime(2025, 12, 15, tzinfo=UTC),
    )

    # Mock course data with slight modifications to simulate re-fetch
    mock_courses = [
        CourseData(
            canvas_course_id=1001,
            name="Software Engineering (Updated)",  # Name changed to trigger drift
            code="SE501",
            workflow_state="available",
            term_id=100,
            enrollments=[
                EnrollmentData(
                    canvas_enrollment_id=5001,
                    role="teacher",
                    enrollment_state="active",
                    course_id=1001,
                )
            ],
        ),
        CourseData(
            canvas_course_id=1002,
            name="Data Structures",
            code="DS101",
            workflow_state="available",
            term_id=100,
            enrollments=[
                EnrollmentData(
                    canvas_enrollment_id=5002,
                    role="ta",
                    enrollment_state="active",
                    course_id=1002,
                )
            ],
        ),
    ]

    client.list_my_courses.return_value = mock_courses
    client.get_term_from_course.return_value = mock_term

    return client


class TestAnnotationSurvivalAcrossIngestion:
    """Tests that annotations persist through re-ingestion."""

    def test_lead_instructor_annotation_survives_reingestion(self, temp_db_path: Path) -> None:
        """Lead instructor annotation should remain after catalog re-ingestion."""
        # Setup: seed initial data and add annotation
        seed_initial_data(temp_db_path)

        # Add lead instructor annotation
        annotation = add_lead_instructor(
            temp_db_path,
            offering_canvas_id=1001,
            person_canvas_id=99999,
            designation="lead",
        )
        initial_id = annotation.id
        initial_created_at = annotation.created_at

        # Verify annotation exists before re-ingestion
        annotations_before = get_lead_instructor_annotations(temp_db_path, offering_canvas_id=1001)
        assert len(annotations_before) == 1
        assert annotations_before[0].person_canvas_id == 99999

        # Re-ingest catalog
        mock_client = create_mock_canvas_client()
        ingest_catalog(mock_client, temp_db_path)

        # Verify annotation still exists after re-ingestion
        annotations_after = get_lead_instructor_annotations(temp_db_path, offering_canvas_id=1001)
        assert len(annotations_after) == 1
        assert annotations_after[0].id == initial_id
        assert annotations_after[0].person_canvas_id == 99999
        assert annotations_after[0].designation.value == "lead"
        assert annotations_after[0].created_at == initial_created_at

    def test_involvement_annotation_survives_reingestion(self, temp_db_path: Path) -> None:
        """Involvement annotation should remain after catalog re-ingestion."""
        # Setup: seed initial data and add annotation
        seed_initial_data(temp_db_path)

        # Add involvement annotation
        annotation = add_involvement(
            temp_db_path,
            offering_canvas_id=1002,
            classification="course developer",
        )
        initial_id = annotation.id

        # Verify annotation exists before re-ingestion
        annotations_before = get_involvement_annotations(temp_db_path, offering_canvas_id=1002)
        assert len(annotations_before) == 1
        assert annotations_before[0].classification == "course developer"

        # Re-ingest catalog
        mock_client = create_mock_canvas_client()
        ingest_catalog(mock_client, temp_db_path)

        # Verify annotation still exists after re-ingestion
        annotations_after = get_involvement_annotations(temp_db_path, offering_canvas_id=1002)
        assert len(annotations_after) == 1
        assert annotations_after[0].id == initial_id
        assert annotations_after[0].classification == "course developer"

    def test_multiple_annotations_survive_reingestion(self, temp_db_path: Path) -> None:
        """Multiple annotations of different types should all survive re-ingestion."""
        # Setup: seed initial data and add multiple annotations
        seed_initial_data(temp_db_path)

        # Add various annotations
        add_lead_instructor(temp_db_path, 1001, 99999, "lead")
        add_lead_instructor(temp_db_path, 1002, 88888, "grade_responsible")
        add_involvement(temp_db_path, 1001, "primary instructor")
        add_involvement(temp_db_path, 1002, "guest lecturer")

        # Count annotations before
        all_before = list_annotations(temp_db_path)
        assert len(all_before) == 4

        # Re-ingest catalog
        mock_client = create_mock_canvas_client()
        ingest_catalog(mock_client, temp_db_path)

        # Count annotations after
        all_after = list_annotations(temp_db_path)
        assert len(all_after) == 4

        # Verify specific annotations
        lead_1001 = get_lead_instructor_annotations(temp_db_path, 1001)
        assert len(lead_1001) == 1
        assert lead_1001[0].person_canvas_id == 99999

        inv_1002 = get_involvement_annotations(temp_db_path, 1002)
        assert len(inv_1002) == 1
        assert inv_1002[0].classification == "guest lecturer"


class TestAnnotationsInQueries:
    """Tests that annotations appear correctly in queries."""

    def test_timeline_shows_declared_involvement(self, temp_db_path: Path) -> None:
        """Timeline should include declared involvement annotation."""
        seed_initial_data(temp_db_path)

        # Add involvement annotation
        add_involvement(temp_db_path, 1001, "course coordinator")

        # Query timeline
        entries = get_my_timeline(temp_db_path)

        # Find the course with annotation
        course1_entry = next(e for e in entries if e.canvas_course_id == 1001)

        # Should have both observed role and declared involvement
        assert "teacher" in course1_entry.roles
        assert course1_entry.declared_involvement == "course coordinator"

    def test_timeline_shows_null_when_no_involvement_annotation(self, temp_db_path: Path) -> None:
        """Timeline should show null for declared_involvement when not annotated."""
        seed_initial_data(temp_db_path)

        # No annotation added
        entries = get_my_timeline(temp_db_path)

        # All entries should have null declared_involvement
        for entry in entries:
            assert entry.declared_involvement is None

    def test_offering_responsibility_shows_declared_lead(self, temp_db_path: Path) -> None:
        """Offering responsibility query should show declared lead instructor."""
        seed_initial_data(temp_db_path)

        # Add lead instructor annotation
        add_lead_instructor(temp_db_path, 1001, 12345, "lead")

        # Query responsibility
        resp = get_offering_responsibility(temp_db_path, 1001)

        assert resp is not None
        assert resp.declared_lead is not None
        assert resp.declared_lead["person_canvas_id"] == 12345
        assert resp.declared_lead["designation"] == "lead"

    def test_offering_responsibility_shows_observed_roles(self, temp_db_path: Path) -> None:
        """Offering responsibility should include user's observed instructor roles."""
        seed_initial_data(temp_db_path)

        # Query responsibility for course where user is teacher
        resp = get_offering_responsibility(temp_db_path, 1001)

        assert resp is not None
        assert len(resp.observed_instructors) >= 1
        roles = [i["role"] for i in resp.observed_instructors]
        assert "teacher" in roles

    def test_offering_responsibility_distinguishes_observed_vs_declared(
        self, temp_db_path: Path
    ) -> None:
        """Responsibility query should clearly distinguish observed vs declared."""
        seed_initial_data(temp_db_path)

        # Add lead annotation
        add_lead_instructor(temp_db_path, 1001, 12345, "grade_responsible")

        resp = get_offering_responsibility(temp_db_path, 1001)

        # Convert to dict to verify structure
        data = resp.to_dict()

        # Should have separate fields for observed and declared
        assert "observed_instructors" in data
        assert "declared_lead" in data

        # Observed should come from user enrollment
        assert isinstance(data["observed_instructors"], list)
        if data["observed_instructors"]:
            assert "source" in data["observed_instructors"][0]
            assert data["observed_instructors"][0]["source"] == "user_enrollment"

        # Declared should come from annotation
        assert data["declared_lead"]["designation"] == "grade_responsible"
