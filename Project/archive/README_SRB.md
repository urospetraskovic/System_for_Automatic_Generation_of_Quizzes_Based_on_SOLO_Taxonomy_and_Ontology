# SOLO Generator Kvizova

Obrazovni softverski sistem koji generiše pitanja sa višestrukim izborom
po SOLO taksonomiji iz PDF materijala, koristeći lokalni LLM (Ollama) plus
naučno utemeljen validacioni sloj koji meri pokrivenost, kvalitet pisanja
stavki i usklađenost sa SOLO nivoom — sve bez ikakvih troškova cloud API-ja.

> Puno naučno utemeljenje — svaki rad koji oblikuje generator i validacioni
> sloj — dokumentovano je u
> [`QUESTION_AND_GENERATION_BEST_PRACTICES.md`](QUESTION_AND_GENERATION_BEST_PRACTICES.md).
> Ovaj README je operativni vodič; dokument o best practices je *zašto*.

## Šta radi

- **Učitavanje.** Upload PDF lekcija; tekst i per-page metapodaci se čuvaju.
- **Parsiranje.** LLM deli svaku lekciju u sekcije i objekte učenja (LO),
  od kojih je svaki tagiran stranicama na kojima se nalazi.
- **Domenska ontologija.** Relacije između LO-a (`isPrerequisiteFor`,
  `buildsUpon`, …) se ekstraktuju i čuvaju kao graf.
- **Generisanje pitanja.** Po SOLO nivou (unistructural / multistructural /
  relational / extended abstract), koristeći PS4 prompt šablon, tipizirane
  strategije distraktora i Haladyna 2002 pravila pisanja stavki.
