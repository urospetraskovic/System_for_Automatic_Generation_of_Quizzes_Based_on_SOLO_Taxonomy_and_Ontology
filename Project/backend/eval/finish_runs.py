# -*- coding: utf-8 -*-
"""Dovršava dva posla server-side (bez HTTP timeouta), redom:
  1. Solvability za lekciju Procesi (popuni cache, resume iz per-pitanje keša).
  2. Preračun CoVe za sva ekspertska EduQG pitanja sa novim širim kontekstom.
Pokreni: venv/Scripts/python.exe -m eval.finish_runs
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import app as _app_module  # noqa: E402,F401  (inicijalizuje bazu i servise)
from core.llm_provider import set_thread_provider  # noqa: E402
from repository import db  # noqa: E402
from services.quality.solvability import solvability_report  # noqa: E402
from services.quality.cove import verify_question  # noqa: E402
from services import validation_cache  # noqa: E402
from eval.eduqg import load_eduqg  # noqa: E402

STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'eduqg_calibration.json')
LESSON_PROCESI = 1


def run_solvability():
    print('=== 1) Solvability za Procesi (lekcija 1) ===', flush=True)
    qs = db.get_questions_by_lesson(LESSON_PROCESI)
    print(f'  {len(qs)} pitanja, n_trials=5', flush=True)
    payload = solvability_report(qs, n_trials=5, use_question_cache=True)
    validation_cache.put('solvability', LESSON_PROCESI, payload)
    print(f'  Gotovo. mean p = {payload.get("mean_p_value")}, '
          f'rešivih = {payload.get("solvable_questions")}/{payload.get("total_questions")}',
          flush=True)


def _supported_rate(recs):
    avail = [r for r in recs if r.get('cove_verdict')]
    if not avail:
        return None
    return round(100 * sum(1 for r in avail if r['cove_verdict'] == 'SUPPORTED') / len(avail), 1)


def run_recove():
    print('\n=== 2) Preračun CoVe za ekspertska pitanja (širi kontekst) ===', flush=True)
    ds = {q['eduqg_id']: q for q in load_eduqg()}
    with open(STORE, encoding='utf-8') as fh:
        recs = json.load(fh)
    print(f'  Pre: CoVe potvrđeno = {_supported_rate(recs)}%  (n={len(recs)})', flush=True)
    for i, r in enumerate(recs, start=1):
        q = ds.get(r['eduqg_id'])
        if q:
            r['cove_verdict'] = verify_question(q).get('verdict')
        if i % 15 == 0 or i == len(recs):
            print(f'  [{i}/{len(recs)}]', flush=True)
    with open(STORE, 'w', encoding='utf-8') as fh:
        json.dump(recs, fh, ensure_ascii=False, indent=1)
    print(f'  Posle: CoVe potvrđeno = {_supported_rate(recs)}%', flush=True)


def main():
    set_thread_provider('anthropic')
    run_solvability()
    run_recove()
    print('\nSve gotovo.')


if __name__ == '__main__':
    main()
