# SOLO Quiz Generator — Struktura projekta

Ovaj dokument je tehnički orijentir kroz repo: koji deo radi šta, gde živi
poslovna logika, kako se delovi povezuju i šta su prečice za razvoj.

Naučno utemeljenje (citati, papiri, koje tehnike se gde primenjuju) je u
**[`QUESTION_AND_GENERATION_BEST_PRACTICES.md`](QUESTION_AND_GENERATION_BEST_PRACTICES.md)**.
Ovaj fajl je operativni, taj je teorijski.

---

## 1. Šta projekat radi (sažeto)

1. Korisnik upload-uje PDF lekciju.
2. LLM (Ollama) parsira lekciju u sekcije i learning objekte (LO).
3. LLM gradi domensku ontologiju iznad LO-a.
4. LLM generiše SOLO MCQ pitanja kroz **PS4 prompt template** + **Haladyna 2002 pravila** u promptu, sa source-line citatima.
5. Šestoslojni a-priori validacioni sloj meri kvalitet: concept coverage, Haladyna lint, embedding plausibility/diversity, Chain-of-Verification, LLM-blind solvability, SOLO LLM-judge (Cohen κ).
6. Pitanja se grupišu u kvizove i opciono prevode.
7. Sve LLM pozive prati SQLite keš, pa su ponovljeni runovi instantni.

LLM je lokalni **Ollama**; default modeli su `qwen2.5:14b-instruct-q4_K_M`
(generator) i `nomic-embed-text` (embeddings). Sve sekundarne komponente
(judge, CoVe, solver, embeddings) imaju zasebne env varijable za
konfigurabilni model.

---

## 2. Tehnološki stek

| Sloj | Tehnologije |
|------|-------------|
| Backend | Python 3, Flask, Flask-CORS, SQLAlchemy 2 (SQLite), Pydantic 2, rdflib, PyPDF2 |
| Background poslovi | `concurrent.futures.ThreadPoolExecutor` + in-memory job store |
| LLM | Ollama HTTP API, JSON mode, model konfigurabilan kroz `OLLAMA_MODEL` (+ judge/cove/solver/embed varijante) |
| Embeddings | Ollama `/api/embeddings` (default `nomic-embed-text`); cosine similarity in-process; SQLite cache |
| Frontend | React 18, axios, react-scripts |
| Ontologija | OWL/RDF (RDF/XML + Turtle), SPARQL kroz rdflib |
| Skladište | SQLite fajl `backend/quiz_database.db` (uklj. `llm_cache` i `embedding_cache` tabele) |

---

## 3. Top-level layout

```
Project/
├── archive/                # Stari MD fajlovi (history-only)
├── backend/
├── frontend/
├── raw_materials/          # Test PDF/TXT lekcije
├── ollama.ps1, start.sh, start.bat
├── CLAUDE.md
├── README.md
├── structure.md            # ovaj fajl
└── QUESTION_AND_GENERATION_BEST_PRACTICES.md
```

---

## 4. Backend

### 4.1 Ulazna tačka

- **`app.py`** — Flask factory.
  - poziva `config.ensure_folders()` i `config.apply_to(app)`,
  - `_bootstrap_services()` inicijalizuje DB, SPARQL ontologiju i chatbot sesiju,
  - `register_routes(app)` montira sve blueprintove,
  - dev pokretanje: `python app.py` (Flask na `:5000`).
