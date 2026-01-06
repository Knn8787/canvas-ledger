"""Query commands for canvas-ledger CLI.

Provides commands for querying the local ledger.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated

import typer

from cl.cli.main import cli_error
from cl.config.settings import load_settings
from cl.export.formatters import format_output
from cl.ledger.queries import (
    get_my_timeline,
    get_offering_by_canvas_id,
    get_offering_responsibility,
)

app = typer.Typer(
    name="query",
    help="Query the local ledger.",
    no_args_is_help=True,
)


class OutputFormat(str, Enum):
    """Output format options."""

    json = "json"
    csv = "csv"
    table = "table"


@app.command("my-timeline")
def my_timeline(
    fmt: Annotated[
        OutputFormat,
        typer.Option(
            "--format",
            "-f",
            help="Output format.",
        ),
    ] = OutputFormat.table,
    term: Annotated[
        str | None,
        typer.Option(
            "--term",
            "-t",
            help="Filter by term name (case-insensitive contains match).",
        ),
    ] = None,
    role: Annotated[
        str | None,
        typer.Option(
            "--role",
            "-r",
            help="Filter by role (exact match: teacher, ta, student, etc.).",
        ),
    ] = None,
) -> None:
    """Show your involvement timeline across all offerings.

    Displays all offerings you have enrollments in, sorted by term
    (most recent first). Shows your role(s) in each offering, along
    with any declared involvement annotations.

    This is the primary answer to: "What courses have I been involved in?"
    """
    settings = load_settings()

    if not settings.db_path.exists():
        cli_error(
            f"Database not found at {settings.db_path}. "
            "Run 'cl db migrate' to initialize, then 'cl ingest catalog' to populate."
        )

    entries = get_my_timeline(
        db_path=settings.db_path,
        term_filter=term,
        role_filter=role,
    )

    if not entries:
        if term or role:
            typer.echo("No offerings found matching the specified filters.")
        else:
            typer.echo("No offerings found. Run 'cl ingest catalog' to fetch your courses.")
        return

    # Convert to list of dicts for formatting
    data = [entry.to_dict() for entry in entries]

    # Define headers for table/CSV output (ordered subset of fields)
    # Include declared_involvement to show both observed and declared data
    headers = [
        "offering_name",
        "offering_code",
        "term_name",
        "observed_roles",
        "declared_involvement",
        "workflow_state",
    ]

    format_output(data, fmt=fmt.value, headers=headers)


@app.command("offering")
def offering(
    offering_id: Annotated[
        int,
        typer.Argument(help="Canvas course ID of the offering."),
    ],
    instructors: Annotated[
        bool,
        typer.Option(
            "--instructors",
            "-i",
            help="Show instructor responsibility information.",
        ),
    ] = False,
    fmt: Annotated[
        OutputFormat,
        typer.Option(
            "--format",
            "-f",
            help="Output format.",
        ),
    ] = OutputFormat.table,
) -> None:
    """Query information about a specific offering.

    By default, shows basic offering information.
    Use --instructors to see who is responsible for the course.

    Note: Full roster information requires deep ingestion (Phase 3).
    Currently shows instructor information from your own enrollments
    and any declared lead instructor annotations.

    Examples:
        cl query offering 12345
        cl query offering 12345 --instructors
        cl query offering 12345 --instructors --format json
    """
    settings = load_settings()

    if not settings.db_path.exists():
        cli_error(
            f"Database not found at {settings.db_path}. "
            "Run 'cl db migrate' to initialize, then 'cl ingest catalog' to populate."
        )

    # First check if offering exists
    off = get_offering_by_canvas_id(settings.db_path, offering_id)
    if off is None:
        cli_error(
            f"Offering {offering_id} not found in local ledger. "
            "Run 'cl ingest catalog' to fetch courses."
        )

    if instructors:
        # Show instructor responsibility information
        resp = get_offering_responsibility(settings.db_path, offering_id)
        if resp is None:
            cli_error(f"Could not get responsibility info for offering {offering_id}.")

        if fmt == OutputFormat.json:
            format_output(resp.to_dict(), fmt="json")
        elif fmt == OutputFormat.csv:
            # Flatten for CSV
            data = {
                "canvas_course_id": resp.canvas_course_id,
                "offering_name": resp.offering_name,
                "offering_code": resp.offering_code,
                "observed_instructor_roles": ", ".join(i["role"] for i in resp.observed_instructors)
                if resp.observed_instructors
                else "",
                "declared_lead_person_id": resp.declared_lead["person_canvas_id"]
                if resp.declared_lead
                else "",
                "declared_lead_designation": resp.declared_lead["designation"]
                if resp.declared_lead
                else "",
            }
            format_output([data], fmt="csv")
        else:
            # Table output
            typer.echo(f"Offering: {resp.offering_name}")
            typer.echo(f"Code: {resp.offering_code or '(none)'}")
            typer.echo(f"Canvas ID: {resp.canvas_course_id}")
            typer.echo("")

            typer.secho("Observed Instructors (your enrollments):", bold=True)
            if resp.observed_instructors:
                for inst in resp.observed_instructors:
                    typer.echo(f"  - Role: {inst['role']}, State: {inst['enrollment_state']}")
            else:
                typer.echo("  (none - you may not have an instructor role in this offering)")
            typer.echo("")

            typer.secho("Declared Lead:", bold=True)
            if resp.declared_lead:
                typer.echo(f"  Person Canvas ID: {resp.declared_lead['person_canvas_id']}")
                typer.echo(f"  Designation: {resp.declared_lead['designation']}")
                typer.echo(f"  Added: {resp.declared_lead['created_at']}")
            else:
                typer.echo("  (not set - use 'cl annotate lead' to declare)")
    else:
        # Show basic offering info
        data = off.to_dict()
        if fmt == OutputFormat.json:
            format_output(data, fmt="json")
        elif fmt == OutputFormat.csv:
            format_output([data], fmt="csv")
        else:
            typer.echo(f"Name: {off.name}")
            typer.echo(f"Code: {off.code or '(none)'}")
            typer.echo(f"Canvas ID: {off.canvas_course_id}")
            typer.echo(f"Workflow State: {off.workflow_state}")
            typer.echo(
                f"Observed At: {off.observed_at.isoformat() if off.observed_at else '(unknown)'}"
            )
            typer.echo(
                f"Last Seen At: {off.last_seen_at.isoformat() if off.last_seen_at else '(unknown)'}"
            )
