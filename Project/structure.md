# SOLO Quiz Generator — Struktura projekta

Ovaj dokument opisuje arhitekturu, glavne module i tok podataka kroz aplikaciju.
Namenjen je kao brz orijentir za razvoj i buduće promene.

---

## 1. Šta je projekat

**SOLO Quiz Generator** je obrazovna aplikacija koja:

- prima PDF lekcije (npr. iz predmeta "Operativni sistemi"),
- automatski (LLM) parsira lekciju u **sekcije** i **learning objekte**,
- gradi **domensku ontologiju** (relacije među pojmovima),
- generiše pitanja po **SOLO taksonomiji** (Unistructural, Multistructural,
  Relational, Extended Abstract) koristeći **PS4 prompt template**
  (role-priming + kratka SOLO definicija + jedan radni primer + tipizirane
  strategije distraktora + chain-of-thought skela),
- traži od LLM-a **source_line** — doslovni navod iz izvornog teksta koji
  opravdava tačan odgovor (anti-halucinacija),
- prati **PDF coverage**: po-stranični broj znakova, koje stranice su
  obuhvaćene pitanjima, ponderisana pokrivenost,
- omogućava ručno dodavanje, prevođenje i eksport pitanja u kvizove,
- nudi **chatbot** za obrazovnu pomoć i **SPARQL** upite nad ontologijom,
- izvršava generisanje pitanja **u background-u** (ThreadPoolExecutor) sa
  progres polling-om sa frontenda — UI više ne čeka 30s na spinneru.

LLM backend je lokalni **Ollama** (model `qwen2.5:14b-instruct-q4_K_M`), pa nema
cloud API troškova. Svi LLM odgovori se keširaju u SQLite tabeli da bi
ponovljeni runovi bili instantni.

---

## 2. Tehnološki stek

| Sloj      | Tehnologije                                                            |
|-----------|------------------------------------------------------------------------|
| Backend   | Python 3, Flask, Flask-CORS, SQLAlchemy 2 (SQLite), Pydantic 2, rdflib, PyPDF2 |
| Background poslovi | `concurrent.futures.ThreadPoolExecutor` + in-memory job store |
| LLM       | Ollama (HTTP API), model `qwen2.5:14b-instruct-q4_K_M`, `format: "json"` mode za pitanja |
| Frontend  | React 18, axios, react-scripts (CRA)                                   |
| Ontologija| OWL/RDF (RDF/XML i Turtle), SPARQL                                     |
| Skladište | SQLite fajl `backend/quiz_database.db` (uklj. `llm_cache` tabelu)      |

---

## 3. Struktura direktorijuma (top-level)

```
Project/
├── backend/                # Flask API + servisi + LLM pipeline
├── frontend/               # React SPA
├── raw_materials/          # Test PDF/TXT lekcije
├── Paper/                  # Akademski rad o projektu
├── ollama.ps1              # PowerShell pokretač za Ollama
├── start.sh / start.bat    # Pokretači
├── README.md / README_SRB.md / START_GUIDE.md
└── structure.md            # (ovaj fajl)
```

---

## 4. Backend (`backend/`)

### 4.1 Ulazna tačka

- **`app.py`** — Flask application factory.
  - poziva `config.ensure_folders()` i `config.apply_to(app)`,
  - `_bootstrap_services()` inicijalizuje DB, SPARQL ontologiju i chatbot sesiju,
  - `register_routes(app)` registruje sve blueprintove.
  - Pokreće se sa `python app.py` (debug, `localhost:5000`).

- **`config.py`** — folder konstante (`UPLOAD_FOLDER`, `LESSON_FOLDER`),
  `ALLOWED_EXTENSIONS`, `MAX_FILE_SIZE` (30 MB),
  `OLLAMA_BASE_URL` / `OLLAMA_MODEL`, i helperi `ensure_folders()` / `apply_to(app)`.

- **`schemas.py`** — Pydantic v2 request schemes (`GenerateQuestionsRequest`)
  za rute koje prihvataju nestrukturisane JSON body-je. Aktivno se koristi u
  `routes/questions.py` i `routes/jobs.py`.

