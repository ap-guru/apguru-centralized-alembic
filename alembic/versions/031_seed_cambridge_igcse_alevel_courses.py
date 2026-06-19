"""Seed the Cambridge IGCSE / A-Level course catalog rows (ids 71-103) into course_configs.

Adds Cambridge / Edexcel IGCSE and A-Level courses to the shared ``course_configs``
catalog so the APGuru grader can grade them. Mirrors migration 028 (the IB seed):
**INSERT** (upsert via ``ON DUPLICATE KEY UPDATE``, keyed on the PK ``id``), with
``course_id = str(id)``. Every row carries ``exam_body = 'Cambridge IGCSE/A-Level'`` —
the value the grader reads to select its Cambridge rubric/grade prompt variants
instead of the AP or IB ones. The grader caches ``course_configs`` in-process, so it
picks these rows up on its next restart.

Cambridge marks two ways and the addenda reflect it:
- **Point-based** (Mathematics + its variants, Statistics, Physics, Chemistry,
  Biology, Computer Science, IT) gets mark-by-mark guidance (method/answer marks,
  ECF/follow-through, accept-equivalent) and, for the diagram-heavy sciences/maths,
  an OCR addendum.
- **Levels-of-response** (English, Languages, History, Sociology, Psychology,
  Business, Economics essays) gets level-descriptor guidance: each rubric point is a
  level ladder scored by best-fit with partial credit. Economics also gets a diagram
  OCR addendum.

The qualification prefix in ``course_name`` ("IGCSE " / "A-Level ") is what tells the
grader the depth expected; the same subject addendum serves both levels.

The required NOT-NULL columns the grader doesn't read (``category``,
``scoring_type``, ``subjects``) carry honest placeholders; refine them if these
courses are later wired into scoring/tutor features.

Revision ID: 031
Create Date: 2026-06-19
"""

import json
import re

import sqlalchemy as sa

from alembic import op

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Grading addenda — point-based subjects (mark-by-mark)
# ---------------------------------------------------------------------------

_MATH_GRADING = (
    "Cambridge Mathematics is marked with method (M) and accuracy (A) marks. Award M "
    "marks for a valid, clearly indicated method even if it carries an arithmetic slip; "
    "award A marks only for a correct result, and an A mark depends on the preceding M "
    "mark. Apply ECF / follow-through unless the scheme marks a point CAO (correct "
    "answer only): a value that is wrong because of an earlier error but is then used "
    "with correct subsequent method still earns the later marks. Accept equivalent forms "
    "(exact surds or correctly rounded decimals, algebraically equivalent expressions, "
    "OE) and any correct alternative method. A correct answer with no working earns full "
    "marks unless the scheme requires working to be shown."
)

_PHYSICS_GRADING = (
    "Cambridge Physics is point-marked (defining relationship, substitution, evaluation "
    "with the correct unit, plus explanation marks). Apply ECF so an incorrect earlier "
    "value used correctly downstream still earns later marks. Accept algebraically "
    "equivalent expressions, correct alternative methods and OWTTE wording, and answers "
    "within the scheme's stated tolerance; require correct units and, where the scheme "
    "specifies, significant figures and vector direction. Award explanation marks only "
    "for a correct, coherent line of physics reasoning tied to the scenario — a bare "
    "statement or an unexplained equation does not earn it."
)

_CHEMISTRY_GRADING = (
    "Cambridge Chemistry is point-marked. For calculations require the correct working "
    "AND the final answer with appropriate units, applying ECF so an incorrect earlier "
    "value used correctly downstream still earns later marks; accept answers within "
    "tolerance and penalise significant figures only where the scheme says so. Require "
    "balanced equations, correct formulae and state symbols where specified. Explanation "
    "marks require correct reasoning at the particulate level (bonding, intermolecular "
    "forces, electronegativity, rates / collision theory, equilibrium shifts) tied to "
    "the prompt — a correct answer with no valid reasoning earns no reasoning mark. "
    "Accept ORA and OWTTE wording."
)

