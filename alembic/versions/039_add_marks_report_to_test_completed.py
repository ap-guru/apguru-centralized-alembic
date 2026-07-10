"""Add marks-report columns to ``online_student_test_completed``.

The "where the marks went" feature (apguru-analytics-dashboard) persists two
per-(student, test) JSON artifacts. Rather than a new table, they hang off the
existing completion row — which already carries ``student_id`` and ``test_id``
(both indexed) — so the report is read/written keyed by that pair with no extra
join:

  - ``where_marks_went_json``       — student+teacher-facing breakdown of where
    marks were lost (authored student-safe). Shown to BOTH roles.
  - ``teacher_talking_points_json`` — teacher-only; the exact points to raise
    with the student in the next class. Omitted from student responses at the
    API layer.

No dedicated ``generated_at`` column: NULL ``where_marks_went_json`` already
signals "no report yet", and the API surfaces the row's existing ``created_at``
as ``generated_at`` — so no redundant timestamp is stored.

Both columns are nullable and purely additive — existing completion rows read as
"no report yet" (the app treats a NULL ``where_marks_went_json`` as absent and
lazily generates on first read). JSON columns cannot carry a DEFAULT, hence
NULL. Columns are appended at the end of the row (no ``AFTER``) so MySQL 8 can
add them ``INSTANT`` (metadata-only) on a large table. No index: the columns are
only selected by the already-indexed ``(student_id, test_id)`` lookup, never
filtered on.

Re-apply safety: each ADD is wrapped in an ``information_schema`` existence
check (prepared statement), mirroring 037/038 — so a re-run, or a DB where a
column was already added, is a pure no-op that only advances
``alembic_version``. MySQL 8 has no ``ADD COLUMN IF NOT EXISTS``, hence the
guard; ``op.execute`` does not accept multi-statement SQL, so each statement is
split and run separately.

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

# (column_name, column_definition) — appended at end of row (no AFTER).
#
# NOTE: each column_def is embedded inside a single-quoted ``@ddl`` string in
# ``_guarded_add`` below, so any single quotes in the COMMENT must be DOUBLED
# (SQL string escaping) — mirrors 038's ``COMMENT ''...''`` style.
_COLUMNS = [
    (
        "where_marks_went_json",
        "`where_marks_went_json` json NULL "
        "COMMENT ''Student+teacher where-the-marks-went report JSON''",
    ),
    (
        "teacher_talking_points_json",
        "`teacher_talking_points_json` json NULL "
        "COMMENT ''Teacher-only talking points JSON''",
    ),
]


def _guarded_add(column: str, column_def: str) -> str:
    return f"""
    SET @col_exists := (
        SELECT COUNT(*) FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = '{_TABLE}'
          AND COLUMN_NAME = '{column}'
    );
    SET @ddl := IF(@col_exists = 0,
        'ALTER TABLE `{_TABLE}` ADD COLUMN {column_def}',
        'SELECT 1'
    );
    PREPARE stmt FROM @ddl;
    EXECUTE stmt;
    DEALLOCATE PREPARE stmt;
    """


def _guarded_drop(column: str) -> str:
    return f"""
    SET @col_exists := (
        SELECT COUNT(*) FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = '{_TABLE}'
          AND COLUMN_NAME = '{column}'
    );
    SET @ddl := IF(@col_exists = 1,
        'ALTER TABLE `{_TABLE}` DROP COLUMN `{column}`',
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
    for column, column_def in _COLUMNS:
        _execute_multi(_guarded_add(column, column_def))


def downgrade() -> None:
    for column, _ in reversed(_COLUMNS):
        _execute_multi(_guarded_drop(column))
