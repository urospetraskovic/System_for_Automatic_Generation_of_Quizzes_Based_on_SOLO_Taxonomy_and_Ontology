"""
Corpus snapshot — preserves every artefact of the current generation run so
it can be compared against a future run with a different LLM (e.g. Claude
API, GPT-4o) after the database is wiped.

Layout:
    snapshots/<label>/
        database.db               — full SQLite copy (perfect rollback)
        courses.json              — flat JSON dumps of every table
        lessons.json
        sections.json
        learning_objects.json
        concept_relationships.json
        questions.json
        translations.json         — all *_translation tables merged
        validation/               — one JSON per validation metric
            coverage.json         (concept + page coverage per lesson)
            lint.json             (Haladyna lint per question)
            solo_judge.json       (Cohen κ, confusion matrix)
            cove.json             (per-question verdicts)
            solvability.json      (LLM-blind p-values)
            stem_only.json        (Haladyna H4 results)
            ioc.json              (Rovinelli & Hambleton ratings)
            ambiguity.json        (Downing 2005 detection)
            readability.json      (Flesch / Flesch-Kincaid)
            misconception_mining.json
            grammar_homogeneity.json
            face_validity.json
        summary.md                — key metrics in human-readable form
        manifest.json             — metadata (model, date, counts, env)

Usage:
    backend/venv/Scripts/python.exe backend/snapshot_corpus.py \
        --label qwen2.5-14b-2026-05-24 \
        --notes "Local Ollama 14B, after BANNED_OPENERS prompt fix"

The validation services are called with their normal entry points. If the
LLM cache has the responses already (e.g. you have already run the Quality
Overview), the snapshot is instant. Otherwise it will make live Ollama
calls — so this should usually be run AFTER running the full Quality
Overview from the UI.
"""

import argparse
import io
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime

# Make sure backend/ is importable.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from config import OLLAMA_MODEL, OLLAMA_BASE_URL  # noqa: E402


def _dump_table(cur, table_name, snapshot_dir):
    """Dump a SQLite table to JSON. Each row is one object; column order is
    preserved. Output filename = <table>.json under snapshot_dir."""
    try:
        cur.execute(f'SELECT * FROM {table_name}')
    except sqlite3.OperationalError:
        return 0
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    with open(os.path.join(snapshot_dir, f'{table_name}.json'), 'w', encoding='utf-8') as f:
        json.dump(rows, f, ensure_ascii=False, indent=2, default=str)
    return len(rows)