### 4.2 Routes (`backend/routes/`)

Svaki blueprint pokriva jedan domen i zove servise + repozitorijum.
`routes/__init__.py` izlaže `register_routes(app)` koji ih sve montira.

| Fajl                       | Domen / prefiks         | Sažetak                                                   |
|----------------------------|-------------------------|-----------------------------------------------------------|
| `health.py`                | `/api/health`           | Health-check                                              |
| `sparql.py`                | `/api/sparql`           | SPARQL upiti, predefinisani primeri                       |
| `courses.py`               | `/api/courses`          | CRUD nad kursevima                                        |
| `lessons.py`               | `/api/...`              | Upload PDF lekcije (čuva i `pages_meta`), parsiranje, **coverage** |
| `sections.py`              | `/api/...`              | Lista i detalji sekcija jedne lekcije                     |
| `learning_objects.py`      | `/api/...`              | CRUD nad learning objektima                               |
| `ontology.py`              | `/api/...`              | Generisanje, brisanje, eksport (OWL/Turtle), KB statistika|
| `questions.py`             | `/api/...`              | Sinhrono generisanje pitanja + CRUD; Pydantic validacija  |
| `quizzes.py`               | `/api/...`              | Kreiranje kvizova, dodavanje pitanja, JSON eksport        |
| `translations.py`          | `/api/translate, /api/...` | Prevod pitanja, lekcija, sekcija, LO, ontologija, kursa |
| `chat.py`                  | `/api/chat`             | Chatbot razgovor i objašnjenja kvizovskih odgovora        |
| `jobs.py`                  | `/api/jobs`             | **Async generisanje pitanja**: `POST /jobs/generate-questions` → `{job_id}` + 202; `GET /jobs/<id>` za polling |
| `admin.py`                 | `/api/admin`            | **LLM cache admin**: stats + clear                        |
| `errors.py`                | n/a                     | `register_error_handlers(app)` (413, 500)                 |

### 4.3 Models (`backend/models/`)

`models/models.py` sadrži sve SQLAlchemy ORM klase. `__init__.py` ih reeksportuje.

Klase i njihova svrha:

- **`Course`** — predmet (top-level kontejner).
- **`Lesson`** — jedna lekcija (PDF + sirovi tekst + summary).
  - **`pages_meta`** (JSON, nullable): per-page offseti i char_count, popunjava
    se pri uploadu PDF-a; koristi se za coverage metrike i za mapiranje
    sekcija/LO na stranice.
- **`Section`** — logička sekcija unutar lekcije.
  - **`content`** sada nosi doslovni snippet iz izvornog teksta (pre se nije
    popunjavalo).
  - **`start_page`**, **`end_page`** se sad popunjavaju iz `pages_meta` po
    pronalaženju ključnih reči sekcije u izvornom tekstu.
- **`LearningObject`** — atomska jedinica znanja.
  - **`source_pages`** (JSON, nullable): lista stranica gde se LO pominje.
- **`ConceptRelationship`** — relacija između dva LO-a (osnova ontologije).
- **`Question`** — pitanje sa SOLO nivoom (`SoloLevel` enum), opcijama, odgovorom.
  - **`learning_object_id`** / **`section_id`** se sad popunjavaju pri AI
    generisanju (ranije su bila NULL).
  - **`source_line`** (Text, nullable): doslovni navod iz izvornog teksta koji
    opravdava tačan odgovor. Pomaže u detekciji halucinacija.
  - **`tags`** (JSON): za relaciona i extended-abstract pitanja drži strukturu
    `{ontology_anchor: {source, target, type, description}, distractor_strategies: [...]}`.
- **`Quiz`** + **`QuizQuestion`** — kviz i veza N–N na pitanja.
- **`QuestionTranslation`** / **`LessonTranslation`** /
  **`SectionTranslation`** / **`LearningObjectTranslation`** /
  **`OntologyTranslation`** — prevodi za svaki tip resursa.

