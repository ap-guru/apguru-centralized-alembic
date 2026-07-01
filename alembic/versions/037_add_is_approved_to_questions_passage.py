"""Add ``is_approved`` to the shared ``questions_online`` and ``passage`` tables.

content-engine writes extracted questions/passages straight into AP Guru's
production ``questions_online`` / ``passage`` with ``is_approved=0`` ("Strategy
B"): a reviewer approves them in place, and only ``is_approved=1`` rows are
student-visible. This revision adds that gate column (+ a covering index) to both
tables. It is the shared-table half of content-engine's centralization, kept in
its **own** revision — separate from 036's content_engine_* tables — because it
touches shared production tables owned outside this slice and should be
reviewable on its own (per CLAUDE.md's "touch shared tables surgically").

``is_approved`` is tri-state in practice: 0 / 2 = pending, 1 = approved. Purely
additive, ``NOT NULL DEFAULT 0`` so existing rows stay "pending" (no consumer
queries ``is_approved=1`` until content-engine does), the index backs the
reviewer/student visibility reads.

Re-apply safety: both ALTERs are wrapped in an ``information_schema`` existence
check (prepared statement), so on UAT / prod — where content-engine already added
these columns before it was centralized — this revision is a pure no-op that only
advances the ``alembic_version`` stamp; on a DB that lacks them it adds them.
MySQL 8 has no ``ADD COLUMN IF NOT EXISTS``, hence the guard. ``op.execute`` does
not accept multi-statement SQL, so each statement is split and run separately.

Like every shared-table migration in this repo (e.g. 027 on ``class``), this
assumes ``questions_online`` / ``passage`` already exist — true on the only DBs
these migrations run against.

Revision ID: 037
Create Date: 2026-06-30
"""

from alembic import op

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


ADD_IS_APPROVED_QUESTIONS_ONLINE = """
SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'questions_online'
      AND COLUMN_NAME = 'is_approved'
);
SET @ddl := IF(@col_exists = 0,
    'ALTER TABLE `questions_online`
        ADD COLUMN `is_approved` tinyint NOT NULL DEFAULT 0,
        ADD INDEX `idx_is_approved` (`is_approved`)',
    'SELECT 1'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
"""

ADD_IS_APPROVED_PASSAGE = """
SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'passage'
      AND COLUMN_NAME = 'is_approved'
);
SET @ddl := IF(@col_exists = 0,
    'ALTER TABLE `passage`
        ADD COLUMN `is_approved` tinyint NOT NULL DEFAULT 0,
        ADD INDEX `idx_is_approved` (`is_approved`)',
    'SELECT 1'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
"""

DROP_IS_APPROVED_QUESTIONS_ONLINE = """
SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'questions_online'
      AND COLUMN_NAME = 'is_approved'
);
SET @ddl := IF(@col_exists = 1,
    'ALTER TABLE `questions_online`
        DROP INDEX `idx_is_approved`,
        DROP COLUMN `is_approved`',
    'SELECT 1'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
"""

DROP_IS_APPROVED_PASSAGE = """
SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'passage'
      AND COLUMN_NAME = 'is_approved'
);
SET @ddl := IF(@col_exists = 1,
    'ALTER TABLE `passage`
        DROP INDEX `idx_is_approved`,
        DROP COLUMN `is_approved`',
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
    _execute_multi(ADD_IS_APPROVED_QUESTIONS_ONLINE)
    _execute_multi(ADD_IS_APPROVED_PASSAGE)


def downgrade() -> None:
    _execute_multi(DROP_IS_APPROVED_PASSAGE)
    _execute_multi(DROP_IS_APPROVED_QUESTIONS_ONLINE)