- **`config.py`** — `UPLOAD_FOLDER`, `LESSON_FOLDER`, `ALLOWED_EXTENSIONS`,
  `MAX_FILE_SIZE` (30 MB), `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, helperi
  `ensure_folders()` i `apply_to(app)`. Sve sekundarne env varijable
  (`OLLAMA_JUDGE_MODEL`, `OLLAMA_COVE_MODEL`, `OLLAMA_SOLVER_MODEL`,
  `OLLAMA_EMBED_MODEL`) čitaju se direktno u modulima koji ih koriste.
- **`schemas.py`** — Pydantic v2 schemes. Trenutno samo
  `GenerateQuestionsRequest` (manual generation endpoint).
- **`repository.py`** — DAO sloj nad SQLAlchemy.
  - `init_database()` poziva `Base.metadata.create_all(...)` i
    `_add_missing_columns()` (idempotentni column-adder za nullable kolone:
    `lessons.pages_meta`, `learning_objects.source_pages`,
    `questions.source_line`, ...).
  - `DatabaseManager` klasa sa CRUD metodama i singleton `db`.

### 4.2 Routes (`backend/routes/`)

`routes/__init__.py` izlaže `register_routes(app)` koji montira sve blueprintove.

| Fajl | Prefiks | Sažetak |
|------|---------|---------|
| `health.py` | `/api/health` | health-check |
| `sparql.py` | `/api/sparql` | SPARQL upiti + predefinisani primeri |
| `courses.py` | `/api/courses` | CRUD nad kursevima |
| `lessons.py` | `/api/...` | Upload PDF-a, parsiranje, **coverage** |
| `sections.py` | `/api/...` | Lista i detalji sekcija |
| `learning_objects.py` | `/api/...` | CRUD nad LO-ima |
| `ontology.py` | `/api/...` | Generisanje, brisanje, eksport (OWL/Turtle), stats |
| `questions.py` | `/api/...` | Sinhrono generisanje + CRUD; **lint**, **SOLO judge**, **CoVe**, **solvability** endpointi |
| `quizzes.py` | `/api/...` | Kvizovi + dodavanje pitanja |
| `translations.py` | `/api/translate, /api/...` | Prevodi |
| `chat.py` | `/api/chat` | Chatbot |
| `jobs.py` | `/api/jobs` | **Async generisanje** (manual, per-lesson, per-course, uncovered) + status |
| `admin.py` | `/api/admin` | LLM cache stats + clear |
| `errors.py` | n/a | `register_error_handlers(app)` |

### 4.3 Models (`backend/models/models.py`)

SQLAlchemy ORM klase i njihova svrha:

- **`Course`** — top-level kontejner za lekcije.
- **`Lesson`** — PDF lekcija. Nosi `raw_content`, `summary`, `pages_meta`
  (JSON, per-page char count + offset).
- **`Section`** — sekcija unutar lekcije. Ima `content` snippet, `start_page`,
  `end_page`.
- **`LearningObject`** — atomska jedinica znanja. Ima `keywords` listu,
  `source_pages`, `description`, `key_points`.
- **`ConceptRelationship`** — ivica grafa znanja između dva LO-a sa tipom
  veze i opisom.
- **`Question`** — generisano ili ručno pitanje. Polja od interesa:
  - `solo_level` (string),
  - `learning_object_id` / `section_id` (anker),
  - `source_line` (doslovni citat za anti-halucinaciju),
  - `tags` (JSON: `ontology_anchor`, `distractor_strategies`),
  - `bloom_level`, `difficulty`, `correct_option_index`, `options` (JSON).
- **`Quiz`** + **`QuizQuestion`** — N–N između kvizova i pitanja.
- **`*Translation`** — `QuestionTranslation`, `LessonTranslation`,
  `SectionTranslation`, `LearningObjectTranslation`,
  `OntologyTranslation`.

Pored ORM tabela, postoje i dve interne tabele kreirane iz core modula
(`CREATE TABLE IF NOT EXISTS`):
- **`llm_cache`** (iz `core/llm_cache.py`) — keširani Ollama odgovori
  ključem `(model, prompt, temperature, json_mode)`.
- **`embedding_cache`** (iz `services/embedding_service.py`) — keširani
  vektori po `(model, text)`.

### 4.4 Core (`backend/core/`)

LLM pipeline.

- **`content_parser.py`** — `ContentParser`:
  - `extract_pdf_text_from_stream()` — PyPDF2 ekstrakcija + `pages_meta`,
  - `parse_lesson_structure(...)` — multi-pass podela na sekcije + LO sa
    page mapping-om,
  - `extract_ontology_relationships()` — multi-pass LLM ekstrakcija odnosa
    po tipu relacije.
- **`quiz_generator.py`** — `SoloQuizGeneratorLocal`:
  - jedan prompt po SOLO nivou kroz `prompt_lib.build_question_prompt(...)`,
  - **dva prolaza za Extended Abstract** (Bitew 2023 predictive prompting),
  - ontology anchor za relational i EA pitanja,
  - dedup preko `(anchor_id, normalized_correct_answer)`,
  - `progress_cb` propagira napredak nazad u job runner.
- **`prompt_lib.py`** — sve PS4 komponente:
  - `SOLO_DEFINITIONS`, `DISTRACTOR_STRATEGIES` (Bitew typed strategies),
    `WORKED_EXAMPLES` (cross-domain — fotosinteza),
  - `ROLE_PRIMER`, `COT_SCAFFOLD`, `OUTPUT_SCHEMA`,
  - **`STEM_RULES` (S1–S4)** i **`OPTION_RULES` (O1–O7)** — Haladyna 2002
    pravila u promptu sa istim rule-codes kao u `mcq_lint`,
  - `build_question_prompt(...)`, `build_extended_abstract_pass1_prompt(...)`,
    `build_extended_abstract_pass2_prompt(...)`.
- **`lang_detect.py`** — heuristička detekcija srpski (latinica + ćirilica)
  vs engleski.
- **`llm_cache.py`** — SQLite keš Ollama odgovora; `get` / `put` / `clear` /
  `stats`.

### 4.5 Services (`backend/services/`)

Poslovna logika i AI integracije. Sve glavne funkcije izložene su kroz
`services/__init__.py`.

| Fajl | Uloga |
|------|------|
| `lesson_service.py` | `LessonService.parse_lesson()` — orkestracija parsiranja |
| `question_service.py` | `QuestionService.generate_questions(lesson_ids, solo_levels, questions_per_level)` — ručni mode; `generate_for_lessons(lesson_ids)` — auto-quota nad izabranim lekcijama (uklj. EA za konsekutivne parove); `generate_for_course(course_id)` — auto-quota nad celim kursom; `generate_for_uncovered(course_id)` — coverage-fill |
| `quiz_service.py` | Operacije nad kvizovima |
| `coverage_service.py` | `CoverageService.compute(lesson_id)` — vraća **stranicu** + **concept coverage v2** (težinski po centralnosti u `ConceptRelationship` grafu) |
| `mcq_lint.py` | **Haladyna lint** + embedding plausibility/diversity. `lint_question`, `lint_questions`. 11 automatskih pravila (H14, H16, H17, H19, H21, H22, H24, H25, H27, H_BLANK, H_OPTION_COUNT) + `D_PLAUS_TOO_LOW` / `D_PLAUS_TOO_HIGH` / `D_DIVERSITY_LOW` flagovi |
| `embedding_service.py` | Tanak wrapper oko Ollama `/api/embeddings`. `embed_text(content)`, `cosine_similarity(a, b)`, SQLite cache, graceful fallback na `None` ako embedding model nije pull-ovan |
| `solo_judge.py` | **SOLO LLM-judge.** `classify_question` — drugi LLM klasifikuje pitanje. `judge_questions` — batch + **Cohen κ** + confusion matrix |
| `self_consistency.py` | **Wang 2022 best-of-N.** `score_candidate`, `pick_best_question`, `generate_with_self_consistency(generator_fn, n=3)` — kompozit score: lint + embedding bonus |
| `cove.py` | **Chain-of-Verification (Dhuliawala 2023).** 4-koračni pipeline (plan → verify ×N → judge). `verify_question`, `verify_questions` |
| `solvability.py` | **LLM-blind solver** za a-priori item difficulty. `assess_solvability(question, n_trials=5)` — sakrije ključ, šuffluje opcije, vraća sintetičku p-vrednost. Plus **`assess_stem_only_solvability`** (Haladyna H4) — sakrije *opcije*, traži free-text odgovor i embedding-poredi sa ključem |
| `ioc.py` | **A. Item-Objective Congruence (Rovinelli & Hambleton 1977).** `ioc_rate_question`, `ioc_report` — drugi LLM rangira svako pitanje -1/0/+1 protiv LO/sekcije gde je anchored; agregira u IOC index ∈ [-1, +1] |
| `readability.py` | **C. Flesch / Flesch-Kincaid (Flesch 1948 + Kincaid 1975).** `compute_readability`, `assess_question_readability`, `readability_report` — pure-Python, bez LLM-a. Grade level se poredi sa SOLO target rangom |
| `ambiguity.py` | **D. Linguistic ambiguity (Downing 2005).** `assess_ambiguity`, `ambiguity_report` — LLM proverava da li pitanje admittuje više interpretacija (lexical / referential / syntactic / scope) |
| `misconception_mining.py` | **E. Source-grounded misconceptions (Sadler 1998).** `mine_misconceptions`, `mine_lesson_misconceptions` — regex cue windows + LLM ekstrakcija (misconception, correction) parova iz izvora |
| `cloze_distractor.py` | **F. Sibling-concept pool (Aldabe 2009).** `gather_sibling_concepts`, `suggest_cloze_distractors`, `format_pool_for_prompt` — pure-Python, vadi distraktorske kandidate iz LO keywords-a |
| `grammar_homogeneity.py` | **G. POS-based homogenost (Haladyna O7 / Tarrant 2009).** `check_homogeneity`, `homogeneity_report` — LLM klasifikuje svaku opciju u tip (`noun_phrase`/`verb_phrase`/…), flag-uje outlier-e. Posebno flag-uje slučaj gde je *correct* outlier |
| `face_validity.py` | **H. Distractor face validity (Considine 2005 + Tarrant & Ware 2008).** `assess_face_validity`, `face_validity_report` — LLM rubrika 1-5 po 4 kriterijuma (plausibility, representativeness, no_giveaways, clarity) |
| `jobs.py` | ThreadPoolExecutor + in-memory job store. `submit(kind, runner)`, `get(job_id)`, `list_recent()` |
| `ontology_manager.py` | Spaja seed TBox (`ontology/`) sa DB ABox-om. `export_lesson_ontology(lesson_id, fmt)` / `export_full_ontology(course_id, fmt)` u `'turtle'` ili `'xml'` (RDF/XML) |
| `sparql_service.py` | Učitava ontologiju, izvršava SPARQL upite |
| `chatbot_service.py` | Kontekstualni chatbot, offline fallback |
| `translation_service.py` | Prevod svih resursa (`SUPPORTED_LANGUAGES`, batch translate) |

### 4.6 Ontology (`backend/ontology/`)

- `seed_ontology.ttl` / `seed_ontology.owl` — bazna ontologija (TBox: klase, propertiji).
- `seed_ontology_base.owl` — minimalna fallback seed.
- `OS_ontology_exported.owl` — primer eksportovane pune ontologije.

### 4.7 Tests (`backend/tests/`)

Pytest suite. **356 testova trenutno**, nijedan ne zahteva Ollama, DB ili
mrežu. `conftest.py` mokuje `requests.get` da import-time probe Ollama
servera ne čeka 5s timeout.

Pokrivene oblasti:
- prompt builders (`test_prompt_lib.py`) — PS4 struktura, worked examples
  po nivou, distractor strategije, language clause, Haladyna rule codes;
- content parser (`test_content_parser_json.py`, `test_section_*`,
  `test_lo_*`, `test_outline_*`, `test_toc_exclusion.py`,
  `test_title_variants.py`) — JSON ekstrakcija, sekcije, LO grounding,
  outline detekcija;
- ontology helpers (`test_ontology_helpers.py`, `test_ontology_batching.py`);
- jezička detekcija (`test_lang_detect.py`);
- question deduplication (`test_quiz_generator_dedup.py`);
- **validity sloj — osnovni** (sve sa injektabilnim `llm_caller`-om):
  - `test_concept_coverage.py` — concept coverage v2
  - `test_mcq_lint.py` — Haladyna 11 pravila + embedding flagovi
  - `test_solo_judge.py` — Cohen κ + confusion matrix + parsing
  - `test_self_consistency.py` — best-of-N selektor
  - `test_cove.py` — 4-step CoVe pipeline
  - `test_solvability.py` — LLM-blind solver + stem-only (H4)
  - `test_generate_for_lessons.py` — auto-quota nad izabranim lekcijama
- **validity sloj — prošireni (A–H)**:
  - `test_ioc.py` — A. IOC rating + index agregat
  - `test_readability.py` — C. Flesch/FK formula + SOLO fit
  - `test_ambiguity.py` — D. ambiguity detection + tipovi
  - `test_misconception_mining.py` — E. cue windows + LLM ekstrakcija
  - `test_cloze_distractor.py` — F. sibling concepts + dedup
  - `test_grammar_homogeneity.py` — G. POS klasifikacija + outlier detekcija
  - `test_face_validity.py` — H. rubrika + criterion means

Pokretanje:
```bash
cd backend
.\venv\Scripts\python.exe -m pytest tests/
```

---

## 5. Frontend

CRA app (React 18 + axios). Pokretanje: `npm start` (port 3000).

### 5.1 Ulazna tačka

- **`src/index.js`** — montira `<App />`.
- **`src/App.js`** — orchestrator. Drži `activeTab`, `chatbotOpen`;
  delegira sve API/data state-ove na `useAppData`.

### 5.2 API klijent (`src/api.js`)

Jedna axios instanca + grupisani objekti:

- `courseApi`, `lessonApi`, `sectionApi`, `learningObjectApi`, `quizApi`,
  `healthApi`, `ontologyApi`, `sparqlApi`, `chatApi`, `translationApi`.
- **`questionApi`** — manual, per-lessons, per-course, uncovered generation,
  CRUD, **`lint`**, **`lintLesson`**, **`soloJudge`**, **`soloJudgeLesson`**,
  **`cove`**, **`coveLesson`**, **`solvability`**, **`solvabilityLesson`**,
  plus extended validity helperi: **`stemOnlySolvabilityLesson`**,
  **`iocLesson`**, **`readabilityLesson`**, **`ambiguityLesson`**,
  **`misconceptionMining`**, **`grammarHomogeneityLesson`**, **`faceValidityLesson`**.
- **`jobsApi`** — `get(jobId)`, `list()` za polling background poslova.
- **`adminApi`** — LLM cache stats + clear.

Bazni URL: `REACT_APP_API_URL` (default `http://localhost:5000/api`).