_BIOLOGY_GRADING = (
    "Cambridge Biology is point-marked; award each mark independently for the specific "
    "idea the scheme credits (accept OWTTE wording and listed alternatives separated by "
    "'/'). 'Explain' and 'suggest' marks require a stated mechanism at the molecular, "
    "cellular, or ecological level tied to the prompt — a correct conclusion with no "
    "reasoning earns no reasoning mark. For data questions require a trend stated with "
    "reference to the figures, not a bare restatement; for calculations require the "
    "working and correct units. Apply ECF on dependent steps; honour ORA."
)

_CS_GRADING = (
    "Cambridge Computer Science and IT answers are marked for correct intent. Accept "
    "pseudocode or program code that is functionally correct even with minor syntax "
    "slips unless the scheme explicitly requires strict syntax; variable-name "
    "differences are not penalised. Award marks for the correct construct (loop, "
    "condition, function / procedure call, correct use of a data structure or SQL / "
    "logic operation) and correct logic and order; deduct only where the logic is wrong "
    "or a required step is missing. For trace-table / output questions require the "
    "correct final result, applying follow-through on an earlier consistent slip. For "
    "any levels-marked evaluative part apply best-fit level judgement."
)


# ---------------------------------------------------------------------------
# Grading addenda — levels-of-response subjects (level descriptors, best-fit)
# ---------------------------------------------------------------------------

_LEVELS_BASE = (
    "This subject's extended responses are marked with levels of response (level "
    "descriptors), not independent points. Each rubric point whose criterion lists "
    "multiple levels is one assessment ladder: read the whole response, choose by "
    "best-fit the single level whose descriptor it matches, and award a specific mark "
    "within that level (lower / middle / upper) reflecting fit — do NOT award the top of "
    "the level merely for reaching it, and never combine levels. Short point-marked "
    "parts (define / identify / calculate) are awarded all-or-nothing. Credit substance "
    "over length; reward sustained, well-evidenced analysis that addresses the command "
    "word. "
)

_ENGLISH_GRADING = _LEVELS_BASE + (
    "English rewards a focused response to the task supported by precise textual "
    "reference / quotation, analysis of language, structure and form and their effects, "
    "and — at higher levels — a perceptive, well-developed argument. For directed / "
    "transactional writing, reward appropriate audience, purpose, tone and accurate "
    "expression. Comprehension and short-answer points are marked all-or-nothing on the "
    "specific content required."
)

_LANGUAGE_GRADING = (
    "Cambridge modern-language papers mix point-marked comprehension with levels-marked "
    "writing. For reading / listening comprehension, award each mark for the specific "
    "correct information (accept answers in the target or response language as the "
    "scheme allows; ignore minor spelling / accent errors that do not change meaning, "
    "OWTTE). For writing and essay tasks apply levels of response across the scheme's "
    "strands (typically Content / Communication and Language / Accuracy): place each "
    "strand by best-fit and award within the level, rewarding range and accuracy of "
    "vocabulary and grammar, task completion, and communicative clarity. Do not penalise "
    "a single slip twice."
)

_HISTORY_GRADING = _LEVELS_BASE + (
    "History rewards accurate, relevant own knowledge, focus on the precise demands of "
    "the question, analysis over narrative, and — for essays — a balanced argument with "
    "a substantiated judgement. For source questions, evaluation of utility / "
    "reliability must be grounded in provenance (origin, purpose and content), not "
    "asserted."
)

_SOCIOLOGY_GRADING = _LEVELS_BASE + (
    "Sociology rewards accurate use of sociological concepts, theories and studies "
    "(e.g. functionalism, Marxism, feminism, interactionism), explicit application to "
    "the question, and — for evaluative parts — a two-sided argument that weighs "
    "perspectives and reaches a conclusion; juxtaposed perspectives with no analysis "
    "stay mid-level."
)

