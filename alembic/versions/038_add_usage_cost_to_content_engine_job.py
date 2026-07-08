"""Add ``usage_cost_usd`` to ``content_engine_job``.

content-engine accumulates the per-PDF LLM + OCR spend (Gemini answer/explain,
coherence, region-classify, topic-map + Mistral OCR) into ``JobState`` while a
job runs. Until now that figure was only mirrored to Langfuse and to a local
``status.json`` — and in the DB/S3 (containerized) deployment that file is
ephemeral and never read back, so the "usage / cost" column the review UI shows
had no durable source. This revision gives it one: a single money column on the
job row.

The save node writes the run's cumulative cost here; the ``/api/v1/jobs`` list +
detail endpoints read it straight off the row (no ``doc`` blob load), so the UI
can show both **per-PDF cost** and a cheap ``SUM()`` **total across all PDFs**.

``DECIMAL(10,6)`` — spend is fractions of a dollar per paper; six decimal places
matches the rounding content-engine already applies (``round(cost, 6)``) and
``DECIMAL(10,6)`` still holds up to 9999.999999, far above any single-job cost.
Purely additive, ``NOT NULL DEFAULT 0`` so existing rows read as ``$0`` (the UI
renders '—' for zero) until they are next processed. No index: the column is only
summed/selected, never filtered on.

Re-apply safety: the ADD is wrapped in an ``information_schema`` existence check
(prepared statement), mirroring 037 — so a re-run, or a DB where the column was
somehow already added, is a pure no-op that only advances ``alembic_version``.
MySQL 8 has no ``ADD COLUMN IF NOT EXISTS``, hence the guard; ``op.execute`` does
not accept multi-statement SQL, so each statement is split and run separately.

Assumes ``content_engine_job`` already exists (created in 036, this revision's
direct parent).

Revision ID: 038
Create Date: 2026-07-07
"""

from alembic import op

revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


ADD_USAGE_COST = """
SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'content_engine_job'
      AND COLUMN_NAME = 'usage_cost_usd'
);
SET @ddl := IF(@col_exists = 0,
    'ALTER TABLE `content_engine_job`
        ADD COLUMN `usage_cost_usd` decimal(10,6) NOT NULL DEFAULT 0
        COMMENT ''Cumulative per-PDF LLM+OCR spend in USD - drives the UI usage/cost column''
        AFTER `doc`',
    'SELECT 1'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
"""

DROP_USAGE_COST = """
SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'content_engine_job'
      AND COLUMN_NAME = 'usage_cost_usd'
);
SET @ddl := IF(@col_exists = 1,
    'ALTER TABLE `content_engine_job` DROP COLUMN `usage_cost_usd`',
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
    _execute_multi(ADD_USAGE_COST)


def downgrade() -> None:
    _execute_multi(DROP_USAGE_COST)
