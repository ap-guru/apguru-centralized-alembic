"""Create the content-engine tables (content_engine_*).

content-engine (the PDF -> reviewed-question-bank pipeline) previously owned its
own Alembic setup on a *separate* ``content_engine_alembic_version`` table. That
is being retired: this repo becomes the single owner of its schema too. This
revision is the **squashed end-state** of content-engine's six historical
migrations — it intentionally does NOT replay them, because that history
(a) created two ``staging_*`` tables it later dropped, and (b) ALTERed a
``content_engine_hash_map`` that no migration ever created (it was born from the
app's old runtime DDL). So we create only the live end-state, in one revision.

Tables (all ``content-engine``-owned; ``content_engine_`` prefix):

- ``content_engine_job``            one row per extraction job: status + the
                                    crash-recovery lease (worker_token /
                                    worker_heartbeat) + the reviewer working
                                    draft (``doc`` JSON).
- ``content_engine_job_stage``      one row per pipeline stage per job; drives
                                    resume / retry. FK -> content_engine_job.
- ``content_engine_hash_map``       (content_hash, table_name) -> AP Guru row_id
                                    side-table for idempotent upserts.
- ``content_engine_ocr_raw_page``   raw-OCR cache, keyed (jid, page_number), so a
                                    crash/resume re-pays only the LLM nodes.
- ``content_engine_pending_mapping``per-question intended passage / topic /
                                    sub_topic while ``is_approved=0``; read at
                                    approval time to materialize the real
                                    AP Guru mapping rows, then deleted.

Foreign keys
------------
``job_stage`` and ``ocr_raw_page`` carry real FKs to ``content_engine_job``
(owned <-> owned). ``pending_mapping`` ALSO carries **real** FKs into the shared
``questions_online`` / ``passage`` tables (question -> CASCADE, passage ->
SET NULL): these mirror exactly what content-engine deployed, and
``pending_mapping`` is the live mechanism that routes approved mappings into the
AP Guru mapping tables, so DB-enforced integrity is wanted. This deliberately
bends the repo's "logical FKs for non-owned legacy tables" guideline — safe
because these migrations only ever run against the real AP Guru DB where
``questions_online`` / ``passage`` exist (037 ALTERs them next).

Re-apply safety: every table uses ``CREATE TABLE IF NOT EXISTS``, so on an
environment that already has these tables (UAT / prod, created by content-engine
before it was centralized) this revision is a pure no-op that only advances the
``alembic_version`` stamp; on a fresh AP Guru DB it builds them.

Every table has a surrogate ``id bigint AUTO_INCREMENT`` PRIMARY KEY (project
convention); ``job`` / ``hash_map`` / ``pending_mapping`` keep their former key
(``jid``; ``(content_hash, table_name)``; ``question_id``) as a UNIQUE constraint
so idempotent upserts and the foreign keys below still work.

Revision ID: 036
Create Date: 2026-06-30
"""

from alembic import op

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


JOB_DDL = """
CREATE TABLE IF NOT EXISTS `content_engine_job` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `jid` varchar(16) NOT NULL,
  `course_id` int DEFAULT NULL,
  `test_type` varchar(16) DEFAULT NULL,
  `source_primary` varchar(255) DEFAULT NULL,
  `job_name` varchar(255) DEFAULT NULL COMMENT 'Optional user-assigned name; falls back to filename',
  `primary_pdf_sha` char(64) DEFAULT NULL COMMENT 'sha256 of the primary uploaded PDF; 409 re-upload dedup guard',
  `current_stage` varchar(32) DEFAULT NULL,
  `overall_status` enum('running','awaiting_user','succeeded','failed') NOT NULL DEFAULT 'running',
  `worker_token` varchar(36) DEFAULT NULL COMMENT 'Recovery lease holder (single-box crash-recovery worker)',
  `worker_heartbeat` datetime DEFAULT NULL,
  `doc` json DEFAULT NULL COMMENT 'Parsed document + reviewer working draft (was data/jobs/<jid>/extracted.json)',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_job_jid` (`jid`),
  KEY `idx_overall_status` (`overall_status`),
  KEY `idx_recovery` (`overall_status`,`worker_heartbeat`),
  KEY `idx_primary_pdf_sha` (`primary_pdf_sha`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
"""


