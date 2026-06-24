# -*- coding: utf-8 -*-
"""Preračunava CoVe za sve sačuvana ekspertska EduQG pitanja sa novim širim
kontekstom (verify_question čita source_line + context), pa ažurira store.
Ostale metrike se ne diraju. Pokreni: venv/Scripts/python.exe -m eval.recove_expert
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from core.llm_provider import set_thread_provider  # noqa: E402
from eval.eduqg import load_eduqg  # noqa: E402
from services.quality.cove import verify_question  # noqa: E402

STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'eduqg_calibration.json')


def supported_rate(recs):
    avail = [r for r in recs if r.get('cove_verdict')]
    if not avail:
        return None
    return round(100 * sum(1 for r in avail if r['cove_verdict'] == 'SUPPORTED') / len(avail), 1)


def main():
    set_thread_provider('anthropic')
    ds = {q['eduqg_id']: q for q in load_eduqg()}
    with open(STORE, encoding='utf-8') as fh:
        recs = json.load(fh)
    print(f'Pre: CoVe potvrđeno = {supported_rate(recs)}%  (n={len(recs)})')

    for i, r in enumerate(recs, start=1):
        q = ds.get(r['eduqg_id'])
        if not q:
            continue
        v = verify_question(q).get('verdict')  # q ima source_line + context (širi)
        r['cove_verdict'] = v
        if i % 10 == 0 or i == len(recs):
            print(f'  [{i}/{len(recs)}]', flush=True)

    with open(STORE, 'w', encoding='utf-8') as fh:
        json.dump(recs, fh, ensure_ascii=False, indent=1)
    print(f'Posle: CoVe potvrđeno = {supported_rate(recs)}%  (n={len(recs)})')
    print('Store ažuriran.')


if __name__ == '__main__':
    main()
