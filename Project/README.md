# SOLO Quiz Generator

An intelligent educational software system that automatically generates quiz questions based on the SOLO (Structure of Observed Learning Outcomes) taxonomy. The application uses a local LLM through Ollama to create pedagogically structured questions from uploaded course materials.

## Overview

This project helps educators automatically create assessment questions at different cognitive levels. It parses PDF course materials, builds a semantic knowledge graph (ontology), and generates multiple-choice questions categorized by SOLO taxonomy levels:

- **Unistructural** — Simple recall of a single fact
- **Multistructural** — Identification of several independent facts
- **Relational** — Understanding connections between concepts
- **Extended Abstract** — Higher-order thinking and application across concepts

## Key Features

### Question Generation
- Upload PDF course materials (Serbian Latin/Cyrillic or English — language auto-detected)
- Automatic parsing into lessons, sections, and learning objects
- AI-powered question generation at all four SOLO levels
- **PS4-style prompts**: role-primed expert persona, concise SOLO definition, one worked example per level, typed distractor strategies, chain-of-thought scaffold
- **Source-line citation**: each generated question stores the verbatim quote from the source PDF that justifies the correct answer
- **Two-pass extended-abstract generation**: question + answer in pass 1; three typed distractors in pass 2 (predictive prompting)
- **Ontology-grounded relational questions**: each relational/extended-abstract question is anchored to one specific `ConceptRelationship` row, making the link traceable in the question bank
- Manual question creation and editing
- Question bank management

### PDF Coverage Tracking
- Per-page character counts and offsets stored alongside every uploaded PDF
- Coverage metrics: pages-touched-by-questions, char-weighted coverage, substantive coverage (excludes near-empty pages)
- Per-page heatmap UI: bar height = char count, color = covered vs uncovered
- List of substantive pages with no questions — a direct cue for follow-up generation
- Backwards-compatible: older lessons reconstruct page metadata from `--- Page N ---` markers in `raw_content`

### Background Jobs with Progress
- Long-running generation jobs run in a thread pool, not in the HTTP request
- `POST /api/jobs/generate-questions` returns `202` + a job id; the frontend polls `GET /api/jobs/<id>` for status and progress
- Progress UI shows `Generated relational question 2/3` and a fillable progress bar
- Question generation no longer freezes the UI on a 30-second spinner

### LLM Response Cache
- SQLite-backed cache keyed by SHA-256 of `(model, prompt, temperature, json_mode)`
- Re-running the same generation is instant
- Top-bar widget shows cache size and an inline "clear" button to force fresh generation

### Ontology System
- Automatic knowledge graph generation from content (multi-pass extraction by relationship type)
- SPARQL query interface for exploring relationships
- Export to OWL format for use in Protégé
- Export to Turtle format for RDF tools
- Conservative fallback: when LLM extraction yields nothing, only same-type and shared-keyword edges are inferred (no fabricated prerequisites)

### AI Chatbot
- Context-aware answers based on course content
- Uses RAG (Retrieval-Augmented Generation) architecture
- Explains quiz answers when students need help
- Offline fallback mode when AI is unavailable

### Quiz Management
- Build quizzes from the question bank
- Filter questions by topic, SOLO level, or lesson
- Quizzes are persisted in the SQLite database
- Interactive quiz-solving interface
- Multi-language translation support

### Translation System
- Translate questions to multiple languages
- Translate entire lessons, sections, or learning objects
- Batch translation support
- Preserves SOLO level metadata

## Tech Stack

**Backend:**
- Python 3.10+
- Flask 2.3.0 (REST API)
- SQLAlchemy 2.0.36 (ORM)
- SQLite (database)
- Pydantic 2.x (request validation)
- RDFLib 7.0.0 (ontology / SPARQL)
- PyPDF2 (PDF parsing)
- `concurrent.futures.ThreadPoolExecutor` for background jobs

**Frontend:**
- React 18
- Axios (HTTP client)
- CSS3 styling

**AI Layer:**
- Ollama (local LLM runner)
- Qwen 2.5 14B instruct (recommended): `qwen2.5:14b-instruct-q4_K_M`

## Prerequisites

Before running the application, make sure you have:

