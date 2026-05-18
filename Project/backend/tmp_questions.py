"""Dump all questions for review."""
import io
import sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from models import Session, Lesson, Section, LearningObject, Question

session = Session()

# Stats first
print("=== STATS ===")
for l in session.query(Lesson).order_by(Lesson.id).all():
    qs = session.query(Question).filter(
        (Question.primary_lesson_id == l.id) | (Question.secondary_lesson_id == l.id)
    ).all()
    by_level = Counter(q.solo_level for q in qs)
    print(f"id={l.id}  '{l.title}'  total questions: {len(qs)}")
    for level, c in sorted(by_level.items()):
        print(f"    {level:25s} {c}")

# Quality stats
all_qs = session.query(Question).all()
print(f"\n=== OVERALL ===")
print(f"Total questions: {len(all_qs)}")
with_source_line = sum(1 for q in all_qs if q.source_line)
print(f"With source_line: {with_source_line} ({100*with_source_line/max(1,len(all_qs)):.0f}%)")
with_lo = sum(1 for q in all_qs if q.learning_object_id)
print(f"With learning_object_id: {with_lo} ({100*with_lo/max(1,len(all_qs)):.0f}%)")
with_section = sum(1 for q in all_qs if q.section_id)
print(f"With section_id: {with_section} ({100*with_section/max(1,len(all_qs)):.0f}%)")
with_anchor = sum(1 for q in all_qs if q.tags and isinstance(q.tags, dict) and q.tags.get('ontology_anchor'))
print(f"With ontology_anchor: {with_anchor}")

# Now dump each question
print(f"\n=== ALL QUESTIONS ===")
for q in all_qs:
    lesson_title = "?"
    if q.primary_lesson:
        lesson_title = q.primary_lesson.title
    print(f"\nQ{q.id}  [{q.solo_level}]  lesson='{lesson_title}'  lo_id={q.learning_object_id}  section_id={q.section_id}")
    print(f"  Q: {q.question_text}")
    if q.options:
        for i, opt in enumerate(q.options):
            marker = " ✓" if i == q.correct_option_index else ""
            print(f"    {opt}{marker}")
    if q.source_line:
        sl = q.source_line[:200]
        print(f"  source_line: \"{sl}\"")
    if q.explanation:
        print(f"  explanation: {q.explanation[:200]}")
    if q.tags and isinstance(q.tags, dict) and q.tags.get('ontology_anchor'):
        a = q.tags['ontology_anchor']
        print(f"  anchor: {a.get('source')} --[{a.get('type')}]--> {a.get('target')}")

session.close()
