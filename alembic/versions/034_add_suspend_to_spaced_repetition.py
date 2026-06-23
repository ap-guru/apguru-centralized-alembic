"""Add suspend flag (suspended / suspended_at) to spaced_repetition.

Backs the admin "suspend a topic" control introduced by the analytics
app's admin-API effort (ap-guru/apguru-analytics-dashboard#114). An ops
admin can pause a topic so it is excluded from a student's reviews and is
NOT silently un-suspended by the next quiz-submit SM-2 write-back. That
behaviour lives entirely in the app; this migration only provides the two
columns it writes to.

Columns added to ``spaced_repetition`` (created in 010, owned by this repo):

- ``suspended``    BOOLEAN (MySQL TINYINT(1)), NOT NULL, server_default 0.
                   Admin-set pause flag. The ``server_default`` populates
                   every existing row with 0 ("not suspended") in the same
                   DDL, so no separate backfill is needed and no current
                   student's review behaviour changes until an admin acts.
                   NOT NULL keeps the suspend state unambiguous.
- ``suspended_at`` DATETIME, nullable. When the topic was suspended; NULL
                   for a topic that has never been suspended.

The change is purely additive and non-breaking.

No index: ``suspended`` is a low-cardinality boolean always filtered
alongside ``student_id``, already covered by ``uq_sr_student_topic`` /
``idx_sr_student_due``; a composite is a follow-up only if profiling the
cross-student overdue roster shows a need.

No foreign key: both columns live inside this Alembic-owned table; no
cross-table reference is introduced, so the logical-FK convention does not
apply.

Re-apply safety: MySQL 8 has no ``ADD COLUMN IF NOT EXISTS``. The chain is
authoritative going forward and every environment is Alembic-tracked, so
``alembic_version`` prevents re-application; a plain ``op.add_column`` is
the right tool here (this is a forward DDL add, not a divergent-env data
backfill).

HAZARD: ``downgrade()`` drops both columns and therefore DISCARDS any
suspend state an admin has set. Per this repo's forward-only contract it is
a dev/staging rollback tool, not a safe production rollback.

ORDERING: apply this migration (``alembic upgrade head``) to an environment
BEFORE deploying the analytics-dashboard SR-suspend slice there — the app
code depends on these columns; the migration has no dependency on the app.

Revision ID: 034
Create Date: 2026-06-23
"""

from alembic import op
import sqlalchemy as sa

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "spaced_repetition",
        sa.Column(
            "suspended",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "spaced_repetition",
        sa.Column("suspended_at", sa.DateTime, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("spaced_repetition", "suspended_at")
    op.drop_column("spaced_repetition", "suspended")
