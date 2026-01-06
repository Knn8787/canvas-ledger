# `canvas-ledger` Product Design Document

## Goal

Build a Python CLI tool that maintains a **local, queryable ledger of Canvas metadata** so you can answer historically meaningful questions about your Auburn involvement that are hard to answer in Canvas (e.g., “what courses have I been involved in, when, and what was my role?”). For deeper explanations (e.g., “why did Jimmy get a D?”), you’ll still jump into Canvas.

## Explicit non-goals

* **No content syncing** (files/modules/pages). You author locally and push to Canvas.
* No attempt to replace Canvas gradebook UI or explain outcomes.
* No enterprise “platform” ambitions (no heavy UI, no orchestration hub).

---

## Design targets

### Canonical query set (what `cl` must support)

These drive ingestion scope, data modeling, and exports.

1. **My Auburn involvement timeline**
   What offerings have I been involved in, when, and in what capacity?
   (Shows *observed Canvas roles* + *declared involvement overrides*.)

2. **Person participation history**
   For a given person, what offerings/terms were they in, and what role/state?

3. **Person performance summary (high-level)**
   For a given person, how did they do across offerings (final/current grade/score, Canvas-reported summary only)?

4. **Offering responsibility clarity**
   For an offering, who was **lead/grade-responsible** (same concept) vs other instructors, and what does Canvas report?

5. **Offering composition snapshot**
   For an offering, who was enrolled (by section), in what roles/states?

6. **Enrollment drift / lifecycle**
   What changed over time (adds/drops/state transitions) for a person or offering?

7. **Course identity evolution hooks**
   Support annotations/mappings for renumbering, special topics, aliases—enough to keep longitudinal history coherent (enriched over time).

---

## Stack (confirmed)

* Python 3.13+
* `uv` for reproducible environments
* CLI: **Typer** (Click-based)
* Canvas API:
  * Primary: `canvasapi`
  * Fallback: `httpx` for edge endpoints/params
* Database: **SQLite** (WAL, FK on, busy timeout)
* ORM: **SQLModel** (SQLAlchemy underneath) + raw SQL for bulk operations where clearer
* Migrations: **Alembic**
* Testing: pytest (+ optional recorded HTTP fixtures later)

**Security / keys**

* Canvas token retrieval via **1Password** (pluggable secret provider; ingestion code never assumes env vars). Existing code provided on request.

---

## Core architectural principles

### 1) Canvas as observed truth; your annotations as declared truth

`cl` stores two kinds of facts side-by-side:

* **Observed**: what Canvas reports (roles, states, ids)
* **Declared**: your corrections/intent (lead/grade-responsible person, your “involvement” classification)

Canvas roles are never overwritten—only complemented.

### 2) Idempotent ingestion + drift-aware state tracking

You will run ingestion:

* at semester start
* mid-semester (add/drop)
* later for historical backfill

So every ingest must be safe to repeat and must preserve change history in a minimal, controlled way.

### 3) Composability-first interfaces

Even though other tools may consume `cl` data later, **they should not read `cl`’s DB directly**.

Design implication for `cl`:

* Provide stable **export** and **query** commands that emit JSON/CSV.
* Keep the internal schema free to evolve.
* Optional import commands may exist (for normalized artifacts), but `cl` stays focused on Canvas metadata.

---

## High-level functional scope

### A) Discovery layer (“My Canvas footprint”)

During development, start by ingesting **all Canvas courses visible to you**, regardless of your role (teacher/TA/student). This provides a stable catalog of offerings and enables your personal timeline query early.

### B) Deep ingestion layer (selected offerings)

Over time, add the ability to “go deeper” on a subset:

* sections
* enrollments
* people encountered through those enrollments
* (later) performance summaries

This avoids pulling student data broadly until you choose.

### C) Annotation layer (responsibility & identity)

Support an override/annotation mechanism for:

* offering lead/grade-responsible person (equivalent)
* your involvement label in an offering (lead / co-instructor / TA / student / etc.)
* course identity aliases and “special topics” course-instance mapping hooks

---

