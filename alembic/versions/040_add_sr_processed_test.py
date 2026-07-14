"""Add spaced_repetition_processed_test idempotency marker table.

One row per (student_id, test_id) whose post-test SR write-back has been
applied. Mirrors ``spaced_repetition_processed_quiz`` (029): guards the
post-test analytics trigger (apguru-analytics-dashboard) against
double-advancing SM-2 intervals when a test's SR commit is dispatched more
than once (duplicate LMS submit, grader completion callback, or retry).

The app's ``try_claim_test`` relies on the unique (student_id, test_id) index:
``INSERT IGNORE`` affects 1 row on a fresh claim, 0 on a duplicate.

Revision ID: 040
Create Date: 2026-07-14
"""

from alembic import op
import sqlalchemy as sa

revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "spaced_repetition_processed_test",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("student_id", sa.BigInteger, nullable=False),
        sa.Column("test_id", sa.BigInteger, nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "uq_sr_processed_student_test",
        "spaced_repetition_processed_test",
        ["student_id", "test_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_sr_processed_student_test",
        table_name="spaced_repetition_processed_test",
    )
    op.drop_table("spaced_repetition_processed_test")
