"""Throwaway: dump Niti lesson."""
import io
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from models import Session, Lesson, Section, LearningObject

session = Session()

print("=== ALL LESSONS ===")
for l in session.query(Lesson).order_by(Lesson.created_at.desc()).all():
    sec_count = session.query(Section).filter(Section.lesson_id == l.id).count()
    lo_count = (
        session.query(LearningObject)
        .join(Section, LearningObject.section_id == Section.id)
        .filter(Section.lesson_id == l.id)
        .count()
    )
    pages = len(l.pages_meta) if l.pages_meta else 0
    print(f"id={l.id}  created={l.created_at}  '{l.title}'  pages={pages}  sections={sec_count}  LOs={lo_count}")

for lesson in session.query(Lesson).filter(Lesson.title.like('%Niti%')).all():
    print(f"\n{'='*70}\nLESSON id={lesson.id}  '{lesson.title}'  ({len(lesson.pages_meta or [])} pages, {len(lesson.raw_content or '')} chars)\n{'='*70}")
    sections = session.query(Section).filter(Section.lesson_id == lesson.id).order_by(Section.order_index).all()
    print(f"{len(sections)} sections\n")
    for s in sections:
        los = session.query(LearningObject).filter(LearningObject.section_id == s.id).order_by(LearningObject.order_index).all()
        page_range = f"pages {s.start_page}-{s.end_page}" if s.start_page and s.end_page else "no pages"
        print(f"  [{s.order_index + 1}] '{s.title}'  ({page_range})  ({len(los)} LOs)")
        for lo in los:
            pages = lo.source_pages or []
            print(f"        - '{lo.title}'  type={lo.object_type}  pages={pages}")

session.close()