Pored ORM klasa, postoji i **`llm_cache`** tabela kreirana iz
`core/llm_cache.py` (`CREATE TABLE IF NOT EXISTS`), koja čuva keširane
Ollama odgovore.

`engine` i `Session` se kreiraju nad lokalnim SQLite fajlom
`backend/quiz_database.db`.

### 4.4 Repository (`backend/repository.py`)

Tanak DAO sloj iznad SQLAlchemy. Sadrži:

- `init_database()` — kreira sve tabele preko `Base.metadata.create_all`
  i poziva `_add_missing_columns()`.
- **`_add_missing_columns()`** — idempotentni column migrator nad SQLite-om.
  Čita `PRAGMA table_info(<table>)` i radi `ALTER TABLE ADD COLUMN` ako kolona
  nedostaje. Trenutno održava `lessons.pages_meta`, `learning_objects.source_pages`
  i `questions.source_line`. Pokreće se na svakom startu backenda.
- `DatabaseManager` klasa sa CRUD metodama (`get_all_courses`, `create_course`,
  `delete_course`, `get_lessons_for_course`, `create_lesson`,
  `update_lesson_pages_meta`, `bulk_create_sections_and_learning_objects`,
  `update_question`, `bulk_create_relationships`, ...).
- Singleton `db = DatabaseManager()` koji koriste route-ovi i servisi.

Cilj je da rute ne dotiču SQLAlchemy direktno, osim za par specifičnih upita.

### 4.5 Services (`backend/services/`)

Poslovna logika i AI integracije.

| Fajl                       | Uloga                                                                                |
|----------------------------|--------------------------------------------------------------------------------------|
| `lesson_service.py`        | `LessonService.parse_lesson()` — orkestracija parsiranja lekcije (sad sa pages_meta) |
| `question_service.py`      | `QuestionService.generate_questions()` — generisanje SOLO pitanja, prosleđuje `progress_cb` |
| `quiz_service.py`          | Pomoćne operacije nad kvizovima                                                      |
| `coverage_service.py`      | `CoverageService.compute()` — metrike PDF pokrivenosti; rekonstruiše `pages_meta` iz `--- Page N ---` markera za starije lekcije |
| `jobs.py`                  | ThreadPoolExecutor + in-memory job store; `submit(kind, runner)` / `get(job_id)` / `list_recent()`; runner-i primaju `report_progress` callback |
| `ontology_manager.py`      | `OntologyManager` — spaja seed TBox (`ontology/`) sa DB ABox-om u kompletan KB. Jedinstveni izvor za eksport: `export_lesson_ontology(lesson_id, fmt)` i `export_full_ontology(course_id, fmt)` gde je `fmt='turtle'` (default) ili `'xml'` (RDF/XML preko rdflib). Stara verzija sa string-templated OWL-om (`ontology_service.py`) je obrisana — sve rute idu kroz `ontology_manager`. |
| `sparql_service.py`        | Učitava ontologiju i izvršava SPARQL upite (rdflib)                                  |
| `chatbot_service.py`       | `ChatbotService` — pozivi prema Ollama, kontekstualni odgovori, fallback offline mod |
| `translation_service.py`   | Prevodi sve resurse, `SUPPORTED_LANGUAGES` mapa, batch prevod                        |

`services/__init__.py` reeksportuje glavne entitete (`LessonService`,
`QuestionService`, `QuizService`, `CoverageService`, `ontology_manager`,
`get_translation_service`, `chatbot_service`, ...).

### 4.6 Core (`backend/core/`)

LLM pipeline za parsiranje sadržaja, generisanje pitanja, jezičku detekciju
i keširanje.

