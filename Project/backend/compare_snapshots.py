"""
Compare two corpus snapshots side-by-side.

Usage:
    backend/venv/Scripts/python.exe backend/compare_snapshots.py \
        --before qwen2.5-14b-2026-05-24 \
        --after claude-haiku-4-5-2026-06-15

Outputs a Markdown comparison report to snapshots/<after>/comparison.md
and prints the headline table to stdout. Designed for the rad: shows
how each metric changed between models.
"""

import argparse
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def _load_snapshot(snapshots_root, label):
    snap_dir = os.path.join(snapshots_root, label)
    if not os.path.isdir(snap_dir):
        print(f'[compare] ERROR: snapshot {label} not found at {snap_dir}')
        sys.exit(1)

    out = {'label': label, 'dir': snap_dir}
    with open(os.path.join(snap_dir, 'manifest.json'), encoding='utf-8') as f:
        out['manifest'] = json.load(f)
    val_dir = os.path.join(snap_dir, 'validation')
    if not os.path.isdir(val_dir):
        out['validation'] = {}
        return out

    out['validation'] = {}
    for fn in os.listdir(val_dir):
        if not fn.endswith('.json'):
            continue
        key = fn[:-5]
        with open(os.path.join(val_dir, fn), encoding='utf-8') as f:
            out['validation'][key] = json.load(f)
    return out


def _row(before_val, after_val, fmt=str, higher_is_better=None):
    try:
        b = fmt(before_val) if before_val is not None else '–'
    except Exception:
        b = str(before_val)
    try:
        a = fmt(after_val) if after_val is not None else '–'
    except Exception:
        a = str(after_val)
    delta = ''
    try:
        if (isinstance(before_val, (int, float)) and
                isinstance(after_val, (int, float))):
            diff = after_val - before_val
            sign = '+' if diff >= 0 else ''
            if higher_is_better is True:
                arrow = '✓' if diff > 0 else ('✗' if diff < 0 else '~')
            elif higher_is_better is False:
                arrow = '✓' if diff < 0 else ('✗' if diff > 0 else '~')
            else:
                arrow = ''
            delta = f'{sign}{diff:.2f} {arrow}'.strip()
    except Exception:
        pass
    return b, a, delta


def _metric(b_val_dict, a_val_dict, key, path, label, fmt=str, higher_is_better=None):
    def _dig(d, p):
        for k in p:
            if not isinstance(d, dict):
                return None
            d = d.get(k)
        return d
    bv = _dig(b_val_dict.get(key, {}), path)
    av = _dig(a_val_dict.get(key, {}), path)
    return (label, *_row(bv, av, fmt=fmt, higher_is_better=higher_is_better))


