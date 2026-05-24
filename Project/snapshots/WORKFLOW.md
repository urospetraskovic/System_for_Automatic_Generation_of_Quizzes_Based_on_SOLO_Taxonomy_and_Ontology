# A/B benchmark workflow — local Ollama vs cloud API

Goal: compare the quality of the same pipeline (parse → ontology → questions
→ validation) when driven by a local Ollama model vs a paid cloud model
(Claude Haiku, GPT-4o, Gemini Flash, etc.).

The pipeline keeps **no in-memory state between runs** — everything lives in
SQLite. To run a fair A/B benchmark, you snapshot the corpus before wiping
the database, swap the model in `backend/.env`, regenerate from scratch,
snapshot again, and run the comparison script.

---

## Step-by-step

### 1. Snapshot the current (local Ollama) state

```bash
# Make sure all quality checks have been run from the UI first
# (Quality Overview → Run all). This populates the LLM cache so the
# snapshot can pull validation data without re-calling the LLM.

backend/venv/Scripts/python.exe backend/snapshot_corpus.py \
    --label qwen2.5-14b-2026-05-24 \
    --notes "Local Ollama qwen2.5:14b, post-prompt-fix (S5/S6/S7 + banned openers)"
```

Output goes to `snapshots/qwen2.5-14b-2026-05-24/`:
- `database.db` — full SQLite copy (perfect rollback)
- `*.json` — every table as JSON (portable, git-friendly)
- `validation/*.json` — every metric (lint, judge, CoVe, IOC, …)
- `summary.md` — headline numbers in Markdown
- `manifest.json` — model, date, env vars, counts

### 2. Switch to a different model

Edit `backend/.env`:

```ini
# Switch the generator to a cloud model. The codebase currently calls
# Ollama's HTTP endpoint, so for a true cloud swap you have two paths:
#
# (a) Use a model served by an OpenAI-compatible proxy (e.g. LiteLLM,
#     Ollama running with --openai-compat). Point OLLAMA_BASE_URL at it.
# (b) Write a thin shim in core/quiz_generator.py that branches on
#     OLLAMA_MODEL prefix (e.g. "claude-*" → Anthropic SDK call).
#
# Path (a) is the lowest-friction option for a one-off comparison.

OLLAMA_BASE_URL=http://localhost:4000   # LiteLLM proxy or similar
OLLAMA_MODEL=claude-haiku-4-5
OLLAMA_JUDGE_MODEL=claude-haiku-4-5     # use the same model for all sub-judges
OLLAMA_COVE_MODEL=claude-haiku-4-5
OLLAMA_SOLVER_MODEL=claude-haiku-4-5
OLLAMA_EMBED_MODEL=nomic-embed-text     # keep embeddings local; cheap and offline
```

### 3. Wipe the database

> ⚠ **Destructive.** Make sure step 1's snapshot completed successfully first.
> Verify `snapshots/<label>/database.db` exists and is non-empty.

```bash
# Stop the backend first
del backend\quiz_database.db
```

Or, less destructive: rename it so it can be rolled back manually if needed:

```bash
move backend\quiz_database.db backend\quiz_database.db.archive
```

### 4. Restart backend + frontend

The empty DB will be re-created by `repository.init_database()` on first
request.

### 5. Re-run the full pipeline through the UI