- **`content_parser.py`** — `ContentParser` (zove Ollama):
  - `extract_pdf_text_from_stream()` — PyPDF2 ekstrakcija; sad vraća i
    `pages_meta` listu sa offsetima i char_count po stranici.
  - `parse_lesson_structure(content, title, pages_meta=...)` — multi-pass podela
    na sekcije + LO; popunjava `Section.start_page`/`end_page` i
    `LearningObject.source_pages`.
  - `extract_ontology_relationships()` — vadi odnose iz teksta (5-pass
    LLM ekstrakcija po tipu relacije; konzervativni fallback samo ako LLM vrati
    nulu — više nema fabrikovanih `prerequisite` lanaca po redosledu).
  - Promptovi su sad **language-aware**: pišu titlove/opise u jeziku izvornog
    teksta (detektovanog kroz `lang_detect.detect_language`), bez prinude
    engleskog.
- **`quiz_generator.py`** — `SoloQuizGeneratorLocal`:
  - jedan prompt po SOLO nivou, izgrađen kroz `prompt_lib.build_question_prompt()`,
  - **dva prolaza za extended_abstract**: pass 1 → pitanje + odgovor + source_line;
    pass 2 (predictive prompting) → 3 tipizirana distraktora,
  - **ontology grounding**: relaciona i extended-abstract pitanja biraju jedan
    `ConceptRelationship` red i postavljaju ga kao "ontology anchor" u prompt;
    sačuva se u `Question.tags.ontology_anchor`,
  - **dedup** preko `(anchor_id, normalized_correct_answer)` ključa umesto
    word-overlap heuristike,
  - `progress_cb(message, current, total)` propagira napredak nazad u job runner.
- **`prompt_lib.py`** — PS4 prompt template + sve fiksne komponente
  (kratke SOLO definicije, jedan worked example po nivou — namerno u domenu
  fotosinteze da model uči STRUKTURU, ne sadržaj; tabela tipiziranih
  distraktorskih strategija po nivou; chain-of-thought skela; striktan output
  schema; klauzula o jeziku izlaza).
- **`lang_detect.py`** — heuristika za detekciju srpskog (latinica + ćirilica)
  vs engleskog. Bez novih zavisnosti; koristi opseg ćirilice + dijakritike +
  malu listu zajedničkih reči.
- **`llm_cache.py`** — SQLite keš Ollama odgovora.
  - `get(model, prompt, temperature, json_mode)` i `put(...)`,
  - ključ je SHA-256 od `(model, prompt, temperature, json_mode)`,
  - tabela `llm_cache` se kreira samo-od-sebe (`CREATE TABLE IF NOT EXISTS`),
  - `clear()` i `stats()` izloženi kroz `/api/admin/llm-cache/*`.
- **`__init__.py`** reeksportuje `content_parser` (instanca) i
  `SoloQuizGeneratorLocal`.

### 4.7 Ontology (`backend/ontology/`)

Statički resursi za RDF/OWL:

- `seed_ontology.owl` / `seed_ontology.ttl` — bazna ontologija (TBox: klase,
  property-ji),
- `seed_ontology_base.owl` — fallback minimalna seed,
- `OS_ontology_exported.owl` — eksportovana puna ontologija (sa primerom
  podataka).

`OntologyManager` čita seed, dodaje individue iz baze i vraća kompletan KB.

### 4.8 Ostalo

- `uploads/` — privremene PDF datoteke (uglavnom prazno; PDF se obrađuje iz
  streama bez snimanja).
- `lessons/` — opciono trajno skladište PDF-ova ako se koristi `file_path`.
- `quiz_database.db` — SQLite baza.
- `requirements.txt` — pinovane verzije Flask 2.3, SQLAlchemy 2.0.36,
  rdflib 7.0, PyPDF2 3.0.1, **pydantic>=2.0**, **pytest>=7.0** (dev).

### 4.9 Tests (`backend/tests/`)

Pytest suite za delove koji su "load-bearing" — sve što sigurnije održati
testovima nego komentarima.

- **`conftest.py`** — dodaje `backend/` na `sys.path` i mockuje
  `requests.get` da import-time Ollama probe ne padaju u mrežu (i ne čekaju
  5s timeout).
