"""Output formatters for canvas-ledger.

Provides consistent formatting for JSON, CSV, and human-readable table output.
All output goes to stdout for composability with shell pipelines.
"""

from __future__ import annotations

import csv
import io
import json
import sys
from typing import Any, TextIO


def to_json(
    data: list[dict[str, Any]] | dict[str, Any],
    indent: int = 2,
    output: TextIO | None = None,
) -> str:
    """Format data as JSON and write to output.

    Args:
        data: Data to format (list of dicts or single dict).
        indent: JSON indentation level.
        output: Output stream (defaults to stdout).

    Returns:
        The JSON string.
    """
    json_str = json.dumps(data, indent=indent, default=str)

    if output is None:
        output = sys.stdout

    output.write(json_str)
    output.write("\n")

    return json_str


def to_csv(
    data: list[dict[str, Any]],
    headers: list[str] | None = None,
    output: TextIO | None = None,
) -> str:
    """Format data as CSV and write to output.

    Args:
        data: List of dictionaries to format.
        headers: Column headers. If None, uses keys from first row.
        output: Output stream (defaults to stdout).

    Returns:
        The CSV string.
    """
    if not data:
        return ""

    if headers is None:
        headers = list(data[0].keys())

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()

    for row in data:
        # Convert any non-string values to strings
        row_str = {k: _format_value(v) for k, v in row.items()}
        writer.writerow(row_str)

    csv_str = buffer.getvalue()

    if output is None:
        output = sys.stdout

    output.write(csv_str)

    return csv_str


def _format_value(value: Any) -> str:
    """Format a value for CSV output."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def to_table(
    data: list[dict[str, Any]],
    headers: list[str] | None = None,
    output: TextIO | None = None,
    max_width: int | None = None,
) -> str:
    """Format data as a human-readable table and write to output.

    Uses a simple column-aligned format without external dependencies.

    Args:
        data: List of dictionaries to format.
        headers: Column headers. If None, uses keys from first row.
        output: Output stream (defaults to stdout).
        max_width: Maximum column width (truncates with ellipsis).

    Returns:
        The formatted table string.
    """
    if not data:
        return "(no data)\n"

    if headers is None:
        headers = list(data[0].keys())

    # Format all values as strings
    rows: list[list[str]] = []
    for row in data:
        formatted_row = []
        for h in headers:
            value = row.get(h)
            formatted = _format_value(value)
            if max_width and len(formatted) > max_width:
                formatted = formatted[: max_width - 3] + "..."
            formatted_row.append(formatted)
        rows.append(formatted_row)

    # Calculate column widths
    col_widths: list[int] = []
    for i, header in enumerate(headers):
        max_col_width = len(header)
        for formatted_row in rows:
            max_col_width = max(max_col_width, len(formatted_row[i]))
        col_widths.append(max_col_width)

    # Build format string
    format_parts = [f"{{:<{w}}}" for w in col_widths]
    format_str = "  ".join(format_parts)

    # Build table
    lines: list[str] = []

    # Header
    header_line = format_str.format(*headers)
    lines.append(header_line)

    # Separator
    sep_parts = ["-" * w for w in col_widths]
    sep_line = "  ".join(sep_parts)
    lines.append(sep_line)

    # Data rows
    for data_row in rows:
        lines.append(format_str.format(*data_row))

    table_str = "\n".join(lines) + "\n"

    if output is None:
        output = sys.stdout

    output.write(table_str)

    return table_str


def format_output(
    data: list[dict[str, Any]] | dict[str, Any],
    fmt: str = "table",
    headers: list[str] | None = None,
    output: TextIO | None = None,
) -> str:
    """Format data in the specified format.

    Convenience function that dispatches to the appropriate formatter.

    Args:
        data: Data to format.
        fmt: Output format ('json', 'csv', or 'table').
        headers: Column headers for CSV/table output.
        output: Output stream (defaults to stdout).

    Returns:
        The formatted string.

    Raises:
        ValueError: If format is not recognized.
    """
    if fmt == "json":
        return to_json(data, output=output)
    elif fmt == "csv":
        data_list: list[dict[str, Any]] = [data] if isinstance(data, dict) else data
        return to_csv(data_list, headers=headers, output=output)
    elif fmt == "table":
        data_list = [data] if isinstance(data, dict) else data
        return to_table(data_list, headers=headers, output=output)
    else:
        raise ValueError(f"Unknown format: {fmt}. Use 'json', 'csv', or 'table'.")
