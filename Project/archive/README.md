# SOLO Quiz Generator

An educational software system that generates SOLO-taxonomy multiple-choice
questions from PDF course materials, using a local LLM (Ollama) plus a
research-grounded validation layer that measures coverage, item-writing
quality, and SOLO-level alignment without any cloud API costs.

> The full scientific underpinning — every paper that informs the generator
> and the validation layer — is documented in
> [`QUESTION_AND_GENERATION_BEST_PRACTICES.md`](QUESTION_AND_GENERATION_BEST_PRACTICES.md).
> This README is the operational guide; the best-practices document is the
> "why".

## What it does

- **Ingest.** Upload PDF lessons; the text and per-page metadata are stored.
- **Parse.** An LLM splits each lesson into sections and learning objects
  (LOs), each tagged with the pages it spans.
- **Build a domain ontology.** Relationships between LOs
  (`isPrerequisiteFor`, `buildsUpon`, …) are extracted and stored as a graph.
- **Generate questions.** Per SOLO level (unistructural / multistructural /
  relational / extended abstract), using the PS4 prompt template, typed
  distractor strategies, and the Haladyna 2002 item-writing rules.
- **Measure quality.** A six-layer a-priori validity stack:
  concept coverage, Haladyna lint, embedding-based distractor plausibility
  and diversity, Chain-of-Verification, LLM-blind solvability, and SOLO
  LLM-judge (with Cohen's κ).
- **Build quizzes.** Hand-curate quiz sets from the question bank, translate
  them, hand them to students.

## Generation modes

Three buttons under the question generator, listed from most manual to most
automated:

1. **Generate Questions** — you pick the lessons, the SOLO levels, and the
   count per level. The generator follows your instructions verbatim.
2. **Generate Full Questions for Selected Lessons** *(new)* — you pick the
   lessons (1, 2, or N); per-level quotas are auto-computed from each
   lesson's LO / section count. Extended Abstract is added across
   consecutive pairs when you select 2+ lessons. This is the right button
   when you want "everything for these lessons, sensibly sized" without
   tweaking sliders.
3. **Generate for Whole Course** — auto-quota across every parsed lesson in
   the course, aiming for ~85–90% slide coverage. Pair this with **Target
   Uncovered Pages** afterwards to fill remaining coverage gaps.

## Quick start

You need **Python 3.10+**, **Node.js 18+**, and **Ollama**. See
[`archive/START_GUIDE.md`](archive/START_GUIDE.md) for the original
three-terminal recipe; the steps are unchanged.

```bash
# Backend
cd backend
python -m venv venv
.\venv\Scripts\activate              # or: source venv/bin/activate
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install

# Ollama models (one-time)
ollama pull qwen2.5:14b-instruct-q4_K_M       # generator
ollama pull nomic-embed-text                  # optional, enables embedding lint
```

Optional: set independent models for the validation layer in `backend/.env`:

```bash
OLLAMA_MODEL=qwen2.5:14b-instruct-q4_K_M
OLLAMA_JUDGE_MODEL=llama3.1:8b      # SOLO LLM-judge (else falls back to OLLAMA_MODEL)
OLLAMA_COVE_MODEL=llama3.1:8b       # Chain-of-Verification
OLLAMA_SOLVER_MODEL=llama3.1:8b     # Solvability blind-solver
OLLAMA_EMBED_MODEL=nomic-embed-text # embeddings
```

Run three terminals (Ollama, backend, frontend) and open
`http://localhost:3000`.

## Tech stack

**Backend** — Python 3.10+, Flask 2.3, SQLAlchemy 2.0, SQLite, Pydantic 2,
RDFLib 7, PyPDF2, `concurrent.futures.ThreadPoolExecutor` for background
jobs.

**Frontend** — React 18 + Axios + CSS3.

**AI layer** — Ollama (local LLM). Default generator model:
`qwen2.5:14b-instruct-q4_K_M`. Default embedding model: `nomic-embed-text`.

## Project structure

A high-level map of the directories that matter for development. The full
walkthrough lives in [`structure.md`](structure.md).

```
Project/
├── archive/                            # superseded MD files (kept for history)
│   ├── README.md, README_SRB.md, structure.md, START_GUIDE.md
├── backend/
│   ├── app.py, config.py, schemas.py, repository.py
│   ├── core/                           # LLM pipeline
│   │   ├── prompt_lib.py              # PS4 + Haladyna rules + distractor strategies
│   │   ├── quiz_generator.py          # SOLO generator (incl. 2-pass EA)
│   │   ├── content_parser.py, lang_detect.py, llm_cache.py
│   ├── models/                         # SQLAlchemy ORM
│   ├── ontology/                       # seed TBox (OWL/Turtle)
│   ├── services/
│   │   ├── lesson_service.py, question_service.py, quiz_service.py
│   │   ├── coverage_service.py        # page + concept coverage
│   │   ├── mcq_lint.py                # Haladyna lint
│   │   ├── embedding_service.py       # Ollama embeddings + cosine helper
│   │   ├── solo_judge.py              # second-LLM SOLO classifier (Cohen κ)
│   │   ├── self_consistency.py        # best-of-N selector
│   │   ├── cove.py                    # Chain-of-Verification
│   │   ├── solvability.py             # LLM-blind solver (synthetic p-value)
│   │   ├── ontology_manager.py, sparql_service.py, translation_service.py
│   │   ├── chatbot_service.py, jobs.py
│   ├── routes/                         # Flask blueprints (one per domain)
│   └── tests/                          # pytest suite (266 tests)
├── frontend/
│   └── src/components/
│       ├── QuestionGenerator.js       # 3-mode generation UI
│       ├── QuestionBank.js
│       ├── CoveragePanel.js           # page + concept coverage UI
│       ├── MCQLintPanel.js            # Haladyna lint UI
│       ├── SoloJudgePanel.js          # Cohen κ + confusion matrix
│       ├── AdvancedQualityPanel.js    # CoVe + solvability
│       ├── ContentViewer.js, LessonManager.js, CourseManager.js
│       ├── QuizBuilder.js, QuizSolver.js, ManualQuestionAdder.js
│       ├── TranslationManager.js, TranslationViewer.js
│       ├── SPARQLQueryTool.js, ChatBot.js
│       └── layout/  (Sidebar, TopBar, AlertMessages, …)
├── QUESTION_AND_GENERATION_BEST_PRACTICES.md   # research → code mapping
├── README.md  (this file)
├── structure.md
└── ollama.ps1, start.sh, start.bat
```

## API endpoints

Grouped by domain. All under `/api`.

### Core
- `GET /health` — health check
- `POST /sparql`, `GET /sparql/examples` — SPARQL queries

### Courses, lessons, sections, learning objects
- `GET|POST /courses`, `GET|DELETE /courses/<id>`
- `GET /courses/<id>/lessons`, `POST /courses/<id>/lessons`
- `GET|DELETE /lessons/<id>`, `POST /lessons/<id>/parse`
- `GET /lessons/<id>/sections`, `GET /sections/<id>`
- `GET|POST /sections/<id>/learning-objects`, `GET|PUT|DELETE /learning-objects/<id>`

### Ontology
- `GET /lessons/<id>/ontology`
- `POST /lessons/<id>/ontology/generate`, `POST /lessons/<id>/ontology/clear`
- `GET /lessons/<id>/ontology/export/owl`, `GET /lessons/<id>/ontology/export/turtle`

### Question generation
- `POST /generate-questions` — synchronous, kept for back-compat
- `POST /jobs/generate-questions` — manual: lesson IDs + level set + count
- `POST /jobs/generate-questions-for-lessons` *(new)* — auto-quota across the listed lessons
- `POST /jobs/generate-questions-for-course` — auto-quota across the entire course
- `POST /jobs/generate-questions-for-uncovered` — coverage-fill mode
- `GET /jobs/<id>`, `GET /jobs` — job status + recent jobs

### Question bank
- `GET /questions` *(filterable by course, lesson, SOLO level)*
- `POST /questions` — manual creation
- `GET|PUT|DELETE /questions/<id>`

### Quality / validity
- `GET /questions/<id>/lint`, `GET /lessons/<id>/lint` — Haladyna + embedding lint
- `GET /questions/<id>/solo-judge`, `GET /lessons/<id>/solo-judge` — Cohen κ vs intended SOLO
- `GET /questions/<id>/cove`, `GET /lessons/<id>/cove` — Chain-of-Verification
- `GET /questions/<id>/solvability?n_trials=N`, `GET /lessons/<id>/solvability?n_trials=N` — LLM-blind solver
- `GET /lessons/<id>/coverage` — page + concept coverage

### Quizzes, translations, chatbot, admin
- Standard CRUD on `/quizzes`, `/translate/*`, `/chat`, `/admin/llm-cache`
  (see `structure.md` for details).

## Database

SQLite at `backend/quiz_database.db`. Key tables: `courses`, `lessons`,
`sections`, `learning_objects`, `concept_relationships`, `questions`,
`quizzes`, `quiz_questions`, plus per-resource `*_translation` tables and
the internal `llm_cache` and `embedding_cache` tables used by the AI
pipeline.

Schema migrations are handled by an idempotent column-adder in
`repository._add_missing_columns()` — adding a new nullable column to an
existing DB works on the next backend start, no Alembic required.

## Testing

```bash
cd backend
.\venv\Scripts\python.exe -m pytest tests/
```

The pytest suite (266 tests at time of writing) does not require Ollama, a
populated database, or a network connection. The validation services
(judge, CoVe, solver) use injectable `llm_caller` parameters so their
tests mock out the LLM with scripted responses.

## Configuration

The frontend reads its API base URL from `REACT_APP_API_URL`; if unset it
falls back to `http://localhost:5000/api`. Set it in `frontend/.env` to
point the UI at a different backend.

Backend models and thresholds are configurable through environment
variables in `backend/.env` — see the Quick Start above.

## License

This project is for educational purposes.