### 5.3 Hooks (`src/hooks/`)

- **`useAppData.js`** — centralni state hook: `courses`, `selectedCourse`,
  `selectedLesson`, `questions`, `loading`, `error`, `success`,
  `apiStatus`. Polluje `/api/health` svakih 30s.

### 5.4 Layout (`src/components/layout/`)

- **`Sidebar.js`** — leva navigacija. Stavke u `NAV_ITEMS`, sa `requires`
  za course/lesson.
- **`TopBar.js`** — breadcrumb + LLM cache widget (zapisi, veličina,
  inline clear; auto-refresh 30s).
- **`AlertMessages.js`** — error/success/api-exhausted alert kartice.
- **`HowItWorksCard.js`** — info kartica na "Courses" tabu.
- **`TabContent.js`** — switch po `activeTab`.

### 5.5 Feature komponente (`src/components/`)

| Fajl | Funkcija |
|------|----------|
| `CourseManager.js` | Lista i CRUD kurseva |
| `LessonManager.js` | Upload PDF lekcija |
| `ContentViewer.js` | Pregled lekcije, sekcija, LO-a, ontologije; ugrađuje **CoveragePanel**, **MCQLintPanel**, **SoloJudgePanel**, **AdvancedQualityPanel** i **ExtendedValidityPanel** |
| `CoveragePanel.js` | Stranice + **concept coverage v2** (heatmap, težinski %, top uncovered concepts chipovi) |
| `MCQLintPanel.js` | Haladyna lint UI + embedding plausibility/diversity stat blok; per-question collapsible flagovi |
| `SoloJudgePanel.js` | Cohen κ + Landis-Koch qualitative label + confusion matrix; "Run" dugme jer je sporo prvi put |
| `AdvancedQualityPanel.js` | Dve sekcije: **CoVe** (verdict counts + per-question status) i **Solvability** (LLM p-value distribucija) |
| `ExtendedValidityPanel.js` | Sedam sekcija (A–H) sa zasebnim "Run" dugmićima: IOC, Stem-Only H4, Readability, Ambiguity, Misconception Mining, Grammar Homogeneity, Face Validity. Rezultati keširani server-side preko `llm_cache` tabele. |
| `QuestionGenerator.js` | 3 moda generisanja: ručni (lessons + levels + count), **Generate Full Questions for Selected Lessons** (auto-quota nad izabranima), Whole Course, Target Uncovered |
| `QuestionBank.js` | Lista pitanja sa `source_line` i ontology anchor chipom |
| `ManualQuestionAdder.js` | Forma za ručno dodavanje pitanja |
| `QuizBuilder.js` | Kreiranje kviza iz banke |
| `QuizSolver.js` | Rešavanje kviza |
| `TranslationManager.js` / `TranslationViewer.js` | Prevodi |
| `SPARQLQueryTool.js` | SPARQL editor + tabela |
| `ChatBot.js` | Floating chat |