_PSYCHOLOGY_GRADING = _LEVELS_BASE + (
    "Psychology rewards accurate use of relevant theories and studies, explicit links to "
    "the question, and critical thinking (methodology, ethics, comparisons, "
    "applications) for extended answers; short answers require an accurate, focused "
    "explanation with a relevant study or concept."
)

_BUSINESS_GRADING = _LEVELS_BASE + (
    "Business rewards application of specific business concepts / tools to the case "
    "context, balanced analysis, and — for 'evaluate / recommend / assess / justify' — a "
    "substantiated judgement; generic theory not tied to the case earns little. Reward "
    "correct calculations (with working and units) where required."
)

_ECONOMICS_GRADING = _LEVELS_BASE + (
    "Economics rewards accurate definitions of key terms, correctly drawn and fully "
    "labelled diagrams, application to the given context, and — for 'evaluate / discuss "
    "/ assess' — reasoned evaluation weighing more than one viewpoint and reaching a "
    "supported judgement; a correct diagram with no explanation, or evaluation with no "
    "economic theory, is limited."
)


# ---------------------------------------------------------------------------
# OCR addenda — diagram-heavy subjects (student draws diagrams in the answer)
# ---------------------------------------------------------------------------

_MATH_OCR = (
    "Transcribe mathematical working faithfully: every line of algebra, each step's "
    "operator, and the final answer (LaTeX between $...$). For graphs / sketches: axis "
    "labels with scale, the curve's shape and key features (intercepts, turning points, "
    "asymptotes), and any points or regions the student marked or shaded. For geometry / "
    "vector / probability diagrams: labelled lengths and angles, vector directions and "
    "magnitudes, and branch labels / probabilities."
)

_PHYSICS_OCR = (
    "For free-body / force diagrams: every vector with its tail point, head direction "
    "(up / down / left / right or angle), labelled magnitude (mg, N, T, f, F_app, etc.), "
    "and the object it acts on. For circuit diagrams: each component (resistor, "
    "capacitor, cell, switch) with its labelled value, the connection topology, and any "
    "labelled current direction or polarity. For field / ray diagrams: arrow directions, "
    "relative density, labelled magnitudes, lens / mirror type, focal points and image "
    "position. For motion / graph sketches: coordinate axes with labels, units and "
    "scale, the curve shape (linear, parabolic, constant), key values at labelled "
    "points, and any area the student shaded."
)

_CHEMISTRY_OCR = (
    "Diagram fidelity matters — marks are awarded for specific bonds, lone pairs, "
    "charges and geometries the student drew. For dot-and-cross / displayed structures: "
    "name every atom by element symbol, every bond by its multiplicity and the two atoms "
    "it joins (e.g. 'C=O', 'N-H'), every lone / bonding pair, every formal charge with "
    "sign and adjacent atom, and the overall shape (bent, trigonal planar, tetrahedral) "
    "when discernible. For energy / reaction-profile diagrams: each peak's relative "
    "height, the position and label of any intermediate, and whether reactants are "
    "higher or lower than products. For apparatus diagrams and titration / rate graphs: "
    "label the components, axes, scale, and every plotted feature including end / "
    "equivalence points."
)

_BIOLOGY_OCR = (
    "For biological diagrams (cell, organelle, tissue, organ, organism): name every "
    "structure the student labelled and where it sits relative to others. For cycle "
    "diagrams (Krebs, Calvin, cell cycle, nitrogen cycle): name each stage in order, the "
    "direction of every arrow, and any inputs / outputs written on the arrows. For "
    "experimental graphs: axes (label + units + scale), trend per group / treatment, "
    "error bars or ranges if drawn, and any annotation the student added. For pedigrees, "
    "Punnett squares and gel images: the row / column layout and what is in each cell."
)

