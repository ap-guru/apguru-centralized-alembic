"""Seed two FRQ-native error types for AP Psychology (course_id 17).

The four existing course-17 types (migration 030) were generated for MCQ and
their detection criteria reference ``distractor_analysis`` — so two of the most
common free-response failure modes have no type to land in, and the FRQ
classifier funnels them into ``APPLICATION_MISMATCH``. This adds:

  - ``INCOMPLETE_EXPLANATION`` — on-topic content, but the required link /
    justification / mechanism is missing or merely restated.
  - ``OFF_PROMPT_RESPONSE``    — answers a different study / variable / source /
    task than the prompt specifies (wrong stimulus or scope).

Detection criteria are written for the FRQ signal the classifier actually sees
(rubric ``criterion`` + the student's ``student_answer`` + grader ``rationale``),
NOT MCQ distractor/timing signals. ``RESEARCH_DESIGN_ERROR`` and
``APPLICATION_MISMATCH`` (migration 030) already fit FRQ and are unchanged.

Idempotent: ``upgrade`` deletes any prior rows for these two keys on course 17
before inserting, so a re-apply does not duplicate. Course-scoped (course 17,
phase 1); other curriculums get their own seeds per the multi-curriculum design.

Revision ID: 033
Create Date: 2026-06-19
"""

import sqlalchemy as sa

from alembic import op

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


_COURSE_ID = 17
_CURRICULUM_NAME = "AP Psychology"
_SUBJECT_AREA = "Psychology"
_CREATED_BY = "frq-error-analysis-design"


ERROR_TYPES: list[dict[str, str]] = [
    {
        "error_type_key": "INCOMPLETE_EXPLANATION",
        "label": "Incomplete Explanation",
        "description": (
            "The student states a relevant fact, concept, or piece of evidence but does "
            "not complete the required reasoning — they fail to explain HOW it supports "
            "the claim, restate a finding instead of explaining the mechanism, or leave "
            "the argument unfinished."
        ),
        "fix": (
            "After citing evidence or defining a concept, explicitly state how it "
            "supports the claim and why (the 'because/therefore' link). Don't stop at "
            "the finding — explain the underlying mechanism."
        ),
        "detection_criteria": (
            "The student_answer is on-topic for the prompt and contains a correct "
            "concept, definition, or finding, but the rubric criterion required an "
            "explanation, justification, or link that is absent or merely restated. The "
            "grader rationale typically says the response 'does not explain how', "
            "'simply restates the finding', or 'fails to connect the evidence to the "
            "claim'. Distinguish from APPLICATION_MISMATCH (which targets the wrong "
            "concept) — here the right material is present but the reasoning step is missing."
        ),
        "rationale": (
            "AP Psychology FRQs weight argumentation heavily: citing evidence or defining "
            "a concept earns little without explaining how it supports the claim. "
            "'Restating instead of explaining' and 'evidence not linked to the claim' are "
            "among the most common FRQ point losses on the redesigned exam."
        ),
    },
    {
        "error_type_key": "OFF_PROMPT_RESPONSE",
        "label": "Off-Prompt Response",
        "description": (
            "The student writes about a different study, variable, source, or task than "
            "the prompt specifies — the response addresses the wrong stimulus or scope, "
            "so it cannot earn the point regardless of how internally coherent it is."
        ),
        "fix": (
            "Re-read the prompt and underline the exact study, variable, or source it "
            "names before writing. Make sure every sentence is about THAT scenario, not a "
            "similar study you may have revised."
        ),
        "detection_criteria": (
            "The student_answer is internally coherent but about the wrong study, "
            "scenario, variable, or source relative to the rubric criterion. The grader "
            "rationale typically says the response is 'unrelated to', 'does not address', "
            "or 'references an entirely different' study/topic than required. Distinguish "
            "from INCOMPLETE_EXPLANATION (on-topic but unfinished) — here the content is "
            "off-target from the start."
        ),
        "rationale": (
            "On the redesigned, evidence-based AP Psychology FRQs, students frequently "
            "answer about a remembered or adjacent study rather than the provided "
            "stimulus, producing fluent but off-prompt responses that earn zero."
        ),
    },
]

_ERROR_TYPE_KEYS = [et["error_type_key"] for et in ERROR_TYPES]


def upgrade() -> None:
    conn = op.get_bind()

    # Idempotent re-apply: clear any prior rows for these keys on course 17 first.
    _delete_seeded_rows(conn)

    insert_stmt = sa.text(
        "INSERT INTO generated_error_types "
        "(course_id, curriculum_name, subject_area, error_type_key, label, "
        " description, fix, detection_criteria, rationale, source, status, "
        " created_by) "
        "VALUES (:course_id, :curriculum_name, :subject_area, :error_type_key, "
        " :label, :description, :fix, :detection_criteria, :rationale, 'manual', "
        " 'accepted', :created_by)"
    )
    params = [
        {
            "course_id": _COURSE_ID,
            "curriculum_name": _CURRICULUM_NAME,
            "subject_area": _SUBJECT_AREA,
            "created_by": _CREATED_BY,
            **et,
        }
        for et in ERROR_TYPES
    ]
    conn.execute(insert_stmt, params)


def downgrade() -> None:
    _delete_seeded_rows(op.get_bind())


def _delete_seeded_rows(conn) -> None:
    """Delete the two seeded rows for course 17 (named params only)."""
    stmt = sa.text(
        "DELETE FROM generated_error_types "
        "WHERE course_id = :course_id AND error_type_key IN :keys"
    ).bindparams(sa.bindparam("keys", expanding=True))
    conn.execute(stmt, {"course_id": _COURSE_ID, "keys": _ERROR_TYPE_KEYS})
