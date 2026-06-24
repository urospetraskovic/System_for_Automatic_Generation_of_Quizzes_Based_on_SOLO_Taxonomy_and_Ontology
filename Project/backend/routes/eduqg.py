# -*- coding: utf-8 -*-
"""EduQG benchmark rute.

Stranica poredi kako se naši validatori ponašaju na dve grupe pitanja:
  1. pitanja koja je naš sistem generisao (lekcije Procesi, Niti, Konkurentnost),
  2. ekspertska pitanja iz EduQG referentnog skupa.

Pošto su ekspertska pitanja po pretpostavci dobra, ona služe da proverimo koliko
su naši validatori dobro podešeni. Ova grupa ruta nudi:
  * /eduqg/overview   poređenje po metrici (moja pitanja vs ekspertska) + oblasti
  * /eduqg/questions  ekspertska pitanja po oblasti (paginirano)
  * /eduqg/evaluate   pokretanje evaluacije jednog ekspertskog pitanja uživo
"""

import json
import os
import sqlite3

from flask import Blueprint, jsonify, request, g

eduqg_bp = Blueprint('eduqg', __name__, url_prefix='/api')

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EVAL_DIR = os.path.join(_BACKEND, 'eval')
_STORE = os.path.join(_EVAL_DIR, 'eduqg_calibration.json')
_DB = os.path.join(_BACKEND, 'quiz_database.db')

_dataset_cache = None


def _dataset():
    """eduqg_id -> normalizovano pitanje (učita se jednom)."""
    global _dataset_cache
    if _dataset_cache is None:
        from eval.eduqg import load_eduqg
        _dataset_cache = {it['eduqg_id']: it for it in load_eduqg()}
    return _dataset_cache


def _load_store():
    if not os.path.exists(_STORE):
        return {}
    with open(_STORE, encoding='utf-8') as fh:
        recs = json.load(fh)
    return {r['eduqg_id']: r for r in recs}


