# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

canvas-ledger (`cl`) is a local CLI tool that maintains a queryable historical ledger of Canvas LMS metadata. It answers questions Canvas cannot: "What courses did I teach in 2022?", "When did this student drop?", "Who was lead instructor across my co-taught courses?"

**Core design principle: Dual-truth model**
- **Observed truth**: Data from Canvas, stored immutably with timestamps. Never modified.
- **Declared truth**: User annotations (lead instructor, involvement, course aliases). Stored separately, survives re-ingestion.

This separation is fundamental—queries return both, clearly distinguished.

## Tech Stack

- **Python 3.13+** with **uv** for environment/dependency management
- **Typer** CLI framework (Click-based)
- **SQLModel** (SQLAlchemy + Pydantic) for ORM
- **Alembic** for database migrations
- **SQLite** database (local-first, no cloud dependencies)
- **mkdocs-material** for documentation site

## Commands

```bash
# Always use `uv`, never `pip` or the `uv pip` interface
uv sync                              # Install dependencies
uv run cl <command>                  # Run CLI
uv run pytest                        # All tests
uv run pytest tests/unit/ -k "name"  # Specific tests
uv run ruff check src/ tests/        # Lint
uv run ruff format src/ tests/       # Format
uv run mypy src/                     # Type check

# Documentation
uv sync --group docs                 # Install docs deps
uv run mkdocs serve                  # Preview at localhost:8000
uv run mkdocs gh-deploy              # Deploy to GitHub Pages
```

## Architecture

```
src/cl/
├── cli/           # Typer commands (one file per command group)
├── canvas/        # Canvas API client (read-only, uses canvasapi library)
├── ledger/        # Core: models, ingestion, queries, store
├── annotations/   # Declared truth: lead instructor, involvement, aliases
├── export/        # JSON/CSV formatters
├── config/        # Settings and secrets (1Password or env var)
└── migrations/    # Alembic migrations (forward-only)
```

### Key Patterns

**CLI structure**: Each `cli/*_cmd.py` defines a Typer sub-app. `main.py` assembles them. Import `cli_error()`, `cli_success()`, `cli_warning()` from `cli/output.py` (not main.py—causes circular imports).

**Ingestion is idempotent**: `ledger/ingest.py` uses upsert patterns. Safe to run repeatedly. Changes recorded in `change_log` table for drift detection.

**Canvas IDs as foreign keys in annotations**: Annotations reference `canvas_course_id`, `canvas_user_id` etc., not internal database PKs. This allows annotations to survive database rebuilds and re-ingestion.

**All queries return dataclasses**: `ledger/queries.py` returns structured objects with `to_dict()` methods. `export/formatters.py` converts to JSON/CSV.

## Design Principles (from Constitution)

These are non-negotiable constraints, not suggestions:

1. **Metadata only** — No course content (files, modules, assignments). Out of scope.
2. **Never modify observed data** — Canvas data is immutable once recorded. Corrections go in annotations.
3. **Historical accuracy over convenience** — Preserve all changes, timestamps, drift. Never delete.
4. **Local-first** — SQLite database. No cloud dependencies after ingestion.
5. **CLI-first, composable** — All features via CLI. Support JSON/CSV output for piping.
6. **Correctness over cleverness** — Explicit logic, no inference for roles/responsibility.

## File Locations

- Config: `~/.config/cl/config.toml`
- Database: `~/.local/share/cl/ledger.db` (configurable)
- Docs source: `mkdocs/docs/`

## Testing

Tests are in `tests/unit/` and `tests/integration/`. Integration tests use a real SQLite database (in-memory or temp file). Mock Canvas API responses, not the database layer.

## Documentation

Docs site uses mkdocs-material with mkdocs-typer2 for auto-generated CLI reference. Source in `mkdocs/docs/`. The CLI reference page (`cli/reference.md`) auto-generates from Typer docstrings—keep command/option help text high quality.

## References

For deeper context on design decisions and requirements:

@.specify/memory/constitution.md — Core principles and non-negotiable constraints
@docs/pdd.md — Product design document with canonical queries and phased implementation
@specs/000-canvas-ledger-core/spec.md — Functional specification with user stories
@specs/000-canvas-ledger-core/plan.md — Technical architecture and implementation plan
@specs/000-canvas-ledger-core/tasks.md — Task breakdown with completion status

Session logs in `docs/sessions/` (gitignored) contain development history and decision context from previous Claude Code sessions.
