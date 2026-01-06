"""Unit tests for catalog ingestion module."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cl.canvas.client import CourseData, EnrollmentData, TermData
from cl.ledger.ingest import IngestResult, ingest_catalog
from cl.ledger.models import IngestScope, IngestStatus, Offering, Term, UserEnrollment
from cl.ledger.store import get_session, reset_engine, run_migrations


class MockCanvasClient:
    """Mock Canvas client for testing."""

    def __init__(self, courses: list[CourseData] | None = None):
        self.courses = courses or []
        self._term_cache: dict[int, TermData] = {}

    def list_my_courses(self) -> list[CourseData]:
        """Return mock courses."""
        return self.courses

    def get_term_from_course(self, course_id: int) -> TermData | None:
        """Return mock term data from course cache."""
        for course in self.courses:
            if course.canvas_course_id == course_id and course.term_id:
                if course.term_id not in self._term_cache:
                    self._term_cache[course.term_id] = TermData(
                        canvas_term_id=course.term_id,
                        name=f"Term {course.term_id}",
                        start_date=datetime(2024, 1, 1, tzinfo=UTC),
                        end_date=datetime(2024, 5, 15, tzinfo=UTC),
                    )
                return self._term_cache[course.term_id]
        return None

    def set_term_data(self, term_id: int, term: TermData) -> None:
        """Set specific term data for testing."""
        self._term_cache[term_id] = term


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Generator[Path]:
    """Create a temporary database with migrations applied."""
    db_path = tmp_path / "test_ledger.db"
    run_migrations(db_path, backup=False)
    yield db_path
    reset_engine()


class TestIngestCatalog:
    """Tests for catalog ingestion."""

    def test_ingest_empty_catalog(self, temp_db_path: Path) -> None:
        """Ingesting empty course list should succeed with zero counts."""
        client = MockCanvasClient(courses=[])

        result = ingest_catalog(client, temp_db_path)

        assert result.error is None
        assert result.new_count == 0
        assert result.updated_count == 0
        assert result.unchanged_count == 0
        assert result.total_count == 0

    def test_ingest_single_course(self, temp_db_path: Path) -> None:
        """Ingesting a single course should create offering and enrollment."""
        courses = [
            CourseData(
                canvas_course_id=123,
                name="Test Course",
                code="TST101",
                workflow_state="available",
                term_id=1,
                enrollments=[
                    EnrollmentData(
                        canvas_enrollment_id=456,
                        role="teacher",
                        enrollment_state="active",
                        course_id=123,
                    )
                ],
            )
        ]
        client = MockCanvasClient(courses=courses)

        result = ingest_catalog(client, temp_db_path)

        assert result.error is None
        assert result.new_count >= 2  # At least offering + enrollment

        # Verify offering was created
        with get_session(temp_db_path) as session:
            from sqlmodel import select

            offerings = list(session.exec(select(Offering)).all())
            assert len(offerings) == 1
            assert offerings[0].canvas_course_id == 123
            assert offerings[0].name == "Test Course"
            assert offerings[0].code == "TST101"

    def test_ingest_course_with_term(self, temp_db_path: Path) -> None:
        """Ingesting a course with term should create term record."""
        courses = [
            CourseData(
                canvas_course_id=123,
                name="Test Course",
                code="TST101",
                workflow_state="available",
                term_id=10,
                enrollments=[],
            )
        ]
        client = MockCanvasClient(courses=courses)
        client.set_term_data(
            10,
            TermData(
                canvas_term_id=10,
                name="Fall 2024",
                start_date=datetime(2024, 8, 15, tzinfo=UTC),
                end_date=datetime(2024, 12, 15, tzinfo=UTC),
            ),
        )

        result = ingest_catalog(client, temp_db_path)

        assert result.error is None

        # Verify term was created
        with get_session(temp_db_path) as session:
            from sqlmodel import select

            terms = list(session.exec(select(Term)).all())
            assert len(terms) == 1
            assert terms[0].canvas_term_id == 10
            assert terms[0].name == "Fall 2024"

    def test_ingest_creates_user_enrollment(self, temp_db_path: Path) -> None:
        """Ingesting should create user enrollment records."""
        courses = [
            CourseData(
                canvas_course_id=123,
                name="Test Course",
                code="TST101",
                workflow_state="available",
                term_id=None,
                enrollments=[
                    EnrollmentData(
                        canvas_enrollment_id=100,
                        role="teacher",
                        enrollment_state="active",
                        course_id=123,
                    ),
                    EnrollmentData(
                        canvas_enrollment_id=101,
                        role="ta",
                        enrollment_state="active",
                        course_id=123,
                    ),
                ],
            )
        ]
        client = MockCanvasClient(courses=courses)

        result = ingest_catalog(client, temp_db_path)

        assert result.error is None

        # Verify enrollments were created
        with get_session(temp_db_path) as session:
            from sqlmodel import select

            enrollments = list(session.exec(select(UserEnrollment)).all())
            assert len(enrollments) == 2
            roles = {e.role for e in enrollments}
            assert roles == {"teacher", "ta"}


class TestIdempotency:
    """Tests for ingestion idempotency."""

    def test_duplicate_ingestion_no_duplicates(self, temp_db_path: Path) -> None:
        """Running ingestion twice with same data should not create duplicates."""
        courses = [
            CourseData(
                canvas_course_id=123,
                name="Test Course",
                code="TST101",
                workflow_state="available",
                term_id=None,
                enrollments=[
                    EnrollmentData(
                        canvas_enrollment_id=456,
                        role="teacher",
                        enrollment_state="active",
                        course_id=123,
                    )
                ],
            )
        ]
        client = MockCanvasClient(courses=courses)

        # First ingestion
        result1 = ingest_catalog(client, temp_db_path)
        reset_engine()

        # Second ingestion
        result2 = ingest_catalog(client, temp_db_path)

        # First run creates new records
        assert result1.new_count > 0

        # Second run should find everything unchanged
        assert result2.new_count == 0
        assert result2.unchanged_count > 0

        # Verify no duplicates
        with get_session(temp_db_path) as session:
            from sqlmodel import select

            offerings = list(session.exec(select(Offering)).all())
            assert len(offerings) == 1

            enrollments = list(session.exec(select(UserEnrollment)).all())
            assert len(enrollments) == 1

    def test_updated_data_triggers_update(self, temp_db_path: Path) -> None:
        """Changed data should be detected and updated."""
        # Initial ingestion
        courses_v1 = [
            CourseData(
                canvas_course_id=123,
                name="Test Course",
                code="TST101",
                workflow_state="available",
                term_id=None,
                enrollments=[],
            )
        ]
        client1 = MockCanvasClient(courses=courses_v1)
        ingest_catalog(client1, temp_db_path)
        reset_engine()

        # Second ingestion with changed name
        courses_v2 = [
            CourseData(
                canvas_course_id=123,
                name="Updated Course Name",  # Changed
                code="TST101",
                workflow_state="available",
                term_id=None,
                enrollments=[],
            )
        ]
        client2 = MockCanvasClient(courses=courses_v2)
        result = ingest_catalog(client2, temp_db_path)

        assert result.updated_count > 0
        assert len(result.drift_detected) > 0

        # Verify name was updated
        with get_session(temp_db_path) as session:
            from sqlmodel import select

            offerings = list(session.exec(select(Offering)).all())
            assert len(offerings) == 1
            assert offerings[0].name == "Updated Course Name"

    def test_drift_detection_workflow_state(self, temp_db_path: Path) -> None:
        """Workflow state changes should be detected as drift."""
        # Initial ingestion
        courses_v1 = [
            CourseData(
                canvas_course_id=123,
                name="Test Course",
                code="TST101",
                workflow_state="available",
                term_id=None,
                enrollments=[],
            )
        ]
        client1 = MockCanvasClient(courses=courses_v1)
        ingest_catalog(client1, temp_db_path)
        reset_engine()

        # Second ingestion with changed workflow state
        courses_v2 = [
            CourseData(
                canvas_course_id=123,
                name="Test Course",
                code="TST101",
                workflow_state="completed",  # Changed
                term_id=None,
                enrollments=[],
            )
        ]
        client2 = MockCanvasClient(courses=courses_v2)
        result = ingest_catalog(client2, temp_db_path)

        assert result.updated_count > 0
        assert any("state" in d for d in result.drift_detected)


class TestIngestRunMetadata:
    """Tests for ingest run metadata tracking."""

    def test_ingest_creates_run_record(self, temp_db_path: Path) -> None:
        """Ingestion should create an ingest run record."""
        client = MockCanvasClient(courses=[])

        result = ingest_catalog(client, temp_db_path)

        assert result.run_id is not None

        # Verify run record exists
        with get_session(temp_db_path) as session:
            from sqlmodel import select

            from cl.ledger.models import IngestRun

            runs = list(session.exec(select(IngestRun)).all())
            assert len(runs) >= 1

            run = runs[-1]  # Most recent
            assert run.id == result.run_id
            assert run.scope == IngestScope.CATALOG
            assert run.status == IngestStatus.COMPLETED

    def test_ingest_run_counts_are_accurate(self, temp_db_path: Path) -> None:
        """Ingest run should have accurate counts."""
        courses = [
            CourseData(
                canvas_course_id=123,
                name="Course 1",
                code="C1",
                workflow_state="available",
                term_id=None,
                enrollments=[
                    EnrollmentData(
                        canvas_enrollment_id=1,
                        role="teacher",
                        enrollment_state="active",
                        course_id=123,
                    )
                ],
            ),
            CourseData(
                canvas_course_id=456,
                name="Course 2",
                code="C2",
                workflow_state="available",
                term_id=None,
                enrollments=[],
            ),
        ]
        client = MockCanvasClient(courses=courses)

        result = ingest_catalog(client, temp_db_path)

        # Should have: 2 offerings + 1 enrollment = 3 new
        assert result.new_count == 3
        assert result.total_count == 3


class TestIngestResult:
    """Tests for IngestResult dataclass."""

    def test_ingest_result_total_count(self) -> None:
        """total_count should sum new, updated, and unchanged."""
        result = IngestResult(
            run_id=1,
            new_count=5,
            updated_count=3,
            unchanged_count=2,
            drift_detected=[],
        )

        assert result.total_count == 10

    def test_ingest_result_to_dict(self) -> None:
        """to_dict should include all fields."""
        result = IngestResult(
            run_id=1,
            new_count=5,
            updated_count=3,
            unchanged_count=2,
            drift_detected=["Offering 123: name changed"],
            error=None,
        )

        data = result.to_dict()

        assert data["run_id"] == 1
        assert data["new_count"] == 5
        assert data["updated_count"] == 3
        assert data["unchanged_count"] == 2
        assert data["total_count"] == 10
        assert len(data["drift_detected"]) == 1
        assert data["error"] is None
