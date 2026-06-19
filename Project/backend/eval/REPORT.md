# EduQG evaluacija — izveštaj (pilot)

Evaluacija našeg MCQ sistema na **EduQG** datasetu (Hadifar et al., *EduQG: A
Multi-Format Multiple-Choice Dataset for the Educational Domain*, IEEE Access
2023). EduQG sadrži 3.397 ekspertski pisanih multiple-choice pitanja iz 12
OpenStax udžbenika, svako vezano za izvorni tekst na nivou rečenice.

Cilj nije „pobediti" eksterni model, nego iskoristiti ekspertska pitanja kao
**zlatni standard** da (A) **kalibrišemo naše validatore** i (C) **uporedimo naše
generisanje distraktora** sa ekspertskim.

## Postavka

- **Uzorak:** stratifikovan pilot **N=149**, proporcionalno po 12 knjiga, fiksni
  seed (`eval/eduqg.py`). Samo pitanja sa 4 opcije.
- **Provajder za LLM-sudije:** Anthropic **Claude Haiku 4.5** (Ollama je bio
  nedostupan tokom evaluacije).
- **Mapiranje:** EduQG `hl_sentences` → `source_line` (grounding za CoVe);
  `hl_context` → širi kontekst; `question_choices` → opcije; `ans_choice` →
  indeks tačnog. Bez ikakvog pisanja u bazu — validatori se zovu direktno.
- **Artefakti:** `eduqg_calibration.json`, `eduqg_distractors.json`,
  `*_run.log`. (gitignored)

---

## A) Kalibracija validatora (`eval/run_calibration.py`)

**Specifičnost** = koliko često validator (pogrešno) flaguje *ekspertsko*
pitanje. Nisko = dobro. **Senzitivnost** = koliko hvata namerno pokvarena
pitanja (wrong-key: tačan indeks pomeren na distraktor). Visoko = dobro.

| Validator | Flag-rate na ekspertima (↓ bolje) | Senzitivnost (wrong-key, ↑ bolje) |
|---|---|---|
| lint (Haladyna ERROR) | **0.0%** | — |
| solvability (p<0.5) | **4.7%** (mean p=0.94) | **98.0%** (mean p=0.02) |
| grammar (correct outlier) | **4.7%** | — |
| face validity (<2.5) | **0.7%** (mean 3.92/5) | — |
| ambiguity | **24.8%** | — |
| CoVe (not SUPPORTED) | **42.3%** | **94.6%** |
| readability | mean FK grade 10.3 (deskriptivno) | — |

### Tumačenje

- **Solvability je najbolji diskriminator:** 95% specifičnost + 98% senzitivnost.
  Naš „slepi solver" rešava ekspertska pitanja (p=0.94) i otkriva pokvarena
  (p=0.02). lint/grammar/face takođe dobro kalibrisani.
- **CoVe:** odlična senzitivnost (94.6%), ali **slaba specifičnost (42.3% FP)**.
  Verdikti su skoro svi UNDERDETERMINED (60), samo 3 CONTRADICTED — dakle CoVe
  ne nalazi *greške*, nego *ne može da potvrdi*. Hipoteza: nedostatak konteksta
  (vidi dole).
- **Ambiguity (24.8% FP):** detektor je strog. Pregled primera pokazuje mešavinu
  stvarno kontekst-zavisnih stemova i pravih false-positiva — traži ljudski
  spot-check pre nego što se prag olabavi.

### CoVe + bogatiji kontekst (`eval/cove_context_probe.py`)

Test hipoteze: ako CoVe-u damo pun `hl_context` umesto minimalnog
`hl_sentences`:

| CoVe izvor | not-SUPPORTED | SUPPORTED |
|---|---|---|
| minimalni grounding (`hl_sentences`) | 42.3% | 86/149 |
| **pun kontekst (`hl_context`)** | **35.6%** | 96/149 |

Kontekst obara FP za **6.7 poena** — potvrđuje *deo* hipoteze. Ali 35.6% ostaje
visoko: **CoVe je istinski prestrog** za faktoidna pitanja koja traže background
znanje (rad sam navodi da su anotatori računali na njega). Preporuka: (1) CoVe
uvek hraniti najširim dostupnim kontekstom; (2) razmotriti labavljenje praga ka
UNDERDETERMINED. Drugo menja produkciono ponašanje — odluka korisnika.

---

## C) Benchmark distraktora (`eval/run_distractors.py`)

Pristup: **LLM-direktno** (EduQG „Distractor Generation" task) — ulaz (kontekst,
pitanje, tačan odgovor) → 3 distraktora → poređenje sa 3 ekspertska (gold).