---

## 6. Tok podataka (high-level)

1. **Upload** PDF → `POST /api/courses/<id>/lessons` → PyPDF2 ekstrakcija →
   `Lesson.raw_content` + `Lesson.pages_meta`.
2. **Parsiranje** → `POST /api/lessons/<id>/parse` → `ContentParser` →
   `Section` + `LearningObject` zapisi.
3. **Ontologija** → `POST /api/lessons/<id>/ontology/generate` →
   `extract_ontology_relationships()` → `ConceptRelationship` zapisi.
4. **Generisanje pitanja** (3 moda):
   - **Manual**: `POST /api/jobs/generate-questions` (Pydantic
     `GenerateQuestionsRequest`) → `QuestionService.generate_questions(...)`.
   - **Per-lessons auto-quota**: `POST /api/jobs/generate-questions-for-lessons`
     → `QuestionService.generate_for_lessons(lesson_ids)`.
   - **Per-course auto-quota**: `POST /api/jobs/generate-questions-for-course`
     → `QuestionService.generate_for_course(course_id)`.
   - **Coverage-fill**: `POST /api/jobs/generate-questions-for-uncovered`.

   Svaki ulazi u `services/jobs.submit()` (ThreadPoolExecutor) →
   `SoloQuizGeneratorLocal` → `Question` zapisi sa `learning_object_id`,
   `section_id`, `source_line`, i (za R/EA) `tags.ontology_anchor`.
   Frontend polluje `GET /api/jobs/<id>`.

