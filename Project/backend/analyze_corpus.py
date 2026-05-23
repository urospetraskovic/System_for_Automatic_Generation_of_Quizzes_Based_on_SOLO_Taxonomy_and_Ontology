"""
One-shot corpus quality analysis.

Loads every question from the DB, runs the validation services against them
(LLM responses are read from the SQLite cache when present — no live Ollama
calls are needed if the user has already executed the Quality Overview),
then summarises:

  * per-lesson failure rates,
  * per-SOLO-level failure rates,
  * per-LO failure clusters,
  * the top-N worst questions by combined-flag count.

Run with:
    backend/venv/Scripts/python.exe backend/analyze_corpus.py

Optional flags:
    --limit N           only analyse the first N questions (sanity testing)
    --top N             show top-N worst questions (default 15)
    --offline           don't make any new LLM calls; treat cache misses as
                        "unavailable" (default: True — we rely on the cache)

The script writes a JSON report to backend/corpus_analysis.json so the
findings can be re-loaded for tooling later.
"""

import argparse
import io
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict

# Make sure backend/ is on sys.path so service imports work.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from core import llm_cache  # noqa: E402
from services.ambiguity import (  # noqa: E402
    AMBIGUITY_MODEL, AMBIGUITY_TEMPERATURE,
    assess_ambiguity, build_ambiguity_prompt,
)
from services.grammar_homogeneity import (  # noqa: E402
    GRAMMAR_MODEL, GRAMMAR_TEMPERATURE,
    check_homogeneity, build_grammar_prompt,
)
from services.ioc import (  # noqa: E402
    IOC_MODEL, IOC_TEMPERATURE,
    rate_question as ioc_rate_question, build_ioc_prompt, _resolve_objective,
)
from services.cove import (  # noqa: E402
    COVE_MODEL, COVE_TEMPERATURE,
    verify_question, build_plan_prompt,
)
from services.mcq_lint import lint_question  # noqa: E402


def _cache_only_llm(model, temperature):
    """Return an llm_caller that only reads from llm_cache. Cache misses → None."""
    def call(prompt: str):
        return llm_cache.get(model, prompt, temperature, json_mode=True)
    return call