- **`test_prompt_lib.py`** — 17 testova: SOLO definicija u prompt-u,
  worked example za pravi nivo (i ne curi iz drugog), sve typed distractor
  strategije, klauzula o jeziku (Serbian), ontology anchor + extra task,
  EA pass-1 sa i bez sekundarne lekcije, EA pass-2 echo + distractor schema.
- **`test_lang_detect.py`** — Cyrillic, Latin diacritics, English,
  Serbian stop-words na kratkom inputu, language_name mapping.
- **`test_quiz_generator_dedup.py`** — ključni invariant: ista LO + isti
  normalizovan tačan odgovor → duplikat, čak i kad je tekst drugačiji.
- **`test_content_parser_json.py`** — `_extract_json_from_response`:
  čist JSON, JSON u prozi, neispravan i nepotpun input.

Pokretanje:
```bash
cd backend
.\venv\Scripts\python.exe -m pytest tests/
```

Tests ne zahtevaju Ollama, DB, niti mrežu.

---

## 5. Frontend (`frontend/`)

CRA aplikacija (React 18 + axios). Pokretanje: `npm start` (port 3000).

### 5.1 Ulazna tačka

- **`src/index.js`** — montira `<App />` u `#root`.
- **`src/App.js`** — orchestrator.
  - drži `activeTab`, `chatbotOpen` u lokalnom stanju,
  - sve API/data state delegira na hook `useAppData`,
  - render se svodi na `Sidebar`, `TopBar`, `AlertMessages`, `TabContent`,
    `HowItWorksCard`, `ChatBot`.

### 5.2 API klijent

- **`src/api.js`** — jedna axios instanca + grupisani objekti
  (`courseApi`, `lessonApi`, `sectionApi`, `learningObjectApi`, `questionApi`,
  `quizApi`, `healthApi`, `ontologyApi`, `sparqlApi`, `chatApi`,
  `translationApi`, **`jobsApi`** za async generisanje, **`adminApi`** za
  LLM cache). Bazni URL se čita iz `process.env.REACT_APP_API_URL` (fallback
  `http://localhost:5000/api`).
  - `lessonApi.getCoverage(lessonId)` — coverage endpoint.
  - `questionApi.generateAsync(...)` — async varijanta koja vraća `{job_id}`.
  - `ontologyApi.downloadLessonOwl/downloadLessonTurtle` — blob download.
  - `ontologyApi.deleteRelationship(relId)` — brisanje ivice grafa.
  - `sparqlApi.execute/getExamples` — SPARQL upiti i primeri.
  - `translationApi.retranslateQuestion/getQuizStatus/fixQuizTranslations/getEntity`.

  Svi komponenti ide kroz `api.js`; nema više sirovih `fetch()` poziva
  rasutih po komponenti.

### 5.3 Custom hook (`src/hooks/`)

- **`useAppData.js`** — centralni state-management hook:
  - drži `courses`, `selectedCourse`, `selectedLesson`, `questions`,
    `loading`, `error`, `success`, `apiStatus`,
  - izlaže `fetchCourses`, `fetchQuestions`, `handleSelectCourse`,
    `handleSelectLesson`, `showSuccess`, `showError`, `clearMessages`,
  - polluje `/api/health` svakih 30s.

### 5.4 Layout komponente (`src/components/layout/`)

- **`Sidebar.js`** — leva navigacija. Stavke su definisane u `NAV_ITEMS`
  konstanti; svaka stavka može imati `requires: 'course' | 'lesson'` zbog
  disabled stanja.
- **`TopBar.js`** — breadcrumb (course / lesson) + **LLM cache widget**
  (broj zapisa, veličina, inline "clear" dugme; auto-refresh svakih 30s).
- **`AlertMessages.js`** — error/success/api-exhausted alert kartice.
- **`HowItWorksCard.js`** — info kartica vidljiva samo na "Courses" tabu.
- **`TabContent.js`** — switch po `activeTab` koji bira odgovarajuću feature
  komponentu (fallback `MissingSelection` kad nedostaje course/lesson).

### 5.5 Feature komponente (`src/components/`)

