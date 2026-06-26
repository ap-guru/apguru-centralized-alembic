"""Replace the per-student suspend flag with a ``topic_snooze`` table.

Lands the schema half of slice-08 ("snooze replaces suspend"). It does two
things in one revision, deliberately coupled because the app slice that drops
the suspend code (apguru-analytics-dashboard, slice-08a) cannot be deployed
until BOTH the new table exists and the dead columns are gone:

1. CREATE ``topic_snooze`` -- the home of the new time-bound snooze model.
2. DROP ``spaced_repetition.suspended`` / ``suspended_at`` -- the now-dead
   columns added by 034 to back the retired admin "suspend a topic" control.

Why snooze instead of suspend
-----------------------------
Suspend (034) was an indefinite, admin-set pause that required a matching
"reactivate" control to undo and was silently re-armed against the SM-2
write-back. Snooze replaces it with a *time-bound* pause: a row says a topic
is paused for one student until ``snoozed_until``, after which it auto-resumes
with no reactivate step. That is why there is no "un-snooze" flag here -- the
date IS the off-switch.

``topic_snooze`` columns (Alembic-owned table; mirrors its sibling
``spaced_repetition`` from 010 -- one row per (student_id, topic_id)):

- ``id``            BIGINT PK, autoincrement.
- ``student_id``    BIGINT, NOT NULL. Logical FK -> legacy ``students``; no
                    ``ForeignKeyConstraint`` (legacy id is BIGINT UNSIGNED and
                    the table is not Alembic-owned), per this repo's
                    logical-FK convention. Enforced in app code.
- ``topic_id``      INT, NOT NULL. Logical FK -> topics; INT to match
                    ``spaced_repetition.topic_id`` (010).
- ``snoozed_until`` DATE, NOT NULL. The day the snooze expires; the topic is
                    paused for the student while today < this date. DATE (not
                    DATETIME) matches the date granularity of SR's
                    ``due_date`` / ``last_reviewed``. NOT NULL on purpose: a
                    nullable "until" would just recreate indefinite suspend.
- ``reason``        VARCHAR(255), NULL. Optional, student-visible note rendered
                    on the SR "Snoozed until {date}" badge explaining why the
                    topic is paused. Added for slice-08b (snooze behaviour).
- ``created_at``    DATETIME, NOT NULL, server_default CURRENT_TIMESTAMP.
- ``updated_at``    TIMESTAMP, NOT NULL, CURRENT_TIMESTAMP ON UPDATE.

Indexes mirror ``spaced_repetition`` (010):

- ``uq_topic_snooze_student_topic`` UNIQUE (student_id, topic_id) -- at most
  one snooze row per student/topic (the app upserts it).
- ``idx_topic_snooze_student_until`` (student_id, snoozed_until) -- covers the
  per-student "is this topic currently snoozed" / "list active snoozes" reads.

Deliberately NOT added: ``created_by`` (admin id) -- admin audit is out of
scope for admin-API v1 (per the slice-08 PRD), so the table records no actor.
``reason`` IS included: slice-08b needs the student-visible pause note, and
folding it in here keeps the snooze table single-migration.

Re-apply safety: plain ``op.create_table`` / ``op.drop_column`` (no
``IF NOT EXISTS``), matching 034's reasoning -- every environment is
``alembic_version``-tracked so the chain itself prevents re-application; this
is forward DDL, not a divergent-env data backfill.

HAZARD: ``upgrade()`` DROPS ``suspended`` / ``suspended_at`` and so DISCARDS
any admin suspend state. ``downgrade()`` re-creates those columns but, exactly
like 034's own downgrade, every row comes back ``suspended = 0`` -- the
original suspend state is NOT recovered. Per this repo's forward-only contract
the downgrade is a dev/staging tool, not a safe production rollback. (The
dropped ``topic_snooze`` table is unused as of slice-08a, so its downgrade
loses nothing in practice.)

Revision ID: 035
Create Date: 2026-06-25
"""

from alembic import op
import sqlalchemy as sa

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. New time-bound snooze model.
    op.create_table(
        "topic_snooze",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("student_id", sa.BigInteger, nullable=False),
        sa.Column("topic_id", sa.Integer, nullable=False),
        sa.Column("snoozed_until", sa.Date, nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP,
            nullable=False,
            server_default=sa.text(
                "CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
            ),
        ),
    )
    op.create_index(
        "uq_topic_snooze_student_topic",
        "topic_snooze",
        ["student_id", "topic_id"],
        unique=True,
    )
    op.create_index(
        "idx_topic_snooze_student_until",
        "topic_snooze",
        ["student_id", "snoozed_until"],
    )

    # 2. Retire the dead suspend columns (exact reverse of 034's upgrade).
    op.drop_column("spaced_repetition", "suspended_at")
    op.drop_column("spaced_repetition", "suspended")


def downgrade() -> None:
    # Restore 034's shape. NOTE: re-added rows are all suspended = 0; the
    # original admin suspend state is not recovered (see HAZARD above).
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

    op.drop_index(
        "idx_topic_snooze_student_until", table_name="topic_snooze"
    )
    op.drop_index(
        "uq_topic_snooze_student_topic", table_name="topic_snooze"
    )
    op.drop_table("topic_snooze")
