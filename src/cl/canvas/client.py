"""Canvas API client for canvas-ledger.

Provides a read-only interface to the Canvas LMS API.
Uses the canvasapi library for core functionality.

All API calls are GET requests - cl never mutates Canvas state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from canvasapi import Canvas
from canvasapi.exceptions import CanvasException, InvalidAccessToken, ResourceDoesNotExist

if TYPE_CHECKING:
    from canvasapi.course import Course as CanvasCourse
    from canvasapi.enrollment import Enrollment as CanvasEnrollmentObj
    from canvasapi.enrollment_term import EnrollmentTerm


class CanvasClientError(Exception):
    """Base exception for Canvas client errors."""

    pass


class CanvasAuthenticationError(CanvasClientError):
    """Raised when Canvas authentication fails."""

    pass


class CanvasNotFoundError(CanvasClientError):
    """Raised when a requested resource is not found."""

    pass


@dataclass
class CourseData:
    """Normalized course data from Canvas API."""

    canvas_course_id: int
    name: str
    code: str | None
    workflow_state: str
    term_id: int | None
    enrollments: list[EnrollmentData]


@dataclass
class EnrollmentData:
    """Normalized enrollment data from Canvas API."""

    canvas_enrollment_id: int
    role: str
    enrollment_state: str
    course_id: int


@dataclass
class TermData:
    """Normalized term data from Canvas API."""

    canvas_term_id: int
    name: str
    start_date: datetime | None
    end_date: datetime | None


class CanvasClient:
    """Client for interacting with Canvas API.

    This client is read-only - it never modifies Canvas state.
    """

    def __init__(self, base_url: str, api_token: str) -> None:
        """Initialize Canvas client.

        Args:
            base_url: Canvas instance base URL (e.g., "https://canvas.instructure.com").
            api_token: Canvas API access token.
        """
        self._base_url = base_url.rstrip("/")
        self._canvas = Canvas(self._base_url, api_token)

    def _parse_datetime(self, value: str | None) -> datetime | None:
        """Parse a datetime string from Canvas API response."""
        if not value:
            return None
        try:
            # Canvas returns ISO 8601 format
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    def _extract_enrollments(self, course: CanvasCourse) -> list[EnrollmentData]:
        """Extract enrollment data from a course object."""
        enrollments: list[EnrollmentData] = []

        # The enrollments attribute is populated when include[]=enrollments is used
        raw_enrollments: list[CanvasEnrollmentObj] = getattr(course, "enrollments", []) or []

        for enrollment in raw_enrollments:
            # Handle both dict and object access patterns
            if isinstance(enrollment, dict):
                enrollment_id = enrollment.get("id")
                role = enrollment.get("role", enrollment.get("type", "unknown"))
                state = enrollment.get("enrollment_state", "unknown")
            else:
                enrollment_id = getattr(enrollment, "id", None)
                role = getattr(enrollment, "role", getattr(enrollment, "type", "unknown"))
                state = getattr(enrollment, "enrollment_state", "unknown")

            if enrollment_id:
                enrollments.append(
                    EnrollmentData(
                        canvas_enrollment_id=int(enrollment_id),
                        role=str(role),
                        enrollment_state=str(state),
                        course_id=int(course.id),
                    )
                )

        return enrollments

    def list_my_courses(self) -> list[CourseData]:
        """List all courses visible to the authenticated user.

        Returns all courses regardless of the user's role (teacher, TA, student, etc.).
        Includes enrollment information for the user in each course.

        Returns:
            List of CourseData objects with normalized course information.

        Raises:
            CanvasAuthenticationError: If the API token is invalid.
            CanvasClientError: For other API errors.
        """
        try:
            # Request courses with enrollments included
            courses = self._canvas.get_current_user().get_courses(
                include=["term", "enrollments"],
            )

            result: list[CourseData] = []
            for course in courses:
                # Extract term ID if available
                term_id: int | None = None
                term = getattr(course, "term", None)
                if term:
                    if isinstance(term, dict):
                        term_id = term.get("id")
                    else:
                        term_id = getattr(term, "id", None)

                # Extract enrollments for this user
                enrollments = self._extract_enrollments(course)

                result.append(
                    CourseData(
                        canvas_course_id=int(course.id),
                        name=str(course.name),
                        code=getattr(course, "course_code", None),
                        workflow_state=str(getattr(course, "workflow_state", "available")),
                        term_id=int(term_id) if term_id else None,
                        enrollments=enrollments,
                    )
                )

            return result

        except InvalidAccessToken as e:
            raise CanvasAuthenticationError(
                "Canvas API token is invalid or expired. Please update your token configuration."
            ) from e
        except CanvasException as e:
            raise CanvasClientError(f"Canvas API error: {e}") from e

    def get_term(self, term_id: int) -> TermData | None:
        """Get term details by ID.

        Args:
            term_id: Canvas term (enrollment_term) ID.

        Returns:
            TermData object or None if term not found.

        Raises:
            CanvasAuthenticationError: If the API token is invalid.
            CanvasClientError: For other API errors.
        """
        try:
            # Get the root account to access enrollment terms
            # Note: This requires appropriate permissions
            account = self._canvas.get_account("self")
            term: EnrollmentTerm = account.get_enrollment_term(term_id)

            return TermData(
                canvas_term_id=int(term.id),
                name=str(term.name),
                start_date=self._parse_datetime(getattr(term, "start_at", None)),
                end_date=self._parse_datetime(getattr(term, "end_at", None)),
            )

        except ResourceDoesNotExist:
            return None
        except InvalidAccessToken as e:
            raise CanvasAuthenticationError(
                "Canvas API token is invalid or expired. Please update your token configuration."
            ) from e
        except CanvasException as e:
            # If we can't access terms via account API, try getting term from course
            # This is a fallback for users without account-level access
            raise CanvasClientError(
                f"Failed to retrieve term {term_id}. "
                "You may not have permission to access enrollment terms directly."
            ) from e

    def get_term_from_course(self, course_id: int) -> TermData | None:
        """Get term details from a course.

        This is a fallback method when direct term access is not available.
        Fetches the course and extracts its term information.

        Args:
            course_id: Canvas course ID.

        Returns:
            TermData object or None if course has no term.

        Raises:
            CanvasAuthenticationError: If the API token is invalid.
            CanvasClientError: For other API errors.
        """
        try:
            course = self._canvas.get_course(course_id, include=["term"])
            term = getattr(course, "term", None)

            if not term:
                return None

            if isinstance(term, dict):
                return TermData(
                    canvas_term_id=int(term["id"]),
                    name=str(term.get("name", "Unknown Term")),
                    start_date=self._parse_datetime(term.get("start_at")),
                    end_date=self._parse_datetime(term.get("end_at")),
                )
            else:
                return TermData(
                    canvas_term_id=int(term.id),
                    name=str(getattr(term, "name", "Unknown Term")),
                    start_date=self._parse_datetime(getattr(term, "start_at", None)),
                    end_date=self._parse_datetime(getattr(term, "end_at", None)),
                )

        except ResourceDoesNotExist:
            raise CanvasNotFoundError(f"Course {course_id} not found.") from None
        except InvalidAccessToken as e:
            raise CanvasAuthenticationError(
                "Canvas API token is invalid or expired. Please update your token configuration."
            ) from e
        except CanvasException as e:
            raise CanvasClientError(f"Canvas API error: {e}") from e


def create_client(base_url: str, api_token: str) -> CanvasClient:
    """Factory function to create a Canvas client.

    Args:
        base_url: Canvas instance base URL.
        api_token: Canvas API access token.

    Returns:
        Configured CanvasClient instance.
    """
    return CanvasClient(base_url, api_token)