def build_comparison(before, after):
    lines = [
        f'# Snapshot comparison — `{before["label"]}` vs `{after["label"]}`',
        '',
        f'**Before generator:** `{before["manifest"].get("generator_model", "?")}`  ',
        f'**After  generator:** `{after["manifest"].get("generator_model", "?")}`  ',
        f'**Before notes:** {before["manifest"].get("notes", "—")}  ',
        f'**After  notes:** {after["manifest"].get("notes", "—")}  ',
        '',
        '## Corpus counts',
        '',
        '| Table | Before | After | Δ |',
        '|---|---:|---:|---:|',
    ]
    bcnt = before['manifest'].get('table_counts', {})
    acnt = after['manifest'].get('table_counts', {})
    for t in set(list(bcnt) + list(acnt)):
        b, a, d = _row(bcnt.get(t, 0), acnt.get(t, 0))
        lines.append(f'| {t} | {b} | {a} | {d} |')

    lines += [
        '',
        '## Headline metrics',
        '',
        '| Metric | Before | After | Δ |',
        '|---|---:|---:|---:|',
    ]

    bv = before.get('validation', {})
    av = after.get('validation', {})

    rows = [
        _metric(bv, av, 'lint', ('average_score',),
                'Haladyna avg score (↑ better)', float, higher_is_better=True),
        _metric(bv, av, 'solo_judge', ('cohen_kappa',),
                "SOLO Judge κ (↑ better)", float, higher_is_better=True),
        _metric(bv, av, 'solo_judge', ('accuracy',),
                "SOLO Judge accuracy (↑ better)", float, higher_is_better=True),
        _metric(bv, av, 'cove', ('support_rate',),
                'CoVe % supported (↑ better)', float, higher_is_better=True),
        _metric(bv, av, 'cove', ('needs_review',),
                'CoVe needs-review count (↓ better)', int, higher_is_better=False),
        _metric(bv, av, 'solvability', ('mean_p_value',),
                'Solver mean p (target 0.6–0.9)', float),
        _metric(bv, av, 'stem_only', ('h4_pass_rate',),
                'H4 stem-only pass % (↑ better)', float, higher_is_better=True),
        _metric(bv, av, 'ioc', ('ioc_index',),
                'IOC index −1..+1 (↑ better)', float, higher_is_better=True),
        _metric(bv, av, 'ambiguity', ('ambiguity_rate',),
                'Ambiguity % (↓ better)', float, higher_is_better=False),
        _metric(bv, av, 'readability', ('mean_flesch_kincaid_grade',),
                'Mean FK grade (lower=easier)', float, higher_is_better=False),
        _metric(bv, av, 'grammar_homogeneity', ('homogeneous_rate',),
                'Grammar homogeneous % (↑ better)', float, higher_is_better=True),
        _metric(bv, av, 'grammar_homogeneity', ('correct_outlier_count',),
                'Grammar clue-risk count (↓ better)', int, higher_is_better=False),
        _metric(bv, av, 'face_validity', ('mean_face_validity_score',),
                'Face validity 1–5 (↑ better)', float, higher_is_better=True),
    ]
    for label, b, a, d in rows:
        lines.append(f'| {label} | {b} | {a} | {d} |')

    # Per-lesson concept coverage table.
    bcov = bv.get('coverage', {})
    acov = av.get('coverage', {})
    if bcov and acov:
        lines += [
            '',
            '## Concept coverage per lesson',
            '',
            '| Lesson | Before % | After % | Δ |',
            '|---|---:|---:|---:|',
        ]
        for lid in set(list(bcov.keys()) + list(acov.keys())):
            bp = (bcov.get(lid, {}).get('concept_coverage') or {}).get('weighted_concept_coverage_pct')
            ap = (acov.get(lid, {}).get('concept_coverage') or {}).get('weighted_concept_coverage_pct')
            title = (bcov.get(lid) or acov.get(lid, {})).get('lesson_title', lid)
            b, a, d = _row(bp, ap, fmt=float, higher_is_better=True)
            lines.append(f'| {title} | {b} | {a} | {d} |')

    # Lint flag frequency comparison.
    bflags = bv.get('lint', {}).get('flag_frequency', {})
    aflags = av.get('lint', {}).get('flag_frequency', {})
    if bflags or aflags:
        lines += [
            '',
            '## Haladyna lint flag frequency',
            '',
            '| Flag | Before | After | Δ |',
            '|---|---:|---:|---:|',
        ]
        all_flags = sorted(set(list(bflags.keys()) + list(aflags.keys())))
        for code in all_flags:
            b, a, d = _row(bflags.get(code, 0), aflags.get(code, 0), fmt=int,
                           higher_is_better=False)
            lines.append(f'| `{code}` | {b} | {a} | {d} |')

    # SOLO judge confusion matrix delta.
    bcm = bv.get('solo_judge', {}).get('confusion_matrix') or {}
    acm = av.get('solo_judge', {}).get('confusion_matrix') or {}
    if bcm and acm:
        lines += [
            '',
            '## SOLO Judge confusion matrix (intended → classified)',
            '',
            '**Before:**',
            '',
            '| ↓ intended \\ classified → | U | M | R | EA |',
            '|---|---:|---:|---:|---:|',
        ]
        for lvl in ('unistructural', 'multistructural', 'relational', 'extended_abstract'):
            row = bcm.get(lvl, {})
            lines.append(
                f'| {lvl} | '
                f'{row.get("unistructural", 0)} | {row.get("multistructural", 0)} | '
                f'{row.get("relational", 0)} | {row.get("extended_abstract", 0)} |'
            )
        lines += ['', '**After:**', '',
                  '| ↓ intended \\ classified → | U | M | R | EA |',
                  '|---|---:|---:|---:|---:|']
        for lvl in ('unistructural', 'multistructural', 'relational', 'extended_abstract'):
            row = acm.get(lvl, {})
            lines.append(
                f'| {lvl} | '
                f'{row.get("unistructural", 0)} | {row.get("multistructural", 0)} | '
                f'{row.get("relational", 0)} | {row.get("extended_abstract", 0)} |'
            )

    return '\n'.join(lines) + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--before', required=True)
    ap.add_argument('--after', required=True)
    ap.add_argument('--snapshots-root', default=None)
    ap.add_argument('--out', default=None,
                    help='Output path (default: snapshots/<after>/comparison.md)')
    args = ap.parse_args()

    backend_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(backend_dir)
    root = args.snapshots_root or os.path.join(project_root, 'snapshots')

    before = _load_snapshot(root, args.before)
    after = _load_snapshot(root, args.after)

    md = build_comparison(before, after)

    out_path = args.out or os.path.join(after['dir'], 'comparison.md')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(md)
    print(f'[compare] Wrote → {out_path}')
    print()
    # Echo the headline metrics table.
    in_table = False
    for line in md.splitlines():
        if line.startswith('## Headline metrics'):
            in_table = True
        if in_table:
            print(line)
        if in_table and line.startswith('## Concept coverage'):
            break


if __name__ == '__main__':
    main()
