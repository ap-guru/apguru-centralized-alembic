"""Add ``ai_performance_analysis`` to ``online_student_test_completed``.

The "where the marks went" feature (apguru-analytics-dashboard) persists
AI-derived, per-(student, test) analysis. Rather than one column per analysis
kind — which would grow the row every time a new blob is added — everything
goes into a **single JSON envelope** on the existing completion row (which
already carries ``student_id`` and ``test_id``, both indexed). New analyses
become new *keys* inside the JSON, not new columns:

  - ``ai_performance_analysis`` (JSON) — envelope holding, today,
    ``where_marks_went`` (student+teacher facing) and
    ``teacher_talking_points`` (teacher-only), with room for future blobs.
    The app validates/serialises the structure through a Pydantic model, so the
    shape stays readable even as the JSON grows.

Nullable and purely additive — existing completion rows read as "no analysis
yet" (the app treats a NULL / empty envelope as absent and lazily generates on
first read). JSON columns cannot carry a DEFAULT, hence NULL. The report's
``generated_at`` is backed by the row's existing ``created_at`` (no dedicated
stamp). Appended at the end of the row (no ``AFTER``) so MySQL 8 adds it
``INSTANT`` (metadata-only) on a large table. No index: the column is only
selected by the already-indexed ``(student_id, test_id)`` lookup, never filtered.

Re-apply safety: the ADD is wrapped in an ``information_schema`` existence check
(prepared statement), mirroring 037/038 — so a re-run, or a DB where the column
was already added, is a pure no-op that only advances ``alembic_version``.
MySQL 8 has no ``ADD COLUMN IF NOT EXISTS``, hence the guard; ``op.execute`` does
not accept multi-statement SQL, so each statement is split and run separately.

Assumes ``online_student_test_completed`` already exists (a legacy platform
table, not alembic-managed here).

Revision ID: 039
Create Date: 2026-07-10
"""

from alembic import op

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


_TABLE = "online_student_test_completed"
_COLUMN = "ai_performance_analysis"
# Embedded in a single-quoted ``@ddl`` string below, so the COMMENT's single
# quotes are DOUBLED (SQL escaping) — mirrors 038's ``COMMENT ''...''`` style.
_COLUMN_DEF = (
    "`ai_performance_analysis` json NULL "
    "COMMENT ''AI-derived analysis for this student+test - JSON envelope "
    "(where_marks_went, teacher_talking_points, and future blobs)''"
)


ADD_COLUMN = f"""
SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = '{_TABLE}'
      AND COLUMN_NAME = '{_COLUMN}'
);
SET @ddl := IF(@col_exists = 0,
    'ALTER TABLE `{_TABLE}` ADD COLUMN {_COLUMN_DEF}',
    'SELECT 1'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
"""

DROP_COLUMN = f"""
SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = '{_TABLE}'
      AND COLUMN_NAME = '{_COLUMN}'
);
SET @ddl := IF(@col_exists = 1,
    'ALTER TABLE `{_TABLE}` DROP COLUMN `{_COLUMN}`',
    'SELECT 1'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
"""


def _execute_multi(sql_block: str) -> None:
    """Split a multi-statement block (PREPARE / EXECUTE / DEALLOCATE) and run
    each separately — ``op.execute`` rejects ';'-separated multi-statement SQL."""
    for stmt in (s.strip() for s in sql_block.strip().split(";")):
        if stmt:
            op.execute(stmt)


def upgrade() -> None:
    _execute_multi(ADD_COLUMN)


def downgrade() -> None:
    _execute_multi(DROP_COLUMN)
