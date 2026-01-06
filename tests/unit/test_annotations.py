"""Unit tests for annotation manager CRUD operations."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cl.annotations.manager import (
    AnnotationNotFoundError,
    OfferingNotFoundError,
    add_involvement,
    add_lead_instructor,
    get_involvement_annotations,
    get_lead_instructor_annotations,
    list_annotations,
    remove_annotation,
    remove_involvement_annotation,
    remove_lead_instructor_annotation,
)
from cl.annotations.models import LeadDesignation
from cl.ledger.models import Offering, Term
from cl.ledger.store import get_session, reset_engine, run_migrations


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Generator[Path]:
    """Create a temporary database with migrations applied."""
    db_path = tmp_path / "test_ledger.db"
    run_migrations(db_path, backup=False)
    yield db_path
    reset_engine()


@pytest.fixture
def seeded_db_path(temp_db_path: Path) -> Generator[Path]:
    """Create a database with test offerings seeded."""
    now = datetime.now(UTC)

    with get_session(temp_db_path) as session:
        # Create a term
        term = Term(
            canvas_term_id=1,
            name="Fall 2025",
            start_date=datetime(2025, 8, 15, tzinfo=UTC),
            end_date=datetime(2025, 12, 15, tzinfo=UTC),
            observed_at=now,
            last_seen_at=now,
        )
        session.add(term)
        session.commit()
        session.refresh(term)

        # Create test offerings
        offerings = [
            Offering(
                canvas_course_id=1001,
                name="Test Course A",
                code="TST101",
                term_id=term.id,
                workflow_state="available",
                observed_at=now,
                last_seen_at=now,
            ),
            Offering(
                canvas_course_id=1002,
                name="Test Course B",
                code="TST102",
                term_id=term.id,
                workflow_state="available",
                observed_at=now,
                last_seen_at=now,
            ),
            Offering(
                canvas_course_id=1003,
                name="Test Course C",
                code="TST103",
                term_id=None,
                workflow_state="completed",
                observed_at=now,
                last_seen_at=now,
            ),
        ]
        for o in offerings:
            session.add(o)
        session.commit()

    yield temp_db_path


class TestAddLeadInstructor:
    """Tests for add_lead_instructor function."""

    def test_add_lead_instructor_success(self, seeded_db_path: Path) -> None:
        """Should add a lead instructor annotation."""
        annotation = add_lead_instructor(
            seeded_db_path,
            offering_canvas_id=1001,
            person_canvas_id=99999,
            designation="lead",
        )

        assert annotation.id is not None
        assert annotation.offering_canvas_id == 1001
        assert annotation.person_canvas_id == 99999
        assert annotation.designation == LeadDesignation.LEAD
        assert annotation.created_at is not None
        assert annotation.updated_at is not None

    def test_add_lead_instructor_grade_responsible(self, seeded_db_path: Path) -> None:
        """Should accept grade_responsible designation."""
        annotation = add_lead_instructor(
            seeded_db_path,
            offering_canvas_id=1001,
            person_canvas_id=99999,
            designation="grade_responsible",
        )

        assert annotation.designation == LeadDesignation.GRADE_RESPONSIBLE

    def test_add_lead_instructor_offering_not_found(self, seeded_db_path: Path) -> None:
        """Should raise error if offering doesn't exist."""
        with pytest.raises(OfferingNotFoundError) as exc_info:
            add_lead_instructor(
                seeded_db_path,
                offering_canvas_id=9999,  # Non-existent
                person_canvas_id=99999,
                designation="lead",
            )

        assert exc_info.value.canvas_course_id == 9999
        assert "not found in local ledger" in str(exc_info.value)

    def test_add_lead_instructor_invalid_designation(self, seeded_db_path: Path) -> None:
        """Should raise error for invalid designation."""
        with pytest.raises(ValueError) as exc_info:
            add_lead_instructor(
                seeded_db_path,
                offering_canvas_id=1001,
                person_canvas_id=99999,
                designation="invalid",
            )

        assert "Invalid designation" in str(exc_info.value)

    def test_add_lead_instructor_updates_existing(self, seeded_db_path: Path) -> None:
        """Should update existing annotation for same offering/person."""
        # Add initial annotation
        annotation1 = add_lead_instructor(
            seeded_db_path,
            offering_canvas_id=1001,
            person_canvas_id=99999,
            designation="lead",
        )
        initial_id = annotation1.id
        initial_created_at = annotation1.created_at

        # Update with different designation
        annotation2 = add_lead_instructor(
            seeded_db_path,
            offering_canvas_id=1001,
            person_canvas_id=99999,
            designation="grade_responsible",
        )

        # Should be same record, updated
        assert annotation2.id == initial_id
        assert annotation2.created_at == initial_created_at
        assert annotation2.updated_at > initial_created_at
        assert annotation2.designation == LeadDesignation.GRADE_RESPONSIBLE

        # Should only have one annotation
        annotations = get_lead_instructor_annotations(seeded_db_path, 1001)
        assert len(annotations) == 1