_ECONOMICS_OCR = (
    "Economics answers rely on diagrams — transcribe them precisely. For supply-and-"
    "demand / cost-and-revenue / AD-AS diagrams: label both axes (with units where "
    "given), name every curve drawn (e.g. S, D, MC, ATC, AD, SRAS), the direction of any "
    "shift and its new position, each equilibrium point and any price / quantity lines "
    "dropped to the axes, and any area the student shaded or labelled (welfare loss, tax "
    "revenue, surplus). State which curves moved and to where. Also transcribe any "
    "calculation working and the final value with units (%, $, etc.)."
)


# ---------------------------------------------------------------------------
# course_configs.id -> addenda
# ---------------------------------------------------------------------------

GRADING_ADDENDA: dict[int, str] = {
    # --- IGCSE (71-88) ---
    71: _ENGLISH_GRADING,     # IGCSE English
    72: _LANGUAGE_GRADING,    # IGCSE Spanish
    73: _LANGUAGE_GRADING,    # IGCSE French
    74: _ECONOMICS_GRADING,   # IGCSE Economics
    75: _PSYCHOLOGY_GRADING,  # IGCSE Psychology
    76: _HISTORY_GRADING,     # IGCSE History
    77: _SOCIOLOGY_GRADING,   # IGCSE Sociology
    78: _BUSINESS_GRADING,    # IGCSE Business
    79: _CS_GRADING,          # IGCSE Computer Science
    80: _CS_GRADING,          # IGCSE Information Technology
    81: _BIOLOGY_GRADING,     # IGCSE Biology
    82: _CHEMISTRY_GRADING,   # IGCSE Chemistry
    83: _PHYSICS_GRADING,     # IGCSE Physics
    84: _MATH_GRADING,        # IGCSE Mathematics
    85: _MATH_GRADING,        # IGCSE Additional Mathematics
    86: _MATH_GRADING,        # IGCSE International Mathematics
    87: _MATH_GRADING,        # IGCSE Extended Mathematics
    88: _MATH_GRADING,        # IGCSE Statistics
    # --- A-Level (89-103) ---
    89: _ENGLISH_GRADING,     # A-Level English
    90: _LANGUAGE_GRADING,    # A-Level Spanish
    91: _LANGUAGE_GRADING,    # A-Level French
    92: _ECONOMICS_GRADING,   # A-Level Economics
    93: _PSYCHOLOGY_GRADING,  # A-Level Psychology
    94: _HISTORY_GRADING,     # A-Level History
    95: _SOCIOLOGY_GRADING,   # A-Level Sociology
    96: _BIOLOGY_GRADING,     # A-Level Biology
    97: _CHEMISTRY_GRADING,   # A-Level Chemistry
    98: _PHYSICS_GRADING,     # A-Level Physics
    99: _BUSINESS_GRADING,    # A-Level Business
    100: _CS_GRADING,         # A-Level Computer Science
    101: _CS_GRADING,         # A-Level Information Technology
    102: _MATH_GRADING,       # A-Level Mathematics
    103: _MATH_GRADING,       # A-Level Further Mathematics
}

OCR_ADDENDA: dict[int, str] = {
    74: _ECONOMICS_OCR,   # IGCSE Economics
    81: _BIOLOGY_OCR,     # IGCSE Biology
    82: _CHEMISTRY_OCR,   # IGCSE Chemistry
    83: _PHYSICS_OCR,     # IGCSE Physics
    84: _MATH_OCR,        # IGCSE Mathematics
    85: _MATH_OCR,        # IGCSE Additional Mathematics
    86: _MATH_OCR,        # IGCSE International Mathematics
    87: _MATH_OCR,        # IGCSE Extended Mathematics
    88: _MATH_OCR,        # IGCSE Statistics
    92: _ECONOMICS_OCR,   # A-Level Economics
    96: _BIOLOGY_OCR,     # A-Level Biology
    97: _CHEMISTRY_OCR,   # A-Level Chemistry
    98: _PHYSICS_OCR,     # A-Level Physics
    102: _MATH_OCR,       # A-Level Mathematics
    103: _MATH_OCR,       # A-Level Further Mathematics
}


