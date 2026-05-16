# SOLO Generator Kvizova

Inteligentni obrazovni softverski sistem koji automatski generiše pitanja za kvizove zasnovana na SOLO (Structure of Observed Learning Outcomes) taksonomiji. Aplikacija koristi lokalni LLM kroz Ollama servis za kreiranje pedagoški strukturiranih pitanja iz učitanih materijala.

## Pregled

Projekat pomaže nastavnicima da automatski kreiraju pitanja za procenu znanja na različitim kognitivnim nivoima. Sistem parsira PDF materijale, gradi semantički graf znanja (ontologiju) i generiše pitanja sa višestrukim izborom kategorisana po SOLO nivoima:

- **Unistrukturalni** — Prisećanje jedne činjenice
- **Multistrukturalni** — Identifikacija više nezavisnih činjenica
- **Relacioni** — Razumevanje veza između koncepata
- **Prošireni apstraktni** — Više-nivovsko razmišljanje i primena preko više koncepata

## Ključne funkcionalnosti

### Generisanje pitanja
- Upload PDF materijala (srpski latinica/ćirilica ili engleski — jezik se automatski detektuje)
- Automatsko parsiranje u lekcije, sekcije i objekte učenja
- AI generisanje pitanja na sva četiri SOLO nivoa
- **PS4 prompt struktura**: ekspertska persona, kratka SOLO definicija, jedan radni primer po nivou, tipizirane strategije distraktora, chain-of-thought skela
- **Citiranje izvora**: svako generisano pitanje čuva doslovni navod iz izvornog PDF-a koji opravdava tačan odgovor
- **Dva-prolaza za extended abstract**: pitanje + odgovor u prvom prolazu; tri tipizirana distraktora u drugom (predictive prompting)
- **Ontološki povezana relaciona pitanja**: svako relaciono/extended-abstract pitanje je vezano za konkretan `ConceptRelationship` red, što čini vezu sledivom u banci pitanja
- Ručno kreiranje i uređivanje pitanja
- Upravljanje bankom pitanja

### Praćenje pokrivenosti PDF-a
- Po-stranični broj znakova i offset-i čuvaju se uz svaki uploadovani PDF
- Metrike pokrivenosti: broj stranica obuhvaćenih pitanjima, pokrivenost ponderisana znakovima, "substantive" pokrivenost (isključuje skoro prazne stranice)
- Po-stranični heatmap u UI-u: visina trake = broj znakova, boja = pokriveno vs nepokriveno
- Lista značajnih stranica bez pitanja — direktan signal za dalju generaciju
- Kompatibilno unazad: starije lekcije rekonstruišu page metadata iz `--- Page N ---` markera u `raw_content`

### Background poslovi sa progresom
- Dugotrajne generacije se izvršavaju u thread pool-u, ne u HTTP zahtevu
- `POST /api/jobs/generate-questions` vraća `202` + job id; frontend polluje `GET /api/jobs/<id>` za status i progres
- Progres UI prikazuje `Generated relational question 2/3` i progress bar
- Generisanje pitanja više ne blokira UI 30 sekundi na spinneru

### Keširanje LLM odgovora
- SQLite-zasnovan keš ključen SHA-256 hash-om od `(model, prompt, temperatura, json_mode)`
- Ponovno pokretanje iste generacije je instantno
- Widget u top baru prikazuje veličinu keša i inline "clear" dugme za prinudno fresh generisanje

### Ontološki sistem
- Automatsko generisanje grafa znanja iz sadržaja (multi-pass ekstrakcija po tipu relacije)
- SPARQL interfejs za istraživanje relacija
- Eksport u OWL format za Protégé
- Eksport u Turtle format za RDF alate
- Konzervativni fallback: ako LLM ekstrakcija ne vrati ništa, samo same-type i shared-keyword ivice se zaključuju (nema više fabrikovanih `prerequisite` veza po redosledu)

### AI Chatbot
- Kontekstualni odgovori zasnovani na sadržaju kursa
- RAG (Retrieval-Augmented Generation) arhitektura
- Objašnjenja kvizovskih odgovora kada studentima treba pomoć
- Offline fallback režim kada AI nije dostupan

### Upravljanje kvizovima
- Kreiranje kvizova iz banke pitanja
- Filtriranje pitanja po temi, SOLO nivou ili lekciji
- Kvizovi se čuvaju u SQLite bazi
- Interaktivni interfejs za rešavanje
- Podrška za prevod na više jezika