- **Merenje kvaliteta.** Dvoslojni a-priori validacioni stack:
  - **Osnovni (6 metrika):** concept coverage, Haladyna lint, embedding
    plausibility i diversity distraktora, Chain-of-Verification, LLM-blind
    solvability, i SOLO LLM-judge (sa Cohen's κ).
  - **Prošireni (7 dodatnih metrika — A–H):** Item-Objective Congruence
    (Rovinelli & Hambleton 1977), Stem-Only Solvability (Haladyna H4),
    Flesch-Kincaid čitljivost u odnosu na SOLO target, lingvistička
    ambiguity detection (Downing 2005), source-grounded misconception
    mining (Sadler 1998), cloze-style sibling-concept distractor pool
    (Aldabe 2009), gramatička homogenost (Haladyna O7 / Tarrant 2009),
    distractor face-validity rubrika (Considine 2005 / Tarrant & Ware 2008).
- **Pravljenje kvizova.** Ručno kuriranje kvizova iz banke pitanja, prevod,
  predaja studentima.

## Modovi generisanja

Tri dugmeta ispod generatora pitanja, od najmanualnijeg do najautomatizovanijeg:

1. **Generate Questions** — sam biraš lekcije, SOLO nivoe, i koliko pitanja
   po nivou. Generator prati tvoje instrukcije doslovno.
2. **Generate Full Questions for Selected Lessons** *(novo)* — biraš
   lekcije (1, 2 ili N); per-nivo kvote se automatski računaju iz LO/sekcija
   svake lekcije. Extended Abstract se dodaje za konsekutivne parove kad
   se izaberu 2+ lekcija. Ovo je pravo dugme kad želiš "sve za ove lekcije,
   pametno odmereno" bez podešavanja klizača.
3. **Generate for Whole Course** — auto-kvota nad svakom parsiranom
   lekcijom u kursu, cilj ~85–90% slide coverage. Pari sa **Target
   Uncovered Pages** posle, da popuniš preostale rupe u pokrivenosti.

## Brz start

Potrebno ti je **Python 3.10+**, **Node.js 18+** i **Ollama**.

```bash
# Backend
cd backend
python -m venv venv
.\venv\Scripts\activate              # ili: source venv/bin/activate
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install

# Ollama modeli (jednokratno)
ollama pull qwen2.5:14b-instruct-q4_K_M       # generator
ollama pull nomic-embed-text                  # opciono, aktivira embedding lint
```

Opciono: nezavisni modeli za validacioni sloj u `backend/.env`:

```bash
OLLAMA_MODEL=qwen2.5:14b-instruct-q4_K_M
OLLAMA_JUDGE_MODEL=llama3.1:8b       # SOLO LLM-judge (inače fallback na OLLAMA_MODEL)
OLLAMA_COVE_MODEL=llama3.1:8b        # Chain-of-Verification
OLLAMA_SOLVER_MODEL=llama3.1:8b      # Solvability blind-solver + stem-only (H4)
OLLAMA_EMBED_MODEL=nomic-embed-text  # embeddings
# Prošireni validacioni sloj (A-H):
OLLAMA_IOC_MODEL=llama3.1:8b         # Item-Objective Congruence
OLLAMA_AMBIGUITY_MODEL=llama3.1:8b   # ambiguity detection
OLLAMA_MINER_MODEL=llama3.1:8b       # misconception mining
OLLAMA_GRAMMAR_MODEL=llama3.1:8b     # grammatical homogeneity
OLLAMA_FACE_MODEL=llama3.1:8b        # face validity rubric
```

Pokreni tri terminala (Ollama, backend, frontend) i otvori
`http://localhost:3000`.

## Tehnološki stek

**Backend** — Python 3.10+, Flask 2.3, SQLAlchemy 2.0, SQLite, Pydantic 2,
RDFLib 7, PyPDF2, `concurrent.futures.ThreadPoolExecutor` za background
poslove.

**Frontend** — React 18 + Axios + CSS3.

**AI sloj** — Ollama (lokalni LLM). Default generator model:
`qwen2.5:14b-instruct-q4_K_M`. Default embedding model: `nomic-embed-text`.

## Struktura projekta

Visok-nivovska mapa direktorijuma. Detaljan obilazak je u
[`structure.md`](structure.md).

```
Project/
├── backend/
│   ├── app.py, config.py, schemas.py, repository.py
│   ├── core/                           # LLM pipeline
│   │   ├── prompt_lib.py              # PS4 + Haladyna pravila + distraktor strategije
│   │   ├── quiz_generator.py          # SOLO generator (uklj. 2-pass EA)
│   │   ├── content_parser.py, lang_detect.py, llm_cache.py
│   ├── models/                         # SQLAlchemy ORM
│   ├── ontology/                       # seed TBox (OWL/Turtle)
│   ├── services/
│   │   ├── lesson_service.py, question_service.py, quiz_service.py
│   │   ├── coverage_service.py        # page + concept coverage
│   │   ├── mcq_lint.py                # Haladyna lint + embedding plausibility
│   │   ├── embedding_service.py       # Ollama embeddings + cosine helper
│   │   ├── solo_judge.py              # second-LLM SOLO klasifikator (Cohen κ)
│   │   ├── self_consistency.py        # best-of-N selektor
│   │   ├── cove.py                    # Chain-of-Verification
│   │   ├── solvability.py             # LLM-blind solver + stem-only (H4)
│   │   ├── ioc.py                     # A. Item-Objective Congruence (Rovinelli 1977)
│   │   ├── readability.py             # C. Flesch / Flesch-Kincaid (pure-Python)
│   │   ├── ambiguity.py               # D. Linguistic ambiguity (Downing 2005)
│   │   ├── misconception_mining.py    # E. Source-grounded misconceptions (Sadler 1998)
│   │   ├── cloze_distractor.py        # F. Sibling-concept pool (Aldabe 2009)
│   │   ├── grammar_homogeneity.py     # G. POS-based O7 (Tarrant 2009)
│   │   ├── face_validity.py           # H. Considine 2005 rubrika
│   │   ├── ontology_manager.py, sparql_service.py, translation_service.py
│   │   ├── chatbot_service.py, jobs.py
│   ├── routes/                         # Flask blueprints (jedan po domenu)
│   └── tests/                          # pytest suite (356 testova)
├── frontend/
│   └── src/components/
│       ├── QuestionGenerator.js       # UI sa 3 moda generisanja
│       ├── QuestionBank.js
│       ├── CoveragePanel.js           # page + concept coverage UI
│       ├── MCQLintPanel.js            # Haladyna lint UI
│       ├── SoloJudgePanel.js          # Cohen κ + confusion matrix
│       ├── AdvancedQualityPanel.js    # CoVe + solvability
│       ├── ExtendedValidityPanel.js   # A-H tehnike on-demand
│       ├── ContentViewer.js, LessonManager.js, CourseManager.js
│       ├── QuizBuilder.js, QuizSolver.js, ManualQuestionAdder.js
│       ├── TranslationManager.js, TranslationViewer.js
│       ├── SPARQLQueryTool.js, ChatBot.js
│       └── layout/  (Sidebar, TopBar, AlertMessages, …)
├── QUESTION_AND_GENERATION_BEST_PRACTICES.md   # naučno → kod mapping
├── README.md, README_SRB.md
├── structure.md
└── ollama.ps1, start.sh, start.bat
```

## API Endpoint-i

Grupisano po domenu. Sve pod `/api`.

### Osnovni
- `GET /health` — health-check
- `POST /sparql`, `GET /sparql/examples` — SPARQL upiti

### Kursevi, lekcije, sekcije, objekti učenja
- `GET|POST /courses`, `GET|DELETE /courses/<id>`
- `GET /courses/<id>/lessons`, `POST /courses/<id>/lessons`
- `GET|DELETE /lessons/<id>`, `POST /lessons/<id>/parse`
- `GET /lessons/<id>/sections`, `GET /sections/<id>`
- `GET|POST /sections/<id>/learning-objects`, `GET|PUT|DELETE /learning-objects/<id>`

### Ontologija
- `GET /lessons/<id>/ontology`
- `POST /lessons/<id>/ontology/generate`, `POST /lessons/<id>/ontology/clear`
- `GET /lessons/<id>/ontology/export/owl`, `GET /lessons/<id>/ontology/export/turtle`

### Generisanje pitanja
- `POST /generate-questions` — sinhrono, zadržano radi kompatibilnosti
- `POST /jobs/generate-questions` — ručno: lesson ID-ovi + set nivoa + broj
- `POST /jobs/generate-questions-for-lessons` *(novo)* — auto-kvota nad listom lekcija
- `POST /jobs/generate-questions-for-course` — auto-kvota nad celim kursom
- `POST /jobs/generate-questions-for-uncovered` — coverage-fill mod
- `GET /jobs/<id>`, `GET /jobs` — status posla + skorašnji poslovi

### Banka pitanja
- `GET /questions` *(filtriranje po course, lesson, SOLO nivou)*
- `POST /questions` — ručno kreiranje
- `GET|PUT|DELETE /questions/<id>`

### Kvalitet / validity — osnovni
- `GET /questions/<id>/lint`, `GET /lessons/<id>/lint` — Haladyna + embedding lint
- `GET /questions/<id>/solo-judge`, `GET /lessons/<id>/solo-judge` — Cohen κ vs intended SOLO
- `GET /questions/<id>/cove`, `GET /lessons/<id>/cove` — Chain-of-Verification
- `GET /questions/<id>/solvability?n_trials=N`, `GET /lessons/<id>/solvability?n_trials=N` — LLM-blind solver
- `GET /lessons/<id>/coverage` — page + concept coverage

### Kvalitet / validity — prošireni (A–H)
- `GET /questions/<id>/ioc`, `GET /lessons/<id>/ioc` — Item-Objective Congruence (A)
- `GET /lessons/<id>/stem-only-solvability` — Haladyna H4 stem-only (B)
- `GET /questions/<id>/readability`, `GET /lessons/<id>/readability` — Flesch / FK grade (C)
- `GET /questions/<id>/ambiguity`, `GET /lessons/<id>/ambiguity` — ambiguity detection (D)
- `GET /lessons/<id>/misconception-mining` — Sadler-style mining (E)
- `GET /questions/<id>/grammar-homogeneity`, `GET /lessons/<id>/grammar-homogeneity` — POS O7 (G)
- `GET /questions/<id>/face-validity`, `GET /lessons/<id>/face-validity` — Considine rubrika (H)

### Kvizovi, prevodi, chatbot, admin
- Standardni CRUD na `/quizzes`, `/translate/*`, `/chat`, `/admin/llm-cache`
  (vidi `structure.md` za detalje).

## Baza

SQLite u `backend/quiz_database.db`. Ključne tabele: `courses`, `lessons`,
`sections`, `learning_objects`, `concept_relationships`, `questions`,
`quizzes`, `quiz_questions`, plus per-resource `*_translation` tabele i
interne `llm_cache` i `embedding_cache` tabele koje koristi AI pipeline.

Šemske migracije idu kroz idempotentni column-adder u
`repository._add_missing_columns()` — dodavanje nove nullable kolone na
postojeću bazu radi pri sledećem startu backenda, bez Alembic-a.

## Testiranje

```bash
cd backend
.\venv\Scripts\python.exe -m pytest tests/
```

Pytest suite (356 testova u trenutku pisanja) ne zahteva Ollamu, popunjenu
bazu ili mrežu. Validacioni servisi (judge, CoVe, solver, IOC, ambiguity,
misconception miner, grammar homogeneity, face validity) koriste injektabilan
`llm_caller` parametar tako da njihovi testovi mokuju LLM sa scripted
odgovorima.

## Konfiguracija

Frontend čita API base URL iz `REACT_APP_API_URL`; ako nije postavljen
koristi `http://localhost:5000/api`. Postavi u `frontend/.env` ako želiš
UI da pokazuje na drugi backend.

Backend modeli i thresholds su konfigurabilni kroz environment varijable
u `backend/.env` — vidi Brz start gore.

## Licenca

Projekat je za obrazovne svrhe.