5. **Validacioni sloj** (svi a-priori, bez studentskih odgovora):
   - **Osnovni:**
     - Concept coverage v2 — `GET /api/lessons/<id>/coverage`
     - Haladyna lint + embedding plausibility/diversity — `GET /api/lessons/<id>/lint`
     - SOLO LLM-judge → Cohen κ — `GET /api/lessons/<id>/solo-judge`
     - Chain-of-Verification — `GET /api/lessons/<id>/cove`
     - LLM-blind solvability — `GET /api/lessons/<id>/solvability?n_trials=5`
   - **Prošireni (A–H):**
     - A. Item-Objective Congruence — `GET /api/lessons/<id>/ioc`
     - B. Stem-Only Solvability (H4) — `GET /api/lessons/<id>/stem-only-solvability`
     - C. Readability (Flesch/FK) — `GET /api/lessons/<id>/readability`
     - D. Linguistic ambiguity — `GET /api/lessons/<id>/ambiguity`
     - E. Misconception mining iz izvora — `GET /api/lessons/<id>/misconception-mining`
     - G. Grammatical homogeneity — `GET /api/lessons/<id>/grammar-homogeneity`
     - H. Distractor face validity — `GET /api/lessons/<id>/face-validity`
     - F. (Cloze sibling pool je pure-Python helper, koristi se u generatoru)