def _save_store(store):
    with open(_STORE, 'w', encoding='utf-8') as fh:
        json.dump(list(store.values()), fh, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- metrike
METRICS = [
    {'key': 'solo_kappa', 'name': 'Slaganje sa SOLO nivoom (Koenova kapa)', 'fmt': 'kappa',
     'higher': True, 'comparable': False,
     'expl': 'Drugi model, koji ne zna koji je nivo tražen, klasifikuje svako pitanje po SOLO '
             'nivou, pa se meri slaganje sa zadatim nivoom Koenovim koeficijentom. Vrednost '
             'preko 0,6 znači značajno slaganje. EduQG nema SOLO nivoe, pa za ekspertska pitanja '
             'ova mera ne postoji.'},
    {'key': 'ioc', 'name': 'Podudaranje sa ciljem (IOC)', 'fmt': 'kappa',
     'higher': True, 'comparable': False,
     'expl': 'Meri koliko pitanje zaista proverava baš onaj ishod učenja za koji je vezano. '
             'Raspon je od minus 1 do 1, gde se vrednosti oko 0,6 i više smatraju prihvatljivim. '
             'EduQG pitanja nemaju vezane ishode učenja, pa ova mera za njih ne postoji.'},
    {'key': 'stem_only', 'name': 'Rešivost iz teksta pitanja', 'fmt': 'pct',
     'higher': True, 'comparable': True,
     'expl': 'Model pokušava da odgovori na pitanje bez ponuđenih opcija, pa se odgovor poredi sa '
             'tačnim. Pravilo (Haladyna H4) kaže da tekst pitanja mora da nosi glavnu misao. '
             'Prikazuje se udeo pitanja koja se mogu rešiti samo iz teksta. Poredimo naša i '
             'ekspertska pitanja.'},
    {'key': 'cove_supported', 'name': 'Lanac provere (potvrđeni odgovori)', 'fmt': 'pct',
     'higher': True, 'comparable': True,
     'expl': 'Nezavisna verifikaciona pitanja proveravaju da li je tačan odgovor zaista '
             'potkrepljen materijalom. Prikazuje se udeo potvrđenih odgovora. Za ekspertska '
             'pitanja očekujemo visok udeo; ako je nizak, naš lanac provere je prestrog.'},
    {'key': 'solvability', 'name': 'Rešivost (prosečno p)', 'fmt': 'p',
     'higher': True, 'comparable': True,
     'expl': 'Tačan odgovor se sakrije, pa model više puta pokušava da reši pitanje. Koeficijent '
             'p govori koliko dobro pogađa. Za dobra pitanja očekujemo visoke vrednosti.'},
    {'key': 'face', 'name': 'Uverljivost distraktora', 'fmt': 'score5',
     'higher': True, 'comparable': True,
     'expl': 'Ocena uverljivosti, reprezentativnosti, odsustva odavanja i jasnoće distraktora, '
             'na skali od 1 do 5. Poredimo prosečnu ocenu naših i ekspertskih distraktora.'},
    {'key': 'ambiguity', 'name': 'Stopa dvosmislenosti', 'fmt': 'pct',
     'higher': False, 'comparable': True,
     'expl': 'Udeo pitanja koja model označi kao dvosmislena, odnosno koja se mogu protumačiti na '
             'više načina. Ako naš detektor često označi ekspertsko pitanje, on je prestrog.'},
    {'key': 'grammar_outlier', 'name': 'Gramatički trag (tačan odudara)', 'fmt': 'pct',
     'higher': False, 'comparable': True,
     'expl': 'Udeo pitanja kod kojih tačan odgovor gramatički odudara od distraktora, što studentu '
             'može da oda tačan odgovor. Niže je bolje.'},
    {'key': 'lint', 'name': 'Haladyna pravila (ocena)', 'fmt': 'score100',
     'higher': True, 'comparable': True,
     'expl': 'Programski mehanizam proverava poštovanje pravila za pisanje pitanja i daje ocenu od '
             '0 do 100. Viša ocena znači manje prekršenih pravila.'},
    {'key': 'readability', 'name': 'Čitljivost (FK razred)', 'fmt': 'grade',
     'higher': None, 'comparable': True,
     'expl': 'Procena školskog razreda potrebnog da se tekst pročita sa razumevanjem, po Flesch '
             'i Kincaid formulama. Niža vrednost znači lakši tekst.'},
]


# ---------------------------------------------------------------- moja pitanja
def _load_snapshot():
    path = os.path.join(_EVAL_DIR, 'my_lessons.json')
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh).get('lessons', [])
    except (OSError, json.JSONDecodeError):
        return []


def _live_lesson_metrics(conn, lid):
    """Sveže vrednosti metrika za lekciju iz validation_cache (može biti prazno)."""
    payloads = {}
    for row in conn.execute(
            "SELECT metric_key, payload FROM validation_cache "
            "WHERE scope_type='lesson' AND scope_id=?", (lid,)):
        try:
            payloads[row['metric_key']] = json.loads(row['payload'])
        except (json.JSONDecodeError, TypeError):
            pass
    m = {}
    if 'ambiguity' in payloads:
        m['ambiguity'] = payloads['ambiguity'].get('ambiguity_rate')
    if 'grammar_homogeneity' in payloads:
        gg = payloads['grammar_homogeneity']
        tot = gg.get('evaluated_questions') or 1
        m['grammar_outlier'] = round(100 * (gg.get('correct_outlier_count', 0)) / tot, 1)
    if 'face_validity' in payloads:
        m['face'] = payloads['face_validity'].get('mean_face_validity_score')
    if 'cove' in payloads:
        m['cove_supported'] = payloads['cove'].get('support_rate')
    if 'solvability' in payloads:
        m['solvability'] = payloads['solvability'].get('mean_p_value')
    if 'lint' in payloads:
        m['lint'] = payloads['lint'].get('average_score')
    if 'readability' in payloads:
        m['readability'] = payloads['readability'].get('mean_flesch_kincaid_grade')
    if 'solo_judge' in payloads:
        m['solo_kappa'] = payloads['solo_judge'].get('cohen_kappa')
    if 'ioc' in payloads:
        m['ioc'] = payloads['ioc'].get('ioc_index')
    if 'stem_only' in payloads:
        m['stem_only'] = payloads['stem_only'].get('h4_pass_rate')
    return m