class TestAddInvolvement:
    """Tests for add_involvement function."""

    def test_add_involvement_success(self, seeded_db_path: Path) -> None:
        """Should add an involvement annotation."""
        annotation = add_involvement(
            seeded_db_path,
            offering_canvas_id=1001,
            classification="course developer",
        )

        assert annotation.id is not None
        assert annotation.offering_canvas_id == 1001
        assert annotation.classification == "course developer"

    def test_add_involvement_offering_not_found(self, seeded_db_path: Path) -> None:
        """Should raise error if offering doesn't exist."""
        with pytest.raises(OfferingNotFoundError):
            add_involvement(
                seeded_db_path,
                offering_canvas_id=9999,  # Non-existent
                classification="test",
            )

    def test_add_involvement_updates_existing(self, seeded_db_path: Path) -> None:
        """Should update existing annotation for same offering."""
        # Add initial annotation
        annotation1 = add_involvement(
            seeded_db_path,
            offering_canvas_id=1001,
            classification="initial",
        )
        initial_id = annotation1.id

        # Update with different classification
        annotation2 = add_involvement(
            seeded_db_path,
            offering_canvas_id=1001,
            classification="updated",
        )

        # Should be same record, updated
        assert annotation2.id == initial_id
        assert annotation2.classification == "updated"

        # Should only have one annotation
        annotations = get_involvement_annotations(seeded_db_path, 1001)
        assert len(annotations) == 1


class TestListAnnotations:
    """Tests for list_annotations function."""

    def test_list_annotations_empty(self, seeded_db_path: Path) -> None:
        """Should return empty list when no annotations exist."""
        annotations = list_annotations(seeded_db_path)
        assert annotations == []

    def test_list_all_annotations(self, seeded_db_path: Path) -> None:
        """Should return all annotations when no filter specified."""
        # Add various annotations
        add_lead_instructor(seeded_db_path, 1001, 99999, "lead")
        add_lead_instructor(seeded_db_path, 1002, 88888, "grade_responsible")
        add_involvement(seeded_db_path, 1001, "developer")

        annotations = list_annotations(seeded_db_path)

        assert len(annotations) == 3
        types = {a["annotation_type"] for a in annotations}
        assert types == {"lead_instructor", "involvement"}

    def test_list_annotations_filter_by_offering(self, seeded_db_path: Path) -> None:
        """Should filter annotations by offering."""
        # Add annotations to different offerings
        add_lead_instructor(seeded_db_path, 1001, 99999, "lead")
        add_lead_instructor(seeded_db_path, 1002, 88888, "lead")
        add_involvement(seeded_db_path, 1001, "developer")

        annotations = list_annotations(seeded_db_path, offering_canvas_id=1001)

        assert len(annotations) == 2
        for a in annotations:
            assert a["offering_canvas_id"] == 1001


