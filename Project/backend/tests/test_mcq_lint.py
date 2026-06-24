"""
Tests for services.quality.mcq_lint — the Haladyna-rule MCQ quality linter.

Each test isolates one rule so a regression makes the failure obvious.

Embedding-based checks (Bitew 2023 plausibility, Falchikov 2008 diversity) are
disabled by default in these tests so they don't depend on Ollama. A dedicated
section below uses a fake embedder to exercise those checks.
"""

from services.quality import mcq_lint as _ml
from services.quality.mcq_lint import lint_question as _lint_question_real, lint_questions as _lint_questions_real


def lint_question(q):
    return _lint_question_real(q, use_embeddings=False)


def lint_questions(qs):
    return _lint_questions_real(qs, use_embeddings=False)


def _q(stem='Šta je proces?', options=None, correct_index=0, correct_answer=None,
       id_=1):
    """Build a minimal question dict in the shape Question.to_dict() returns."""
    if options is None:
        options = [
            'Program u izvršavanju.',
            'Datoteka u memoriji.',
            'Korisnik prijavljen u sistem.',
            'Zauzeti procesorski takt.',
        ]
    if correct_answer is None and isinstance(correct_index, int) and 0 <= correct_index < len(options):
        correct_answer = options[correct_index] if isinstance(options[correct_index], str) else None
    return {
        'id': id_,
        'question_text': stem,
        'options': options,
        'correct_option_index': correct_index,
        'correct_answer': correct_answer,
    }


def _codes(report):
    return {f['code'] for f in report['flags']}


# -----------------------------------------------------------------------------
# Stem checks
# -----------------------------------------------------------------------------

def test_clean_question_has_no_flags():
    r = lint_question(_q())
    assert r['flags'] == []
    assert r['score'] == 100


def test_empty_stem_is_error():
    r = lint_question(_q(stem=''))
    assert 'H14_NO_STEM' in _codes(r)
    assert r['counts']['error'] >= 1


def test_unclear_directive_flagged():
    r = lint_question(_q(stem='Proces je program u izvršavanju'))
    assert 'H14_UNCLEAR_DIRECTIVE' in _codes(r)


def test_imperative_stem_passes_directive_check():
    r = lint_question(_q(stem='Definiši pojam procesa'))
    assert 'H14_UNCLEAR_DIRECTIVE' not in _codes(r)


def test_overlong_stem_flagged():
    long_stem = 'Koji od navedenih iskaza je tačan? ' + ('Vrlo opširno objašnjenje ' * 30) + '?'
    r = lint_question(_q(stem=long_stem))
    assert 'H16_LONG_STEM' in _codes(r)


def test_unemphasized_negation_flagged():
    r = lint_question(_q(stem='Koji NIJE atribut procesa?'))
    assert 'H17_NEGATIVE_STEM' in _codes(r)


def test_emphasized_negation_passes():
    r = lint_question(_q(stem='Koji **NIJE** atribut procesa?'))
    assert 'H17_NEGATIVE_STEM' not in _codes(r)


def test_negative_token_osim_flagged():
    r = lint_question(_q(stem='Sve su odlike procesa, osim:'))
    assert 'H17_NEGATIVE_STEM' in _codes(r)


# -----------------------------------------------------------------------------
# Option checks
# -----------------------------------------------------------------------------

def test_too_few_options_flagged():
    r = lint_question(_q(options=['a', 'b']))
    assert 'H_OPTION_COUNT' in _codes(r)


def test_blank_option_is_error():
    r = lint_question(_q(options=['a', '', 'c', 'd']))
    assert 'H_BLANK' in _codes(r)
    assert r['counts']['error'] >= 1


def test_no_key_is_error():
    q = _q()
    q['correct_option_index'] = None
    r = lint_question(q)
    assert 'H19_NO_KEY' in _codes(r)


def test_key_out_of_range():
    r = lint_question(_q(correct_index=99))
    assert 'H19_KEY_OUT_OF_RANGE' in _codes(r)


def test_correct_answer_text_mismatch():
    r = lint_question(_q(correct_index=0, correct_answer='totalno drugačiji tekst'))
    assert 'H19_KEY_MISMATCH' in _codes(r)