1. **Python 3.10 or higher** — [Download](https://www.python.org/downloads/)
2. **Node.js 18 or higher** — [Download](https://nodejs.org/)
3. **Ollama** — [Download](https://ollama.com/)

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd Project
```

### 2. Set Up Backend

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate (Windows)
.\venv\Scripts\activate

# Activate (Linux/Mac)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Set Up Frontend

```bash
cd frontend
npm install
```

### 4. Set Up Ollama

Download and install Ollama, then pull the recommended model:

```bash
ollama pull qwen2.5:14b-instruct-q4_K_M
```

## Running the Application

You need 3 terminals running simultaneously. See [START_GUIDE.md](START_GUIDE.md) for quick-start instructions.

**Terminal 1 — Ollama AI Server:**
```bash
.\ollama.ps1 serve
```

**Terminal 2 — Backend API:**
```bash
cd backend
.\venv\Scripts\python.exe app.py
```

**Terminal 3 — Frontend:**
```bash
cd frontend
npm start
```

The application will be available at `http://localhost:3000`.

## Project Structure

```
Project/
├── backend/
│   ├── app.py                  # Flask application factory
│   ├── config.py               # Paths, Ollama URL/model, file limits
│   ├── schemas.py              # Pydantic request schemas
│   ├── repository.py           # DB CRUD + idempotent column migrator
│   ├── requirements.txt        # Python dependencies (incl. pydantic)
│   ├── core/
│   │   ├── content_parser.py   # PDF parsing + section/LO extraction (PS4 prompts)
│   │   ├── quiz_generator.py   # SOLO question generation (PS4 + 2-pass EA)
│   │   ├── prompt_lib.py       # Prompt template, SOLO defs, worked examples,
│   │   │                       #   typed distractor strategies
│   │   ├── lang_detect.py      # Serbian (Latin/Cyrillic) vs English heuristic
│   │   └── llm_cache.py        # SQLite-backed Ollama response cache
│   ├── models/
│   │   └── models.py           # SQLAlchemy models
│   ├── ontology/
│   │   └── seed_ontology.ttl   # Seed TBox
│   ├── services/
│   │   ├── lesson_service.py     # Lesson parsing orchestration
│   │   ├── question_service.py   # Question generation orchestration
│   │   ├── quiz_service.py       # Quiz operations
│   │   ├── coverage_service.py   # PDF coverage metrics
│   │   ├── jobs.py               # ThreadPoolExecutor + in-memory job store
│   │   ├── ontology_manager.py   # Seed TBox + DB ABox merger; serves both
│   │   │                         #   knowledge-base and lesson-scoped exports
│   │   │                         #   in Turtle and RDF/XML (via rdflib)
│   │   ├── sparql_service.py     # SPARQL execution
│   │   ├── chatbot_service.py    # Context-aware chatbot
│   │   └── translation_service.py # Multi-language translation
│   ├── routes/
│   │   ├── health.py, courses.py, lessons.py, sections.py,
│   │   ├── learning_objects.py, ontology.py, questions.py, quizzes.py,
│   │   ├── translations.py, chat.py, sparql.py, errors.py,
│   │   ├── jobs.py             # Async job endpoints
│   │   └── admin.py            # LLM cache admin
│   ├── tests/                  # pytest suite — prompt builders, dedup,
│   │                           #   language detection, JSON extraction
│   ├── uploads/                # Temporary PDF uploads (mostly empty;
│   │                           #   PDFs are processed from stream)
│   └── quiz_database.db        # SQLite database
├── frontend/
│   ├── src/
│   │   ├── App.js              # Main application
│   │   ├── api.js              # Axios client (incl. jobsApi, adminApi)
│   │   ├── hooks/useAppData.js # Centralized state
│   │   ├── context/LanguageContext.js
│   │   └── components/
│   │       ├── ChatBot.js, QuizBuilder.js, QuizSolver.js,
│   │       ├── QuestionGenerator.js  # Async job polling + progress bar
│   │       ├── QuestionBank.js       # Shows source_line + ontology anchor
│   │       ├── CoveragePanel.js      # PDF coverage heatmap UI
│   │       ├── ContentViewer.js, LessonManager.js, CourseManager.js,
│   │       ├── ManualQuestionAdder.js, SPARQLQueryTool.js,
│   │       ├── TranslationManager.js, TranslationViewer.js,
│   │       └── layout/   # Sidebar, TopBar (LLM cache widget), AlertMessages, ...
│   └── public/index.html
├── raw_materials/              # Sample lesson files
├── ollama.ps1                  # Ollama startup script
├── start.sh, start.bat         # Convenience launchers
└── START_GUIDE.md              # Quick-start guide
```

## API Endpoints

The backend exposes REST API endpoints grouped by domain.

### Core
- `GET /api/health` — Health check
- `POST /api/sparql` — Execute SPARQL queries
- `GET /api/sparql/examples` — Example SPARQL queries

### Courses
- `GET /api/courses` — List courses
- `POST /api/courses` — Create a course
- `GET /api/courses/:id` — Get a course
- `DELETE /api/courses/:id` — Delete a course

### Lessons
- `GET /api/courses/:id/lessons` — List lessons for a course
- `POST /api/courses/:id/lessons` — Upload a PDF lesson (page metadata captured at upload time)
- `GET /api/lessons/:id` — Get lesson + sections
- `DELETE /api/lessons/:id` — Delete a lesson
- `POST /api/lessons/:id/parse` — Parse a lesson into sections + learning objects
- `GET /api/lessons/:id/coverage` — **PDF coverage metrics** (pages covered, char-weighted coverage, per-page array, uncovered substantive pages)

### Ontology
- `GET /api/lessons/:id/ontology` — Relationships for a lesson
- `POST /api/lessons/:id/ontology/generate` — Build ontology from sections/LOs
- `POST /api/lessons/:id/ontology/clear` — Drop ontology for a lesson
- `GET /api/lessons/:id/ontology/export/owl` — Export to OWL
- `GET /api/lessons/:id/ontology/export/turtle` — Export to Turtle

### Questions
- `POST /api/generate-questions` — **Synchronous** legacy generation (still works)
- `POST /api/jobs/generate-questions` — **Async** generation, returns `{job_id}` + 202
- `GET /api/jobs/:id` — Job status + progress + result
- `GET /api/jobs` — Recent jobs
- `GET /api/questions` — List questions (filter by course/lesson/SOLO level)
- `POST /api/questions` — Create a manual question
- `PUT/DELETE /api/questions/:id` — Update/delete a question

### Quizzes
- `GET /api/courses/:id/quizzes` — List quizzes for a course
- `POST /api/quizzes` — Create a quiz
- `POST /api/quizzes/:id/questions` — Add questions to a quiz
- `GET /api/quizzes/:id` — Get quiz (optionally with questions)

### Translation
- `GET /api/translate/languages` — Available languages
- `POST /api/translate/question` — Translate a question
- `POST /api/translate/quiz/:id` — Translate an entire quiz

### Chatbot
- `POST /api/chat` — Send a message to the chatbot
- `POST /api/chat/explain-answer` — Explain a quiz answer

### Admin (LLM cache)
- `GET /api/admin/llm-cache/stats` — Cache entry count + size
- `DELETE /api/admin/llm-cache` — Clear the cache

## Database Schema

SQLite database with the following main entities:

- **Course** — Top-level container for lessons
- **Lesson** — Individual lessons with PDF content; carries `pages_meta` (per-page char counts and offsets)
- **Section** — Lesson subsections, with `start_page`, `end_page`, and verbatim `content` snippet
- **LearningObject** — Atomic content units for questions; tracks `source_pages` (which PDF pages mention it)
- **Question** — Quiz questions with SOLO level, `learning_object_id` / `section_id` anchors, `source_line` (verbatim quote justifying the correct answer), `tags` (ontology anchor + distractor strategies for higher levels)
- **QuestionTranslation** — Translated question content
- **Quiz** + **QuizQuestion** — Quiz collections and N:N links to questions
- **ConceptRelationship** — Knowledge graph edges
- **LLMCache** — SQLite table storing Ollama responses keyed by prompt hash

Schema migrations are handled by an idempotent column-adder in `repository._add_missing_columns()` — adding a new nullable column on an existing DB works without dropping data.

## Usage Tips

### Generating Good Questions

1. Upload well-structured PDF materials. Language is detected automatically — Serbian PDFs produce Serbian questions, English PDFs produce English questions.
2. Parse the lesson to extract sections and learning objects.
3. Generate the ontology to build domain relationships (relational and extended-abstract questions use this).
4. Generate questions — the LLM uses learning-object metadata, the verbatim section text, and (for relational/extended-abstract) a specific ontology anchor.
5. Review the generated questions. Each carries a `source_line` quote — if it doesn't match the source PDF, that's a hallucination signal.
6. Re-run as needed. The LLM cache makes repeat runs instant. Clear it from the top bar to force fresh generation.

### Reading the Coverage Panel

After parsing a lesson and generating some questions, the Coverage panel inside the lesson view shows:

- **Pages covered** — raw count of pages touched by any question
- **Weighted coverage** — coverage weighted by page character count (a 100-character header page counts less than a 2000-character content page)
- **Substantive coverage** — weighted coverage that excludes near-empty pages (cover pages, blank pages)
- A per-page heatmap and a list of uncovered substantive pages

If a 50-page PDF only has questions touching 10 pages, this panel will surface that immediately.

### Using SPARQL Queries

```sparql
# Find all concepts in a lesson
SELECT ?concept WHERE {
  ?concept a :Concept .
}

# Find relationships between concepts
SELECT ?subject ?predicate ?object WHERE {
  ?subject ?predicate ?object .
}
```

### Exporting for Protégé

1. Navigate to the ontology view
2. Click "Export to OWL"
3. Open the downloaded `.owl` file in Protégé
4. Visualize with OntoGraf or OWLViz plugins

## Testing

A pytest suite lives in `backend/tests/`. It covers the load-bearing pieces — prompt construction (PS4 structure, worked examples, distractor strategies, language clause), the question-dedup contract (same anchor + same correct answer is a duplicate even with different wording), the Serbian/English heuristic, and the JSON extraction from LLM responses.

Tests do not require Ollama, a populated database, or a network connection (a `conftest.py` stubs out the Ollama probe).

```bash
cd backend
.\venv\Scripts\python.exe -m pytest tests/
```

## Configuration

The frontend reads its API base URL from `REACT_APP_API_URL`; if unset, it falls back to `http://localhost:5000/api`. Set it in `frontend/.env` to point the UI at a different backend.

## Contributing

This project was developed as part of an educational software research project focused on applying SOLO taxonomy to automated question generation.

## License

This project is for educational purposes.