1. Create the same course.
2. Upload the same PDF lessons.
3. Parse each lesson.
4. Generate ontology for each lesson.
5. Generate questions (use the same mode — "Generate Full Questions for
   Selected Lessons" with the same lesson selection).
6. Click Quality Overview → **Run all 12 quality metrics**.

The key constraint: **use the same inputs** (same PDFs, same lessons, same
generation mode) so the comparison isolates the model variable.

### 6. Snapshot the new state

```bash
backend/venv/Scripts/python.exe backend/snapshot_corpus.py \
    --label claude-haiku-4-5-2026-06-15 \
    --notes "Claude Haiku 4.5 via LiteLLM proxy, same prompt + same lessons as qwen2.5-14b-2026-05-24"
```

### 7. Compare side-by-side

```bash
backend/venv/Scripts/python.exe backend/compare_snapshots.py \
    --before qwen2.5-14b-2026-05-24 \
    --after  claude-haiku-4-5-2026-06-15
```

Output: `snapshots/<after-label>/comparison.md` with:
- Side-by-side headline metrics with Δ and ✓/✗ arrows
- Per-lesson concept coverage comparison
- Haladyna lint flag frequency by code
- SOLO judge confusion matrices for both runs

---

## Restore an old snapshot

If you want to go back to a previous state (e.g. compare results, roll back
after experimentation):

```bash
# Stop the backend first
copy snapshots\qwen2.5-14b-2026-05-24\database.db backend\quiz_database.db
# Restart backend
```

That gives you exactly the same DB you snapshotted — every question, every
ontology relationship, every translation.

---

## What's in a snapshot, exactly

For each `snapshots/<label>/`:

| File / dir | Contents |
|---|---|
| `database.db` | Byte-for-byte copy of `backend/quiz_database.db` — perfect rollback target |
| `manifest.json` | Label, timestamp, generator model name, Ollama URL, env vars, row counts per table, list of validation files |
| `summary.md` | Human-readable headline numbers, suitable for pasting into the thesis |
| `courses.json` | One course record per row in the courses table |
| `lessons.json` | All lessons with `pages_meta`, `raw_content`, etc. |
| `sections.json` | All sections with `start_page`, `end_page`, `content` |
| `learning_objects.json` | All LOs with `keywords`, `source_pages` |
| `concept_relationships.json` | All ontology edges between LOs |
| `questions.json` | All generated questions with `solo_level`, `source_line`, `options`, `correct_option_index`, `tags` |
| `quizzes.json`, `quiz_questions.json` | Quiz collections |
| `translations.json` | All `*_translation` tables merged into one object |
| `validation/coverage.json` | Concept + page coverage per lesson |
| `validation/lint.json` | Haladyna lint reports (incl. embeddings) per question |
| `validation/solo_judge.json` | SOLO classification + Cohen's κ + confusion matrix |
| `validation/cove.json` | Chain-of-Verification verdicts |
| `validation/solvability.json` | LLM-blind p-values |
| `validation/stem_only.json` | Haladyna H4 results |
| `validation/ioc.json` | Rovinelli & Hambleton ratings |
| `validation/ambiguity.json` | Downing 2005 detections |
| `validation/readability.json` | Flesch / Flesch-Kincaid |
| `validation/misconception_mining.json` | Sadler 1998 cue extractions |
| `validation/grammar_homogeneity.json` | POS-based O7 check |
| `validation/face_validity.json` | Considine 2005 rubric scores |

Each validation JSON is a complete dump of the service's return value —
including per-question detail, not just aggregates. So you can do
fine-grained comparisons (e.g. *"which specific questions improved on
CoVe between the two runs?"*) by joining `questions.json` and the
per-validation reports on `question_id`.

---

## Tips for the thesis

The comparison report (`snapshots/<after>/comparison.md`) is intentionally
formatted for direct inclusion in your thesis appendix. Two tables that
land especially well:

1. **Headline metrics table** — model on cols, metrics on rows, Δ with
   ✓/✗ arrows. Reviewers love a single-glance comparison.

2. **SOLO judge confusion matrices** — shows whether the new model
   actually hits the intended SOLO level more often, not just whether
   the κ number went up.

Cite this in the thesis as: *"To isolate the contribution of the
underlying LLM, we held the prompt structure, source PDFs, ontology
extraction, and validation suite constant, then re-ran the full
generation pipeline with model X. Results are summarised in Table N."*

---

## Cost discipline

The validation suite runs ~N×(N_questions) LLM calls per metric, where
N = the number of judge prompts in that metric (1 for IOC/ambiguity/
grammar/face, 4 for CoVe, 5 for solvability). On 200 questions that's
~3000–5000 LLM calls. At Claude Haiku 4.5 pricing (~$1/M input,
$5/M output) you're looking at $3–8 per full validation run. Plan
accordingly:

- Generate the corpus first (~$5 on Haiku for 200 questions)
- Run Quality Overview once (~$5)
- Snapshot
- Total: ~$10 per full A/B point.

For deeper exploration (multiple models), the cached validation makes
re-snapshots free as long as nothing in the prompts or questions change.