def test_numeric_disorder_flagged():
    r = lint_question(_q(options=['10', '1', '5', '100']))
    assert 'H21_NUMERIC_DISORDER' in _codes(r)


def test_numeric_ascending_ok():
    r = lint_question(_q(options=['1', '5', '10', '100']))
    assert 'H21_NUMERIC_DISORDER' not in _codes(r)


def test_numeric_descending_ok():
    r = lint_question(_q(options=['100', '50', '10', '1']))
    assert 'H21_NUMERIC_DISORDER' not in _codes(r)


def test_option_overlap_flagged():
    r = lint_question(_q(options=[
        'Program u izvršavanju koji koristi resurse',
        'Program u izvršavanju koji troši resurse',  # near-duplicate
        'Niti i mutex objekti',
        'Korisnička sesija',
    ]))
    assert 'H22_OPTION_OVERLAP' in _codes(r)


def test_distractor_equals_key_permutation_flagged():
    # A distractor that is just the correct answer with its terms reordered is
    # not a distractor — it is also correct.
    r = lint_question(_q(
        options=[
            'izlaganje, prianjanje, invazija, infekcija',
            'prianjanje, izlaganje, infekcija, invazija',  # permutation of key
            'groznica, kašalj, osip, umor',
            'rođenje, rast, opadanje, smrt',
        ],
        correct_index=0,
    ))
    assert 'H_DISTRACTOR_EQUALS_KEY' in _codes(r)


def test_distractor_sharing_a_word_with_key_not_flagged():
    # A legitimate sibling that merely shares a token with the key must NOT trip
    # the key-duplicate rule (no false positive).
    r = lint_question(_q(
        options=['ATP sintaza', 'ATP', 'adenilat kinaza', 'heksokinaza'],
        correct_index=0,
    ))
    assert 'H_DISTRACTOR_EQUALS_KEY' not in _codes(r)


def test_correct_answer_longest_is_length_clue():
    r = lint_question(_q(
        options=[
            'Program u izvršavanju koji ima sve atribute, PCB, registre i stanje',  # 65+ chars
            'Datoteka',
            'Korisnik',
            'Resurs',
        ],
        correct_index=0,
    ))
    assert 'H27_CORRECT_LONGEST' in _codes(r)
    assert 'H24_LENGTH_DISPARITY' in _codes(r)


def test_correct_answer_shortest_is_inverted_length_clue():
    """Naively over-correcting H27 produces 'correct is always shortest' clues.
    The lint must catch that symmetrically."""
    r = lint_question(_q(
        options=[
            'Proces',  # correct, shortest
            'Datoteka koja se nalazi u sistemu i koristi se za skladištenje',
            'Korisnik koji je trenutno prijavljen u operativni sistem',
            'Resurs koji procesi koriste tokom svog izvršavanja',
        ],
        correct_index=0,
    ))
    assert 'H27_CORRECT_SHORTEST' in _codes(r)
    assert 'H27_CORRECT_LONGEST' not in _codes(r)


def test_correct_answer_middle_length_passes():
    """When all options are similar length and correct is in the middle,
    neither length-clue flag should fire."""
    r = lint_question(_q(
        options=[
            'Program u izvršavanju',
            'Datoteka u memoriji',         # correct (medium length)
            'Korisnik prijavljen na sistem',
            'Hardver',
        ],
        correct_index=1,
    ))
    assert 'H27_CORRECT_LONGEST' not in _codes(r)
    assert 'H27_CORRECT_SHORTEST' not in _codes(r)


def test_all_of_the_above_flagged():
    r = lint_question(_q(options=[
        'Program u izvršavanju.',
        'Niz instrukcija.',
        'Apstraktni entitet.',
        'Svi navedeni odgovori.',
    ]))
    assert 'H25_AOTA_NOTA' in _codes(r)


def test_none_of_the_above_flagged():
    r = lint_question(_q(options=[
        'Program u izvršavanju.',
        'Niz instrukcija.',
        'Apstraktni entitet.',
        'Nijedan od navedenih.',
    ]))
    assert 'H25_AOTA_NOTA' in _codes(r)


# -----------------------------------------------------------------------------
# Score & batch
# -----------------------------------------------------------------------------

