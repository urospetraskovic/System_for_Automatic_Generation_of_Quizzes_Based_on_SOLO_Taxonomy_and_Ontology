"""
Hydrate validation_cache from a snapshot directory.

The validation_cache table is what the UI reads on lesson mount to show
previously-computed metrics without re-running. If the cache is empty
(e.g. you just upgraded to the persistence patch and your old runs are
only on disk as snapshots), this script reads any
`snapshots/<label>/validation/*.json` files and writes them into the
cache as-is.

Two flavours of validation reports get stored differently:

1. Lesson-keyed reports (coverage, misconception_mining) — already an
   object {lesson_id: payload}, so we write each entry to the cache
   with its own lesson_id.

2. Corpus-wide reports (lint, solo_judge, cove, ioc, etc.) — a single
   aggregate payload covering ALL questions. We don't have per-lesson
   data to split it, so we write the SAME payload under every lesson
   present in the snapshot. UI sub-panels show aggregate numbers anyway,
   so this is correct.

Usage:
    backend/venv/Scripts/python.exe backend/hydrate_cache_from_snapshot.py \\
        --snapshot qwen2.5-14b-2026-05-24
"""

import argparse
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from services import validation_cache  # noqa: E402


# Reports that store one entry per lesson at the top level of the JSON.
# Key in the JSON is the lesson id as a string.
PER_LESSON_REPORTS = {'coverage', 'misconception_mining'}

# Reports that store a single corpus-wide aggregate. We replicate the same
# payload under each lesson in the snapshot.
CORPUS_WIDE_REPORTS = {
    'lint', 'solo_judge', 'cove', 'solvability', 'stem_only',
    'ioc', 'ambiguity', 'readability', 'grammar_homogeneity',
    'face_validity',
}


def _load_lesson_ids(snapshot_dir):
    """Pull the list of lesson ids from the snapshot's lessons.json so we
    know which lesson_ids to attach corpus-wide reports to."""
    path = os.path.join(snapshot_dir, 'lessons.json')
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        rows = json.load(f)
    return [r['id'] for r in rows if 'id' in r]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--snapshot', required=True,
                    help='Snapshot label (folder name under snapshots/)')
    ap.add_argument('--snapshots-root', default=None)
    ap.add_argument('--overwrite', action='store_true',
                    help='If a cache entry already exists for a (metric, '
                         'lesson) pair, overwrite it. By default we skip '
                         'existing entries.')
    args = ap.parse_args()

    backend_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(backend_dir)
    root = args.snapshots_root or os.path.join(project_root, 'snapshots')
    snap_dir = os.path.join(root, args.snapshot)
    val_dir = os.path.join(snap_dir, 'validation')

    if not os.path.isdir(val_dir):
        print(f'[hydrate] ERROR: {val_dir} not found.')
        sys.exit(1)

    lesson_ids = _load_lesson_ids(snap_dir)
    if not lesson_ids:
        print('[hydrate] WARNING: no lessons.json or empty — corpus-wide '
              'reports will not be written.')

    written = 0
    skipped = 0
    for fn in sorted(os.listdir(val_dir)):
        if not fn.endswith('.json'):
            continue
        metric_key = fn[:-5]
        path = os.path.join(val_dir, fn)
        with open(path, encoding='utf-8') as f:
            payload = json.load(f)

        if metric_key in PER_LESSON_REPORTS:
            if not isinstance(payload, dict):
                print(f'[hydrate] {metric_key}: expected dict at top level, got '
                      f'{type(payload).__name__}; skipping.')
                continue
            for lid_str, sub_payload in payload.items():
                try:
                    lid = int(lid_str)
                except (TypeError, ValueError):
                    continue
                if not args.overwrite and validation_cache.get(metric_key, lid):
                    skipped += 1
                    continue
                validation_cache.put(metric_key, lid, sub_payload)
                written += 1
                print(f'[hydrate] {metric_key} → lesson {lid}')
        elif metric_key in CORPUS_WIDE_REPORTS:
            for lid in lesson_ids:
                if not args.overwrite and validation_cache.get(metric_key, lid):
                    skipped += 1
                    continue
                validation_cache.put(metric_key, lid, payload)
                written += 1
                print(f'[hydrate] {metric_key} → lesson {lid}')
        else:
            print(f'[hydrate] {metric_key}: unknown metric, skipping.')

    print()
    print(f'[hydrate] DONE — wrote {written} cache entries, skipped {skipped}.')
    print(f'[hydrate] Re-open the lesson view; metrics should appear in every '
          f'sub-panel without clicking Run.')


if __name__ == '__main__':
    main()