def load_questions(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    rows = cur.execute('''
        SELECT q.id, q.solo_level, q.question_text, q.options, q.correct_answer,
               q.correct_option_index, q.source_line, q.primary_lesson_id,
               q.secondary_lesson_id, q.section_id, q.learning_object_id,
               l.title AS lesson_title
        FROM questions q
        LEFT JOIN lessons l ON q.primary_lesson_id = l.id
        ORDER BY q.id
    ''').fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d['options'] = json.loads(d['options']) if d['options'] else []
        except json.JSONDecodeError:
            d['options'] = []
        out.append(d)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--top', type=int, default=15)
    ap.add_argument('--out', default='backend/corpus_analysis.json')
    args = ap.parse_args()

    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'quiz_database.db')
    questions = load_questions(db_path)
    if args.limit:
        questions = questions[: args.limit]

    print(f'[analysis] Loaded {len(questions)} questions.')

    # Cache-only LLM callers for the four LLM-judge services.
    ambig_call = _cache_only_llm(AMBIGUITY_MODEL, AMBIGUITY_TEMPERATURE)
    grammar_call = _cache_only_llm(GRAMMAR_MODEL, GRAMMAR_TEMPERATURE)
    ioc_call = _cache_only_llm(IOC_MODEL, IOC_TEMPERATURE)
    cove_call = _cache_only_llm(COVE_MODEL, COVE_TEMPERATURE)

    per_q = []
    cache_hits = Counter()
    cache_misses = Counter()

    for i, q in enumerate(questions, start=1):
        if i % 25 == 0 or i == len(questions):
            print(f'[analysis] Processing {i}/{len(questions)}…', flush=True)

        record = {
            'id': q['id'],
            'solo_level': q['solo_level'],
            'lesson_id': q['primary_lesson_id'],
            'lesson_title': q['lesson_title'],
            'learning_object_id': q['learning_object_id'],
            'question_text': q['question_text'],
            'correct_answer': q['correct_answer'],
            'flags': [],
        }

        # 1) Lint (pure-Python, deterministic, always available).
        lint = lint_question(q, use_embeddings=False)
        record['lint_score'] = lint['score']
        record['lint_flags'] = [f['code'] for f in lint['flags']]
        record['has_length_clue'] = 'H27_CORRECT_LONGEST' in record['lint_flags']

        # 2) Ambiguity — cache lookup.
        amb_prompt = build_ambiguity_prompt(q['question_text'] or '', q['options'] or [])
        amb_raw = ambig_call(amb_prompt)
        if amb_raw is not None:
            cache_hits['ambiguity'] += 1
            amb_result = assess_ambiguity(q, llm_caller=lambda p: amb_raw)
            record['ambiguous'] = amb_result.get('ambiguous')
            record['ambiguity_type'] = amb_result.get('ambiguity_type')
            if amb_result.get('ambiguous'):
                record['flags'].append('AMBIGUOUS')
        else:
            cache_misses['ambiguity'] += 1
            record['ambiguous'] = None

        # 3) Grammatical homogeneity — cache lookup.
        if q['options']:
            gram_prompt = build_grammar_prompt(q['options'])
            gram_raw = grammar_call(gram_prompt)
            if gram_raw is not None:
                cache_hits['grammar'] += 1
                gram_result = check_homogeneity(q, llm_caller=lambda p: gram_raw)
                record['grammar_verdict'] = gram_result.get('verdict')
                record['correct_is_outlier'] = gram_result.get('correct_is_outlier')
                if gram_result.get('correct_is_outlier'):
                    record['flags'].append('GRAMMAR_CLUE')
                elif gram_result.get('verdict') == 'mixed':
                    record['flags'].append('GRAMMAR_MIXED')
            else:
                cache_misses['grammar'] += 1
                record['grammar_verdict'] = None

        # 4) IOC — cache lookup. Need the objective to build the prompt.
        objective = _resolve_objective(q)
        if objective is not None:
            ioc_prompt = build_ioc_prompt(
                q['question_text'] or '',
                q['options'] or [],
                q['correct_answer'],
                objective['title'],
                objective['content'],
            )
            ioc_raw = ioc_call(ioc_prompt)
            if ioc_raw is not None:
                cache_hits['ioc'] += 1
                ioc_result = ioc_rate_question(q, objective=objective, llm_caller=lambda p: ioc_raw)
                record['ioc_rating'] = ioc_result.get('rating')
                if ioc_result.get('rating') is not None and ioc_result['rating'] <= 0:
                    record['flags'].append(f"IOC_{ioc_result['rating']}")
            else:
                cache_misses['ioc'] += 1
                record['ioc_rating'] = None

        # 5) CoVe — multi-step, only check whether the FIRST step is cached
        #    (plan prompt). If yes, run the full pipeline (subsequent steps
        #    may or may not be cached; the function tolerates None responses).
        cove_plan_prompt = build_plan_prompt(q['question_text'] or '', q['correct_answer'] or '')
        cove_plan_raw = cove_call(cove_plan_prompt)
        if cove_plan_raw is not None:
            cache_hits['cove'] += 1
            cove_result = verify_question(q, llm_caller=cove_call)
            record['cove_verdict'] = cove_result.get('verdict')
            if cove_result.get('verdict') in ('UNDERDETERMINED', 'CONTRADICTED'):
                record['flags'].append(f"COVE_{cove_result['verdict']}")
        else:
            cache_misses['cove'] += 1
            record['cove_verdict'] = None

        record['flag_count'] = len(record['flags']) + (1 if record['has_length_clue'] else 0)
        per_q.append(record)

    print()
    print(f"[analysis] Cache coverage: {dict(cache_hits)}")
    print(f"[analysis] Cache misses:   {dict(cache_misses)}")
    print()

    # --- Aggregate analysis ---
    print('=' * 70)
    print('PATTERN ANALYSIS')
    print('=' * 70)

    # Per lesson
    by_lesson = defaultdict(lambda: {'total': 0, 'AMBIGUOUS': 0, 'GRAMMAR_CLUE': 0,
                                     'COVE_BAD': 0, 'IOC_NEG': 0, 'IOC_ZERO': 0,
                                     'LENGTH_CLUE': 0})
    for r in per_q:
        L = by_lesson[r['lesson_title'] or f"Lesson {r['lesson_id']}"]
        L['total'] += 1
        if 'AMBIGUOUS' in r['flags']: L['AMBIGUOUS'] += 1
        if 'GRAMMAR_CLUE' in r['flags']: L['GRAMMAR_CLUE'] += 1
        if any(f.startswith('COVE_') for f in r['flags']): L['COVE_BAD'] += 1
        if 'IOC_-1' in r['flags']: L['IOC_NEG'] += 1
        if 'IOC_0' in r['flags']: L['IOC_ZERO'] += 1
        if r['has_length_clue']: L['LENGTH_CLUE'] += 1

    print('Per LESSON (%):')
    print(f'  {"Lesson":<35} {"N":>4} {"Amb":>5} {"GClu":>5} {"CoVe-":>6} {"IOC≤0":>6} {"LenC":>5}')
    for name, s in by_lesson.items():
        n = s['total'] or 1
        print(f"  {name[:34]:<35} {s['total']:>4} "
              f"{100*s['AMBIGUOUS']/n:>5.1f} "
              f"{100*s['GRAMMAR_CLUE']/n:>5.1f} "
              f"{100*s['COVE_BAD']/n:>6.1f} "
              f"{100*(s['IOC_NEG']+s['IOC_ZERO'])/n:>6.1f} "
              f"{100*s['LENGTH_CLUE']/n:>5.1f}")

    # Per SOLO
    by_solo = defaultdict(lambda: {'total': 0, 'AMBIGUOUS': 0, 'GRAMMAR_CLUE': 0,
                                   'COVE_BAD': 0, 'IOC_NEG': 0, 'IOC_ZERO': 0,
                                   'LENGTH_CLUE': 0})
    for r in per_q:
        S = by_solo[r['solo_level']]
        S['total'] += 1
        if 'AMBIGUOUS' in r['flags']: S['AMBIGUOUS'] += 1
        if 'GRAMMAR_CLUE' in r['flags']: S['GRAMMAR_CLUE'] += 1
        if any(f.startswith('COVE_') for f in r['flags']): S['COVE_BAD'] += 1
        if 'IOC_-1' in r['flags']: S['IOC_NEG'] += 1
        if 'IOC_0' in r['flags']: S['IOC_ZERO'] += 1
        if r['has_length_clue']: S['LENGTH_CLUE'] += 1

    print()
    print('Per SOLO LEVEL (%):')
    print(f'  {"Level":<20} {"N":>4} {"Amb":>5} {"GClu":>5} {"CoVe-":>6} {"IOC≤0":>6} {"LenC":>5}')
    for name, s in by_solo.items():
        n = s['total'] or 1
        print(f"  {name[:19]:<20} {s['total']:>4} "
              f"{100*s['AMBIGUOUS']/n:>5.1f} "
              f"{100*s['GRAMMAR_CLUE']/n:>5.1f} "
              f"{100*s['COVE_BAD']/n:>6.1f} "
              f"{100*(s['IOC_NEG']+s['IOC_ZERO'])/n:>6.1f} "
              f"{100*s['LENGTH_CLUE']/n:>5.1f}")

    # LO clusters — which LOs produce the most flagged questions?
    by_lo = defaultdict(lambda: {'total': 0, 'flagged': 0, 'sample_text': ''})
    for r in per_q:
        lo_id = r['learning_object_id']
        if lo_id is None:
            continue
        L = by_lo[lo_id]
        L['total'] += 1
        if r['flag_count'] > 0:
            L['flagged'] += 1
            if not L['sample_text']:
                L['sample_text'] = (r['question_text'] or '')[:80]

    bad_los = sorted(by_lo.items(), key=lambda kv: -kv[1]['flagged'])[:10]
    print()
    print(f'Top 10 LOs with most flagged questions:')
    for lo_id, s in bad_los:
        if s['flagged'] == 0:
            break
        print(f"  LO #{lo_id}: {s['flagged']}/{s['total']} flagged — sample: {s['sample_text']}")

    # Most frequent ambiguity types
    amb_types = Counter(r.get('ambiguity_type') for r in per_q if r.get('ambiguous'))
    print()
    print('Ambiguity types:')
    for t, n in amb_types.most_common():
        print(f"  {t}: {n}")

    # Top N worst questions
    worst = sorted(per_q, key=lambda r: -r['flag_count'])[:args.top]
    print()
    print(f'TOP {args.top} WORST QUESTIONS (by flag count):')
    for r in worst:
        if r['flag_count'] == 0:
            break
        print(f"  Q#{r['id']} ({r['solo_level']}, LO #{r['learning_object_id']}, {r['lesson_title']})")
        print(f"    flags: {r['flags']} + length_clue={r['has_length_clue']}")
        print(f"    text: {(r['question_text'] or '')[:120]}")
        print()

    # Write JSON report
    report = {
        'total_questions': len(per_q),
        'cache_hits': dict(cache_hits),
        'cache_misses': dict(cache_misses),
        'per_lesson': {k: v for k, v in by_lesson.items()},
        'per_solo': {k: v for k, v in by_solo.items()},
        'worst_questions': worst,
        'ambiguity_types': dict(amb_types),
        'top_problematic_los': [
            {'lo_id': lo_id, 'flagged': s['flagged'], 'total': s['total'], 'sample': s['sample_text']}
            for lo_id, s in bad_los if s['flagged'] > 0
        ],
        'all_questions': per_q,
    }
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f'[analysis] Wrote JSON report → {args.out}')


if __name__ == '__main__':
    main()