## CLI surface (conceptual)

`cl` should feel like a toolbox, not an app. Example command families:

### 1) Database ops

* `cl db migrate`
* `cl db status`
* `cl db reset` (dev only)

### 2) Ingestion

* `cl ingest courses` (all courses visible to you)
* `cl ingest offering <offering-id>` (deep ingest one)
* `cl ingest term <term>` (deep ingest selected set by term; later)

### 3) Overrides / annotations

* `cl annotate offering <id> --lead <person>` (or via YAML file)
* `cl annotate person <id> …` (optional)
* `cl annotate alias …` (course identity hooks)

### 4) Query / export

* `cl query my-timeline`
* `cl query person-history <person>`
* `cl query offering-roster <offering>`
* `cl query offering-responsibility <offering>`
* `cl export … --format json|csv`

(Exact command names can evolve; the intent is stable.)

---

## Implementation plan (phased)

### Phase 0: Scaffolding & conventions

* Establish project structure: `canvas/`, `db/`, `ingest/`, `cli/`, `config/`
* Define identifier conventions and stable export formats (versioned)
* Implement settings + secret provider interface (1Password-backed later)

**Exit criteria**

* `cl` runs, reads config, connects to DB
* migrations wired and runnable

---

### Phase 1: Migrations + DB foundation

* Alembic initialized and configured against SQLModel metadata
* SQLite configured (WAL/FK/busy timeout)
* `ingest_run` tracking established (start/end/status/counts)

**Exit criteria**

* repeatable `db migrate` from empty DB
* ingest runs are logged with deterministic metadata

---

### Phase 2: Offerings ingestion (“all visible courses”)

* Ingest all courses visible to you:

  * offering identifiers
  * term association where available
  * course code/name metadata
* Ingest **your observed roles** for each offering (teacher/TA/student, etc.)

**Exit criteria**

* Query #1 (your involvement timeline) can be answered from local data
* Re-running ingestion updates offering metadata without duplication

---

### Phase 3: Annotation / responsibility overrides

* Add declared truth layer:

  * offering lead/grade-responsible person
  * your involvement label override
* Overrides stored in DB and/or YAML (implementation choice), but always visible in query output alongside observed roles.

**Exit criteria**

* Query #4 (offering responsibility clarity) is reliably answerable even when Canvas roles don’t reflect reality

---

### Phase 4: Deep ingest for selected offerings (sections + enrollments)

* Add “deep ingest” command(s) that:

  * fetch sections for an offering
  * fetch enrollments for each section (roles + workflow_state)
  * ingest people encountered through enrollments
* Implement drift handling:

  * idempotent upserts
  * “last seen” timestamps
  * tombstones/inactive markers for missing enrollments after a scoped run

**Exit criteria**

* Queries #2, #5, #6 are answerable for ingested offerings
* Mid-semester re-ingest reflects adds/drops cleanly

---

### Phase 5: Performance summaries (high-level only)

* Ingest Canvas-reported summary grade fields where accessible (final/current score/grade)
* Store as “Canvas-reported” values (no interpretation)

**Exit criteria**

* Query #3 is answerable: “how did Jimmy do?” at a summary level

---

### Phase 6: Course identity evolution hooks

* Provide a lightweight mechanism to maintain continuity across:

  * renumbering / title changes
  * “special topics” offerings representing different real courses
  * local aliases (e.g., “BET 3510”)
* This starts as annotations/mappings; it can evolve later without breaking earlier data.

**Exit criteria**

* Query #7 is supported enough to keep historical views coherent and searchable

---

## Operational behaviors to bake in early

* **Idempotency everywhere**: safe to re-run at any time
* **Scoped tombstoning**: only mark missing enrollments inactive after completing the relevant scope (e.g., “this section’s enrollments”)
* **Provenance**: store ingest run id/time on updated entities (at least last seen)
* **Auditability**: clear logs + ingest_run summaries
* **Export stability**: JSON/CSV outputs are versioned contracts; downstream tools rely on exports, not internal tables

---

*updated: Jan 6, 2026*