def _my_lessons():
    """Vrednosti metrika po lekciji. Prednost ima sveži validation_cache; kada
    metrika nije sveže izračunata, koristi se stabilan snapshot iz
    my_lessons.json, pa stranica uvek prikazuje sve tri lekcije bez praznina."""
    snapshot = _load_snapshot()
    live = {}
    if os.path.exists(_DB):
        conn = sqlite3.connect(_DB)
        conn.row_factory = sqlite3.Row
        try:
            for L in snapshot:
                live[L['lesson_id']] = _live_lesson_metrics(conn, L['lesson_id'])
        finally:
            conn.close()
    out = []
    for L in snapshot:
        livem = live.get(L['lesson_id'], {})
        metrics = {}
        for key, snapval in (L.get('metrics') or {}).items():
            lv = livem.get(key)
            metrics[key] = lv if lv is not None else snapval
        out.append({'lesson_id': L['lesson_id'], 'name': L['name'], 'n': L['n'],
                    'computed': True, 'metrics': metrics})
    return out


# ---------------------------------------------------------------- ekspertski agregat
def _mean(vals):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


def _expert_agg(store):
    recs = list(store.values())
    n = len(recs)

    def rate(pred):
        xs = [pred(r) for r in recs if pred(r) is not None]
        return round(100 * sum(1 for v in xs if v) / len(xs), 1) if xs else None

    cove = [r for r in recs if r.get('cove_verdict')]
    return {
        'n': n,
        'ambiguity': rate(lambda r: r.get('ambiguous')),
        'grammar_outlier': rate(lambda r: r.get('grammar_outlier')),
        'face': _mean([r.get('face_score') for r in recs]),
        'cove_supported': (round(100 * sum(1 for r in cove if r['cove_verdict'] == 'SUPPORTED')
                                 / len(cove), 1) if cove else None),
        'solvability': _mean([r.get('p_value') for r in recs]),
        'lint': _mean([r.get('lint_score') for r in recs]),
        'readability': _mean([r.get('fk_grade') for r in recs]),
        'stem_only': rate(lambda r: r.get('stem_only_pass')),
    }


# ---------------------------------------------------------------- jedno pitanje
def _evaluate_one(q, trials=3):
    """Pokrene bateriju nad jednim EduQG pitanjem i vrati zapis u shemi store-a."""
    from services.quality.mcq_lint import lint_question
    from services.quality.readability import assess_question_readability
    from services.quality.ambiguity import assess_ambiguity
    from services.quality.grammar_homogeneity import check_homogeneity
    from services.quality.face_validity import assess_face_validity
    from services.quality.cove import verify_question
    from services.quality.solvability import assess_solvability, assess_stem_only_solvability

    lint = lint_question(q, use_embeddings=False)
    read = assess_question_readability(q)
    amb = assess_ambiguity(q)
    gram = check_homogeneity(q)
    face = assess_face_validity(q)
    cove = verify_question(q)
    solv = assess_solvability(q, n_trials=trials)
    stem = assess_stem_only_solvability(q)
    return {
        'eduqg_id': q['eduqg_id'], 'book': q['book'], 'bloom': q.get('bloom_name'),
        'lint_score': lint['score'],
        'lint_error': any(f.get('severity') == 'error' for f in lint['flags']),
        'lint_flags': [f['code'] for f in lint['flags']],
        'fk_grade': read['metrics'].get('flesch_kincaid_grade'),
        'ambiguous': amb.get('ambiguous'),
        'grammar_outlier': gram.get('correct_is_outlier'),
        'grammar_verdict': gram.get('verdict'),
        'face_score': face.get('face_validity_score') if face.get('available') else None,
        'cove_verdict': cove.get('verdict'),
        'p_value': solv.get('p_value') if solv.get('available') else None,
        'stem_only_pass': stem.get('h4_passes') if stem.get('available') else None,
        'stem_only_verdict': stem.get('verdict'),
    }


