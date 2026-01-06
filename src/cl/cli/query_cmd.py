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
from cl.ledger.queries import get_my_timeline

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
    (most recent first). Shows your role(s) in each offering.

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
    headers = [
        "offering_name",
        "offering_code",
        "term_name",
        "roles",
        "workflow_state",
    ]

    format_output(data, fmt=fmt.value, headers=headers)