| Metrika | Rezultat |
|---|---|
| Gold distraktori reprodukovani (tačno) | 55/447 = **12.3%** |
| Gold distraktori reprodukovani (fuzzy, token-Jaccard≥0.5) | 87/447 = **19.5%** |
| Face validity — **naši** | mean **4.07**/5 |
| Face validity — **gold** | mean **3.95**/5 |

### Tumačenje (sa oprezom)

- **Niska leksička obnova (12–20%)** je očekivana: prostor validnih distraktora
  je velik, naši se legitimno razilaze od ekspertskih (rad pravi istu opasku).
- **Naši distraktori se ocenjuju malo VIŠE od ekspertskih** (4.07 vs 3.95; naši
  ≥ gold u 51% pitanja) — ali ovo **ne znači** da su bolji. Otkriven je defekt:
  - **„Preblizu tačnom odgovoru" failure: 10.7% pitanja (16/149)** ima bar jedan
    naš distraktor koji je parafraza/permutacija tačnog odgovora. Primeri:
    - tačno `deinstitutionalization` → naš `psychiatric deinstitutionalization`
    - tačno `exposure, adhesion, invasion, infection` → naši samo **permutacije
      istog spiska**
  - **Naš `face_validity` ne kažnjava ovaj defekt** — čak ga nagrađuje kao
    „plausible/representative". Zato se face_validity **ne sme koristiti sam** kao
    dokaz da su naši distraktori ravni ekspertskim.

---

## Zaključci i preporuke

1. **Validatori su uglavnom dobro kalibrisani** prema eksternom ekspertskom
   standardu — solvability, lint, grammar, face (na specifičnost) prolaze.
   Ovo je jak rezultat za rad: naša baterija **ne baca lažne uzbune na dobra
   pitanja**.
2. **CoVe je prestrog** (42% FP). Akcija: hraniti ga širim kontekstom (−6.7
   poena dokazano); razmotriti prag.
3. **Ambiguity strog** (25% FP) — ljudski spot-check pre podešavanja.
4. **Generisanje distraktora ima „preblizu tačnom" failure (11%)**, a
   **face_validity ga ne hvata**. Dve akcije:
   (a) u distraktor-promptu pojačati zabranu parafraze/permutacije tačnog
   odgovora; (b) dodati eksplicitnu proveru „distraktor ≠ ~tačan odgovor"
   (postoji `_is_near_duplicate` u `cloze_distractor.py`).

## Primenjene popravke

Na osnovu nalaza primenjene su tri produkcione izmene (svih 407 testova prolazi):

1. **CoVe → širi kontekst.** `verify_question` sada verifikuje protiv najšireg
   dostupnog konteksta: pored `source_line` koristi `context` ključ koji rute
   popunjavaju sadržajem sekcije/learning-objecta
   (`services/cove.py`, `routes/questions.py`). Mereno: FP 42% → ~33–36%.
2. **Distraktor prompt — pravilo O9.** `OPTION_RULES` sada eksplicitno zabranjuje
   da distraktor bude parafraza/preuređenje/sub-superset tačnog odgovora; važi za
   oba generativna prompta (`core/prompt_lib.py`).
3. **Deterministička provera `H_DISTRACTOR_EQUALS_KEY`.** `mcq_lint` flaguje
   (ERROR) distraktor čiji je skup tokena identičan tačnom odgovoru
   (permutacija/duplikat), bez lažnih uzbuna na legitimne srodne pojmove
   (`services/mcq_lint.py`; testovi u `tests/test_mcq_lint.py`).

Ostaje za odluku: labavljenje CoVe praga ka UNDERDETERMINED (35% rezidualni FP);
ljudski spot-check ambiguity detektora (25% FP).

## Reprodukcija

```bash
# iz backend/  (Haiku 4.5; rezultati se keširaju, re-run je jeftin)
venv/Scripts/python.exe -m eval.eduqg                              # M0 smoke
venv/Scripts/python.exe -m eval.run_calibration --n 150 --trials 3 # A
venv/Scripts/python.exe -m eval.cove_context_probe                 # CoVe probe
venv/Scripts/python.exe -m eval.run_distractors --n 150 --no-embed # C
```

## Ograničenja

- **Domenski/jezički pomak:** EduQG je engleski (humanistika/bio/biznis), naš
  produkcioni korpus je srpski (OS/CS). Brojke generisanja treba čitati u tom
  svetlu; kalibracija validatora je robusnija na pomak.
- **Pilot N=149** od 3.397 — dovoljno za signal, ne za uske intervale poverenja.
- **Embedding sličnost preskočena** (Ollama embedder nedostupan); face_validity
  + leksička obnova su nosile poređenje distraktora.
- **SOLO↔Bloom (pravac D) nije rađen** — u uzorku je samo 41 Bloom-labelirano
  pitanje, bez nivoa Analyze.