def _question_view(qid, q, store):
    rec = store.get(qid)
    return {
        'eduqg_id': qid,
        'book': q.get('book'),
        'bloom': q.get('bloom_name'),
        'question_text': q.get('question_text'),
        'options': q.get('options'),
        'correct_index': q.get('correct_option_index'),
        'grounding': q.get('source_line'),
        'context': q.get('context'),
        'evaluated': rec is not None,
        'result': {
            'lint': {'score': rec.get('lint_score'), 'error': rec.get('lint_error')},
            'ambiguity': {'ambiguous': rec.get('ambiguous')},
            'grammar': {'outlier': rec.get('grammar_outlier')},
            'face': {'score': rec.get('face_score')},
            'cove': {'verdict': rec.get('cove_verdict')},
            'solvability': {'p_value': rec.get('p_value')},
            'readability': {'fk_grade': rec.get('fk_grade')},
            'stem_only': {'pass': rec.get('stem_only_pass'), 'verdict': rec.get('stem_only_verdict')},
        } if rec else None,
    }


# ================================================================ rute
@eduqg_bp.route('/eduqg/overview', methods=['GET'])
def eduqg_overview():
    try:
        ds = _dataset()
    except Exception as e:
        return jsonify({'available': False,
                        'reason': f'EduQG skup nije pronađen ({e}). Postavi ga u '
                                  'question-generation-main/.'}), 200
    store = _load_store()
    expert = _expert_agg(store)
    my = _my_lessons()

    # oblasti (knjige) sa brojem pitanja i koliko je evaluirano
    from collections import Counter
    totals = Counter(q['book'] for q in ds.values())
    evaluated_books = Counter(store[qid]['book'] for qid in store if qid in ds)
    books = [{'book': b, 'total': totals[b], 'evaluated': evaluated_books.get(b, 0)}
             for b in sorted(totals)]

    metrics = []
    for spec in METRICS:
        key = spec['key']
        metrics.append({
            **{k: spec[k] for k in ('key', 'name', 'fmt', 'higher', 'comparable', 'expl')},
            'expert': expert.get(key) if spec['comparable'] else None,
            'my': [{'name': L['name'], 'value': L['metrics'].get(key), 'computed': L['computed']}
                   for L in my],
        })

    return jsonify({
        'available': True,
        'expert_n': expert['n'],
        'dataset_total': len(ds),
        'metrics': metrics,
        'my_lessons': my,
        'books': books,
    }), 200


@eduqg_bp.route('/eduqg/questions', methods=['GET'])
def eduqg_questions():
    book = request.args.get('book')
    offset = int(request.args.get('offset', 0))
    limit = min(int(request.args.get('limit', 25)), 100)
    only_evaluated = request.args.get('evaluated') == '1'
    ds = _dataset()
    store = _load_store()
    ids = [qid for qid, q in ds.items() if (not book or q['book'] == book)]
    ids.sort()
    if only_evaluated:
        ids = [qid for qid in ids if qid in store]
    total = len(ids)
    page = ids[offset:offset + limit]
    return jsonify({
        'book': book, 'total': total, 'offset': offset, 'limit': limit,
        'questions': [_question_view(qid, ds[qid], store) for qid in page],
    }), 200


@eduqg_bp.route('/eduqg/evaluate', methods=['POST'])
def eduqg_evaluate():
    data = request.get_json(silent=True) or {}
    qid = data.get('eduqg_id')
    ds = _dataset()
    if qid not in ds:
        return jsonify({'error': 'Nepoznato pitanje.'}), 404
    # Evaluaciju radimo na Anthropic modelu, isto kao postojeći referentni skup.
    g.llm_provider = 'anthropic'
    rec = _evaluate_one(ds[qid])
    store = _load_store()
    store[qid] = rec
    _save_store(store)
    return jsonify({
        'question': _question_view(qid, ds[qid], store),
        'expert': _expert_agg(store),
    }), 200
