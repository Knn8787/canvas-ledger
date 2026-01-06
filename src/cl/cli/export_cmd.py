"""Export commands for canvas-ledger CLI.

Provides commands for exporting data in structured formats.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated

import typer

from cl.cli.main import cli_error
from cl.config.settings import load_settings
from cl.export.formatters import format_output
from cl.ledger.queries import get_offerings_with_terms

app = typer.Typer(
    name="export",
    help="Export data in structured formats.",
    no_args_is_help=True,
)


class ExportFormat(str, Enum):
    """Export format options."""

    json = "json"
    csv = "csv"


@app.command("offerings")
def offerings(
    fmt: Annotated[
        ExportFormat,
        typer.Option(
            "--format",
            "-f",
            help="Output format.",
        ),
    ] = ExportFormat.json,
) -> None:
    """Export all offerings with term information.

    Exports offering data suitable for use by other tools.
    Includes Canvas course ID, name, code, workflow state,
    and term information.
    """
    settings = load_settings()

    if not settings.db_path.exists():
        cli_error(
            f"Database not found at {settings.db_path}. "
            "Run 'cl db migrate' to initialize, then 'cl ingest catalog' to populate."
        )

    data = get_offerings_with_terms(settings.db_path)

    if not data:
        typer.echo("No offerings found. Run 'cl ingest catalog' first.", err=True)
        return

    # Define headers for CSV output
    headers = [
        "canvas_course_id",
        "name",
        "code",
        "workflow_state",
        "term_name",
        "term_start_date",
        "term_end_date",
        "observed_at",
        "last_seen_at",
    ]

    format_output(data, fmt=fmt.value, headers=headers)