JOB_STAGE_DDL = """
CREATE TABLE IF NOT EXISTS `content_engine_job_stage` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `jid` varchar(16) NOT NULL,
  `stage` enum('upload','ocr','parse','eval_answer_explain','eval_coherence','eval_section_map','eval_topic_map','user_approval','push_to_db') NOT NULL,
  `status` enum('pending','running','succeeded','failed','skipped','awaiting_user') NOT NULL DEFAULT 'pending',
  `attempt_count` int NOT NULL DEFAULT '0',
  `error_class` enum('transient','terminal') DEFAULT NULL,
  `error_message` text,
  `started_at` datetime DEFAULT NULL,
  `ended_at` datetime DEFAULT NULL,
  `next_retry_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_job_stage` (`jid`,`stage`),
  KEY `idx_retry` (`status`,`error_class`,`next_retry_at`),
  CONSTRAINT `fk_stage_job` FOREIGN KEY (`jid`) REFERENCES `content_engine_job` (`jid`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
"""


HASH_MAP_DDL = """
CREATE TABLE IF NOT EXISTS `content_engine_hash_map` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `content_hash` char(16) NOT NULL,
  `table_name` varchar(64) NOT NULL,
  `row_id` int NOT NULL,
  `jid` varchar(16) DEFAULT NULL COMMENT 'Owning job; nullable, stamped on promote/re-promote',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_hash_map` (`content_hash`,`table_name`),
  KEY `idx_table_row` (`table_name`,`row_id`),
  KEY `idx_hashmap_jid` (`jid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
"""


OCR_RAW_PAGE_DDL = """
CREATE TABLE IF NOT EXISTS `content_engine_ocr_raw_page` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `jid` varchar(16) NOT NULL,
  `page_number` int NOT NULL,
  `payload` json NOT NULL COMMENT 'Raw OCR response for the page (Mistral)',
  `provider` varchar(32) NOT NULL,
  `model` varchar(64) DEFAULT NULL,
  `s3_key` varchar(512) DEFAULT NULL,
  `s3_url` varchar(1024) DEFAULT NULL,
  `md_chars` int NOT NULL DEFAULT '0',
  `images_count` int NOT NULL DEFAULT '0',
  `tables_count` int NOT NULL DEFAULT '0',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_ocr_job_page` (`jid`,`page_number`),
  KEY `idx_ocr_jid` (`jid`),
  CONSTRAINT `fk_ocr_job` FOREIGN KEY (`jid`) REFERENCES `content_engine_job` (`jid`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
"""


PENDING_MAPPING_DDL = """
CREATE TABLE IF NOT EXISTS `content_engine_pending_mapping` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `question_id` int NOT NULL COMMENT 'questions_online.id this intended mapping belongs to',
  `passage_id` int DEFAULT NULL,
  `topic_id` int DEFAULT NULL,
  `sub_topic_id` int DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_pending_question` (`question_id`),
  KEY `idx_pending_passage` (`passage_id`),
  KEY `idx_pending_topic` (`topic_id`),
  KEY `idx_pending_subtopic` (`sub_topic_id`),
  CONSTRAINT `fk_pending_question` FOREIGN KEY (`question_id`) REFERENCES `questions_online` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_pending_passage` FOREIGN KEY (`passage_id`) REFERENCES `passage` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
"""


def upgrade() -> None:
    # Parent first, then children (FK order); pending_mapping last (FKs into the
    # shared questions_online / passage, which already exist on every target DB).
    op.execute(JOB_DDL)
    op.execute(JOB_STAGE_DDL)
    op.execute(HASH_MAP_DDL)
    op.execute(OCR_RAW_PAGE_DDL)
    op.execute(PENDING_MAPPING_DDL)


def downgrade() -> None:
    # Children before parent (FK order). IF EXISTS so downgrade is idempotent.
    op.execute("DROP TABLE IF EXISTS `content_engine_pending_mapping`")
    op.execute("DROP TABLE IF EXISTS `content_engine_ocr_raw_page`")
    op.execute("DROP TABLE IF EXISTS `content_engine_hash_map`")
    op.execute("DROP TABLE IF EXISTS `content_engine_job_stage`")
    op.execute("DROP TABLE IF EXISTS `content_engine_job`")