6. **Kviz** → `POST /api/quizzes` + `add-questions` → `Quiz` + `QuizQuestion`.
7. **Prevodi** → `POST /api/translate/...` → `*Translation` zapisi.
8. **Eksport** → ontologija u OWL (RDF/XML) ili Turtle preko
   `OntologyManager.export_lesson_ontology(...)`.
9. **Chatbot** → `POST /api/chat` → kontekst (course + lesson + section
   prefix) → `chatbot_service`.
10. **LLM keš** je transparentan: svaki LLM poziv (generator, judge, CoVe,
    solver, IOC, ambiguity, miner, grammar, face) prvo proverava
    `llm_cache.get(...)`. Embeddings imaju zasebnu `embedding_cache`
    tabelu sa istim mehanizmom. `/api/admin/llm-cache` izlaže stats + clear.

---

## 7. Pokretanje

Tri terminala (videti `archive/START_GUIDE.md` za originalni vodič — koraci nisu menjani):

1. **Ollama**: `./ollama.ps1 serve`.
2. **Backend**: `cd backend && python app.py` (`:5000`).
3. **Frontend**: `cd frontend && npm start` (`:3000`).

Pre prvog pokretanja:
```bash
ollama pull qwen2.5:14b-instruct-q4_K_M    # generator
ollama pull nomic-embed-text               # opciono, za embedding lint
```