### Sistem prevođenja
- Prevod pitanja na više jezika
- Prevod celih lekcija, sekcija ili objekata učenja
- Batch prevod
- Očuvanje SOLO metapodataka

## Tehnološki stek

**Backend:**
- Python 3.10+
- Flask 2.3.0 (REST API)
- SQLAlchemy 2.0.36 (ORM)
- SQLite (baza)
- Pydantic 2.x (validacija request body-ja)
- RDFLib 7.0.0 (ontologija / SPARQL)
- PyPDF2 (PDF parsiranje)
- `concurrent.futures.ThreadPoolExecutor` za background poslove

**Frontend:**
- React 18
- Axios (HTTP klijent)
- CSS3 stilizacija

**AI sloj:**
- Ollama (lokalni LLM pokretač)
- Qwen 2.5 14B instruct (preporučeno): `qwen2.5:14b-instruct-q4_K_M`

## Preduslovi

Pre pokretanja:

1. **Python 3.10 ili noviji** — [Preuzimanje](https://www.python.org/downloads/)
2. **Node.js 18 ili noviji** — [Preuzimanje](https://nodejs.org/)
3. **Ollama** — [Preuzimanje](https://ollama.com/)

## Instalacija

### 1. Kloniranje repozitorijuma

```bash
git clone <https://github.com/urospetraskovic/ObrazovniSoftProjekat>
cd Project
```

### 2. Backend

```bash
cd backend

# Virtualno okruženje
python -m venv venv

# Aktivacija (Windows)
.\venv\Scripts\activate

# Aktivacija (Linux/Mac)
source venv/bin/activate

# Zavisnosti
pip install -r requirements.txt
```

### 3. Frontend

```bash
cd frontend
npm install
```

### 4. Ollama

```bash
ollama pull qwen2.5:14b-instruct-q4_K_M
```

## Pokretanje aplikacije

Tri terminala paralelno. Pogledajte [START_GUIDE.md](START_GUIDE.md).

**Terminal 1 — Ollama:**
```bash
.\ollama.ps1 serve
```

**Terminal 2 — Backend:**
```bash
cd backend
.\venv\Scripts\python.exe app.py
```

**Terminal 3 — Frontend:**
```bash
cd frontend
npm start
```

Aplikacija je dostupna na `http://localhost:3000`.

## Struktura projekta

```
Project/
├── backend/
│   ├── app.py                  # Flask application factory
│   ├── config.py               # Putanje, Ollama URL/model, file limiti
│   ├── schemas.py              # Pydantic request šeme
│   ├── repository.py           # DB CRUD + idempotentni column migrator
│   ├── requirements.txt        # Python zavisnosti (uklj. pydantic)
│   ├── core/
│   │   ├── content_parser.py   # PDF parsiranje + ekstrakcija sekcija/LO (PS4 promptovi)
│   │   ├── quiz_generator.py   # SOLO generisanje pitanja (PS4 + 2-pass EA)
│   │   ├── prompt_lib.py       # Prompt šablon, SOLO definicije, radni primeri,
│   │   │                       #   tipizirane strategije distraktora
│   │   ├── lang_detect.py      # Srpski (lat/ćir) vs engleski heuristika
│   │   └── llm_cache.py        # SQLite keš Ollama odgovora
│   ├── models/
│   │   └── models.py           # SQLAlchemy modeli
│   ├── ontology/
│   │   └── seed_ontology.ttl   # Seed TBox
│   ├── services/
│   │   ├── lesson_service.py     # Orkestracija parsiranja
│   │   ├── question_service.py   # Orkestracija generisanja pitanja
│   │   ├── quiz_service.py       # Operacije nad kvizovima
│   │   ├── coverage_service.py   # Metrike PDF pokrivenosti
│   │   ├── jobs.py               # ThreadPoolExecutor + in-memory job store
│   │   ├── ontology_manager.py   # Seed TBox + DB ABox; izvozi i KB i
│   │   │                         #   lesson-scoped ontologiju u Turtle i
│   │   │                         #   RDF/XML formatu (preko rdflib-a)
│   │   ├── sparql_service.py     # SPARQL izvršavanje
│   │   ├── chatbot_service.py    # Kontekstualni chatbot
│   │   └── translation_service.py # Prevodi
│   ├── routes/
│   │   ├── health.py, courses.py, lessons.py, sections.py,
│   │   ├── learning_objects.py, ontology.py, questions.py, quizzes.py,
│   │   ├── translations.py, chat.py, sparql.py, errors.py,
│   │   ├── jobs.py             # Async job endpoint-i
│   │   └── admin.py            # LLM cache admin
│   ├── tests/                  # pytest suite — promptovi, dedup,
│   │                           #   detekcija jezika, JSON ekstrakcija
│   ├── uploads/                # Privremeni PDF-ovi (uglavnom prazno;
│   │                           #   PDF se obrađuje iz stream-a)
│   └── quiz_database.db        # SQLite baza
├── frontend/
│   ├── src/
│   │   ├── App.js              # Glavna aplikacija
│   │   ├── api.js              # Axios klijent (uklj. jobsApi, adminApi)
│   │   ├── hooks/useAppData.js # Centralni state
│   │   ├── context/LanguageContext.js
│   │   └── components/
│   │       ├── ChatBot.js, QuizBuilder.js, QuizSolver.js,
│   │       ├── QuestionGenerator.js  # Async job polling + progres bar
│   │       ├── QuestionBank.js       # Prikazuje source_line + ontology anchor
│   │       ├── CoveragePanel.js      # PDF coverage heatmap UI
│   │       ├── ContentViewer.js, LessonManager.js, CourseManager.js,
│   │       ├── ManualQuestionAdder.js, SPARQLQueryTool.js,
│   │       ├── TranslationManager.js, TranslationViewer.js,
│   │       └── layout/   # Sidebar, TopBar (LLM cache widget), AlertMessages, ...
│   └── public/index.html
├── raw_materials/              # Primeri lekcija
├── ollama.ps1                  # Ollama startup skripta
├── start.sh, start.bat         # Pokretači
└── START_GUIDE.md              # Vodič za brzo pokretanje
```

## API Endpoint-i

Backend izlaže REST API endpoint-e grupisane po domenu.

### Osnovni
- `GET /api/health` — Provera stanja
- `POST /api/sparql` — Izvršavanje SPARQL upita
- `GET /api/sparql/examples` — Primeri SPARQL upita

### Kursevi
- `GET /api/courses` — Lista kurseva
- `POST /api/courses` — Kreiranje kursa
- `GET /api/courses/:id` — Preuzimanje kursa
- `DELETE /api/courses/:id` — Brisanje kursa

### Lekcije
- `GET /api/courses/:id/lessons` — Lista lekcija
- `POST /api/courses/:id/lessons` — Upload PDF-a (page metadata se hvata pri uploadu)
- `GET /api/lessons/:id` — Lekcija sa sekcijama
- `DELETE /api/lessons/:id` — Brisanje lekcije
- `POST /api/lessons/:id/parse` — Parsiranje u sekcije + LO
- `GET /api/lessons/:id/coverage` — **Metrike PDF pokrivenosti** (pokrivene stranice, ponderisana pokrivenost, po-stranični niz, nepokrivene značajne stranice)

### Ontologija
- `GET /api/lessons/:id/ontology` — Relacije za lekciju
- `POST /api/lessons/:id/ontology/generate` — Izgradnja ontologije
- `POST /api/lessons/:id/ontology/clear` — Brisanje ontologije
- `GET /api/lessons/:id/ontology/export/owl` — Eksport u OWL
- `GET /api/lessons/:id/ontology/export/turtle` — Eksport u Turtle

### Pitanja
- `POST /api/generate-questions` — **Sinhrono** legacy generisanje (i dalje radi)
- `POST /api/jobs/generate-questions` — **Async** generisanje, vraća `{job_id}` + 202
- `GET /api/jobs/:id` — Status posla + progres + rezultat
- `GET /api/jobs` — Skoriji poslovi
- `GET /api/questions` — Lista pitanja (filter po course/lesson/SOLO nivou)
- `POST /api/questions` — Ručno pitanje
- `PUT/DELETE /api/questions/:id` — Ažuriranje/brisanje pitanja

### Kvizovi
- `GET /api/courses/:id/quizzes` — Lista kvizova
- `POST /api/quizzes` — Kreiranje kviza
- `POST /api/quizzes/:id/questions` — Dodavanje pitanja u kviz
- `GET /api/quizzes/:id` — Kviz (opciono sa pitanjima)

### Prevođenje
- `GET /api/translate/languages` — Dostupni jezici
- `POST /api/translate/question` — Prevod pitanja
- `POST /api/translate/quiz/:id` — Prevod celog kviza

### Chatbot
- `POST /api/chat` — Poruka chatbotu
- `POST /api/chat/explain-answer` — Objašnjenje odgovora

### Admin (LLM keš)
- `GET /api/admin/llm-cache/stats` — Broj zapisa + veličina
- `DELETE /api/admin/llm-cache` — Brisanje keša

## Šema baze podataka

SQLite baza sa sledećim glavnim entitetima:

- **Course** — Kontejner najvišeg nivoa
- **Lesson** — Lekcije sa PDF sadržajem; nosi `pages_meta` (po-stranični broj znakova i offset-i)
- **Section** — Pod-sekcije lekcije, sa `start_page`, `end_page` i doslovnim `content` excerpt-om
- **LearningObject** — Atomske jedinice znanja; prati `source_pages` (na kojim stranicama se pojavljuju)
- **Question** — Pitanja sa SOLO nivoom, `learning_object_id` / `section_id` ankorima, `source_line` (doslovni navod koji opravdava tačan odgovor), `tags` (ontološki ankor + strategije distraktora za više SOLO nivoe)
- **QuestionTranslation** — Prevodi pitanja
- **Quiz** + **QuizQuestion** — Kviz kolekcije i N:N veze
- **ConceptRelationship** — Ivice grafa znanja
- **LLMCache** — Tabela koja čuva Ollama odgovore ključene prompt hash-om

Migracije šeme idu kroz idempotentni column-adder u `repository._add_missing_columns()` — dodavanje nove nullable kolone preko postojeće baze radi bez gubitka podataka.

## Saveti za korišćenje

### Generisanje kvalitetnih pitanja

1. Uploaduj dobro strukturirane PDF materijale. Jezik se detektuje automatski — srpski PDF-ovi daju srpska pitanja, engleski daju engleska.
2. Parsiraj lekciju da bi se izvukle sekcije i objekti učenja.
3. Generiši ontologiju da bi se izgradile domenske relacije (relaciona i extended-abstract pitanja je koriste).
4. Generiši pitanja — LLM koristi LO metapodatke, doslovni tekst sekcije, i (za relaciona/extended-abstract) konkretan ontološki ankor.
5. Pregledaj generisana pitanja. Svako nosi `source_line` navod — ako se ne poklapa sa izvornim PDF-om, to je signal halucinacije.
6. Ponavljaj po potrebi. LLM keš čini repeat-runs instantnim. Obriši ga iz top bara za prinudno fresh generisanje.

### Čitanje Coverage panela

Posle parsiranja lekcije i generisanja nekih pitanja, Coverage panel u prikazu lekcije pokazuje:

- **Pokrivene stranice** — sirovi broj stranica koje neko pitanje pominje
- **Ponderisana pokrivenost** — pokrivenost ponderisana brojem znakova na stranici (naslovna stranica od 100 znakova vredi manje od stranice sadržaja od 2000 znakova)
- **"Substantive" pokrivenost** — ponderisana pokrivenost koja isključuje skoro prazne stranice
- Po-stranični heatmap i listu značajnih nepokrivenih stranica

Ako 50-stranični PDF ima pitanja samo iz 10 stranica, ovaj panel će to odmah prikazati.

### SPARQL upiti

```sparql
# Svi koncepti u lekciji
SELECT ?concept WHERE {
  ?concept a :Concept .
}

# Relacije među konceptima
SELECT ?subject ?predicate ?object WHERE {
  ?subject ?predicate ?object .
}
```

### Eksport za Protégé

1. Otvoriti prikaz ontologije
2. Kliknuti "Export to OWL"
3. Otvoriti preuzeti `.owl` fajl u Protégé-u
4. Vizualizovati sa OntoGraf ili OWLViz dodacima

## Testiranje

Pytest suite se nalazi u `backend/tests/`. Pokriva ključne delove — konstrukciju prompt-a (PS4 struktura, radni primeri, distractor strategije, klauzula o jeziku), ugovor o deduplikaciji pitanja (isti ankor + isti tačan odgovor je duplikat čak i sa drugačijim tekstom), srpsko-engleski heuristika i ekstrakcija JSON-a iz LLM odgovora.

Testovi ne zahtevaju Ollamu, popunjenu bazu, niti mrežu (`conftest.py` mockuje Ollama probe).

```bash
cd backend
.\venv\Scripts\python.exe -m pytest tests/
```

## Konfiguracija

Frontend čita API base URL iz `REACT_APP_API_URL` env varijable; ako nije postavljen, koristi `http://localhost:5000/api`. Postaviti u `frontend/.env` ako se UI usmerava na drugi backend.

## Doprinos

Projekat je razvijen kao deo istraživanja u oblasti obrazovnog softvera, sa fokusom na primenu SOLO taksonomije na automatsko generisanje pitanja.

## Licenca

Projekat je za obrazovne svrhe.
