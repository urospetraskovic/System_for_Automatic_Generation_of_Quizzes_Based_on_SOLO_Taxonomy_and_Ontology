"""Probe: is CoVe's 42% flag-rate on EduQG experts a context-starvation artifact?

M1 found CoVe flags 42% of expert questions as not-SUPPORTED, almost all
UNDERDETERMINED (not CONTRADICTED). We fed it only `hl_sentences` (the minimal
grounding, ~100-400 chars). Hypothesis: given the richer `hl_context`, the
verifier finds enough evidence and the false-positive rate drops.

This re-runs CoVe on the same pilot with source_line = hl_context and compares.

Run (from backend/):
    venv/Scripts/python.exe -m eval.cove_context_probe
"""

import io
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from eval.eduqg import load_eduqg, sample_pilot  # noqa: E402
from core.llm_provider import set_thread_provider  # noqa: E402
from services.cove import verify_question  # noqa: E402


def _rate(verdicts):
    n = sum(1 for v in verdicts if v is not None)
    bad = sum(1 for v in verdicts if v not in (None, 'SUPPORTED'))
    return bad, n, Counter(verdicts)


def main():
    set_thread_provider('anthropic')
    pilot = sample_pilot(load_eduqg(), n=150)
    print(f'CoVe context probe on {len(pilot)} expert questions '
          f'(source = full hl_context)\n')

    verdicts = []
    for i, q in enumerate(pilot, start=1):
        if i % 10 == 0 or i == len(pilot):
            print(f'  [{i}/{len(pilot)}]', flush=True)
        rich = dict(q)
        rich['source_line'] = q['context']  # the wider passage instead of hl_sentences
        verdicts.append(verify_question(rich).get('verdict'))

    bad, n, dist = _rate(verdicts)
    print('\n' + '=' * 56)
    print(f'CoVe not-SUPPORTED with RICH context: {100*bad/n:.1f}%  (n={n})')
    print(f'  vs M1 (minimal grounding):          42.3%')
    print(f'  verdict distribution: {dict(dist)}')
    print('=' * 56)


if __name__ == '__main__':
    main()
