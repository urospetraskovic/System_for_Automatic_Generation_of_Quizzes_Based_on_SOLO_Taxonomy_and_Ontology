"""M1 - Validator calibration on EduQG expert questions.

We treat EduQG's expert-written MCQs as a gold standard of "good" questions and
ask: does our validator battery PASS them? A well-calibrated quality framework
should rarely flag an expert question as defective.

  * SPECIFICITY view: flag-rate of each validator on the untouched expert
    questions. Low is good (few false positives on known-good items).
  * SENSITIVITY view: we then corrupt each question with a wrong answer key
    (point the "correct" index at a distractor) and re-run the two validators
    that should react to it - CoVe (answer no longer supported by the source)
    and solvability (the blind solver still picks the true answer, which now
    mismatches the key). Flag-rate here should JUMP. A validator that passes
    both the clean and the corrupted version is not actually discriminating.

Run (from backend/):
    venv/Scripts/python.exe -m eval.run_calibration --limit 149 --trials 3

Results are cached by the underlying LLM layer, so re-runs are cheap and
incremental. Use --no-solvability / --no-cove to skip the expensive judges.
"""

import argparse
import io
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from eval.eduqg import load_eduqg, sample_pilot  # noqa: E402
from core.llm_provider import set_thread_provider  # noqa: E402
from services.mcq_lint import lint_question  # noqa: E402
from services.ambiguity import assess_ambiguity  # noqa: E402
from services.grammar_homogeneity import check_homogeneity  # noqa: E402
from services.cove import verify_question  # noqa: E402
from services.face_validity import assess_face_validity  # noqa: E402
from services.solvability import assess_solvability  # noqa: E402
from services.readability import assess_question_readability  # noqa: E402

SEVERITY_ERROR = 'error'


def _corrupt_wrong_key(q):
    """Return a copy whose correct index points at the first distractor.

    The source_line still grounds the TRUE answer, so CoVe should flip to
    not-SUPPORTED and the blind solver should now disagree with the key.
    """
    bad_idx = next(i for i in range(len(q['options'])) if i != q['correct_option_index'])
    c = dict(q)
    c['correct_option_index'] = bad_idx
    c['correct_answer'] = q['options'][bad_idx]
    return c


def run(pilot, *, trials, do_solvability, do_cove):
    rows = []
    n = len(pilot)
    for i, q in enumerate(pilot, start=1):
        if i % 10 == 0 or i == n:
            print(f'  [{i}/{n}] processed', flush=True)

        rec = {'eduqg_id': q['eduqg_id'], 'book': q['book'], 'bloom': q['bloom_name']}

        # --- free / deterministic ---
        lint = lint_question(q, use_embeddings=False)
        rec['lint_score'] = lint['score']
        rec['lint_error'] = any(f.get('severity') == SEVERITY_ERROR for f in lint['flags'])
        rec['lint_flags'] = [f['code'] for f in lint['flags']]

        read = assess_question_readability(q)
        rec['fk_grade'] = read['metrics'].get('flesch_kincaid_grade')

        # --- LLM judges (live, cached) ---
        amb = assess_ambiguity(q)
        rec['ambiguous'] = amb.get('ambiguous')

        gram = check_homogeneity(q)
        rec['grammar_outlier'] = gram.get('correct_is_outlier')
        rec['grammar_verdict'] = gram.get('verdict')

        face = assess_face_validity(q)
        rec['face_score'] = face.get('face_validity_score') if face.get('available') else None

        if do_cove:
            cove = verify_question(q)
            rec['cove_verdict'] = cove.get('verdict')
            cove_c = verify_question(_corrupt_wrong_key(q))
            rec['cove_verdict_corrupt'] = cove_c.get('verdict')

        if do_solvability:
            solv = assess_solvability(q, n_trials=trials)
            rec['p_value'] = solv.get('p_value') if solv.get('available') else None
            solv_c = assess_solvability(_corrupt_wrong_key(q), n_trials=trials)
            rec['p_value_corrupt'] = solv_c.get('p_value') if solv_c.get('available') else None

        rows.append(rec)
    return rows


def _pct(num, den):
    return f'{100 * num / den:5.1f}%' if den else '  n/a'