def _dump_translations(cur, snapshot_dir):
    """Merge every *_translation table into a single translations.json."""
    out = {}
    for table in [
        'question_translation', 'questiontranslation', 'question_translations',
        'lesson_translation', 'lessontranslation', 'lesson_translations',
        'section_translation', 'sectiontranslation', 'section_translations',
        'learning_object_translation', 'learning_object_translations',
        'learningobjecttranslation', 'ontologytranslation',
    ]:
        try:
            cur.execute(f'SELECT * FROM {table}')
        except sqlite3.OperationalError:
            continue
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        if rows:
            out[table] = rows
    with open(os.path.join(snapshot_dir, 'translations.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    return sum(len(v) for v in out.values())


def _load_question_dicts(db_path):
    """Load every question in the shape the validation services expect."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    rows = cur.execute('SELECT * FROM questions').fetchall()
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


def _per_lesson_ids(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    rows = cur.execute('SELECT id, title FROM lessons').fetchall()
    conn.close()
    return rows


def _run_validation(db_path, snapshot_dir, skip_validation, include_solvability):
    """Run every validation metric and dump JSON. Per-lesson where lesson_id
    is required (coverage), per-corpus where the metric is corpus-wide.

    `include_solvability` defaults to False because the solver service runs
    with use_cache=False (it needs trial variance) — that means snapshot
    re-runs would make ~970 live LLM calls. Opt in only if you want to
    refresh solvability data.
    """
    os.makedirs(os.path.join(snapshot_dir, 'validation'), exist_ok=True)

    if skip_validation:
        print('[snapshot] --no-validation set — skipping validation dump.')
        return {}

    from services.coverage_service import CoverageService
    from services.mcq_lint import lint_questions
    from services.solo_judge import judge_questions
    from services.cove import verify_questions
    from services.solvability import (
        solvability_report, stem_only_solvability_report,
    )
    from services.ioc import ioc_report
    from services.ambiguity import ambiguity_report
    from services.readability import readability_report
    from services.misconception_mining import mine_lesson_misconceptions
    from services.grammar_homogeneity import homogeneity_report
    from services.face_validity import face_validity_report

    val_dir = os.path.join(snapshot_dir, 'validation')
    questions = _load_question_dicts(db_path)
    lessons = _per_lesson_ids(db_path)

    summary = {}

    # 1) Concept + page coverage — per lesson.
    coverage = {}
    for lid, ltitle in lessons:
        try:
            coverage[str(lid)] = {
                'lesson_title': ltitle,
                **(CoverageService.compute(lid) or {}),
            }
        except Exception as e:
            coverage[str(lid)] = {'error': str(e)}
    with open(os.path.join(val_dir, 'coverage.json'), 'w', encoding='utf-8') as f:
        json.dump(coverage, f, ensure_ascii=False, indent=2, default=str)
    summary['coverage'] = coverage
    print(f'[snapshot]   coverage ✓ ({len(coverage)} lessons)')

    # The rest are corpus-wide.
    def _dump(name, payload):
        with open(os.path.join(val_dir, f'{name}.json'), 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        summary[name] = payload

    print('[snapshot]   running lint…')
    _dump('lint', lint_questions(questions, use_embeddings=True))
    print('[snapshot]   running SOLO judge…')
    _dump('solo_judge', judge_questions(questions))
    print('[snapshot]   running CoVe…')
    _dump('cove', verify_questions(questions))
    if include_solvability:
        print('[snapshot]   running solvability… (LIVE — slow, ~970 LLM calls)')
        _dump('solvability', solvability_report(questions))
    else:
        print('[snapshot]   skipping solvability (use --include-solvability to run live)')
    print('[snapshot]   running stem-only…')
    _dump('stem_only', stem_only_solvability_report(questions))
    print('[snapshot]   running IOC…')
    _dump('ioc', ioc_report(questions))
    print('[snapshot]   running ambiguity…')
    _dump('ambiguity', ambiguity_report(questions))
    print('[snapshot]   running readability…')
    _dump('readability', readability_report(questions))

    print('[snapshot]   running misconception mining (per lesson)…')
    miners = {}
    for lid, ltitle in lessons:
        try:
            miners[str(lid)] = {
                'lesson_title': ltitle,
                **(mine_lesson_misconceptions(lid) or {}),
            }
        except Exception as e:
            miners[str(lid)] = {'error': str(e)}
    with open(os.path.join(val_dir, 'misconception_mining.json'), 'w', encoding='utf-8') as f:
        json.dump(miners, f, ensure_ascii=False, indent=2, default=str)
    summary['misconception_mining'] = miners

    print('[snapshot]   running grammar homogeneity…')
    _dump('grammar_homogeneity', homogeneity_report(questions))
    print('[snapshot]   running face validity…')
    _dump('face_validity', face_validity_report(questions))

    return summary


def _build_summary_md(snapshot_dir, label, notes, counts, validation, model):
    """Human-readable summary in Markdown."""
    lines = [
        f'# Snapshot — `{label}`',
        '',
        f'**Created:** {datetime.now().isoformat(timespec="seconds")}  ',
        f'**Generator model:** `{model}`  ',
        f'**Ollama URL:** `{OLLAMA_BASE_URL}`  ',
    ]
    if notes:
        lines += [f'**Notes:** {notes}', '']

    lines += [
        '',
        '## Corpus counts',
        '',
        '| Table | Rows |',
        '|---|---:|',
    ]
    for table, n in counts.items():
        lines.append(f'| {table} | {n} |')

    if validation:
        lines += ['', '## Headline metrics', '']
        # Coverage
        cov = validation.get('coverage', {})
        if cov:
            lines.append('### Concept Coverage (per lesson)')
            lines.append('')
            lines.append('| Lesson | Concepts covered | Weighted % | Page % |')
            lines.append('|---|---|---:|---:|')
            for lid, c in cov.items():
                cc = c.get('concept_coverage') or {}
                if cc.get('available'):
                    lines.append(
                        f"| {c.get('lesson_title', lid)} | "
                        f"{cc.get('concepts_covered', '–')}/{cc.get('total_concepts', '–')} | "
                        f"{cc.get('weighted_concept_coverage_pct', '–')}% | "
                        f"{c.get('weighted_coverage_pct', '–')}% |"
                    )
            lines.append('')

        def _h(key, label, fmt):
            data = validation.get(key)
            if not data:
                return
            try:
                lines.append(f'- **{label}**: {fmt(data)}')
            except Exception as e:
                lines.append(f'- **{label}**: (error: {e})')

        _h('lint', 'Haladyna avg score',
           lambda d: f"{d.get('average_score', '–')}/100 "
                     f"({d.get('aggregate_counts', {}).get('error', 0)} errors, "
                     f"{d.get('aggregate_counts', {}).get('warn', 0)} warnings)")
        _h('solo_judge', "SOLO Judge Cohen's κ",
           lambda d: f"{d.get('cohen_kappa', '–')} (accuracy {d.get('accuracy', '–')})")
        _h('cove', 'CoVe Support rate',
           lambda d: f"{d.get('support_rate', '–')}% ({d.get('needs_review', '–')} need review)")
        _h('solvability', 'Solver mean p',
           lambda d: f"{d.get('mean_p_value', '–')}")
        _h('stem_only', 'H4 stem-only pass rate',
           lambda d: f"{d.get('h4_pass_rate', '–')}%")
        _h('ioc', 'IOC index',
           lambda d: f"{d.get('ioc_index', '–')} ({d.get('ioc_label', '–')})")
        _h('ambiguity', 'Ambiguity rate',
           lambda d: f"{d.get('ambiguity_rate', '–')}% "
                     f"({d.get('ambiguous_count', '–')} flagged)")
        _h('readability', 'Mean Flesch-Kincaid grade',
           lambda d: f"{d.get('mean_flesch_kincaid_grade', '–')}")
        _h('grammar_homogeneity', 'Grammar homogeneous rate',
           lambda d: f"{d.get('homogeneous_rate', '–')}% "
                     f"({d.get('correct_outlier_count', '–')} clue risks)")
        _h('face_validity', 'Mean face-validity',
           lambda d: f"{d.get('mean_face_validity_score', '–')}/5")

    with open(os.path.join(snapshot_dir, 'summary.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--label', required=True,
                    help='Snapshot label, e.g. "qwen2.5-14b-2026-05-24"')
    ap.add_argument('--notes', default='', help='Free-text notes for the manifest')
    ap.add_argument('--no-validation', action='store_true',
                    help='Skip running validation services (only dump DB tables)')
    ap.add_argument('--include-solvability', action='store_true',
                    help='Also run the solver-based difficulty test. This makes '
                         '~5×N_questions LIVE LLM calls because the solver does not '
                         'cache (it needs trial variance). Slow — only enable if Ollama '
                         'is running and you have time.')
    ap.add_argument('--out-root', default=None,
                    help='Override snapshots/ root directory')
    args = ap.parse_args()

    backend_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(backend_dir)
    out_root = args.out_root or os.path.join(project_root, 'snapshots')
    snapshot_dir = os.path.join(out_root, args.label)
    if os.path.exists(snapshot_dir):
        print(f'[snapshot] WARNING: {snapshot_dir} already exists — overwriting.')
    os.makedirs(snapshot_dir, exist_ok=True)

    db_path = os.path.join(backend_dir, 'quiz_database.db')
    if not os.path.exists(db_path):
        print(f'[snapshot] ERROR: database not found at {db_path}')
        sys.exit(1)

    print(f'[snapshot] Writing snapshot → {snapshot_dir}')

    # 1) Copy the entire SQLite file for perfect rollback.
    shutil.copy2(db_path, os.path.join(snapshot_dir, 'database.db'))
    print('[snapshot] database.db copied.')

    # 2) Dump every table to its own JSON for portability.
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    tables = ['courses', 'lessons', 'sections', 'learning_objects',
              'concept_relationships', 'questions', 'quizzes', 'quiz_questions']
    counts = {}
    for t in tables:
        counts[t] = _dump_table(cur, t, snapshot_dir)
        print(f'[snapshot]   {t}: {counts[t]} rows')
    counts['translations'] = _dump_translations(cur, snapshot_dir)
    print(f"[snapshot]   translations: {counts['translations']} rows")
    conn.close()

    # 3) Run validation and dump per-metric JSON.
    print('[snapshot] Running validation services…')
    validation = _run_validation(
        db_path, snapshot_dir, args.no_validation, args.include_solvability,
    )

    # 4) Manifest.
    manifest = {
        'label': args.label,
        'created_at': datetime.now().isoformat(),
        'generator_model': OLLAMA_MODEL,
        'ollama_base_url': OLLAMA_BASE_URL,
        'notes': args.notes,
        'table_counts': counts,
        'validation_keys': sorted(validation.keys()) if validation else [],
        'env': {
            'OLLAMA_MODEL': os.getenv('OLLAMA_MODEL'),
            'OLLAMA_JUDGE_MODEL': os.getenv('OLLAMA_JUDGE_MODEL'),
            'OLLAMA_COVE_MODEL': os.getenv('OLLAMA_COVE_MODEL'),
            'OLLAMA_SOLVER_MODEL': os.getenv('OLLAMA_SOLVER_MODEL'),
            'OLLAMA_EMBED_MODEL': os.getenv('OLLAMA_EMBED_MODEL'),
            'OLLAMA_IOC_MODEL': os.getenv('OLLAMA_IOC_MODEL'),
            'OLLAMA_AMBIGUITY_MODEL': os.getenv('OLLAMA_AMBIGUITY_MODEL'),
            'OLLAMA_GRAMMAR_MODEL': os.getenv('OLLAMA_GRAMMAR_MODEL'),
            'OLLAMA_FACE_MODEL': os.getenv('OLLAMA_FACE_MODEL'),
            'OLLAMA_MINER_MODEL': os.getenv('OLLAMA_MINER_MODEL'),
        },
    }
    with open(os.path.join(snapshot_dir, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    # 5) Human-readable summary.
    _build_summary_md(snapshot_dir, args.label, args.notes, counts, validation, OLLAMA_MODEL)

    print()
    print(f'[snapshot] DONE — see {snapshot_dir}/summary.md')


if __name__ == '__main__':
    main()
