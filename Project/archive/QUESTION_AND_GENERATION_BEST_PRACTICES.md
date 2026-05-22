# Question and Generation Best Practices

This document explains every scientifically-grounded technique used in the SOLO
Quiz Generator for **producing**, **validating**, and **measuring** multiple-choice
questions. Each section names the technique, cites the paper it comes from, and
points at the exact file in the codebase that implements it — so the link
between research and code is verifiable rather than aspirational.

---

## Table of contents

1. [Overview](#1-overview)
2. [Generation techniques (what happens when you click "Generate")](#2-generation-techniques)
3. [Distractor techniques (what fills the three wrong options)](#3-distractor-techniques)
4. [A-priori quality and validity layer](#4-a-priori-quality-and-validity-layer)
5. [Composite techniques (how the layers stack on top of each other)](#5-composite-techniques)
6. [References (alphabetical, with DOIs / arXiv IDs)](#6-references)

---

## 1. Overview

The pipeline produces a question in three logical stages, each grounded in
established research:

```
                        ┌─────────────────────────────────┐
                        │ 1. PROMPT (prevention layer)    │
                        │    PS4 template, CoT scaffold,  │
                        │    Haladyna 2002 rules,         │
                        │    typed distractor strategies  │
                        └────────────────┬────────────────┘
                                         │
                                         ▼
                        ┌─────────────────────────────────┐
                        │ 2. LLM CALL → JSON question     │
                        │    Single Ollama call, JSON     │
                        │    mode, source_line citation   │
                        └────────────────┬────────────────┘
                                         │
                                         ▼
                        ┌─────────────────────────────────┐
                        │ 3. POST-HOC VALIDATION layer    │
                        │    Haladyna lint, embedding     │
                        │    plausibility/diversity,      │
                        │    CoVe, Solvability, SOLO      │
                        │    judge, concept coverage      │
                        └─────────────────────────────────┘
```

The same rule codes (e.g. `H22`, `H27`) appear in **both** the prevention layer
(the prompt that asks the model not to violate them) and the detection layer
(the lint that flags them when the model violates them anyway). This shared
vocabulary is intentional: you can quote your own metrics back to the
prompt and the link is exact.

---

## 2. Generation techniques

### 2.1. SOLO Taxonomy (Biggs & Collis, 1982)

**What it is.** A four-level model of cognitive complexity in learning
outcomes: *unistructural* (recall one fact), *multistructural* (list several
independent facts), *relational* (explain how concepts connect), *extended
abstract* (apply a principle in a new context). Unlike Bloom, SOLO is
explicitly hierarchical and built around the *structure* of student answers,
which is exactly what generated questions need to target.

**Why used here.** It is the project's main difficulty / cognitive-demand axis.
Every generated question carries a SOLO level, every prompt specialises on
that level, and every measurement (judge, solvability trend) is reported per
level.

**Where in the code.**
- [`backend/core/prompt_lib.py`](backend/core/prompt_lib.py), `SOLO_DEFINITIONS`
  dict (one short definition per level).
- [`backend/models/models.py`](backend/models/models.py), `SoloLevel` enum
  on the `Question` table.

**Reference.** Biggs & Collis (1982). *Evaluating the Quality of Learning: The
SOLO Taxonomy.* Academic Press.

---

### 2.2. PS4 prompting strategy (Scaria et al., 2024)

**What it is.** A specific prompt template for educational MCQ generation that
combines:
- a role-priming sentence ("You are an expert educational assessment designer…"),
- a one-or-two sentence definition of the target level,
- *one* worked example per level (not five — the paper found PS5 lost to PS4),
- a chain-of-thought scaffold listing internal reasoning steps,
- a strict output schema with verbatim source-line citation.

The PS4 variant beat every other configuration in the original paper.

**Why used here.** It's the published baseline for SOLO-style MCQ generation
and matches the project's structural needs (level-aware, source-anchored,
JSON output). The docstring at the top of `prompt_lib.py` cites the paper
explicitly so future contributors can trace the design back to its origin.

**Where in the code.**
- [`backend/core/prompt_lib.py:1-16`](backend/core/prompt_lib.py) — module
  docstring naming the paper.
- `ROLE_PRIMER`, `SOLO_DEFINITIONS`, `WORKED_EXAMPLES`, `COT_SCAFFOLD`, and
  `OUTPUT_SCHEMA` constants together compose PS4.
- `build_question_prompt(level, ...)` is the assembly function.

**Reference.** Scaria, N. et al. (2024). *Automated Educational Question
Generation at Different Bloom's Skill Levels using Large Language Models:
Strategies and Evaluation.* arXiv:2408.04394.

---

### 2.3. Chain-of-Thought prompting (Wei et al., 2022)

**What it is.** Instructing the LLM to reason step-by-step before producing
the final answer. Wei et al. found this dramatically improves performance on
reasoning-heavy tasks because intermediate steps anchor the model's output
distribution.

**Why used here.** Question writing is a reasoning-heavy task: the model has
to identify the target fact, locate it in the source text, draft a stem,
write the correct option, build distractors, and verify the rule set. CoT
makes that procedure explicit. The reasoning is suppressed in the output
(`THINK STEP BY STEP INTERNALLY (do not include this reasoning…)`) so only
the JSON schema is emitted.

**Where in the code.**
- [`backend/core/prompt_lib.py`](backend/core/prompt_lib.py), `COT_SCAFFOLD`
  constant.

**Reference.** Wei, J. et al. (2022). *Chain-of-Thought Prompting Elicits
Reasoning in Large Language Models.* NeurIPS 2022. arXiv:2201.11903.

---

### 2.4. Worked-example pedagogy with cross-domain transfer (Sweller & Cooper, 1985)

**What it is.** Showing a learner one fully solved example before asking them
to produce one. The cognitive-load-theory result is that worked examples
reduce extraneous load and accelerate schema acquisition. The cross-domain
twist used here — the worked example is in a different topic (photosynthesis)
from what the user is generating about (operating systems) — is a deliberate
form of structure-mapping: the model copies the *form* of a good question,
not the topic.

**Why used here.** A single worked example per SOLO level is included in
every generation prompt. The photosynthesis domain was chosen specifically
because it is far from typical CS/OS material in the source PDFs, so the
model cannot copy facts; it has to learn the structure (stem shape,
distractor variety, correct-answer phrasing).

**Where in the code.**
- [`backend/core/prompt_lib.py`](backend/core/prompt_lib.py),
  `WORKED_EXAMPLES` dict — one full worked example per SOLO level.
- The framing line `"WORKED EXAMPLE (study the STRUCTURE; do NOT copy the
  topic)"` makes the intent explicit to the model.

**Reference.** Sweller, J. & Cooper, G. A. (1985). *The use of worked
examples as a substitute for problem solving in learning algebra.* Cognition
and Instruction 2(1), 59–89.

---

### 2.5. Verbatim source-line grounding (anti-hallucination)

**What it is.** Each generated question must include a `source_line` field —
a verbatim quote from the source text that justifies the correct answer.
This is a lightweight form of retrieval-augmented grounding: the model is
forced to surface its citation, which makes hallucinations visible to a
reviewer.

**Why used here.** It's the cheapest possible halluci­nation detector. If
the `source_line` doesn't appear in the lesson, the question's correct
answer is suspect. The field is stored on the `Question` row so a reviewer
can spot-check it later, and the prompt explicitly demands it.

**Where in the code.**
- [`backend/core/prompt_lib.py`](backend/core/prompt_lib.py), `OUTPUT_SCHEMA`
  — `source_line: verbatim quote from SOURCE TEXT that justifies the
  correct answer`.
- [`backend/models/models.py`](backend/models/models.py),
  `Question.source_line` column.

**Reference.** The mechanism is folk knowledge in the RAG literature; the
canonical citation for *Retrieval-Augmented Generation* is Lewis et al.
(2020), arXiv:2005.11401. The specific "demand a verbatim quote" pattern
appears in many follow-up papers on attribution.

---

### 2.6. Two-pass predictive prompting for Extended Abstract (Bitew et al., 2023)

**What it is.** For the hardest SOLO level, the generator runs the LLM
twice:
- **Pass 1** produces only the stem, correct answer, explanation, and
  source line.
- **Pass 2** is given those four things and produces *only* the three
  distractors, each from a different typed strategy.

Bitew et al. call this *predictive prompting*: the model is anchored on a
known good question, so all of its capacity is focused on misconception
generation rather than question writing.

**Why used here.** Extended Abstract requires the model to invent a
*scenario* and then write distractors for it. Splitting the two tasks
materially improves both. The paper reports ~53% of generated distractors
rated production-ready by teachers, beating prior SOTA.

**Where in the code.**
- [`backend/core/prompt_lib.py`](backend/core/prompt_lib.py),
  `build_extended_abstract_pass1_prompt` and
  `build_extended_abstract_pass2_prompt`.
- The two-pass orchestration lives in
  [`backend/core/quiz_generator.py`](backend/core/quiz_generator.py).

**Reference.** Bitew, S. K. et al. (2023). *Distractor Generation for
Multiple-Choice Questions with Predictive Prompting and Large Language
Models.* arXiv:2307.16338.

---

### 2.7. Ontology-anchored relational generation (KAQG-style)

**What it is.** The relational and extended-abstract prompts accept an
`ontology_anchor_block` showing one specific concept-to-concept
relationship from the domain ontology (e.g.
`Process --[isPrerequisiteFor]--> Thread`). The model is told the question
must test that exact relationship, not a randomly chosen one. The anchor
identifier is saved on the question (`Question.tags.ontology_anchor`) so
the link is auditable in the question bank.

**Why used here.** Without an anchor, "relational" questions drift towards
generic comparisons. The anchor turns a vague level into a specific edge of
the knowledge graph, making coverage and diversity measurable.

**Where in the code.**
- [`backend/core/prompt_lib.py`](backend/core/prompt_lib.py),
  `build_question_prompt(..., ontology_anchor_block=...)`.
- [`backend/core/quiz_generator.py`](backend/core/quiz_generator.py)
  picks a `ConceptRelationship` row and formats it into the prompt.
- [`backend/models/models.py`](backend/models/models.py),
  `Question.tags` JSON column stores the chosen anchor.

**Reference.** Lin, C.-Y. et al. (2025). *KAQG: A Knowledge-Graph-Enhanced
RAG for Difficulty-Controlled Question Generation.* arXiv:2505.07618.
The general framework — using a knowledge graph to constrain generation —
predates KAQG by many years; KAQG is cited as a recent, well-described
example of the pattern.

---

### 2.8. Explicit Haladyna item-writing rules in the prompt (Haladyna, Downing & Rodriguez, 2002)

**What it is.** Haladyna, Downing & Rodriguez compiled a 31-rule taxonomy
of multiple-choice item-writing guidelines, validated against 27 textbooks
and 27 empirical studies. The project includes the automatable subset of
those rules — broken into `STEM_RULES` (S1–S4) and `OPTION_RULES` (O1–O7) —
directly inside the generation prompt as numbered constraints.

**Why used here.** Numbered constraints are respected by LLMs much more
reliably than free-text advice. Putting the rules into the prompt (as
prevention) closes the loop with the lint that checks them post-hoc (as
detection). The rule codes (`H14`, `H17`, `H19`, `H21`, `H22`, `H24`, `H25`,
`H27`) match the lint codes in `services/mcq_lint.py` exactly.

**Where in the code.**
- [`backend/core/prompt_lib.py`](backend/core/prompt_lib.py), `STEM_RULES`
  and `OPTION_RULES` constants. Both blocks are inserted by
  `build_question_prompt`, and `OPTION_RULES` is also inserted into the
  Extended-Abstract pass-2 prompt.

**Rules covered in the prompt**

| Code | Rule | Where it's enforced in the prompt |
|------|------|-----------------------------------|
| H14 | End the stem with a question mark or a clear imperative | `STEM_RULES` S1 |
| H16 | Keep stem under ~250 chars; no window dressing | `STEM_RULES` S2 |
| H17 | Avoid negation; if used, emphasise with `**…**` | `STEM_RULES` S3 |
| H19 | Exactly one correct option | `OPTION_RULES` O1 |
| H21 | Numeric options in ascending or descending order | `OPTION_RULES` O6 |
| H22 | No two options are paraphrases of one another | `OPTION_RULES` O2 |
| H24 | Longest option ≤ 2× shortest | `OPTION_RULES` O3 |
| H25 | Never use "all/none of the above" | `OPTION_RULES` O5 |
| H27 | Correct option must not be the longest | `OPTION_RULES` O4 |

**Reference.** Haladyna, T. M., Downing, S. M. & Rodriguez, M. C. (2002).
*A Review of Multiple-Choice Item-Writing Guidelines for Classroom
Assessment.* Applied Measurement in Education 15(3), 309–334.

---

## 3. Distractor techniques

### 3.1. Typed distractor strategies (Bitew et al., 2023; Sadler, 1998)

**What it is.** Instead of telling the model "make the distractors
plausible", the prompt lists three concrete *types* of misconception per
SOLO level. Each distractor must follow one of the named strategies.

The strategies were chosen to match how students actually misread material
at each cognitive level — Sadler's (1998) work on psychometric models of
student conceptions provides the underlying theory.

| SOLO level | Distractor types |
|------------|-----------------|
| Unistructural | `VARIANT_OF_CORRECT`, `NEAR_SYNONYM`, `COMMON_MISCONCEPTION` |
| Multistructural | `LIST_WITH_ONE_WRONG_ITEM`, `LIST_MISSING_ONE_ITEM`, `RELATED_BUT_OUT_OF_SCOPE` |
| Relational | `REVERSED_CAUSE_EFFECT`, `CORRELATION_AS_CAUSATION`, `DIFFERENT_REAL_RELATIONSHIP` |
| Extended Abstract | `APPLIES_WRONG_PRINCIPLE`, `RIGHT_PRINCIPLE_WRONG_DOMAIN`, `OVER_GENERALIZATION` |

**Why used here.** Bitew et al. found that concrete misconception templates
outperform abstract advice. The strategy that the model used for a given
distractor is also stored on `Question.tags.distractor_strategies` so the
choice is auditable later.

**Where in the code.**
- [`backend/core/prompt_lib.py`](backend/core/prompt_lib.py),
  `DISTRACTOR_STRATEGIES` dict.
- [`backend/core/prompt_lib.py`](backend/core/prompt_lib.py),
  `_format_distractor_table(level)` inserts the table into the prompt.

**References.**
- Bitew, S. K. et al. (2023). arXiv:2307.16338. (Same paper as 2.6.)
- Sadler, P. M. (1998). *Psychometric Models of Student Conceptions in
  Science.* Journal of Research in Science Teaching 35(3), 265–296.

---

### 3.2. Distractor homogeneity (Haladyna O7 / H24 / H27)

**What it is.** The four options of an MCQ should match in length, register,
grammatical class, and topic. If the correct answer is a noun phrase and
the distractors are verbs, the student can answer the question without
knowing the material. The same intuition holds for length: a much longer
correct answer is a "length clue".

**Why used here.** The prompt rule `O7 — Match grammatical structure across
options — same part of speech, same register, same tense` directly encodes
this. The lint detects length disparity (`H24`) and the case where the
correct answer is the longest (`H27`) — both are listed as item-writing
flaws in Haladyna 2002 (rules from which the H-codes are taken). The
embedding diversity check (`D_DIVERSITY_LOW`) catches semantic homogeneity
that length-based checks miss.

**Where in the code.**
- [`backend/core/prompt_lib.py`](backend/core/prompt_lib.py), `OPTION_RULES`
  O3 (length parity), O4 (correct not longest), O7 (grammatical match).
- [`backend/services/mcq_lint.py`](backend/services/mcq_lint.py), `H24` and
  `H27` checks.

**Reference.** Haladyna, Downing & Rodriguez (2002) — same paper as 2.8.
Additional empirical evidence for length clues in real exams comes from
Tarrant, M., Knierim, A., Hayes, S. K. & Ware, J. (2009). *The frequency
of item writing flaws in multiple-choice questions used in high-stakes
nursing assessments.* Nurse Education in Practice 9(3), 184–191 — cited
as background reading, not directly implemented.

---

## 4. A-priori quality and validity layer

These checks all run *after* the LLM has produced a question, but *before*
any student sees it. They produce a-priori validity metrics — no student
responses required.

### 4.1. Haladyna MCQ lint (detection of 11 rules)

**What it is.** A pure-Python rule engine that scans an emitted question
and flags violations of the 11 automatable Haladyna rules. Each flag has a
stable code, a severity (`error` / `warn`), and a human-readable message
in Serbian + English. Questions get a composite 0–100 score
(−15 per error, −5 per warn).

**Why used here.** It is the detection partner of the prompt-level rule
block. The same rule codes (`H14`, `H17`, `H22`, `H25`, `H27`, …) appear in
both the prompt and the lint, so you can quote the metric back to the
prompt and the linkage is exact.

**Where in the code.**
- [`backend/services/mcq_lint.py`](backend/services/mcq_lint.py).
- API:
  - `GET /api/questions/<id>/lint`
  - `GET /api/lessons/<id>/lint` (batch + aggregate + flag frequency)
- UI: [`frontend/src/components/MCQLintPanel.js`](frontend/src/components/MCQLintPanel.js).

**Reference.** Haladyna, Downing & Rodriguez (2002). (Same paper as 2.8.)

---

### 4.2. Embedding-based distractor plausibility (Bitew et al., 2023 + BERTScore)

**What it is.** For each distractor, compute a cosine similarity to the
correct answer using sentence embeddings (Ollama `nomic-embed-text` by
default). Flag distractors that are too close (`> 0.92` — paraphrase, leads
to ambiguity) or too far (`< 0.40` — trivially wrong). The thresholds are
calibrated for the default embedding model and are tunable.

**Why used here.** Length and lexical checks (Haladyna) miss semantic
overlap; embeddings catch it. BERTScore-style cosine similarity over
contextual embeddings is the standard semantic-similarity tool in modern
NLP evaluation.

**Where in the code.**
- [`backend/services/embedding_service.py`](backend/services/embedding_service.py)
  — thin wrapper around Ollama's `/api/embeddings` with SQLite caching.
- [`backend/services/mcq_lint.py`](backend/services/mcq_lint.py),
  `_check_embeddings` function. Flag codes: `D_PLAUS_TOO_LOW`,
  `D_PLAUS_TOO_HIGH`.

**References.**
- Bitew, S. K. et al. (2023). arXiv:2307.16338.
- Zhang, T. et al. (2020). *BERTScore: Evaluating Text Generation with BERT.*
  ICLR 2020. arXiv:1904.09675.

---

### 4.3. Distractor diversity check (Falchikov, 2008)

**What it is.** Compute pairwise cosine similarity between the three
distractors. If any pair exceeds `0.92`, that pair is too similar — two
"different" wrong answers turn into one effective option, weakening the
item's discrimination. The check rides on the same embedding cache as 4.2.

**Why used here.** A common failure mode of LLM-generated distractors is
to produce three paraphrases of the same misconception. Diversity is the
correlate of "three genuinely different ways to be wrong".

**Where in the code.**
- [`backend/services/mcq_lint.py`](backend/services/mcq_lint.py),
  `_check_embeddings` function. Flag code: `D_DIVERSITY_LOW`.

**Reference.** Falchikov, N. (2008). *Improving Assessment Through Student
Involvement.* Routledge. The specific argument about pairwise distractor
distance also appears in Tarrant et al. (2009).

---

### 4.4. Self-consistency sampling (Wang et al., 2022)

**What it is.** Generate *N* candidate questions for the same (lesson, SOLO
level) target, score each one with the Haladyna lint + embedding
plausibility / diversity, and keep the highest scorer. The composite score
penalises out-of-range plausibility (−10) and diversity flags (−5) in
addition to the base lint score.

The original paper used majority-vote over arithmetic-reasoning paths;
adapting it to MCQ writing replaces "majority vote" with "max by lint
score" because there is no single "answer" to vote on.

**Why used here.** Question quality has high variance across LLM samples.
Best-of-N is a cheap way to absorb that variance without retraining or
fine-tuning.

**Where in the code.**
- [`backend/services/self_consistency.py`](backend/services/self_consistency.py).
- Public API: `score_candidate(...)`, `pick_best_question(...)`,
  `generate_with_self_consistency(generator_fn, n=3)`.

**Reference.** Wang, X. et al. (2023). *Self-Consistency Improves Chain of
Thought Reasoning in Language Models.* ICLR 2023. arXiv:2203.11171.

---

### 4.5. Chain-of-Verification — CoVe (Dhuliawala et al., 2023)

**What it is.** A four-step fact-checking pipeline:
1. Take the generated question and its correct answer.
2. Plan 2–3 short verification questions whose answers, in combination,
   confirm or refute the correct answer.
3. Answer each verification question *independently*, given only the source
   excerpt (not the original question).
4. Judge whether the correct answer is `SUPPORTED`, `UNDERDETERMINED`, or
   `CONTRADICTED` by the verification evidence.

Questions with verdict `UNDERDETERMINED` or `CONTRADICTED` are flagged for
human review.

**Why used here.** Source-line grounding (2.5) catches the easy case where
the model hallucinates a quote that's not in the source. CoVe catches the
harder case: the source line is real, but it doesn't actually justify the
correct answer.

**Where in the code.**
- [`backend/services/cove.py`](backend/services/cove.py).
- API:
  - `GET /api/questions/<id>/cove`
  - `GET /api/lessons/<id>/cove`
- UI: [`frontend/src/components/AdvancedQualityPanel.js`](frontend/src/components/AdvancedQualityPanel.js).

**Reference.** Dhuliawala, S. et al. (2023). *Chain-of-Verification Reduces
Hallucination in Large Language Models.* ACL Findings 2024.
arXiv:2309.11495.

---

### 4.6. Solvability test — LLM-blind solver

**What it is.** Hide the correct answer key from a question and ask an LLM
to pick the best option. Repeat *N=5* trials with shuffled option order
(to defeat position bias). The resulting "LLM p-value" is the empirical
probability the model picks the actual correct answer.

Interpretation:
- `p ≈ 1.0` → trivially easy (or there is a length / grammar clue).
- `0.6 ≤ p ≤ 0.9` → appropriate difficulty for an LLM-class solver.
- `p < 0.5` → either the question is misframed, the key is wrong, or the
  question tests material outside the source.

This is a *synthetic* analogue of the classical-test-theory item difficulty
index (Crocker & Algina, 1986), computed before any student sees the test.

**Why used here.** It catches items where the model "knows" the right
answer is too obvious, and items where it cannot find the right answer at
all — both of which signal problems that won't be visible from the prompt
alone.

**Where in the code.**
- [`backend/services/solvability.py`](backend/services/solvability.py).
- Public API: `assess_solvability(question, n_trials=5)`,
  `solvability_report(questions, ...)`.
- HTTP API:
  - `GET /api/questions/<id>/solvability?n_trials=N`
  - `GET /api/lessons/<id>/solvability?n_trials=N`
- UI: [`frontend/src/components/AdvancedQualityPanel.js`](frontend/src/components/AdvancedQualityPanel.js).

**References.**
- Crocker, L. & Algina, J. (1986). *Introduction to Classical and Modern
  Test Theory.* Holt, Rinehart and Winston. (Source for the p-value
  definition.)
- The specific "use an LLM as a synthetic student" pattern is folk
  knowledge in the recent automatic-question-generation evaluation
  literature; the closest formal cite is Kurdi et al. (2020), Section on
  evaluation metrics.

---

### 4.7. SOLO LLM-judge with Cohen's κ (Landis & Koch, 1977 + LLM-as-judge)

**What it is.** A second LLM independently classifies each generated
question into a SOLO level, given only the question and its options
(*not* the level the generator was told to produce). The agreement between
the *intended* level (generator) and the *classified* level (judge) is
reported as Cohen's κ plus a confusion matrix.

The judge prompt is intentionally framed differently from the generator
prompt ("you are *analysing* an existing item") and runs at a different
temperature (0.1, near-deterministic) to reduce shared-bias artefacts. If
the user configures `OLLAMA_JUDGE_MODEL` in `.env`, a different model can
be used for full independence; otherwise the same model is used with the
different prompt as a softer separation.

Landis & Koch's qualitative labels are surfaced in the UI:
- `κ < 0` worse than chance
- `0–0.20` slight
- `0.21–0.40` fair
- `0.41–0.60` moderate
- `0.61–0.80` substantial
- `0.81–1.00` almost perfect

**Why used here.** It is the a-priori validity check for "did the
generator hit the SOLO level it was asked to produce?" — the question
behind professor's point 4.

**Where in the code.**
- [`backend/services/solo_judge.py`](backend/services/solo_judge.py).
- API:
  - `GET /api/questions/<id>/solo-judge`
  - `GET /api/lessons/<id>/solo-judge`
- UI: [`frontend/src/components/SoloJudgePanel.js`](frontend/src/components/SoloJudgePanel.js).

**References.**
- Landis, J. R. & Koch, G. G. (1977). *The Measurement of Observer
  Agreement for Categorical Data.* Biometrics 33(1), 159–174. (Source of
  the κ landmark labels.)
- Cohen, J. (1960). *A Coefficient of Agreement for Nominal Scales.*
  Educational and Psychological Measurement 20(1), 37–46. (Original κ.)
- Zheng, L. et al. (2023). *Judging LLM-as-a-Judge with MT-Bench and
  Chatbot Arena.* NeurIPS 2023. arXiv:2306.05685. (LLM-as-judge framing.)

---

### 4.8. Concept Coverage v2 (Kurdi et al., 2020 framework)

**What it is.** A semantic coverage metric over the lesson's ontology:
- The concept set is the union of all `LearningObject.keywords` plus LO
  titles.
- Each concept's weight is `1 + (degree in ConceptRelationship graph)`, so
  hub concepts count for more than peripheral ones.
- A question covers a concept if the concept appears (case-insensitive
  substring, with word-boundary matching for single-word concepts) in the
  stem, options, correct answer, or explanation.
- The metric reports both unweighted and weighted coverage, plus the
  highest-weight uncovered concepts.

This replaces the older character-weighted PDF coverage, which mapped
questions to *pages* rather than to *ideas*.

**Why used here.** Kurdi et al.'s systematic review of automatic question
generation flagged that BLEU / ROUGE-style metrics miss curricular
coverage; topic-level metrics are needed for educational evaluation.
The ontology-based concept set is the project's available structure for
"topic", so it's the natural unit.

**Where in the code.**
- [`backend/services/coverage_service.py`](backend/services/coverage_service.py).
  Both the page-based metric (kept for back-compatibility) and the
  concept-based metric are returned in one response.
- API: `GET /api/lessons/<id>/coverage`.
- UI: [`frontend/src/components/CoveragePanel.js`](frontend/src/components/CoveragePanel.js).

**Reference.** Kurdi, G., Leo, J., Parsia, B., Sattler, U. & Al-Emari, S.
(2020). *A Systematic Review of Automatic Question Generation for
Educational Purposes.* International Journal of Artificial Intelligence in
Education 30(1), 121–204.

---

## 5. Composite techniques

### 5.1. Prompt + lint hybrid (prevention + detection)

The same Haladyna rule codes appear in:
- the prompt as *prevention* (`STEM_RULES` S1–S4, `OPTION_RULES` O1–O7),
- and the lint as *detection* (`H14`, `H17`, `H19`, `H21`, `H22`, `H24`,
  `H25`, `H27`, …).

This is a deliberate hybrid. The prompt reduces the violation rate
proactively (Haladyna 2002 argues the rules are followed best when stated
as numbered constraints); the lint quantifies what gets through anyway.
You can quote any lint flag back to the exact prompt rule it corresponds
to.

### 5.2. Self-consistency over the same prompt (5.1 raised to *N*)

When self-consistency sampling (4.4) is enabled, *N* candidates are drawn
from the same Haladyna-augmented prompt, lint-scored using both Haladyna
rules and embedding metrics, and the best one is kept. This is the
recommended generation pipeline for high-stakes use.

### 5.3. Source citation + CoVe (two-layer hallucination defence)

The `source_line` field (2.5) is the cheap front line — easy to spot-check.
CoVe (4.5) is the expensive but stronger second line — it actually answers
the question from the source and judges whether the answer holds up.
Combined, they catch both kinds of hallucination:
- the model invents a quote that isn't in the source (`source_line`
  mismatch is visible immediately),
- the source quote is real but doesn't justify the correct answer
  (CoVe flags `UNDERDETERMINED` or `CONTRADICTED`).

---

## 6. References

Bibliography in alphabetical order. Where possible, an open-access link
(DOI, arXiv, or publisher page) is given.

- Biggs, J. B. & Collis, K. F. (1982). *Evaluating the Quality of Learning:
  The SOLO Taxonomy.* Academic Press.
- Bitew, S. K., Deleu, J., Develder, C. & Demeester, T. (2023). *Distractor
  Generation for Multiple-Choice Questions with Predictive Prompting and
  Large Language Models.* arXiv:2307.16338.
- Cohen, J. (1960). *A Coefficient of Agreement for Nominal Scales.*
  Educational and Psychological Measurement 20(1), 37–46.
- Crocker, L. & Algina, J. (1986). *Introduction to Classical and Modern
  Test Theory.* Holt, Rinehart and Winston.
- Dhuliawala, S., Komeili, M., Xu, J., Raileanu, R., Li, X., Celikyilmaz,
  A. & Weston, J. (2023). *Chain-of-Verification Reduces Hallucination in
  Large Language Models.* ACL Findings 2024. arXiv:2309.11495.
- Falchikov, N. (2008). *Improving Assessment Through Student Involvement.*
  Routledge.
- Haladyna, T. M., Downing, S. M. & Rodriguez, M. C. (2002). *A Review of
  Multiple-Choice Item-Writing Guidelines for Classroom Assessment.*
  Applied Measurement in Education 15(3), 309–334.
- Kurdi, G., Leo, J., Parsia, B., Sattler, U. & Al-Emari, S. (2020).
  *A Systematic Review of Automatic Question Generation for Educational
  Purposes.* International Journal of Artificial Intelligence in Education
  30(1), 121–204.
- Landis, J. R. & Koch, G. G. (1977). *The Measurement of Observer
  Agreement for Categorical Data.* Biometrics 33(1), 159–174.
- Lewis, P. et al. (2020). *Retrieval-Augmented Generation for
  Knowledge-Intensive NLP Tasks.* NeurIPS 2020. arXiv:2005.11401.
- Lin, C.-Y. et al. (2025). *KAQG: A Knowledge-Graph-Enhanced RAG for
  Difficulty-Controlled Question Generation.* arXiv:2505.07618.
- Sadler, P. M. (1998). *Psychometric Models of Student Conceptions in
  Science.* Journal of Research in Science Teaching 35(3), 265–296.
- Scaria, N. et al. (2024). *Automated Educational Question Generation at
  Different Bloom's Skill Levels using Large Language Models: Strategies
  and Evaluation.* arXiv:2408.04394.
- Sweller, J. & Cooper, G. A. (1985). *The use of worked examples as a
  substitute for problem solving in learning algebra.* Cognition and
  Instruction 2(1), 59–89.
- Tarrant, M., Knierim, A., Hayes, S. K. & Ware, J. (2009). *The frequency
  of item writing flaws in multiple-choice questions used in high-stakes
  nursing assessments.* Nurse Education in Practice 9(3), 184–191.
- Wang, X., Wei, J., Schuurmans, D., Le, Q., Chi, E., Narang, S.,
  Chowdhery, A. & Zhou, D. (2023). *Self-Consistency Improves Chain of
  Thought Reasoning in Language Models.* ICLR 2023. arXiv:2203.11171.
- Wei, J., Wang, X., Schuurmans, D., Bosma, M., Ichter, B., Xia, F.,
  Chi, E., Le, Q. & Zhou, D. (2022). *Chain-of-Thought Prompting Elicits
  Reasoning in Large Language Models.* NeurIPS 2022. arXiv:2201.11903.
- Zhang, T., Kishore, V., Wu, F., Weinberger, K. Q. & Artzi, Y. (2020).
  *BERTScore: Evaluating Text Generation with BERT.* ICLR 2020.
  arXiv:1904.09675.
- Zheng, L. et al. (2023). *Judging LLM-as-a-Judge with MT-Bench and
  Chatbot Arena.* NeurIPS 2023. arXiv:2306.05685.
