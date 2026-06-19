# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

The **single source of truth for database schema migrations** of the APGuru platform
(AP / IB / SAT exam-prep product). It is intentionally **standalone**: it contains no
application code and **no SQLAlchemy models**. Every migration is hand-written raw SQL /
explicit DDL. Migrations were extracted from `apguru-analytics-dashboard` (which no longer
carries them); revision ids were preserved verbatim so existing `alembic_version` pointers
stay valid.

Target DB is **MySQL 8 / InnoDB** (`utf8mb4_0900_ai_ci`), reached with the **sync PyMySQL**
driver (`mysql+pymysql://…`), never aiomysql.

## Commands

```bash
# One-time setup
python -m venv .venv
.venv\Scripts\activate            # Windows;  source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env              # then set DATABASE_URL (or DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME)

# Inspect (read-only, safe against any DB)
alembic current                   # revision the target DB is at
alembic history                   # full chain
alembic heads                     # MUST print exactly ONE head — see "Single head" below

# Apply
alembic upgrade head              # bring DB to latest
alembic upgrade <rev>             # apply up to a specific revision (e.g. alembic upgrade 015)
alembic downgrade -1              # roll back one revision
alembic downgrade <rev>           # roll back to a specific revision

# Preview the SQL without connecting (offline mode; still reads the configured URL for dialect)
alembic upgrade head --sql
alembic upgrade <from>:<to> --sql

# Author a new migration (NEVER --autogenerate; it is disabled)
alembic revision -m "add widget table"
```

There is no build step, linter, or test suite. The closest thing to a "test" is applying a
single migration and rolling it back against a scratch MySQL: `alembic upgrade <rev>` then
`alembic downgrade -1`.

## Architecture & conventions

**Connection resolution** lives entirely in `alembic/env.py`: it prefers `DATABASE_URL`,
otherwise composes `mysql+pymysql://…` from the `DB_*` vars (so an app `.env` can be reused).
The placeholder `sqlalchemy.url` in `alembic.ini` is overridden at runtime and is not used.

**No autogenerate.** `target_metadata = None` by design — there are no models to diff against.
Write `upgrade()` / `downgrade()` by hand with `op.execute(...)`, `op.create_table(...)`,
`op.alter_column(...)`, etc. `alembic revision --autogenerate` is intentionally unsupported.

**The migration chain is one linear, single-headed sequence** (`001 → 002 → … → 030`).
Files are zero-padded sequential; each declares `revision` / `down_revision` as **bare
strings** (`revision = "001"`), *not* the typed annotations the stock `script.py.mako`
emits — match the existing bare style when authoring. Revision ids are decoupled from
authoring dates (the chain was renumbered during extraction, so `Create Date`s are not
monotonic, and a few in-code comments reference old pre-extraction file numbers — e.g.
"006_add_spaced_repetition_table" is actually `010`).

### Single head (the #1 operational hazard)

`alembic heads` must return **exactly one** entry. This repo has twice been bitten by
duplicate-revision multi-heads (the duplicate `005` and duplicate `029`, both resolved — see
README "Migration-history notes"). Before deploying, or after merging any branch that adds a
migration, confirm one head. If there are two, reconcile by rebasing the stray revision's
`down_revision` onto the real head — do not merge-head your way around it.

### Logical foreign keys, not DB constraints

Most cross-table references are plain `BigInteger` columns with **no `ForeignKeyConstraint`**,
enforced in application code instead. This is deliberate, for two recurring reasons documented
inline (e.g. `001_add_error_analysis_tables.py`):

- Several referenced legacy tables (`course`, etc.) are **MyISAM**, which does not support FKs.
- Legacy id columns are often **`BIGINT UNSIGNED`**, incompatible with the signed `BIGINT`
  used here.

Real `ForeignKeyConstraint`s appear only between two Alembic-owned tables (e.g.
`grading_job → ap_exam` in `020`). When adding a reference to a legacy table, follow the
logical-FK convention and note why in a comment.

### This repo owns only some of the schema

Migrations freely `ALTER` and reference tables this repo did **not** create and does not own:
`course` (MyISAM), `class` (PHP-managed), `students`, `tests`, `sub_topics`,
`student_course_mapping`, `student_todo_quiz_mapping`, `online_student_test_answers`, and more.
Touch these surgically — `027` is the model: it widens a single column on `class` via raw
backticked DDL and explicitly warns the rest of the table is owned elsewhere.

### Idempotency & environment drift

Environments diverged before Alembic was introduced, so migrations are written to converge
them safely on re-apply: `CREATE TABLE IF NOT EXISTS` (`015`, `020`),
`INSERT … ON DUPLICATE KEY UPDATE` for seed data (`021`, `022`, `028`), and DELETE-before-INSERT
(`030`). New data/backfill migrations should be similarly safe to run against a DB that may
already be partially in the target state.

### Forward-only in practice

Several `downgrade()`s are intentionally lossy or destructive and say so in comments: `017`
truncates `chat_messages`, `026` deletes all grader rows, `027` truncates briefs over 500 chars,
`024`'s downgrade fails if multi-course plan data exists. Treat downgrades as a dev/staging tool,
not a safe production rollback. The deployment contract is forward-only: the **app does not run
migrations on boot** — a schema-changing deploy must run `alembic upgrade head` from this repo as
an explicit step.

## Authoring rules

- **Named SQL parameters only — never f-strings** in `op.execute` / `text(...)`. For `IN`
  clauses use an expanding bindparam (`sa.bindparam("ids", expanding=True)`), as in `028` / `030`.
- Match the existing **bare `revision = "NNN"`** style, not the typed `script.py.mako` output.
- Keep the chain linear and single-headed (above).
- Write a docstring that explains *why* (intent, hazards, env assumptions), matching the existing
  files — they are unusually thorough and are the primary documentation for each schema decision.

## Known naming gotcha

`subtopics` and `sub_topics` are **two different tables**. `007` creates a new `subtopics`
(College Board skill decomposition); `009` *alters* a separate, legacy `sub_topics` table with
overlapping columns (`difficulty`, `skill`, `domain`, `approximate_frequency`). Confirm which one
you mean before writing SQL against either.