Opcionalna `.env` konfiguracija u `backend/.env`:
```
OLLAMA_MODEL=qwen2.5:14b-instruct-q4_K_M
OLLAMA_JUDGE_MODEL=llama3.1:8b
OLLAMA_COVE_MODEL=llama3.1:8b
OLLAMA_SOLVER_MODEL=llama3.1:8b
OLLAMA_EMBED_MODEL=nomic-embed-text
# Prošireni validacioni sloj (A-H):
OLLAMA_IOC_MODEL=llama3.1:8b
OLLAMA_AMBIGUITY_MODEL=llama3.1:8b
OLLAMA_MINER_MODEL=llama3.1:8b
OLLAMA_GRAMMAR_MODEL=llama3.1:8b
OLLAMA_FACE_MODEL=llama3.1:8b
```

---

## 8. Konvencije i napomene

- **Rute** se dodaju u odgovarajući blueprint pod `backend/routes/`. Novi
  domen → novi fajl + dodati ga u `ALL_BLUEPRINTS` u `routes/__init__.py`.
- **Servisi** ne smeju zvati Flask `request`; ulaze prosleđuju rute.
- **Pydantic validacija** se trenutno koristi samo na `/generate-questions`.
  Za druge endpointe sa neproverenim body-jem, dodati šemu u `schemas.py`.
- **Background poslovi** su u in-memory store-u (`services/jobs.py`).
  Ne preživljavaju restart backenda — to je svesna odluka za dev setup.
- **Prompt promene** raditi u `core/prompt_lib.py`. Sve PS4 komponente i
  Haladyna pravila su tu na jednom mestu.
- **LLM cache** se okida na nivou bilo kog `_call_*` u core/services
  modulima. Ako prompt promeni i jedan karakter — keš miss.
  `DELETE /api/admin/llm-cache` za forsiran reset.
- **Embedding cache** je nezavisan od LLM cache-a (zasebna tabela
  `embedding_cache`). Brisanje se trenutno radi ručno kroz SQLite ili
  brisanjem fajla baze.
- **Validacioni servisi** (judge, cove, solver) primaju injektabilni
  `llm_caller` parametar — testovi ga mokuju, produkcija zove pravi
  Ollama.
- **Schema migrations** — dodavanje nullable kolone radi se kroz
  `repository._add_missing_columns()`. Za destruktivne migracije
  (rename, drop) treba uvesti Alembic ili sličan alat.
- **Tests** treba držati offline i deterministične. Sve nove validacione
  funkcije imaju injektabilni LLM caller upravo zbog ovoga.
