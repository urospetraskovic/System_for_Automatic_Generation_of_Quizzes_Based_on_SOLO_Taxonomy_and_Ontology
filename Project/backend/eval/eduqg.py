"""EduQG dataset adapter + pilot sampler.

EduQG (Hadifar et al., IEEE Access 2023) is a dataset of 3,397 expert-written
multiple-choice questions from 12 OpenStax textbooks, each grounded to the
source text at sentence level. We use it as an external gold standard to

  * calibrate our validator battery (do our quality checks PASS expert
    questions? = specificity), and
  * benchmark our distractor generation against expert distractors.

This module only loads and normalises the data into the same dict shape our
validators already consume (see analyze_corpus.load_questions). No DB needed.

Raw data lives in the cloned repo at:
    Project/question-generation-main/raw_data/{qg_train_v0,qg_valid_v0}.json

Each raw question has the shape:
    {"question": {"question_id", "question_text", "question_choices",
                  "cloze_format", "normal_format"},
     "answer":   {"ans_text": "<letter>", "ans_choice": <int index>},
     "bloom":    null | "1".."4",          # 1=Remember 2=Understand 3=Apply 4=Analyze
     "hl_sentences": "<minimal grounding sentence(s)>",
     "hl_context":   "<wider context with <hl> markers around the grounding>"}

Run as a smoke test:
    backend/venv/Scripts/python.exe -m eval.eduqg        # from backend/
"""

import json
import os
import random
from collections import Counter, defaultdict

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_DIR = os.path.dirname(BACKEND_DIR)


def _find_raw_dir():
    """Locate the EduQG raw_data dir. The GitHub zip extracts with a nested
    'question-generation-main/question-generation-main/' folder, so we search a
    couple of likely depths rather than hard-coding one."""
    candidates = [
        os.path.join(PROJECT_DIR, 'question-generation-main', 'raw_data'),
        os.path.join(PROJECT_DIR, 'question-generation-main',
                     'question-generation-main', 'raw_data'),
    ]
    for c in candidates:
        if os.path.exists(os.path.join(c, 'qg_train_v0.json')):
            return c
    return candidates[0]


RAW_DIR = _find_raw_dir()

BLOOM_NAMES = {'1': 'Remember', '2': 'Understand', '3': 'Apply', '4': 'Analyze'}


def _strip_hl(text):
    """Remove the <hl> grounding markers from hl_context, leaving plain prose."""
    return ' '.join(text.replace('<hl>', ' ').split())


def load_eduqg(raw_dir=RAW_DIR):
    """Load both splits and normalise into our internal question dict shape.

    Returns a list of dicts. Questions whose answer index is out of range are
    skipped (data hygiene). `n_options` is kept so callers can filter to the
    canonical 4-option items.
    """
    items = []
    for fname, split in (('qg_train_v0.json', 'train'), ('qg_valid_v0.json', 'valid')):
        path = os.path.join(raw_dir, fname)
        with open(path, encoding='utf-8') as fh:
            chapters = json.load(fh)
        for ch in chapters:
            for q in ch['questions']:
                qq = q['question']
                choices = qq.get('question_choices') or []
                ci = q['answer'].get('ans_choice')
                if ci is None or not (0 <= ci < len(choices)):
                    continue
                items.append({
                    # identity / metadata
                    'eduqg_id': qq.get('question_id'),
                    'book': ch.get('bname'),
                    'chapter': ch.get('chapter'),
                    'split': split,
                    'bloom': q.get('bloom'),
                    'bloom_name': BLOOM_NAMES.get(q.get('bloom')),
                    # the fields our validators consume (mirror DB column names)
                    'question_text': qq.get('normal_format') or qq.get('question_text'),
                    'options': choices,
                    'correct_option_index': ci,
                    'correct_answer': choices[ci],
                    'source_line': q.get('hl_sentences', ''),
                    # extras for distractor benchmark + context-aware judges
                    'cloze_format': qq.get('cloze_format'),
                    'distractors': [c for i, c in enumerate(choices) if i != ci],
                    'context': _strip_hl(q.get('hl_context', '')),
                    'n_options': len(choices),
                })
    return items


def sample_pilot(items, n=150, seed=42, only_4_options=True):
    """Stratified pilot sample, proportional across the 12 source books.

    Proportional-by-book keeps the domain mix of the full dataset. A fixed seed
    makes the pilot reproducible. Returns at most `n` items.
    """
    pool = [it for it in items if (not only_4_options or it['n_options'] == 4)]
    by_book = defaultdict(list)
    for it in pool:
        by_book[it['book']].append(it)

    rng = random.Random(seed)
    total = len(pool)
    sampled = []
    for book, group in sorted(by_book.items()):
        rng.shuffle(group)
        take = max(1, round(n * len(group) / total))
        sampled.extend(group[:take])

    # Proportional rounding can overshoot/undershoot n; trim/pad deterministically.
    rng.shuffle(sampled)
    return sampled[:n]


def _smoke_test():
    items = load_eduqg()
    print(f'Loaded {len(items)} questions (4-option: '
          f'{sum(1 for i in items if i["n_options"] == 4)}).')

    pilot = sample_pilot(items, n=150)
    print(f'\nPilot N = {len(pilot)}')

    by_book = Counter(it['book'] for it in pilot)
    print('\nBy book:')
    for book, c in by_book.most_common():
        print(f'  {c:3d}  {book}')

    by_bloom = Counter(it['bloom_name'] or '(unlabeled)' for it in pilot)
    print('\nBy Bloom:')
    for name, c in by_bloom.most_common():
        print(f'  {c:3d}  {name}')

    print('\nTwo examples:')
    for it in pilot[:2]:
        print(f'\n  [{it["book"]} ch{it["chapter"]}] {it["question_text"]}')
        for i, opt in enumerate(it['options']):
            mark = '*' if i == it['correct_option_index'] else ' '
            print(f'    {mark} {opt}')
        print(f'    grounding: {it["source_line"][:140]}')


if __name__ == '__main__':
    _smoke_test()