# course_configs.id -> course_name (verbatim from the supplied CSV). These rows are
# INSERTed because the grader's catalog was missing them.
COURSES: dict[int, str] = {
    71: "IGCSE English",
    72: "IGCSE Spanish",
    73: "IGCSE French",
    74: "IGCSE Economics",
    75: "IGCSE Psychology",
    76: "IGCSE History",
    77: "IGCSE Sociology",
    78: "IGCSE Business",
    79: "IGCSE Computer Science",
    80: "IGCSE Information Technology",
    81: "IGCSE Biology",
    82: "IGCSE Chemistry",
    83: "IGCSE Physics",
    84: "IGCSE Mathematics",
    85: "IGCSE Additional Mathematics",
    86: "IGCSE International Mathematics",
    87: "IGCSE Extended Mathematics",
    88: "IGCSE Statistics",
    89: "A-Level English",
    90: "A-Level Spanish",
    91: "A-Level French",
    92: "A-Level Economics",
    93: "A-Level Psychology",
    94: "A-Level History",
    95: "A-Level Sociology",
    96: "A-Level Biology",
    97: "A-Level Chemistry",
    98: "A-Level Physics",
    99: "A-Level Business",
    100: "A-Level Computer Science",
    101: "A-Level Information Technology",
    102: "A-Level Mathematics",
    103: "A-Level Further Mathematics",
}

# exam_body is the live flag the grader reads (selects the Cambridge prompts). A
# single board-agnostic value covers IGCSE and A-Level since the marking structure is
# the same; see app/services/grader_prompts.py (CAMBRIDGE_EXAM_BODY). category /
# scoring_type / subjects are required NOT-NULL columns the grader does not read.
_EXAM_BODY = "Cambridge IGCSE/A-Level"
_CATEGORY = "academic"
_SCORING_TYPE = "grade"

_slug_re = re.compile(r"[^a-z0-9]+")


def _subject_slug(course_name: str) -> str:
    """Lowercase hyphen slug of the course name (drops a leading 'IGCSE '/'A-Level ')."""
    name = course_name.strip()
    low = name.lower()
    for prefix in ("igcse ", "a-level "):
        if low.startswith(prefix):
            name = name[len(prefix):]
            break
    return _slug_re.sub("-", name.lower()).strip("-")


def upgrade() -> None:
    conn = op.get_bind()
    stmt = sa.text(
        "INSERT INTO course_configs "
        "(id, course_id, course_name, exam_body, category, scoring_type, subjects, "
        " is_active, grading_addendum, ocr_addendum) "
        "VALUES (:id, :course_id, :course_name, :exam_body, :category, :scoring_type, "
        " :subjects, 1, :g, :o) "
        "ON DUPLICATE KEY UPDATE "
        " course_name=VALUES(course_name), exam_body=VALUES(exam_body), "
        " category=VALUES(category), scoring_type=VALUES(scoring_type), "
        " subjects=VALUES(subjects), is_active=VALUES(is_active), "
        " grading_addendum=VALUES(grading_addendum), ocr_addendum=VALUES(ocr_addendum)"
    )
    params = [
        {
            "id": cid,
            "course_id": str(cid),
            "course_name": name,
            "exam_body": _EXAM_BODY,
            "category": _CATEGORY,
            "scoring_type": _SCORING_TYPE,
            "subjects": json.dumps([_subject_slug(name)]),
            "g": GRADING_ADDENDA.get(cid, ""),
            "o": OCR_ADDENDA.get(cid, ""),
        }
        for cid, name in COURSES.items()
    ]
    conn.execute(stmt, params)  # one batched executemany roundtrip


def downgrade() -> None:
    conn = op.get_bind()
    # Single batched delete via an expanding bound param — named params, not an
    # f-string IN clause (CLAUDE.md: "named SQL parameters only — never f-strings").
    stmt = sa.text("DELETE FROM course_configs WHERE id IN :ids").bindparams(
        sa.bindparam("ids", expanding=True)
    )
    conn.execute(stmt, {"ids": list(COURSES)})