| Fajl                       | Funkcija                                                              |
|----------------------------|-----------------------------------------------------------------------|
| `CourseManager.js`         | Lista kurseva + kreiranje/brisanje                                    |
| `LessonManager.js`         | Upload PDF lekcija u izabrani kurs                                    |
| `ContentViewer.js`         | Pregled lekcije, sekcija, LO-a, generisanje/prikaz ontologije; ugrađuje `CoveragePanel` |
| `CoveragePanel.js`         | **PDF coverage heatmap**: po-stranični prikaz (visina = char count, boja = pokriveno vs ne), agregatne metrike, lista značajnih nepokrivenih stranica |
| `QuestionGenerator.js`     | UI za pokretanje LLM generisanja; koristi **async job endpoint**, polluje status, prikazuje progres bar sa `current/total` |
| `QuestionBank.js`          | Pregled, filtriranje, brisanje pitanja; prikazuje `source_line` navod i strukturisani **ontology anchor chip** (source → type → target) |
| `ManualQuestionAdder.js`   | Forma za ručno dodavanje pitanja                                      |
| `QuizBuilder.js`           | Kreiranje kviza iz odabranih pitanja, dodavanje pitanja u kviz        |
| `QuizSolver.js`            | UI za rešavanje kviza, snimanje rezultata                             |
| `TranslationManager.js`    | Pregled prevoda kviza, pokretanje prevoda po jezicima                 |
| `TranslationViewer.js`     | Prikaz prevedenog sadržaja                                            |
| `SPARQLQueryTool.js`       | Editor SPARQL upita + tabelarni prikaz rezultata                      |
| `ChatBot.js`               | Floating chat sa kontekstom (course/lesson) i objašnjenjima           |

CSS je deljen kroz `App.css` + per-komponentni fajlovi.

### 5.6 Context (`src/context/`)

- **`LanguageContext.js`** — `LanguageProvider` koji obavija aplikaciju i drži
  aktivni jezik za prevode (koristi se u `TranslationManager` i
  `TranslationViewer`).

---

## 6. Tok podataka (high-level)

1. **Upload** PDF lekcije → `POST /api/courses/<id>/lessons` → PyPDF2
   ekstrakcija → `Lesson.raw_content` + `Lesson.pages_meta` (po-stranični
   offset-i i char_count).
2. **Parsiranje** → `POST /api/lessons/<id>/parse` → `content_parser` →
   `Section`-i (sa `start_page`/`end_page`/`content` snippet) i
   `LearningObject`-i (sa `source_pages`) u DB. Promptovi koriste jezik
   izvornog teksta.
3. **Ontologija** → `POST /api/lessons/<id>/ontology/generate` →
   `content_parser.extract_ontology_relationships()` → `ConceptRelationship`
   zapisi. Fallback se okida samo ako LLM vrati nulu.
4. **Pitanja (async preporučeno)** → `POST /api/jobs/generate-questions` →
   `services/jobs.submit()` stavlja runner u ThreadPoolExecutor →
   `QuestionService.generate_questions(progress_cb=...)` →
   `SoloQuizGeneratorLocal` → `Question` zapisi sa `learning_object_id`,
   `section_id`, `source_line` i (za relacionalna/EA) `tags.ontology_anchor`.
   Frontend polluje `GET /api/jobs/<id>`.
5. **Pitanja (sync legacy)** → `POST /api/generate-questions` — radi i dalje,
   ali blokira HTTP zahtev. Frontend ga ne koristi.
6. **Coverage** → `GET /api/lessons/<id>/coverage` → `CoverageService.compute()`
   iz `pages_meta` + `Section.start_page/end_page` + `LearningObject.source_pages`
   + `Question.learning_object_id` izračunava agregatne i po-stranične metrike.
7. **Kviz** → `POST /api/quizzes` + `add-questions` → `Quiz` + `QuizQuestion`.
8. **Prevodi** → `POST /api/translate/...` → `TranslationService` (Ollama) →
   tabela odgovarajućeg `*Translation` modela.
