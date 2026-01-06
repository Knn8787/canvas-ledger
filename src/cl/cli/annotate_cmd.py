"""Annotate commands for canvas-ledger CLI.

Provides commands for managing annotations (declared truth).
"""

from __future__ import annotations

from typing import Annotated

import typer

from cl.annotations.manager import (
    AnnotationError,
    add_involvement,
    add_lead_instructor,
    list_annotations,
    remove_annotation,
)
from cl.cli.main import cli_error, cli_success
from cl.config.settings import load_settings
from cl.export.formatters import format_output

app = typer.Typer(
    name="annotate",
    help="Manage annotations (declared truth).",
    no_args_is_help=True,
)


def _ensure_db_exists() -> None:
    """Ensure the database exists, or error out."""
    settings = load_settings()
    if not settings.db_path.exists():
        cli_error(f"Database not found at {settings.db_path}. Run 'cl db migrate' first.")


@app.command("lead")
def lead(
    offering_id: Annotated[
        int,
        typer.Argument(help="Canvas course ID of the offering."),
    ],
    person_id: Annotated[
        int,
        typer.Argument(help="Canvas user ID of the lead instructor."),
    ],
    designation: Annotated[
        str,
        typer.Option(
            "--designation",
            "-d",
            help="Designation type: 'lead' or 'grade_responsible'.",
        ),
    ] = "lead",
) -> None:
    """Declare the lead/grade-responsible instructor for an offering.

    This annotation clarifies who is primarily responsible for the course
    when Canvas data shows multiple instructors or when the Canvas role
    doesn't reflect reality.

    Example:
        cl annotate lead 12345 67890 --designation lead
    """
    _ensure_db_exists()
    settings = load_settings()

    try:
        annotation = add_lead_instructor(
            settings.db_path,
            offering_canvas_id=offering_id,
            person_canvas_id=person_id,
            designation=designation,
        )
        cli_success(f"Lead instructor annotation added (ID: {annotation.id}).")
        typer.echo(f"  Offering: {annotation.offering_canvas_id}")
        typer.echo(f"  Person:   {annotation.person_canvas_id}")
        typer.echo(f"  Type:     {annotation.designation.value}")
    except AnnotationError as e:
        cli_error(str(e))
    except ValueError as e:
        cli_error(str(e))


@app.command("involvement")
def involvement(
    offering_id: Annotated[
        int,
        typer.Argument(help="Canvas course ID of the offering."),
    ],
    classification: Annotated[
        str,
        typer.Argument(help="Involvement classification (e.g., 'developed course')."),
    ],
) -> None:
    """Classify your involvement in an offering.

    This annotation allows you to describe your actual involvement when
    the Canvas role doesn't tell the full story.

    Examples:
        cl annotate involvement 12345 "developed course"
        cl annotate involvement 12345 "guest lecturer"
        cl annotate involvement 12345 "course coordinator"
    """
    _ensure_db_exists()
    settings = load_settings()

    try:
        annotation = add_involvement(
            settings.db_path,
            offering_canvas_id=offering_id,
            classification=classification,
        )
        cli_success(f"Involvement annotation added (ID: {annotation.id}).")
        typer.echo(f"  Offering:       {annotation.offering_canvas_id}")
        typer.echo(f"  Classification: {annotation.classification}")
    except AnnotationError as e:
        cli_error(str(e))


@app.command("list")
def list_cmd(
    offering_id: Annotated[
        int | None,
        typer.Option(
            "--offering",
            "-o",
            help="Filter by Canvas course ID.",
        ),
    ] = None,
    fmt: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Output format (table, json, csv).",
        ),
    ] = "table",
) -> None:
    """List annotations.

    By default, lists all annotations. Use --offering to filter by course.

    Examples:
        cl annotate list
        cl annotate list --offering 12345
        cl annotate list --format json
    """
    _ensure_db_exists()
    settings = load_settings()

    annotations = list_annotations(settings.db_path, offering_canvas_id=offering_id)

    if not annotations:
        if offering_id:
            typer.echo(f"No annotations found for offering {offering_id}.")
        else:
            typer.echo("No annotations found.")
        return

    # Format output
    if fmt == "table":
        # Custom table output for annotations
        typer.echo(f"{'ID':<6} {'Type':<16} {'Offering':<12} {'Details':<40}")
        typer.echo("-" * 76)
        for ann in annotations:
            ann_type = ann["annotation_type"]
            offering = str(ann["offering_canvas_id"])
            if ann_type == "lead_instructor":
                details = f"Person: {ann['person_canvas_id']}, {ann['designation']}"
            else:
                details = ann.get("classification", "")
            typer.echo(f"{ann['id']:<6} {ann_type:<16} {offering:<12} {details:<40}")
    else:
        format_output(annotations, fmt=fmt)


@app.command("remove")
def remove(
    annotation_id: Annotated[
        int,
        typer.Argument(help="ID of the annotation to remove."),
    ],
    annotation_type: Annotated[
        str,
        typer.Option(
            "--type",
            "-t",
            help="Type of annotation: 'lead_instructor' or 'involvement'.",
        ),
    ] = "lead_instructor",
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-y",
            help="Skip confirmation prompt.",
        ),
    ] = False,
) -> None:
    """Remove an annotation by ID.

    Examples:
        cl annotate remove 1 --type lead_instructor
        cl annotate remove 2 --type involvement --force
    """
    _ensure_db_exists()
    settings = load_settings()

    # Confirm removal unless --force
    if not force:
        confirm = typer.confirm(f"Remove {annotation_type} annotation ID {annotation_id}?")
        if not confirm:
            typer.echo("Cancelled.")
            raise typer.Exit()

    try:
        remove_annotation(settings.db_path, annotation_id, annotation_type)
        cli_success(f"Annotation {annotation_id} removed.")
    except AnnotationError as e:
        cli_error(str(e))
    except ValueError as e:
        cli_error(str(e))
