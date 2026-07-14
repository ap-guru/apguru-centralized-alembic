"""Seed 190 missing grader courses into course_configs (AP Micro/CSP, MYP, IB HL/SL
splits + languages + bridges, and the full Cambridge/Edexcel/AQA IGCSE/GCSE/A-Level
catalog). Backfills every catalog course that had no course_configs row so the grader
stops returning UNKNOWN_COURSE for them.

Addenda reuse the archetype text authored in 021/022/028/031 verbatim, plus five newly
authored archetypes (AP Microeconomics, AP CS Principles, combined/co-ordinated Science,
Cambridge Global Perspectives, IB English markband). exam_body routes the grader's prompt
set (College Board->AP, IBO->IB, Cambridge IGCSE/A-Level->Cambridge; see
app/services/grader_prompts.py); category/scoring_type/subjects are honest placeholders.

Idempotent and keyed on course_id (INSERT ... WHERE NOT EXISTS), NOT on the PK id, because
live instances autoincrement course_configs.id and key on course_id (id != course.id), so an
id-based upsert could overwrite unrelated rows. Safe to re-run. NOTE: prod (ai-services /
database-2) and uat were already seeded directly with these exact rows on 2026-07-14; this
migration is the durable record and a no-op there.

Revision ID: 041
Create Date: 2026-07-14
"""

import sqlalchemy as sa

from alembic import op

revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