9. **Eksport** → ontologija u OWL (RDF/XML) ili Turtle preko
   `OntologyManager.export_lesson_ontology(lesson_id, fmt='xml'|'turtle')`
   (rdflib serijalizacija). Kvizovi se ne eksportuju — žive u SQLite bazi i
   rešavaju se direktno iz UI-ja.
10. **Chatbot** → `POST /api/chat` → kontekst (course + lesson + sections
    prefix) prosleđuje se `chatbot_service`.
11. **LLM cache** je transparentan: svaki `_call_ollama` u `quiz_generator` i
    `content_parser` prvo proverava `llm_cache.get(...)`; pri uspehu upisuje
    odgovor u keš. `/api/admin/llm-cache` izlaže stats i clear.

---

## 7. Pokretanje

Tri terminala (vidi `START_GUIDE.md`):

1. **Ollama**: `./ollama.ps1 serve` (port `11434`/`11435` po konfiguraciji).
2. **Backend**: `cd backend && python app.py` (Flask na `:5000`).
3. **Frontend**: `cd frontend && npm start` (CRA dev server na `:3000`).

---

## 8. Konvencije i napomene za buduće promene

- **Rute** treba dodavati u odgovarajući blueprint u `backend/routes/`.
  Novi domen → novi fajl + dodati ga u `ALL_BLUEPRINTS` u
  `routes/__init__.py`.
- **Repozitorijum** (`repository.py`) je izvor istine za jednostavan CRUD.
  Kompleksni upiti i agregati su u servisima ili (gde je to čist SQLAlchemy)
  direktno u rutama.
- **Schema migrations** — dodavanje nove nullable kolone radi se kroz
  `_add_missing_columns()`. Za destruktivne migracije (rename, drop) treba
  uvesti pravu migracioni alat (Alembic).
- **Servisi** ne smeju zvati Flask `request`; ulazne argumente prosleđuju rute.
- **Pydantic** se trenutno koristi samo na rutama sa najvišim rizikom
  (`/generate-questions`, `/api/jobs/generate-questions`). Pri proširenju
  validacije, dodavati šeme u `schemas.py` i podizati ih kroz
  `Model.model_validate(request.get_json(silent=True) or {})` sa `ValidationError`
  hvatanjem koje vraća 422.
- **Background poslovi** koriste in-memory job store (`services/jobs.py`).
  Poslovi NE preživljavaju restart backenda — to je svesna odluka za dev
  setup; za produkciju treba prebaciti na Celery+Redis ili sličan trajni store.
- **Prompt promene** treba raditi u `core/prompt_lib.py` (radni primeri,
  distraktorske strategije, definicije nivoa) tako da se sve drži na jednom
  mestu. Generator metode u `quiz_generator.py` samo pozivaju
  `build_question_prompt(level=..., ...)`.
- **LLM cache** se okida na nivou `_call_ollama` — ako prompt promeni i jedan
  karakter, keš miss je garantovan. Ručno čišćenje (`DELETE /api/admin/llm-cache`)
  je neophodno samo ako želiš svežu generaciju nad istim promptom.
- **Ontologija** se sastoji iz seed TBox-a (`backend/ontology/`) i ABox-a
  generisanog iz baze. `OntologyManager` ih spaja u `rdflib.Graph`.
- **Prevodi** su sinhroni preko Ollama-e; `translate_batch` i
  `translate_course_content` rade redom (ne paralelno) — može biti sporo.
  Cache za njih trenutno nije dodat (pošto idu kroz drugi pipeline od
  `quiz_generator`/`content_parser`).
- **Front state** je centralizovan u `useAppData`; tab-routing je još uvek
  lokalni `useState` u `App.js`. Ako se uvodi pravi router, najbolje je
  uvesti ga oko `<App />` u `index.js` i derivirati `activeTab` iz URL-a.
- **CSS** je čist (bez Tailwind-a, bez CSS-in-JS); klase iz `App.css` su
  deljene (npr. `.card`, `.btn-primary`, `.alert`).
