"""Create error_analysis_frq_flags: per-rubric-point FRQ error classifications.

One row per denied (``awarded=false``) grader rubric point, classified into the
course-scoped ``generated_error_types``. Shares ``error_analysis_runs`` via
``run_id`` (CASCADE). Course-scoped / multi-curriculum — AP Psychology is phase 1.
See ``docs/superpowers/specs/2026-06-18-frq-error-analysis-design.md`` §7.

``CREATE TABLE IF NOT EXISTS`` keeps the migration a no-op where the table
already exists (matches migration 020's style).

Revision ID: 032
Create Date: 2026-06-19
"""

from alembic import op

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


FRQ_FLAGS_DDL = """
CREATE TABLE IF NOT EXISTS `error_analysis_frq_flags` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `run_id` bigint unsigned NOT NULL COMMENT 'FK to error_analysis_runs.id',
  `student_id` bigint unsigned NOT NULL,
  `course_id` int NOT NULL COMMENT 'course-scoped; 17 for AP Psychology',
  `test_id` bigint unsigned NOT NULL COMMENT 'from scorecard.test_id',
  `grading_job_id` bigint unsigned NOT NULL COMMENT 'provenance: grading_job.id',
  `major_question` varchar(16) NOT NULL COMMENT 'scorecard major number (sequence within FRQ section)',
  `sub_question_id` varchar(32) NOT NULL COMMENT 'scorecard rubric label e.g. 1f',
  `point_id` varchar(64) NOT NULL COMMENT 'scorecard point id e.g. 1f-p2',
  `question_id` bigint unsigned DEFAULT NULL COMMENT 'resolved questions_online.id (logical FK)',
  `attempt_id` bigint unsigned DEFAULT NULL COMMENT 'resolved online_student_test_answers.id (logical FK)',
  `section_id` int DEFAULT NULL,
  `error_type` varchar(100) NOT NULL COMMENT 'generated_error_types.error_type_key or UNCLASSIFIED',
  `confidence` decimal(5,4) NOT NULL,
  `llm_reasoning` text,
  `evidence` json NOT NULL COMMENT 'criterion, rationale, transcript_evidence, grading_confidence, prompt_summary',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_frq_flag` (`run_id`,`grading_job_id`,`point_id`),
  KEY `idx_frq_run` (`run_id`),
  KEY `idx_frq_student` (`student_id`),
  KEY `idx_frq_error_type` (`error_type`),
  CONSTRAINT `fk_frq_flag_run` FOREIGN KEY (`run_id`)
    REFERENCES `error_analysis_runs` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
"""


def upgrade() -> None:
    op.execute(FRQ_FLAGS_DDL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS `error_analysis_frq_flags`")