def test_score_drops_with_more_flags():
    clean = lint_question(_q())
    messy = lint_question(_q(stem='', options=['a', '', 'c']))
    assert clean['score'] > messy['score']
    assert messy['score'] < 100


def test_batch_aggregates_correctly():
    qs = [
        _q(id_=1),  # clean
        _q(id_=2, stem='Sve je atribut procesa, osim:'),  # H17, also H14 (no ?)
        _q(id_=3, options=['', 'b', 'c', 'd']),  # H_BLANK
    ]
    report = lint_questions(qs)
    assert report['total_questions'] == 3
    assert report['aggregate_counts']['error'] >= 1
    assert 'H_BLANK' in report['flag_frequency']
    assert report['average_score'] < 100


# -----------------------------------------------------------------------------
# Embedding-based checks (Bitew 2023 plausibility, Falchikov 2008 diversity).
# We inject a fake embedder that returns deterministic vectors per text,
# avoiding any Ollama dependency.
# -----------------------------------------------------------------------------

def _vec_from_chars(s):
    """Toy embedder: text → fixed-length vector seeded from chars. Same string
    always yields the same vector; vectors of similar strings overlap a lot."""
    v = [0.0] * 32
    for i, ch in enumerate(s.lower()):
        v[ord(ch) % 32] += 1.0
    return v


def _fake_embedder(text):
    return _vec_from_chars(text)


def _real_cosine(a, b):
    from services.quality.embedding_service import cosine_similarity
    return cosine_similarity(a, b)


def test_embedding_check_skipped_when_embedder_returns_none():
    """If Ollama isn't available, lint must still work and just skip these checks."""
    r = _lint_question_real(
        _q(),
        embedder=lambda t: None,
        cosine=_real_cosine,
        use_embeddings=True,
    )
    embed_codes = {f['code'] for f in r['flags'] if f['code'].startswith('D_')}
    assert embed_codes == set()
    assert 'embeddings' not in r


def test_embedding_plausibility_too_high_flags_paraphrase():
    """A distractor whose embedding is near-identical to the key should trip
    D_PLAUS_TOO_HIGH. We use a stub embedder that returns a known-high cosine
    for the paraphrase pair, so the test is independent of any specific
    embedding model."""
    vecs = {
        'Program u izvršavanju.':    [1.0, 0.0],
        'Program u izvrsavanju!':    [0.99, 0.005],   # near-identical → cos ≈ 1.0
        'Datoteka u memoriji.':      [0.0, 1.0],
        'Korisnik prijavljen.':      [0.1, 0.99],
    }
    q = _q(options=list(vecs.keys()), correct_index=0)
    r = _lint_question_real(
        q,
        embedder=lambda t: vecs.get(t),
        cosine=_real_cosine,
        use_embeddings=True,
    )
    codes = {f['code'] for f in r['flags']}
    assert 'D_PLAUS_TOO_HIGH' in codes


def test_embedding_diversity_flags_when_two_distractors_too_similar():
    q = _q(options=[
        'Tačan odgovor.',
        'Distraktor jedan blizak drugom.',
        'Distraktor jedan blizak drugom.',   # near-clone of #1 → D_DIVERSITY_LOW
        'Sasvim različit distraktor.',
    ], correct_index=0)
    r = _lint_question_real(
        q, embedder=_fake_embedder, cosine=_real_cosine, use_embeddings=True,
    )
    codes = {f['code'] for f in r['flags']}
    assert 'D_DIVERSITY_LOW' in codes


def test_embedding_summary_present_when_embeddings_used():
    q = _q()
    r = _lint_question_real(
        q, embedder=_fake_embedder, cosine=_real_cosine, use_embeddings=True,
    )
    assert 'embeddings' in r
    # Each distractor has a similarity-to-key score.
    assert 'distractor_key_similarity' in r['embeddings']
    assert 'mean_plausibility' in r['embeddings']


def test_batch_aggregate_embeddings_when_available():
    qs = [_q(id_=1), _q(id_=2)]
    report = _lint_questions_real(
        qs, embedder=_fake_embedder, cosine=_real_cosine, use_embeddings=True,
    )
    assert 'embeddings_summary' in report
    assert 'mean_plausibility' in report['embeddings_summary']
