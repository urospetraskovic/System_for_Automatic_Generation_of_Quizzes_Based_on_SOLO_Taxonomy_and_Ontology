"""M2 - Distractor generation benchmark against EduQG gold distractors.

EduQG defines a Distractor Generation (DG) task: given the source passage, the
question, and the correct answer, produce plausible wrong options. The paper's
T5 baseline reaches ~17.73 BLEU. We generate distractors LLM-directly (the DG
task as stated) and compare ours to the 3 expert gold distractors on:

  * face validity  - our face_validity rubric (LLM judge) scores OUR distractor
    set and the GOLD set side by side. Do ours match expert quality?
  * lexical recovery - how often do we reproduce an expert distractor
    (exact, and fuzzy token-Jaccard >= 0.5)?
  * embedding similarity - mean cosine of each gold distractor to its best
    match among ours (skipped automatically if the embedder is unavailable).

Run (from backend/):
    venv/Scripts/python.exe -m eval.run_distractors --n 150 --limit 149
"""

import argparse
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from eval.eduqg import load_eduqg, sample_pilot  # noqa: E402
from core.llm_provider import set_thread_provider, call_llm  # noqa: E402
from services.face_validity import assess_face_validity  # noqa: E402
from services.embedding_service import embed_text, cosine_similarity  # noqa: E402


def build_distractor_prompt(context, question, correct):
    return f"""You are an assessment expert writing distractors (wrong options) for a multiple-choice question. Using ONLY the SOURCE passage and your domain knowledge, write exactly THREE distractors for the question below.

Rules:
- Each distractor must be clearly WRONG but plausible to a student who has not mastered the material.
- Same category and grammatical form as the CORRECT answer (if it is a noun phrase, they are noun phrases; if a number, numbers).
- Mutually distinct; none may be a paraphrase of the correct answer.
- Concise - match the length and style of the correct answer.

SOURCE:
{context}

QUESTION: {question}
CORRECT ANSWER: {correct}

OUTPUT - strict JSON, no other text:
{{"distractors": ["<d1>", "<d2>", "<d3>"]}}"""


def generate_distractors(context, question, correct):
    raw = call_llm(build_distractor_prompt(context, question, correct),
                   role="generator", temperature=0.7, json_mode=True)
    if not raw:
        return []
    m = re.search(r'\{[\s\S]*\}', raw)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    ds = data.get('distractors') or []
    return [str(d).strip() for d in ds if str(d).strip()][:3]


# -------- lexical helpers --------
def _stem(w):
    """Crude suffix stripper so 'decomposer'/'decomposers' match."""
    for suf in ('ies', 'es', 's', 'ing', 'ed'):
        if len(w) > len(suf) + 2 and w.endswith(suf):
            return w[:-len(suf)]
    return w


def _norm(s):
    return [_stem(w) for w in re.sub(r'[^a-z0-9 ]', '', s.lower()).split()]


def _jaccard(a, b):
    sa, sb = set(_norm(a)), set(_norm(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _best_match(target, candidates):
    return max((_jaccard(target, c) for c in candidates), default=0.0)


def _face_score(question_text, correct, distractors):
    """Run our face-validity rubric over an option set (correct first)."""
    q = {
        'question_text': question_text,
        'options': [correct] + list(distractors),
        'correct_option_index': 0,
    }
    r = assess_face_validity(q)
    return r.get('face_validity_score') if r.get('available') else None


def run(pilot, *, do_embed):
    rows = []
    n = len(pilot)
    for i, q in enumerate(pilot, start=1):
        if i % 10 == 0 or i == n:
            print(f'  [{i}/{n}]', flush=True)
        ours = generate_distractors(q['context'], q['question_text'], q['correct_answer'])
        gold = q['distractors']

        rec = {
            'eduqg_id': q['eduqg_id'], 'book': q['book'],
            'ours': ours, 'gold': gold, 'n_ours': len(ours),
        }
        # lexical recovery: per gold distractor, best fuzzy match among ours
        rec['gold_exact_recovered'] = sum(
            1 for g in gold if any(_norm(g) == _norm(o) for o in ours))
        rec['gold_fuzzy_recovered'] = sum(
            1 for g in gold if _best_match(g, ours) >= 0.5)
        # quality: face validity ours vs gold
        if ours:
            rec['face_ours'] = _face_score(q['question_text'], q['correct_answer'], ours)
        rec['face_gold'] = _face_score(q['question_text'], q['correct_answer'], gold)
        # optional embedding similarity (gold -> best of ours)
        if do_embed and ours:
            sims = []
            for g in gold:
                gv = embed_text(g)
                if gv is None:
                    sims = None
                    break
                best = max((cosine_similarity(gv, embed_text(o)) or 0.0) for o in ours)
                sims.append(best)
            rec['embed_gold_to_ours'] = (sum(sims) / len(sims)) if sims else None
        rows.append(rec)
    return rows


def summarise(rows):
    n = len(rows)
    with_ours = [r for r in rows if r['n_ours'] == 3]
    print('\n' + '=' * 60)
    print(f'DISTRACTOR BENCHMARK  -  {n} questions '
          f'({len(with_ours)} with a full set of 3 generated)')
    print('=' * 60)

    tot_gold = sum(len(r['gold']) for r in rows)
    exact = sum(r['gold_exact_recovered'] for r in rows)
    fuzzy = sum(r['gold_fuzzy_recovered'] for r in rows)
    print(f'  gold distractors recovered (exact):  {exact}/{tot_gold} '
          f'({100*exact/tot_gold:.1f}%)')
    print(f'  gold distractors recovered (fuzzy):  {fuzzy}/{tot_gold} '
          f'({100*fuzzy/tot_gold:.1f}%)')

    fo = [r['face_ours'] for r in rows if r.get('face_ours') is not None]
    fg = [r['face_gold'] for r in rows if r.get('face_gold') is not None]
    if fo:
        print(f'  face validity  OURS: mean={sum(fo)/len(fo):.2f} (n={len(fo)})')
    if fg:
        print(f'  face validity  GOLD: mean={sum(fg)/len(fg):.2f} (n={len(fg)})')

    es = [r['embed_gold_to_ours'] for r in rows if r.get('embed_gold_to_ours') is not None]
    if es:
        print(f'  embedding sim (gold->best ours): mean={sum(es)/len(es):.3f} (n={len(es)})')
    else:
        print('  embedding sim: skipped (embedder unavailable)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=150)
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--no-embed', action='store_true',
                    help='skip embedding similarity (Ollama embedder)')
    ap.add_argument('--provider', default='anthropic', choices=['anthropic', 'ollama'])
    ap.add_argument('--out', default=os.path.join(os.path.dirname(__file__),
                                                  'eduqg_distractors.json'))
    args = ap.parse_args()

    set_thread_provider(args.provider)
    pilot = sample_pilot(load_eduqg(), n=args.n)
    if args.limit:
        pilot = pilot[:args.limit]
    print(f'Distractor benchmark: {len(pilot)} questions, provider={args.provider}, '
          f'embed={not args.no_embed}')

    rows = run(pilot, do_embed=not args.no_embed)
    summarise(rows)
    with open(args.out, 'w', encoding='utf-8') as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)
    print(f'\nWrote per-question records to {args.out}')


if __name__ == '__main__':
    main()