# --- archetype addenda (verbatim from 021/022/028/031 + newly authored) ---
AP_MICROECONOMICS_G = "Graded on correct economic reasoning, not prose quality. For graph points, require correctly labeled axes, correctly shaped/positioned curves (supply/demand, a perfectly competitive or monopoly firm's MR/MC/ATC/AVC, factor markets, per-unit tax, etc.), and clearly indicated equilibria, shifts, or shaded areas (profit, loss, deadweight loss, consumer/producer surplus) as the rubric specifies. Award an explanation point only when the response gives the correct direction of change AND the causal chain. Apply follow-through on dependent points."
AP_MICROECONOMICS_O = "Answers are graph-heavy; reproduce each diagram precisely (supply and demand, perfectly competitive firm and industry, monopoly, monopolistic competition, factor/labor market, production possibilities curve, externality/per-unit-tax diagrams, game-theory payoff matrix): axis labels with their exact variables (e.g. price vs quantity; wage vs quantity of labor), every curve the student labelled (S, D, MR, MC, ATC, AVC, MRP, etc.), the direction of any shift (arrow plus from/to), the old/new equilibria marked, and any area the student shaded or labelled (profit, loss, deadweight loss, consumer/producer surplus, tax revenue). For a payoff matrix, transcribe the players, strategies, and every cell's payoffs. Transcribe any calculation (elasticity, profit, per-unit tax, marginal analysis) with setup and result."
ENGLISH_G = "This subject's extended responses are marked with IB markbands (level descriptors), not independent points. Each rubric point whose criterion lists multiple mark bands is one assessment criterion: read the whole response, choose by best-fit the single band whose descriptor it matches, and award a specific mark within that band (lower/middle/upper) reflecting fit — do NOT award the full marks merely for reaching the band, and never combine bands. Short 'define/identify/outline' parts that are point-marked are awarded all-or-nothing as usual. Credit substance over length; reward a sustained, well-evidenced argument that addresses the command term. IB English rewards a focused, defensible interpretation of the text(s) that addresses the task; understanding supported by well-chosen, precise textual reference; analysis of the writer's language, structure, style and their effects on meaning (for Language & Literature, including how context, audience and purpose shape the text); a coherent, well-organised argument; and clear, accurate, suitably registered language. Reward insight and substance over length; paraphrase or unsupported assertion without analysis stays low."
ENGLISH_O = 'Responses are essays or literary commentaries — transcribe the written answer verbatim, preserving paragraphing and any labelled parts. Capture every quotation and line / paragraph reference the student cites from the text, since the analysis marks depend on them. Diagrams are not expected; if the student annotates a passage or sketches a structure map, describe what is marked.'
HISTORY_G = "This subject's extended responses are marked with IB markbands (level descriptors), not independent points. Each rubric point whose criterion lists multiple mark bands is one assessment criterion: read the whole response, choose by best-fit the single band whose descriptor it matches, and award a specific mark within that band (lower/middle/upper) reflecting fit — do NOT award the full marks merely for reaching the band, and never combine bands. Short 'define/identify/outline' parts that are point-marked are awarded all-or-nothing as usual. Credit substance over length; reward a sustained, well-evidenced argument that addresses the command term. History rewards accurate, relevant own knowledge, focus on the demands of the question, analysis over narrative, and — for essays — a balanced argument with a substantiated judgement; for source questions, value/limitation must be grounded in origin, purpose and content."
GEOGRAPHY_G = "This subject's extended responses are marked with IB markbands (level descriptors), not independent points. Each rubric point whose criterion lists multiple mark bands is one assessment criterion: read the whole response, choose by best-fit the single band whose descriptor it matches, and award a specific mark within that band (lower/middle/upper) reflecting fit — do NOT award the full marks merely for reaching the band, and never combine bands. Short 'define/identify/outline' parts that are point-marked are awarded all-or-nothing as usual. Credit substance over length; reward a sustained, well-evidenced argument that addresses the command term. Geography rewards accurate geographic terminology, support from located examples/case studies and any provided resources, and — for 'examine/evaluate/discuss' — a structured, balanced argument that reaches a conclusion."
ECONOMICS_G = "This subject's extended responses are marked with IB markbands (level descriptors), not independent points. Each rubric point whose criterion lists multiple mark bands is one assessment criterion: read the whole response, choose by best-fit the single band whose descriptor it matches, and award a specific mark within that band (lower/middle/upper) reflecting fit — do NOT award the full marks merely for reaching the band, and never combine bands. Short 'define/identify/outline' parts that are point-marked are awarded all-or-nothing as usual. Credit substance over length; reward a sustained, well-evidenced argument that addresses the command term. Economics rewards accurate definitions of key terms, correctly drawn and fully labelled diagrams, application to the context, and — for 'evaluate/discuss' — reasoned evaluation weighing more than one viewpoint; a correct diagram with no explanation, or evaluation with no economic theory, is limited."
ECONOMICS_O = 'Economics answers rely on diagrams — transcribe them precisely. For supply-and-demand / cost-and-revenue / AD-AS diagrams: label both axes (with units where given), name every curve drawn (e.g. S, D, MC, ATC, AD, SRAS), the direction of any shift and its new position, each equilibrium point and any price/quantity lines dropped to the axes, and any area the student shaded or labelled (welfare loss, tax revenue, surplus). State which curves moved and to where. Also transcribe any calculation working and the final value with units (%, $, etc.).'
BIOLOGY_G = "IB Biology is point-marked; award each mark independently for the specific idea the scheme credits (accept 'OWTTE' wording). 'Explain' / 'suggest' marks require a stated mechanism at the molecular, cellular, or ecological level tied to the prompt — a correct conclusion with no valid reasoning earns no reasoning mark. For data-analysis parts require a trend stated with reference to the data (manipulated and responding variables), not a bare restatement of figures; for calculations require the working and correct units. Apply ECF on dependent steps."
BIOLOGY_O = 'For biological diagrams (cell, organelle, tissue, organ, organism): name every structure the student labelled and where it sits relative to others. For cycle diagrams (Krebs, Calvin, cell cycle, nitrogen cycle): name each stage in order, the direction of every arrow, and any inputs/outputs written on the arrows. For experimental graphs: axes (label + units + scale), trend per group/treatment, error bars or ranges if drawn, and any annotation the student added (significance markers, labelled controls vs experimentals). For pedigrees, Punnett squares and gel images: the row/column layout and what is in each cell.'
CHEMISTRY_G = "IB Chemistry is point-marked. For calculations require the correct setup AND the final answer with appropriate units, applying ECF so an incorrect earlier value used correctly downstream still earns later marks; accept answers within the scheme's tolerance and penalize significant figures only where the scheme says so. Require balanced equations, correct formulae and state symbols where specified. Explanation marks require correct particulate-/molecular-level reasoning (bonding, intermolecular forces, electronegativity, collision theory, equilibrium shifts) tied to the prompt — a correct answer with no valid reasoning earns no reasoning mark."
CHEMISTRY_O = "Diagram fidelity matters — marks are awarded for specific bonds, lone pairs, charges and geometries the student drew. For Lewis / dot structures: name every atom by element symbol, every bond by its multiplicity and the two atoms it joins (e.g. 'C=O', 'N-H'), every lone pair (count and on which atom), every formal charge with sign and adjacent atom, and the overall shape (bent, trigonal planar, tetrahedral, octahedral) when discernible. For intermolecular-force diagrams: for each interaction line drawn, state the donor atom (and which H), the acceptor atom (and which lone pair), the molecule each belongs to, and its position on the page. For energy / reaction-profile diagrams: each peak's relative height, the position and label of any intermediate, and whether reactants are higher or lower than products. For graphs/titration curves: axes, scale, and every plotted feature including equivalence points."
PHYSICS_G = "IB Physics is point-marked (relationship/setup, substitution, final answer with units, plus explanation marks). Apply ECF / follow-through so an incorrect earlier value used correctly downstream still earns later marks. Accept algebraically equivalent expressions and correct alternative methods; require correct units, significant figures within the scheme's tolerance where it specifies, and vector direction where relevant. Award explanation marks only for a correct, coherent line of physics reasoning linked to the scenario — a bare claim or an unexplained equation does not earn it. 'OWTTE' (or words to that effect) means accept any wording carrying the same physics."
PHYSICS_O = 'For free-body / force diagrams: every vector with its tail point, head direction (up/down/left/right or angle), labelled magnitude (mg, N, T, f, F_app, etc.), and the object it acts on. For circuit diagrams: each component (resistor, capacitor, cell, switch) with its labelled value, the connection topology, and any labelled current direction or polarity. For field / ray diagrams: arrow directions, relative density, labelled magnitudes, lens/mirror type, focal points and image position. For motion / P-V / graph sketches: coordinate axes with labels, units and scale, the curve shape (linear, parabolic, constant), key values at labelled points, and any area the student shaded.'
SCIENCE_COMBINED_G = "Combined / co-ordinated science is point-marked across biology, chemistry and physics; award each mark independently for the specific idea the scheme credits (accept equivalent wording and listed alternatives separated by '/'). For calculations require the correct working AND the final answer with appropriate units, applying ECF / follow-through so an incorrect earlier value used correctly downstream still earns later marks; accept answers within the scheme's tolerance and penalise significant figures only where it says so. Require balanced equations and correct formulae in chemistry, correct units and vector direction in physics, and a stated mechanism where a biology 'explain' mark demands it. 'Explain / suggest' marks require correct reasoning tied to the prompt — a bare correct answer earns no reasoning mark; 'state / identify' may be brief."
SCIENCE_COMBINED_O = "Science answers span all three disciplines — transcribe every diagram precisely. Biology (cells, organs, cycles): name each labelled structure or stage and the direction of every arrow. Chemistry (apparatus, dot-and-cross / bonding structures, energy profiles): label components, each bond and lone pair, formal charges, and relative energies. Physics (circuits, force / ray diagrams, motion graphs): each component with its value and the connection topology, every vector's direction and labelled magnitude, and axes with units and scale. For data tables and graphs: reproduce headers with units, every plotted point or cell value, the trend, and anything the student read off or annotated. Transcribe all calculation working with units."
MATH_G = 'IB Mathematics is marked with method (M), accuracy (A) and reasoning (R) marks. Award M marks for a valid, clearly indicated method even if it contains an arithmetic slip; award A marks only for correct results, and an A mark depends on the preceding M mark. Apply ECF / follow-through: a value that is wrong because of an earlier error but is then used with correct subsequent method still earns the later M (and dependent A) marks. Accept equivalent forms (exact or correctly rounded decimals, algebraically equivalent expressions) and correct alternative valid methods. Where the answer is given (AG), the working must justify it; a bare answer with no working earns only what the scheme allows for the answer alone.'
MATH_O = "Transcribe mathematical working faithfully: every line of algebra, each step's operator, and the final answer (LaTeX between $...$). For graphs/sketches: axis labels with scale, the curve's shape and key features (intercepts, turning points, asymptotes), and any points or regions the student marked or shaded. For geometry/vector/probability diagrams: labelled lengths and angles, vector directions and magnitudes, and branch labels/probabilities."
ESS_G = "IB Environmental Systems & Societies is point-marked and rewards specificity. Vague or generic statements earn no credit — require a concrete mechanism, named example, or specific cause-and-effect link relevant to the systems/sustainability context. For calculation parts require the setup/working and correct units, applying follow-through on arithmetic. 'Explain/evaluate' demands developed reasoning (and, for evaluate, more than one perspective); 'identify/state' may be brief. Where a part is marked by a level band, apply best-fit markband judgement."
ESS_O = 'For data tables: reproduce the row and column headers (with units) and every cell value the student wrote. For graphs: axis labels with units and scale, the trend per series, and any value the student read off or annotated. For cycle / system diagrams (carbon, nitrogen, water, energy flow): name each labelled pool or stage and the direction of every arrow, with any flux value written on it. For calculation work: transcribe the setup, the units, and the final value verbatim.'
PHILOSOPHY_G = "This subject's extended responses are marked with IB markbands (level descriptors), not independent points. Each rubric point whose criterion lists multiple mark bands is one assessment criterion: read the whole response, choose by best-fit the single band whose descriptor it matches, and award a specific mark within that band (lower/middle/upper) reflecting fit — do NOT award the full marks merely for reaching the band, and never combine bands. Short 'define/identify/outline' parts that are point-marked are awarded all-or-nothing as usual. Credit substance over length; reward a sustained, well-evidenced argument that addresses the command term. Philosophy rewards a clear grasp of the philosophical issue, a well-structured argument with reasons, use of relevant philosophical material, and critical evaluation including counter-arguments."
CS_G = 'IB Computer Science answers are marked for correct algorithmic intent. Accept pseudocode or Java that is functionally correct even with minor syntax slips (missing semicolons, approximate variable names) unless the scheme explicitly requires strict syntax; variable-name differences are not penalized. Award marks for the correct construct (loop, condition, method call, correct use of a data structure) and correct logic/order; deduct only where the logic is wrong or a required step is missing. For trace/output questions require the correct final result, applying follow-through on an earlier consistent slip.'
LANGUAGE_G = "Cambridge modern-language papers mix point-marked comprehension with levels-marked writing. For reading / listening comprehension, award each mark for the specific correct information (accept answers in the target or response language as the scheme allows; ignore minor spelling / accent errors that do not change meaning, OWTTE). For writing and essay tasks apply levels of response across the scheme's strands (typically Content / Communication and Language / Accuracy): place each strand by best-fit and award within the level, rewarding range and accuracy of vocabulary and grammar, task completion, and communicative clarity. Do not penalise a single slip twice."
GLOBAL_POLITICS_G = "This subject's extended responses are marked with IB markbands (level descriptors), not independent points. Each rubric point whose criterion lists multiple mark bands is one assessment criterion: read the whole response, choose by best-fit the single band whose descriptor it matches, and award a specific mark within that band (lower/middle/upper) reflecting fit — do NOT award the full marks merely for reaching the band, and never combine bands. Short 'define/identify/outline' parts that are point-marked are awarded all-or-nothing as usual. Credit substance over length; reward a sustained, well-evidenced argument that addresses the command term. Global Politics rewards use of political concepts, real-world examples/case studies, consideration of different perspectives and levels of analysis, and an explicit, justified conclusion for 'evaluate/to what extent' prompts."
PSYCHOLOGY_G = "This subject's extended responses are marked with levels of response (level descriptors), not independent points. Each rubric point whose criterion lists multiple levels is one assessment ladder: read the whole response, choose by best-fit the single level whose descriptor it matches, and award a specific mark within that level (lower / middle / upper) reflecting fit — do NOT award the top of the level merely for reaching it, and never combine levels. Short point-marked parts (define / identify / calculate) are awarded all-or-nothing. Credit substance over length; reward sustained, well-evidenced analysis that addresses the command word. Psychology rewards accurate use of relevant theories and studies, explicit links to the question, and critical thinking (methodology, ethics, comparisons, applications) for extended answers; short answers require an accurate, focused explanation with a relevant study or concept."
SOCIOLOGY_G = "This subject's extended responses are marked with levels of response (level descriptors), not independent points. Each rubric point whose criterion lists multiple levels is one assessment ladder: read the whole response, choose by best-fit the single level whose descriptor it matches, and award a specific mark within that level (lower / middle / upper) reflecting fit — do NOT award the top of the level merely for reaching it, and never combine levels. Short point-marked parts (define / identify / calculate) are awarded all-or-nothing. Credit substance over length; reward sustained, well-evidenced analysis that addresses the command word. Sociology rewards accurate use of sociological concepts, theories and studies (e.g. functionalism, Marxism, feminism, interactionism), explicit application to the question, and — for evaluative parts — a two-sided argument that weighs perspectives and reaches a conclusion; juxtaposed perspectives with no analysis stay mid-level."
CAM_ENGLISH_G = "This subject's extended responses are marked with levels of response (level descriptors), not independent points. Each rubric point whose criterion lists multiple levels is one assessment ladder: read the whole response, choose by best-fit the single level whose descriptor it matches, and award a specific mark within that level (lower / middle / upper) reflecting fit — do NOT award the top of the level merely for reaching it, and never combine levels. Short point-marked parts (define / identify / calculate) are awarded all-or-nothing. Credit substance over length; reward sustained, well-evidenced analysis that addresses the command word. English rewards a focused response to the task supported by precise textual reference / quotation, analysis of language, structure and form and their effects, and — at higher levels — a perceptive, well-developed argument. For directed / transactional writing, reward appropriate audience, purpose, tone and accurate expression. Comprehension and short-answer points are marked all-or-nothing on the specific content required."
CAM_PHYSICS_G = "Cambridge Physics is point-marked (defining relationship, substitution, evaluation with the correct unit, plus explanation marks). Apply ECF so an incorrect earlier value used correctly downstream still earns later marks. Accept algebraically equivalent expressions, correct alternative methods and OWTTE wording, and answers within the scheme's stated tolerance; require correct units and, where the scheme specifies, significant figures and vector direction. Award explanation marks only for a correct, coherent line of physics reasoning tied to the scenario — a bare statement or an unexplained equation does not earn it."
CAM_PHYSICS_O = 'For free-body / force diagrams: every vector with its tail point, head direction (up / down / left / right or angle), labelled magnitude (mg, N, T, f, F_app, etc.), and the object it acts on. For circuit diagrams: each component (resistor, capacitor, cell, switch) with its labelled value, the connection topology, and any labelled current direction or polarity. For field / ray diagrams: arrow directions, relative density, labelled magnitudes, lens / mirror type, focal points and image position. For motion / graph sketches: coordinate axes with labels, units and scale, the curve shape (linear, parabolic, constant), key values at labelled points, and any area the student shaded.'
CAM_MATH_G = 'Cambridge Mathematics is marked with method (M) and accuracy (A) marks. Award M marks for a valid, clearly indicated method even if it carries an arithmetic slip; award A marks only for a correct result, and an A mark depends on the preceding M mark. Apply ECF / follow-through unless the scheme marks a point CAO (correct answer only): a value that is wrong because of an earlier error but is then used with correct subsequent method still earns the later marks. Accept equivalent forms (exact surds or correctly rounded decimals, algebraically equivalent expressions, OE) and any correct alternative method. A correct answer with no working earns full marks unless the scheme requires working to be shown.'
CAM_MATH_O = "Transcribe mathematical working faithfully: every line of algebra, each step's operator, and the final answer (LaTeX between $...$). For graphs / sketches: axis labels with scale, the curve's shape and key features (intercepts, turning points, asymptotes), and any points or regions the student marked or shaded. For geometry / vector / probability diagrams: labelled lengths and angles, vector directions and magnitudes, and branch labels / probabilities."
CAM_BIOLOGY_G = "Cambridge Biology is point-marked; award each mark independently for the specific idea the scheme credits (accept OWTTE wording and listed alternatives separated by '/'). 'Explain' and 'suggest' marks require a stated mechanism at the molecular, cellular, or ecological level tied to the prompt — a correct conclusion with no reasoning earns no reasoning mark. For data questions require a trend stated with reference to the figures, not a bare restatement; for calculations require the working and correct units. Apply ECF on dependent steps; honour ORA."
CAM_BIOLOGY_O = 'For biological diagrams (cell, organelle, tissue, organ, organism): name every structure the student labelled and where it sits relative to others. For cycle diagrams (Krebs, Calvin, cell cycle, nitrogen cycle): name each stage in order, the direction of every arrow, and any inputs / outputs written on the arrows. For experimental graphs: axes (label + units + scale), trend per group / treatment, error bars or ranges if drawn, and any annotation the student added. For pedigrees, Punnett squares and gel images: the row / column layout and what is in each cell.'
CAM_CHEMISTRY_G = 'Cambridge Chemistry is point-marked. For calculations require the correct working AND the final answer with appropriate units, applying ECF so an incorrect earlier value used correctly downstream still earns later marks; accept answers within tolerance and penalise significant figures only where the scheme says so. Require balanced equations, correct formulae and state symbols where specified. Explanation marks require correct reasoning at the particulate level (bonding, intermolecular forces, electronegativity, rates / collision theory, equilibrium shifts) tied to the prompt — a correct answer with no valid reasoning earns no reasoning mark. Accept ORA and OWTTE wording.'
CAM_CHEMISTRY_O = "Diagram fidelity matters — marks are awarded for specific bonds, lone pairs, charges and geometries the student drew. For dot-and-cross / displayed structures: name every atom by element symbol, every bond by its multiplicity and the two atoms it joins (e.g. 'C=O', 'N-H'), every lone / bonding pair, every formal charge with sign and adjacent atom, and the overall shape (bent, trigonal planar, tetrahedral) when discernible. For energy / reaction-profile diagrams: each peak's relative height, the position and label of any intermediate, and whether reactants are higher or lower than products. For apparatus diagrams and titration / rate graphs: label the components, axes, scale, and every plotted feature including end / equivalence points."
CAM_CS_G = 'Cambridge Computer Science and IT answers are marked for correct intent. Accept pseudocode or program code that is functionally correct even with minor syntax slips unless the scheme explicitly requires strict syntax; variable-name differences are not penalised. Award marks for the correct construct (loop, condition, function / procedure call, correct use of a data structure or SQL / logic operation) and correct logic and order; deduct only where the logic is wrong or a required step is missing. For trace-table / output questions require the correct final result, applying follow-through on an earlier consistent slip. For any levels-marked evaluative part apply best-fit level judgement.'
BUSINESS_G = "This subject's extended responses are marked with levels of response (level descriptors), not independent points. Each rubric point whose criterion lists multiple levels is one assessment ladder: read the whole response, choose by best-fit the single level whose descriptor it matches, and award a specific mark within that level (lower / middle / upper) reflecting fit — do NOT award the top of the level merely for reaching it, and never combine levels. Short point-marked parts (define / identify / calculate) are awarded all-or-nothing. Credit substance over length; reward sustained, well-evidenced analysis that addresses the command word. Business rewards application of specific business concepts / tools to the case context, balanced analysis, and — for 'evaluate / recommend / assess / justify' — a substantiated judgement; generic theory not tied to the case earns little. Reward correct calculations (with working and units) where required."
CAM_ECONOMICS_G = "This subject's extended responses are marked with levels of response (level descriptors), not independent points. Each rubric point whose criterion lists multiple levels is one assessment ladder: read the whole response, choose by best-fit the single level whose descriptor it matches, and award a specific mark within that level (lower / middle / upper) reflecting fit — do NOT award the top of the level merely for reaching it, and never combine levels. Short point-marked parts (define / identify / calculate) are awarded all-or-nothing. Credit substance over length; reward sustained, well-evidenced analysis that addresses the command word. Economics rewards accurate definitions of key terms, correctly drawn and fully labelled diagrams, application to the given context, and — for 'evaluate / discuss / assess' — reasoned evaluation weighing more than one viewpoint and reaching a supported judgement; a correct diagram with no explanation, or evaluation with no economic theory, is limited."
CAM_ECONOMICS_O = 'Economics answers rely on diagrams — transcribe them precisely. For supply-and-demand / cost-and-revenue / AD-AS diagrams: label both axes (with units where given), name every curve drawn (e.g. S, D, MC, ATC, AD, SRAS), the direction of any shift and its new position, each equilibrium point and any price / quantity lines dropped to the axes, and any area the student shaded or labelled (welfare loss, tax revenue, surplus). State which curves moved and to where. Also transcribe any calculation working and the final value with units (%, $, etc.).'
CAM_HISTORY_G = "This subject's extended responses are marked with levels of response (level descriptors), not independent points. Each rubric point whose criterion lists multiple levels is one assessment ladder: read the whole response, choose by best-fit the single level whose descriptor it matches, and award a specific mark within that level (lower / middle / upper) reflecting fit — do NOT award the top of the level merely for reaching it, and never combine levels. Short point-marked parts (define / identify / calculate) are awarded all-or-nothing. Credit substance over length; reward sustained, well-evidenced analysis that addresses the command word. History rewards accurate, relevant own knowledge, focus on the precise demands of the question, analysis over narrative, and — for essays — a balanced argument with a substantiated judgement. For source questions, evaluation of utility / reliability must be grounded in provenance (origin, purpose and content), not asserted."
AP_CS_PRINCIPLES_G = "AP Computer Science Principles written responses are scored against the College Board scoring guidelines, each row/point awarded independently. Award a point only for specific, accurate evidence tied to the student's own program or the provided stimulus: a program function and purpose that match the code, a correctly identified algorithm and how it uses sequencing, selection, and iteration, a genuine abstraction (a student-developed procedure or list) and how it manages complexity, and a correct account of how the program stores and uses data. Do not award a point for a vague or generic statement, a restatement of the prompt, or a feature the code does not actually implement. Accept functionally correct explanations regardless of the programming language or minor terminology slips."
AP_CS_PRINCIPLES_O = 'Responses mix written prose with program code or pseudocode and occasionally a flowchart. Transcribe code verbatim — every line, the nesting/indentation, procedure and parameter names, loop and conditional structure, and any list operations — because scoring depends on identifying the algorithm and the abstraction. Transcribe the written answers in full, preserving labelled parts (a, b, c, ...). For any flowchart or diagram, describe each block and the direction of flow.'
GLOBAL_PERSPECTIVES_G = 'Cambridge Global Perspectives is marked with levels of response against assessment criteria (typically Analysis, Evaluation, Reflection, use of Research / sources, and Communication), not independent points. For each criterion read the whole response and award by best-fit the single level whose descriptor it matches, with a specific mark within that level reflecting fit — never combine levels or award the top of a level merely for reaching it. Reward analysis of an issue from different perspectives (personal / national / global), evaluation of the strength and credibility of evidence and reasoning rather than just its content, well-supported use of relevant sources with awareness of bias, and a clear, structured argument that reaches a substantiated conclusion. Description, narration, or unsupported opinion stays low; genuine evidenced critical judgement scores highest.'
GLOBAL_PERSPECTIVES_O = 'Responses are essays or structured reports rather than diagrams — transcribe the written answer in full, preserving section headings, any labelled perspectives, and every source reference or citation the student gives (these carry the research / use-of-sources marks). If the student includes a table, chart, or figure to present evidence, reproduce its headers, values, and what it is intended to show.'