class TestRemoveAnnotations:
    """Tests for remove annotation functions."""

    def test_remove_lead_instructor_annotation(self, seeded_db_path: Path) -> None:
        """Should remove a lead instructor annotation."""
        annotation = add_lead_instructor(seeded_db_path, 1001, 99999, "lead")

        remove_lead_instructor_annotation(seeded_db_path, annotation.id)

        annotations = get_lead_instructor_annotations(seeded_db_path)
        assert len(annotations) == 0

    def test_remove_lead_instructor_not_found(self, seeded_db_path: Path) -> None:
        """Should raise error if annotation doesn't exist."""
        with pytest.raises(AnnotationNotFoundError) as exc_info:
            remove_lead_instructor_annotation(seeded_db_path, 9999)

        assert exc_info.value.annotation_id == 9999
        assert "Lead instructor" in exc_info.value.annotation_type

    def test_remove_involvement_annotation(self, seeded_db_path: Path) -> None:
        """Should remove an involvement annotation."""
        annotation = add_involvement(seeded_db_path, 1001, "developer")

        remove_involvement_annotation(seeded_db_path, annotation.id)

        annotations = get_involvement_annotations(seeded_db_path)
        assert len(annotations) == 0

    def test_remove_involvement_not_found(self, seeded_db_path: Path) -> None:
        """Should raise error if annotation doesn't exist."""
        with pytest.raises(AnnotationNotFoundError):
            remove_involvement_annotation(seeded_db_path, 9999)

    def test_remove_annotation_by_type(self, seeded_db_path: Path) -> None:
        """Should remove annotation using type parameter."""
        ann1 = add_lead_instructor(seeded_db_path, 1001, 99999, "lead")
        ann2 = add_involvement(seeded_db_path, 1001, "developer")

        # Remove lead instructor by type
        remove_annotation(seeded_db_path, ann1.id, "lead_instructor")
        assert len(get_lead_instructor_annotations(seeded_db_path)) == 0
        assert len(get_involvement_annotations(seeded_db_path)) == 1

        # Remove involvement by type
        remove_annotation(seeded_db_path, ann2.id, "involvement")
        assert len(get_involvement_annotations(seeded_db_path)) == 0

    def test_remove_annotation_invalid_type(self, seeded_db_path: Path) -> None:
        """Should raise error for invalid annotation type."""
        with pytest.raises(ValueError) as exc_info:
            remove_annotation(seeded_db_path, 1, "invalid_type")

        assert "Invalid annotation type" in str(exc_info.value)


class TestAnnotationModels:
    """Tests for annotation model to_dict methods."""

    def test_lead_instructor_to_dict(self, seeded_db_path: Path) -> None:
        """LeadInstructorAnnotation.to_dict should include all fields."""
        annotation = add_lead_instructor(seeded_db_path, 1001, 99999, "lead")

        data = annotation.to_dict()

        assert data["id"] == annotation.id
        assert data["annotation_type"] == "lead_instructor"
        assert data["offering_canvas_id"] == 1001
        assert data["person_canvas_id"] == 99999
        assert data["designation"] == "lead"
        assert "created_at" in data
        assert "updated_at" in data

    def test_involvement_to_dict(self, seeded_db_path: Path) -> None:
        """InvolvementAnnotation.to_dict should include all fields."""
        annotation = add_involvement(seeded_db_path, 1001, "course developer")

        data = annotation.to_dict()

        assert data["id"] == annotation.id
        assert data["annotation_type"] == "involvement"
        assert data["offering_canvas_id"] == 1001
        assert data["classification"] == "course developer"
        assert "created_at" in data
        assert "updated_at" in data


class TestMultipleAnnotationsPerOffering:
    """Tests for handling multiple annotations on same offering."""

    def test_multiple_lead_instructors_different_people(self, seeded_db_path: Path) -> None:
        """Should allow multiple lead instructor annotations for different people."""
        add_lead_instructor(seeded_db_path, 1001, 99999, "lead")
        add_lead_instructor(seeded_db_path, 1001, 88888, "grade_responsible")

        annotations = get_lead_instructor_annotations(seeded_db_path, 1001)

        assert len(annotations) == 2
        people = {a.person_canvas_id for a in annotations}
        assert people == {99999, 88888}

    def test_involvement_is_single_per_offering(self, seeded_db_path: Path) -> None:
        """Should only have one involvement annotation per offering (updates existing)."""
        add_involvement(seeded_db_path, 1001, "first")
        add_involvement(seeded_db_path, 1001, "second")

        annotations = get_involvement_annotations(seeded_db_path, 1001)

        # Should only have one (the second one updated the first)
        assert len(annotations) == 1
        assert annotations[0].classification == "second"