def summarise(rows, *, do_solvability, do_cove):
    n = len(rows)
    print('\n' + '=' * 64)
    print(f'SPECIFICITY  -  validator flag-rate on {n} EXPERT questions')
    print('(low = good: we rarely flag a known-good question)')
    print('=' * 64)

    lint_err = sum(1 for r in rows if r['lint_error'])
    print(f'  lint (any ERROR flag)        {_pct(lint_err, n)}')
    amb = sum(1 for r in rows if r['ambiguous'])
    print(f'  ambiguity (ambiguous)        {_pct(amb, n)}')
    gram = sum(1 for r in rows if r['grammar_outlier'])
    print(f'  grammar (correct is outlier) {_pct(gram, n)}')

    faces = [r['face_score'] for r in rows if r.get('face_score') is not None]
    if faces:
        low = sum(1 for f in faces if f < 2.5)
        print(f'  face validity  mean={sum(faces)/len(faces):.2f}  '
              f'(<2.5: {_pct(low, len(faces))}, n={len(faces)})')

    grades = [r['fk_grade'] for r in rows if r.get('fk_grade') is not None]
    if grades:
        print(f'  readability    mean FK grade={sum(grades)/len(grades):.1f}')

    if do_cove:
        cove_bad = sum(1 for r in rows if r.get('cove_verdict') not in (None, 'SUPPORTED'))
        cove_avail = sum(1 for r in rows if r.get('cove_verdict') is not None)
        print(f'  CoVe (not SUPPORTED)         {_pct(cove_bad, cove_avail)}  '
              f'(n={cove_avail})')
    if do_solvability:
        pv = [r['p_value'] for r in rows if r.get('p_value') is not None]
        if pv:
            unsolv = sum(1 for p in pv if p < 0.5)
            print(f'  solvability    mean p={sum(pv)/len(pv):.2f}  '
                  f'(p<0.5: {_pct(unsolv, len(pv))}, n={len(pv)})')

    if do_cove or do_solvability:
        print('\n' + '=' * 64)
        print('SENSITIVITY  -  flag-rate after WRONG-KEY corruption')
        print('(high = good: we catch a deliberately broken question)')
        print('=' * 64)
        if do_cove:
            bad = sum(1 for r in rows if r.get('cove_verdict_corrupt') not in (None, 'SUPPORTED'))
            avail = sum(1 for r in rows if r.get('cove_verdict_corrupt') is not None)
            print(f'  CoVe (not SUPPORTED)         {_pct(bad, avail)}  (n={avail})')
        if do_solvability:
            pvc = [r['p_value_corrupt'] for r in rows if r.get('p_value_corrupt') is not None]
            if pvc:
                caught = sum(1 for p in pvc if p < 0.5)
                print(f'  solvability    mean p={sum(pvc)/len(pvc):.2f}  '
                      f'(p<0.5: {_pct(caught, len(pvc))}, n={len(pvc)})')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=150, help='pilot sample size')
    ap.add_argument('--limit', type=int, default=None, help='cap questions processed')
    ap.add_argument('--trials', type=int, default=3, help='solvability trials per question')
    ap.add_argument('--no-solvability', action='store_true')
    ap.add_argument('--no-cove', action='store_true')
    ap.add_argument('--provider', default='anthropic', choices=['anthropic', 'ollama'],
                    help='LLM provider for the judges (default anthropic / Haiku 4.5)')
    ap.add_argument('--out', default=os.path.join(os.path.dirname(__file__),
                                                  'eduqg_calibration.json'))
    args = ap.parse_args()

    set_thread_provider(args.provider)

    pilot = sample_pilot(load_eduqg(), n=args.n)
    if args.limit:
        pilot = pilot[:args.limit]
    print(f'Calibration pilot: {len(pilot)} questions, provider={args.provider}, '
          f'trials={args.trials}, cove={not args.no_cove}, '
          f'solvability={not args.no_solvability}')

    rows = run(pilot, trials=args.trials,
               do_solvability=not args.no_solvability, do_cove=not args.no_cove)
    summarise(rows, do_solvability=not args.no_solvability, do_cove=not args.no_cove)

    with open(args.out, 'w', encoding='utf-8') as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)
    print(f'\nWrote per-question records to {args.out}')


if __name__ == '__main__':
    main()