# course.id -> (course_name, exam_body, category, scoring_type, subjects_json, grading, ocr)
ROWS: dict[int, tuple] = {
    19: ('AP Microeconomics', 'College Board', 'prep', 'composite', '["microeconomics"]', AP_MICROECONOMICS_G, AP_MICROECONOMICS_O),
    61: ('MYP English', 'IBO', 'academic', 'grade', '["english"]', ENGLISH_G, ENGLISH_O),
    62: ('MYP History', 'IBO', 'academic', 'grade', '["history"]', HISTORY_G, ""),
    63: ('MYP Geography', 'IBO', 'academic', 'grade', '["geography"]', GEOGRAPHY_G, ""),
    64: ('MYP Economics', 'IBO', 'academic', 'grade', '["economics"]', ECONOMICS_G, ECONOMICS_O),
    65: ('MYP Biology', 'IBO', 'academic', 'grade', '["biology"]', BIOLOGY_G, BIOLOGY_O),
    66: ('MYP Chemistry', 'IBO', 'academic', 'grade', '["chemistry"]', CHEMISTRY_G, CHEMISTRY_O),
    67: ('MYP Physics', 'IBO', 'academic', 'grade', '["physics"]', PHYSICS_G, PHYSICS_O),
    68: ('MYP Integrated Science', 'IBO', 'academic', 'grade', '["integrated-science"]', SCIENCE_COMBINED_G, SCIENCE_COMBINED_O),
    69: ('MYP Standard Math', 'IBO', 'academic', 'grade', '["standard-math"]', MATH_G, MATH_O),
    70: ('MYP Extended Math', 'IBO', 'academic', 'grade', '["extended-math"]', MATH_G, MATH_O),
    119: ('IB Math SL AI Bridge Course', 'IBO', 'academic', 'grade', '["math-sl-ai-bridge-course"]', MATH_G, MATH_O),
    120: ('IB Math HL AI Bridge Course', 'IBO', 'academic', 'grade', '["math-hl-ai-bridge-course"]', MATH_G, MATH_O),
    121: ('IB Math SL AA Bridge Course', 'IBO', 'academic', 'grade', '["math-sl-aa-bridge-course"]', MATH_G, MATH_O),
    122: ('IB Math HL AA Bridge Course', 'IBO', 'academic', 'grade', '["math-hl-aa-bridge-course"]', MATH_G, MATH_O),
    123: ('IB English SL Bridge Course', 'IBO', 'academic', 'grade', '["english-sl-bridge-course"]', ENGLISH_G, ENGLISH_O),
    124: ('IB English HL Bridge Course', 'IBO', 'academic', 'grade', '["english-hl-bridge-course"]', ENGLISH_G, ENGLISH_O),
    125: ('IB Physics HL Bridge Course', 'IBO', 'academic', 'grade', '["physics-hl-bridge-course"]', PHYSICS_G, PHYSICS_O),
    126: ('IB Physics SL Bridge Course', 'IBO', 'academic', 'grade', '["physics-sl-bridge-course"]', PHYSICS_G, PHYSICS_O),
    127: ('IB Economics HL Bridge Course', 'IBO', 'academic', 'grade', '["economics-hl-bridge-course"]', ECONOMICS_G, ECONOMICS_O),
    128: ('IB Economics SL Bridge Course', 'IBO', 'academic', 'grade', '["economics-sl-bridge-course"]', ECONOMICS_G, ECONOMICS_O),
    129: ('IB ESS SL', 'IBO', 'academic', 'grade', '["ess-sl"]', ESS_G, ESS_O),
    130: ('IB ESS HL', 'IBO', 'academic', 'grade', '["ess-hl"]', ESS_G, ESS_O),
    131: ('IB Philosophy HL', 'IBO', 'academic', 'grade', '["philosophy-hl"]', PHILOSOPHY_G, ""),
    132: ('IB Philosophy SL', 'IBO', 'academic', 'grade', '["philosophy-sl"]', PHILOSOPHY_G, ""),
    133: ('IB Computer Science SL', 'IBO', 'academic', 'grade', '["computer-science-sl"]', CS_G, ""),
    134: ('IB Computer Science HL', 'IBO', 'academic', 'grade', '["computer-science-hl"]', CS_G, ""),
    135: ('IB History HL', 'IBO', 'academic', 'grade', '["history-hl"]', HISTORY_G, ""),
    136: ('IB History SL', 'IBO', 'academic', 'grade', '["history-sl"]', HISTORY_G, ""),
    137: ('IB Geography HL', 'IBO', 'academic', 'grade', '["geography-hl"]', GEOGRAPHY_G, ""),
    138: ('IB Geography SL', 'IBO', 'academic', 'grade', '["geography-sl"]', GEOGRAPHY_G, ""),
    139: ('IB English HL', 'IBO', 'academic', 'grade', '["english-hl"]', ENGLISH_G, ENGLISH_O),
    140: ('IB English SL', 'IBO', 'academic', 'grade', '["english-sl"]', ENGLISH_G, ENGLISH_O),
    144: ('IB Spanish SL B', 'IBO', 'academic', 'grade', '["spanish-sl-b"]', LANGUAGE_G, ""),
    145: ('IB Spanish SL AB Initio', 'IBO', 'academic', 'grade', '["spanish-sl-ab-initio"]', LANGUAGE_G, ""),
    146: ('IB French SL B', 'IBO', 'academic', 'grade', '["french-sl-b"]', LANGUAGE_G, ""),
    147: ('IB French SL AB Initio', 'IBO', 'academic', 'grade', '["french-sl-ab-initio"]', LANGUAGE_G, ""),
    148: ('IB Global Politics HL', 'IBO', 'academic', 'grade', '["global-politics-hl"]', GLOBAL_POLITICS_G, ""),
    149: ('IB Global Politics SL', 'IBO', 'academic', 'grade', '["global-politics-sl"]', GLOBAL_POLITICS_G, ""),
    150: ('IB Hindi SL', 'IBO', 'academic', 'grade', '["hindi-sl"]', LANGUAGE_G, ""),
    151: ('AS-Level Cambridge Psychology', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["psychology"]', PSYCHOLOGY_G, ""),
    152: ('A-Level Cambridge Psychology', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["psychology"]', PSYCHOLOGY_G, ""),
    153: ('AS-Level Cambridge Sociology', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["sociology"]', SOCIOLOGY_G, ""),
    154: ('A-Level Cambridge Sociology', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["sociology"]', SOCIOLOGY_G, ""),
    155: ('AS-Level Cambridge English', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["english"]', CAM_ENGLISH_G, ""),
    156: ('A-Level Cambridge English', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["english"]', CAM_ENGLISH_G, ""),
    157: ('AS-Level General English', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["english"]', CAM_ENGLISH_G, ""),
    158: ('AS-Level Cambridge Physics', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["physics"]', CAM_PHYSICS_G, CAM_PHYSICS_O),
    159: ('A-Level Cambridge Physics', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["physics"]', CAM_PHYSICS_G, CAM_PHYSICS_O),
    160: ('AS-Level Edexcel Further Math', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["further-math"]', CAM_MATH_G, CAM_MATH_O),
    161: ('A-Level Edexcel Further Math', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["further-math"]', CAM_MATH_G, CAM_MATH_O),
    162: ('IGCSE Cambridge Spanish', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["spanish"]', LANGUAGE_G, ""),
    163: ('IGCSE Cambridge Spanish as a Foreign Language', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["spanish-as-a-foreign-language"]', LANGUAGE_G, ""),
    164: ('IGCSE Cambridge English', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["english"]', CAM_ENGLISH_G, ""),
    165: ('IGCSE Cambridge First Language English', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["first-language-english"]', CAM_ENGLISH_G, ""),
    166: ('IGCSE Cambridge Literature in English', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["literature-in-english"]', CAM_ENGLISH_G, ""),
    167: ('IGCSE Cambridge English as a Second Language', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["english-as-a-second-language"]', LANGUAGE_G, ""),
    168: ('AS-Level Cambridge Further Math', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["further-math"]', CAM_MATH_G, CAM_MATH_O),
    169: ('A-Level Cambridge Further Math', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["further-math"]', CAM_MATH_G, CAM_MATH_O),
    170: ('IGCSE Cambridge Physics', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["physics"]', CAM_PHYSICS_G, CAM_PHYSICS_O),
    171: ('IGCSE Cambridge Physics - Core', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["physics-core"]', CAM_PHYSICS_G, CAM_PHYSICS_O),
    172: ('IGCSE Cambridge Physics - Extended', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["physics-extended"]', CAM_PHYSICS_G, CAM_PHYSICS_O),
    173: ('IAS Biology', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["biology"]', CAM_BIOLOGY_G, CAM_BIOLOGY_O),
    174: ('IAL Biology', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["biology"]', CAM_BIOLOGY_G, CAM_BIOLOGY_O),
    175: ('IGCSE Cambridge Math', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["math"]', CAM_MATH_G, CAM_MATH_O),
    176: ('IGCSE Cambridge Math - Core', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["math-core"]', CAM_MATH_G, CAM_MATH_O),
    177: ('IGCSE Cambridge Math - Extended', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["math-extended"]', CAM_MATH_G, CAM_MATH_O),
    178: ('IGCSE Cambridge Additional Math', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["additional-math"]', CAM_MATH_G, CAM_MATH_O),
    179: ('IGCSE Cambridge International Math', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["math"]', CAM_MATH_G, CAM_MATH_O),
    180: ('AS-Level Edexcel Physics', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["physics"]', CAM_PHYSICS_G, CAM_PHYSICS_O),
    181: ('IGCSE Cambridge Chemistry', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["chemistry"]', CAM_CHEMISTRY_G, CAM_CHEMISTRY_O),
    182: ('IGCSE Cambridge Chemistry - Core', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["chemistry-core"]', CAM_CHEMISTRY_G, CAM_CHEMISTRY_O),
    183: ('IGCSE Cambridge Chemistry - Extended', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["chemistry-extended"]', CAM_CHEMISTRY_G, CAM_CHEMISTRY_O),
    184: ('IGCSE Cambridge Computer Science', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["computer-science"]', CAM_CS_G, ""),
    185: ('IGCSE Cambridge Co-ordinated Science', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["co-ordinated-science"]', SCIENCE_COMBINED_G, SCIENCE_COMBINED_O),
    186: ('IGCSE Cambridge Co-ordinated Science - Core', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["co-ordinated-science-core"]', SCIENCE_COMBINED_G, SCIENCE_COMBINED_O),
    187: ('IGCSE Cambridge Co-ordinated Science - Extended', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["co-ordinated-science-extended"]', SCIENCE_COMBINED_G, SCIENCE_COMBINED_O),
    188: ('IAS Chemistry', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["chemistry"]', CAM_CHEMISTRY_G, CAM_CHEMISTRY_O),
    189: ('IAL Chemistry', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["chemistry"]', CAM_CHEMISTRY_G, CAM_CHEMISTRY_O),
    190: ('IGCSE Edexcel Further Math', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["further-math"]', CAM_MATH_G, CAM_MATH_O),
    191: ('IGCSE Cambridge Biology', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["biology"]', CAM_BIOLOGY_G, CAM_BIOLOGY_O),
    192: ('IGCSE Cambridge Biology - Core', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["biology-core"]', CAM_BIOLOGY_G, CAM_BIOLOGY_O),
    193: ('IGCSE Cambridge Biology - Extended', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["biology-extended"]', CAM_BIOLOGY_G, CAM_BIOLOGY_O),
    194: ('AS-Level Cambridge Math', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["math"]', CAM_MATH_G, CAM_MATH_O),
    195: ('A-Level Cambridge Math', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["math"]', CAM_MATH_G, CAM_MATH_O),
    196: ('IAS Physics', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["physics"]', CAM_PHYSICS_G, CAM_PHYSICS_O),
    197: ('IAL Physics', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["physics"]', CAM_PHYSICS_G, CAM_PHYSICS_O),
    198: ('IAS Math', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["math"]', CAM_MATH_G, CAM_MATH_O),
    199: ('IAL Math', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["math"]', CAM_MATH_G, CAM_MATH_O),
    200: ('IAL Business', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["business"]', BUSINESS_G, ""),
    201: ('AS-Level AQA Sociology', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["sociology"]', SOCIOLOGY_G, ""),
    202: ('A-Level AQA Sociology', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["sociology"]', SOCIOLOGY_G, ""),
    203: ('Cambridge Lower Secondary Science', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["science"]', SCIENCE_COMBINED_G, SCIENCE_COMBINED_O),
    204: ('Cambridge Lower Secondary Math', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["math"]', CAM_MATH_G, CAM_MATH_O),
    205: ('GCSE AQA Psychology', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["psychology"]', PSYCHOLOGY_G, ""),
    206: ('GCSE AQA English', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["english"]', CAM_ENGLISH_G, ""),
    207: ('GCSE AQA English Literature', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["english-literature"]', CAM_ENGLISH_G, ""),
    208: ('GCSE AQA English Language', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["english-language"]', CAM_ENGLISH_G, ""),
    209: ('AS-Level Edexcel Math', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["math"]', CAM_MATH_G, CAM_MATH_O),
    210: ('A-Level Edexcel Math', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["math"]', CAM_MATH_G, CAM_MATH_O),
    211: ('AS-Level AQA Computer Science', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["computer-science"]', CAM_CS_G, ""),
    212: ('A-Level AQA Computer Science', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["computer-science"]', CAM_CS_G, ""),
    213: ('GCSE Edexcel Math', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["math"]', CAM_MATH_G, CAM_MATH_O),
    214: ('GCSE Edexcel Math - Foundation', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["math-foundation"]', CAM_MATH_G, CAM_MATH_O),
    215: ('GCSE Edexcel Math - Higher', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["math-higher"]', CAM_MATH_G, CAM_MATH_O),
    216: ('IAS Edexcel Business', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["business"]', BUSINESS_G, ""),
    217: ('IAL Edexcel Business', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["business"]', BUSINESS_G, ""),
    218: ('KS3 Math', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["math"]', CAM_MATH_G, CAM_MATH_O),
    219: ('KS3 Science', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["science"]', SCIENCE_COMBINED_G, SCIENCE_COMBINED_O),
    220: ('AS-Level Edexcel Biology', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["biology"]', CAM_BIOLOGY_G, CAM_BIOLOGY_O),
    221: ('AS-Level Edexcel Biology A', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["biology-a"]', CAM_BIOLOGY_G, CAM_BIOLOGY_O),
    222: ('AS-Level Edexcel Biology B', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["biology-b"]', CAM_BIOLOGY_G, CAM_BIOLOGY_O),
    223: ('A-Level Edexcel Biology', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["biology"]', CAM_BIOLOGY_G, CAM_BIOLOGY_O),
    224: ('A-Level Edexcel Biology A', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["biology-a"]', CAM_BIOLOGY_G, CAM_BIOLOGY_O),
    225: ('A-Level Edexcel Biology B', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["biology-b"]', CAM_BIOLOGY_G, CAM_BIOLOGY_O),
    226: ('AS-Level AQA Physics', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["physics"]', CAM_PHYSICS_G, CAM_PHYSICS_O),
    227: ('A-Level AQA Physics', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["physics"]', CAM_PHYSICS_G, CAM_PHYSICS_O),
    228: ('GCSE Edexcel English', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["english"]', CAM_ENGLISH_G, ""),
    229: ('GCSE Edexcel English Language', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["english-language"]', CAM_ENGLISH_G, ""),
    230: ('GCSE Edexcel English Literature', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["english-literature"]', CAM_ENGLISH_G, ""),
    231: ('AS-Level Edexcel Economics', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["economics"]', CAM_ECONOMICS_G, CAM_ECONOMICS_O),
    232: ('AS-Level Edexcel Economics A', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["economics-a"]', CAM_ECONOMICS_G, CAM_ECONOMICS_O),
    233: ('AS-Level Edexcel Economics B', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["economics-b"]', CAM_ECONOMICS_G, CAM_ECONOMICS_O),
    234: ('A-Level Edexcel Economics A', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["economics-a"]', CAM_ECONOMICS_G, CAM_ECONOMICS_O),
    235: ('A-Level Edexcel Economics B', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["economics-b"]', CAM_ECONOMICS_G, CAM_ECONOMICS_O),
    236: ('KS2 Math', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["math"]', CAM_MATH_G, CAM_MATH_O),
    237: ('KS2 Science', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["science"]', SCIENCE_COMBINED_G, SCIENCE_COMBINED_O),
    238: ('IGCSE Edexcel Math A', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["math-a"]', CAM_MATH_G, CAM_MATH_O),
    239: ('IGCSE Edexcel Math A - Foundation', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["math-a-foundation"]', CAM_MATH_G, CAM_MATH_O),
    240: ('IGCSE Edexcel Math A - Higher', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["math-a-higher"]', CAM_MATH_G, CAM_MATH_O),
    241: ('IGCSE Edexcel Geography', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["geography"]', GEOGRAPHY_G, ""),
    242: ('GCSE AQA Business', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["business"]', BUSINESS_G, ""),
    243: ('IGCSE Edexcel Biology', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["biology"]', CAM_BIOLOGY_G, CAM_BIOLOGY_O),
    245: ('IGCSE Edexcel Physics', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["physics"]', CAM_PHYSICS_G, CAM_PHYSICS_O),
    246: ('GCSE Edexcel History', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["history"]', CAM_HISTORY_G, ""),
    247: ('AS-Level Cambridge Economics', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["economics"]', CAM_ECONOMICS_G, CAM_ECONOMICS_O),
    248: ('A-Level Cambridge Economics', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["economics"]', CAM_ECONOMICS_G, CAM_ECONOMICS_O),
    249: ('IGCSE Edexcel Biology - Modular', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["biology-modular"]', CAM_BIOLOGY_G, CAM_BIOLOGY_O),
    250: ('IGCSE Edexcel Chemistry - Modular', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["chemistry-modular"]', CAM_CHEMISTRY_G, CAM_CHEMISTRY_O),
    251: ('IGCSE Edexcel Math - Modular', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["math-modular"]', CAM_MATH_G, CAM_MATH_O),
    252: ('IGCSE Edexcel Physics - Modular', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["physics-modular"]', CAM_PHYSICS_G, CAM_PHYSICS_O),
    253: ('AS-Level AQA Economics', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["economics"]', CAM_ECONOMICS_G, CAM_ECONOMICS_O),
    254: ('A-Level AQA Economics', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["economics"]', CAM_ECONOMICS_G, CAM_ECONOMICS_O),
    255: ('GCSE Edexcel Chemistry', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["chemistry"]', CAM_CHEMISTRY_G, CAM_CHEMISTRY_O),
    256: ('GCSE Edexcel Physics', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["physics"]', CAM_PHYSICS_G, CAM_PHYSICS_O),
    257: ('AS-Level Edexcel Business', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["business"]', BUSINESS_G, ""),
    258: ('A-Level Edexcel Business', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["business"]', BUSINESS_G, ""),
    259: ('IGCSE Cambridge Business', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["business"]', BUSINESS_G, ""),
    260: ('IGCSE Cambridge Economics', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["economics"]', CAM_ECONOMICS_G, CAM_ECONOMICS_O),
    261: ('AS-Level Cambridge Chemistry', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["chemistry"]', CAM_CHEMISTRY_G, CAM_CHEMISTRY_O),
    262: ('A-Level Cambridge Chemistry', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["chemistry"]', CAM_CHEMISTRY_G, CAM_CHEMISTRY_O),
    263: ('GCSE AQA Math', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["math"]', CAM_MATH_G, CAM_MATH_O),
    264: ('IGCSE Edexcel English', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["english"]', CAM_ENGLISH_G, ""),
    265: ('AS-Level Cambridge Biology', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["biology"]', CAM_BIOLOGY_G, CAM_BIOLOGY_O),
    266: ('A-Level Cambridge Biology', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["biology"]', CAM_BIOLOGY_G, CAM_BIOLOGY_O),
    267: ('AS-Level AQA Psychology', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["psychology"]', PSYCHOLOGY_G, ""),
    268: ('A-Level AQA Psychology', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["psychology"]', PSYCHOLOGY_G, ""),
    269: ('GCSE AQA Further Math', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["further-math"]', CAM_MATH_G, CAM_MATH_O),
    270: ('IGCSE AQA Science', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["science"]', SCIENCE_COMBINED_G, SCIENCE_COMBINED_O),
    271: ('IGCSE Edexcel Chemistry', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["chemistry"]', CAM_CHEMISTRY_G, CAM_CHEMISTRY_O),
    272: ('AS-Level AQA Geography', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["geography"]', GEOGRAPHY_G, ""),
    273: ('A-Level AQA Geography', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["geography"]', GEOGRAPHY_G, ""),
    274: ('AS-Level Cambridge CS', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["cs"]', CAM_CS_G, ""),
    276: ('GCSE AQA Biology', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["biology"]', CAM_BIOLOGY_G, CAM_BIOLOGY_O),
    277: ('GCSE AQA Chemistry', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["chemistry"]', CAM_CHEMISTRY_G, CAM_CHEMISTRY_O),
    278: ('GCSE AQA Physics', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["physics"]', CAM_PHYSICS_G, CAM_PHYSICS_O),
    281: ('AP Computer Science Principles', 'College Board', 'prep', 'composite', '["computer-science-principles"]', AP_CS_PRINCIPLES_G, AP_CS_PRINCIPLES_O),
    302: ('A-Level Edexcel Physics', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["physics"]', CAM_PHYSICS_G, CAM_PHYSICS_O),
    303: ('A-Level Edexcel Chemistry', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["chemistry"]', CAM_CHEMISTRY_G, CAM_CHEMISTRY_O),
    304: ('Cambridge Lower Secondary Physics', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["physics"]', CAM_PHYSICS_G, CAM_PHYSICS_O),
    305: ('Cambridge Lower Secondary Chemistry', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["chemistry"]', CAM_CHEMISTRY_G, CAM_CHEMISTRY_O),
    307: ('IGCSE Cambridge Global Perspectives', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["global-perspectives"]', GLOBAL_PERSPECTIVES_G, GLOBAL_PERSPECTIVES_O),
    308: ('Cambridge Lower Secondary Global Perspectives', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["global-perspectives"]', GLOBAL_PERSPECTIVES_G, GLOBAL_PERSPECTIVES_O),
    310: ('A-Level Cambridge Business', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["business"]', BUSINESS_G, ""),
    315: ('Biology', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["biology"]', CAM_BIOLOGY_G, CAM_BIOLOGY_O),
    316: ('Mathematics', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["mathematics"]', CAM_MATH_G, CAM_MATH_O),
    317: ('Physics', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["physics"]', CAM_PHYSICS_G, CAM_PHYSICS_O),
    318: ('Chemistry', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["chemistry"]', CAM_CHEMISTRY_G, CAM_CHEMISTRY_O),
    320: ('IGCSE Cambridge History', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["history"]', CAM_HISTORY_G, ""),
    321: ('AS-Level Cambridge Computer Science', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["computer-science"]', CAM_CS_G, ""),
    322: ('A-Level Cambridge Computer Science', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["computer-science"]', CAM_CS_G, ""),
    323: ('KS3 English', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["english"]', CAM_ENGLISH_G, ""),
    324: ('IGCSE Edexcel Triple Science', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["triple-science"]', SCIENCE_COMBINED_G, SCIENCE_COMBINED_O),
    326: ('IGCSE Edexcel Economics', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["economics"]', CAM_ECONOMICS_G, CAM_ECONOMICS_O),
    329: ('IB Economics HL IO', 'IBO', 'academic', 'grade', '["economics-hl-io"]', ECONOMICS_G, ECONOMICS_O),
    336: ('A-Level Oxford AQA Physics', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["physics"]', CAM_PHYSICS_G, CAM_PHYSICS_O),
    340: ('IB English Language and Lit HL', 'IBO', 'academic', 'grade', '["english-language-and-lit-hl"]', ENGLISH_G, ENGLISH_O),
    341: ('IB English Language and Lit SL', 'IBO', 'academic', 'grade', '["english-language-and-lit-sl"]', ENGLISH_G, ENGLISH_O),
    344: ('IB Math SL AA', 'IBO', 'academic', 'grade', '["math-sl-aa"]', MATH_G, MATH_O),
    349: ('A-Level AQA Business', 'Cambridge IGCSE/A-Level', 'academic', 'grade', '["business"]', BUSINESS_G, ""),
}


def upgrade() -> None:
    conn = op.get_bind()
    stmt = sa.text(
        "INSERT INTO course_configs "
        "(course_id, course_name, exam_body, category, scoring_type, subjects, is_active, "
        " grading_addendum, ocr_addendum) "
        "SELECT :course_id, :name, :body, :cat, :scoring, :subjects, 1, :g, :o "
        "FROM DUAL WHERE NOT EXISTS "
        "(SELECT 1 FROM course_configs WHERE course_id = :course_id)"
    )
    for cid, (name, body, cat, scoring, subjects, g, o) in ROWS.items():
        conn.execute(stmt, {
            "course_id": str(cid), "name": name, "body": body, "cat": cat,
            "scoring": scoring, "subjects": subjects, "g": g, "o": o,
        })


def downgrade() -> None:
    conn = op.get_bind()
    stmt = sa.text("DELETE FROM course_configs WHERE course_id IN :ids").bindparams(
        sa.bindparam("ids", expanding=True)
    )
    conn.execute(stmt, {"ids": [str(cid) for cid in ROWS]})
