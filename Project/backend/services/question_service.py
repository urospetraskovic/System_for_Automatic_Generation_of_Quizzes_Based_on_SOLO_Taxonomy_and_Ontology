"""
Question Service
Handles question generation and management logic
"""

from repository import db
from core import SoloQuizGeneratorLocal as SoloQuizGenerator


def _quotas_for_lesson(num_los: int, num_sections: int) -> dict:
    """
    Compute reasonable per-level question counts for one lesson aiming
    for ~85-90% slide coverage. Tuned so each LO has ~1 chance of being
    picked for unistructural and most sections get at least one mid/high
    level question.
    """
    return {
        'unistructural':   max(10, min(40, num_los // 5)),
        'multistructural': max(6,  min(30, int(num_sections * 0.75))),
        'relational':      max(4,  min(20, num_sections // 2)),
    }


class QuestionService:
    """Handle question generation and management"""
    
    @staticmethod
    def generate_questions(lesson_ids, solo_levels, questions_per_level,
                          section_ids=None, save_to_db=True, progress_cb=None):
        """Generate SOLO taxonomy questions from lessons"""
        
        # Validate input
        if not lesson_ids:
            return {'error': 'At least one lesson_id is required', 'status': 400}
        
        # Ensure lesson_ids are integers
        lesson_ids = [int(lid) for lid in lesson_ids]
        
        # Check for extended_abstract - requires 2 lessons
        if 'extended_abstract' in solo_levels and len(lesson_ids) < 2:
            return {
                'error': 'Extended abstract questions require at least 2 lessons',
                'status': 400
            }
        
        try:
            # Get lesson content
            lessons_data = []
            lesson_titles = {}
            ontology_relationships = []
            
            for lid in lesson_ids:
                lesson = db.get_lesson_with_sections(lid)
                if not lesson:
                    return {'error': f'Lesson {lid} not found', 'status': 404}
                lessons_data.append(lesson)
                lesson_titles[lid] = db.get_lesson(lid).get('title')
                
                # Get ontology relationships for this lesson to enhance question generation
                rels = db.get_relationships_for_lesson(lid)
                if rels:
                    ontology_relationships.extend(rels)
            
            print(f"[QuestionService] Found {len(ontology_relationships)} ontology relationships for enhanced question generation")
            
            # Generate questions using AI with ontology support
            generator = SoloQuizGenerator()
            generated_questions = generator.generate_solo_questions(
                lessons_data=lessons_data,
                solo_levels=solo_levels,
                questions_per_level=questions_per_level,
                section_ids=section_ids,
                ontology_relationships=ontology_relationships,
                progress_cb=progress_cb,
            )
            
            # Save to database if requested
            if save_to_db and generated_questions:
                # Add lesson IDs and titles to questions
                for q in generated_questions:
                    if q.get('solo_level') == 'extended_abstract':
                        if not q.get('primary_lesson_id'):
                            q['primary_lesson_id'] = lesson_ids[0]
                        if not q.get('secondary_lesson_id') and len(lesson_ids) > 1:
                            q['secondary_lesson_id'] = lesson_ids[1]
                    else:
                        q['primary_lesson_id'] = lesson_ids[0]
                    
                    # Add titles for frontend
                    if q.get('primary_lesson_id'):
                        q['primary_lesson_title'] = lesson_titles.get(q['primary_lesson_id'])
                    if q.get('secondary_lesson_id'):
                        q['secondary_lesson_title'] = lesson_titles.get(q['secondary_lesson_id'])
                
                question_ids = db.bulk_create_questions(generated_questions)
                for i, q in enumerate(generated_questions):
                    q['id'] = question_ids[i]
            
            return {
                'questions': generated_questions,
                'count': len(generated_questions),
                'solo_distribution': {
                    level: len([q for q in generated_questions if q.get('solo_level') == level])
                    for level in solo_levels
                },
                'status': 200
            }
        
        except Exception as e:
            print(f"[SERVICE] Question generation error: {str(e)}")
            raise

    # ------------------------------------------------------------------
    # Course-wide auto-quota generation
    # ------------------------------------------------------------------

    @staticmethod
    def generate_for_course(course_id, save_to_db=True, progress_cb=None):
        """
        Auto-quota mode: for every lesson in the course, generate enough
        questions at every SOLO level to aim for ~85-90% slide coverage.

        Quotas are derived from the lesson's actual LO/section counts so
        small lessons don't get oversized batches and big lessons get
        sufficient coverage. Extended-Abstract is generated by pairing
        consecutive lessons when the course has 2+.
        """
        course = db.get_course(course_id)
        if not course:
            return {'error': f'Course {course_id} not found', 'status': 404}

        lesson_summaries = db.get_lessons_for_course(course_id)
        if not lesson_summaries:
            return {'error': 'Course has no lessons', 'status': 400}

        # Build a plan with computed quotas per lesson, skipping unparsed ones.
        plans = []
        for ls in lesson_summaries:
            full = db.get_lesson_with_sections(ls['id'])
            sections = (full or {}).get('sections', []) or []
            if not sections:
                continue
            n_sections = len(sections)
            n_los = sum(len(s.get('learning_objects') or []) for s in sections)
            if n_los == 0:
                continue
            quotas = _quotas_for_lesson(n_los, n_sections)
            plans.append({
                'lesson_id': ls['id'],
                'lesson_title': ls['title'],
                'n_sections': n_sections,
                'n_los': n_los,
                'quotas': quotas,
            })

        if not plans:
            return {'error': 'No parsed lessons in this course', 'status': 400}

        # If we have multiple lessons, generate a few EA questions per
        # consecutive pair too.
        ea_per_pair = 5 if len(plans) >= 2 else 0

        # Rough total for progress reporting.
        total_target = sum(
            sum(p['quotas'].values()) for p in plans
        ) + ea_per_pair * max(0, len(plans) - 1)

        def _emit(msg, current=None, total=None):
            if progress_cb:
                try:
                    progress_cb(message=msg, current=current, total=total)
                except Exception:
                    pass

        all_questions = []
        solo_distribution = {
            'unistructural': 0, 'multistructural': 0,
            'relational': 0, 'extended_abstract': 0,
        }
        running_done = 0

        for i, plan in enumerate(plans):
            _emit(
                f"Lesson {i+1}/{len(plans)}: {plan['lesson_title']} "
                f"({plan['n_sections']} sections, {plan['n_los']} LOs)",
                running_done, total_target,
            )

            for level in ('unistructural', 'multistructural', 'relational'):
                count = plan['quotas'][level]
                if count <= 0:
                    continue
                _emit(
                    f"{plan['lesson_title']}: {count} × {level}",
                    running_done, total_target,
                )
                result = QuestionService.generate_questions(
                    lesson_ids=[plan['lesson_id']],
                    solo_levels=[level],
                    questions_per_level=count,
                    save_to_db=save_to_db,
                )
                # Surface known bad-input errors without aborting the whole course.
                if isinstance(result, dict) and result.get('error'):
                    print(f"[SERVICE] Skipping {plan['lesson_title']}/{level}: {result['error']}")
                    continue
                got = result.get('questions') or []
                all_questions.extend(got)
                solo_distribution[level] += len(got)
                running_done += count

            # Extended-Abstract for consecutive pairs.
            if ea_per_pair and i + 1 < len(plans):
                pair_ids = [plan['lesson_id'], plans[i + 1]['lesson_id']]
                _emit(
                    f"Cross-lesson EA: {plan['lesson_title']} + {plans[i+1]['lesson_title']}",
                    running_done, total_target,
                )
                result = QuestionService.generate_questions(
                    lesson_ids=pair_ids,
                    solo_levels=['extended_abstract'],
                    questions_per_level=ea_per_pair,
                    save_to_db=save_to_db,
                )
                if isinstance(result, dict) and not result.get('error'):
                    got = result.get('questions') or []
                    all_questions.extend(got)
                    solo_distribution['extended_abstract'] += len(got)
                running_done += ea_per_pair

        return {
            'questions': all_questions,
            'count': len(all_questions),
            'solo_distribution': solo_distribution,
            'lessons_processed': len(plans),
            'status': 200,
        }

    # ------------------------------------------------------------------
    # Auto-quota generation limited to a user-selected subset of lessons
    # ------------------------------------------------------------------

    @staticmethod
    def generate_for_lessons(lesson_ids, save_to_db=True, progress_cb=None):
        """
        Auto-quota generation across an explicit list of lesson IDs.

        Same quota-sizing and EA-pairing strategy as `generate_for_course`,
        but the caller chooses the lessons. Useful when the user wants the
        "smart" sizing (so they don't have to set `questions_per_level`
        themselves) but only for one or two lessons at a time.

        Behaviour matches `generate_for_course` per lesson:
          * U/M/R quotas come from `_quotas_for_lesson` (LO and section counts).
          * EA is generated for *consecutive pairs* of provided lesson_ids,
            in the order they were passed. With one lesson selected, EA is
            skipped (matching the schema validation in the manual mode).
        """
        if not lesson_ids:
            return {'error': 'lesson_ids is required', 'status': 400}

        # De-duplicate while preserving order.
        seen = set()
        ordered_ids = []
        for lid in lesson_ids:
            try:
                lid_int = int(lid)
            except (TypeError, ValueError):
                continue
            if lid_int not in seen:
                seen.add(lid_int)
                ordered_ids.append(lid_int)
        if not ordered_ids:
            return {'error': 'No valid lesson_ids provided', 'status': 400}

        # Build plans for the requested lessons only, skipping unparsed ones.
        plans = []
        for lid in ordered_ids:
            full = db.get_lesson_with_sections(lid)
            if not full:
                continue
            sections = full.get('sections') or []
            if not sections:
                continue
            n_sections = len(sections)
            n_los = sum(len(s.get('learning_objects') or []) for s in sections)
            if n_los == 0:
                continue
            quotas = _quotas_for_lesson(n_los, n_sections)
            plans.append({
                'lesson_id': lid,
                'lesson_title': full.get('title') or f'Lesson {lid}',
                'n_sections': n_sections,
                'n_los': n_los,
                'quotas': quotas,
            })

        if not plans:
            return {
                'error': 'None of the provided lessons have been parsed yet',
                'status': 400,
            }

        ea_per_pair = 5 if len(plans) >= 2 else 0
        total_target = sum(
            sum(p['quotas'].values()) for p in plans
        ) + ea_per_pair * max(0, len(plans) - 1)

        def _emit(msg, current=None, total=None):
            if progress_cb:
                try:
                    progress_cb(message=msg, current=current, total=total)
                except Exception:
                    pass

        all_questions = []
        solo_distribution = {
            'unistructural': 0, 'multistructural': 0,
            'relational': 0, 'extended_abstract': 0,
        }
        running_done = 0

        for i, plan in enumerate(plans):
            _emit(
                f"Lesson {i+1}/{len(plans)}: {plan['lesson_title']} "
                f"({plan['n_sections']} sections, {plan['n_los']} LOs)",
                running_done, total_target,
            )

            for level in ('unistructural', 'multistructural', 'relational'):
                count = plan['quotas'][level]
                if count <= 0:
                    continue
                _emit(
                    f"{plan['lesson_title']}: {count} × {level}",
                    running_done, total_target,
                )
                result = QuestionService.generate_questions(
                    lesson_ids=[plan['lesson_id']],
                    solo_levels=[level],
                    questions_per_level=count,
                    save_to_db=save_to_db,
                )
                if isinstance(result, dict) and result.get('error'):
                    print(f"[SERVICE] Skipping {plan['lesson_title']}/{level}: {result['error']}")
                    continue
                got = result.get('questions') or []
                all_questions.extend(got)
                solo_distribution[level] += len(got)
                running_done += count

            # EA across consecutive pairs of the selected lessons.
            if ea_per_pair and i + 1 < len(plans):
                pair_ids = [plan['lesson_id'], plans[i + 1]['lesson_id']]
                _emit(
                    f"Cross-lesson EA: {plan['lesson_title']} + {plans[i+1]['lesson_title']}",
                    running_done, total_target,
                )
                result = QuestionService.generate_questions(
                    lesson_ids=pair_ids,
                    solo_levels=['extended_abstract'],
                    questions_per_level=ea_per_pair,
                    save_to_db=save_to_db,
                )
                if isinstance(result, dict) and not result.get('error'):
                    got = result.get('questions') or []
                    all_questions.extend(got)
                    solo_distribution['extended_abstract'] += len(got)
                running_done += ea_per_pair

        return {
            'questions': all_questions,
            'count': len(all_questions),
            'solo_distribution': solo_distribution,
            'lessons_processed': len(plans),
            'status': 200,
        }

    # ------------------------------------------------------------------
    # Coverage-targeted (fill the gaps) generation
    # ------------------------------------------------------------------

    @staticmethod
    def generate_for_uncovered(course_id, save_to_db=True, progress_cb=None):
        """
        For each lesson in the course, query the coverage panel to find
        substantive pages that no question currently touches, then ask
        the generator to produce one unistructural question per LO that
        sits on those pages.

        This is the natural follow-up to `generate_for_course` to fill
        the remaining 10-15% coverage gap.
        """
        from services.coverage_service import CoverageService

        course = db.get_course(course_id)
        if not course:
            return {'error': f'Course {course_id} not found', 'status': 404}

        lesson_summaries = db.get_lessons_for_course(course_id)
        if not lesson_summaries:
            return {'error': 'Course has no lessons', 'status': 400}

        def _emit(msg, current=None, total=None):
            if progress_cb:
                try:
                    progress_cb(message=msg, current=current, total=total)
                except Exception:
                    pass

        all_questions = []
        pages_targeted_total = 0
        los_targeted_total = 0

        for i, ls in enumerate(lesson_summaries):
            _emit(
                f"Lesson {i+1}/{len(lesson_summaries)}: {ls['title']}",
                i, len(lesson_summaries),
            )

            cov = CoverageService.compute(ls['id'])
            if not cov or not cov.get('available'):
                print(f"[SERVICE] '{ls['title']}': coverage unavailable, skipping")
                continue
            uncovered = set(cov.get('uncovered_substantive_pages') or [])
            if not uncovered:
                print(f"[SERVICE] '{ls['title']}': no uncovered substantive pages, skipping")
                continue

            full = db.get_lesson_with_sections(ls['id'])
            if not full:
                continue

            # Find LOs whose source_pages intersect the uncovered set.
            target_lo_ids: set = set()
            filtered_sections = []
            for section in full.get('sections') or []:
                kept_los = []
                for lo in section.get('learning_objects') or []:
                    lo_pages = set(lo.get('source_pages') or [])
                    if lo_pages & uncovered:
                        kept_los.append(lo)
                        target_lo_ids.add(lo['id'])
                if kept_los:
                    filt = dict(section)
                    filt['learning_objects'] = kept_los
                    filtered_sections.append(filt)

            if not target_lo_ids:
                print(f"[SERVICE] '{ls['title']}': uncovered pages have no anchored LOs")
                continue

            pages_targeted_total += len(uncovered)
            los_targeted_total += len(target_lo_ids)

            # Build the filtered lesson_data the generator expects.
            filtered_lesson = dict(full)
            filtered_lesson['sections'] = filtered_sections

            _emit(
                f"'{ls['title']}': targeting {len(target_lo_ids)} LO(s) on {len(uncovered)} uncovered page(s)",
                i, len(lesson_summaries),
            )

            generator = SoloQuizGenerator()
            ontology_rels = db.get_relationships_for_lesson(ls['id']) or []
            generated = generator.generate_solo_questions(
                lessons_data=[filtered_lesson],
                solo_levels=['unistructural'],
                questions_per_level=len(target_lo_ids),
                ontology_relationships=ontology_rels,
            ) or []

            # Tag with lesson info and save.
            if save_to_db and generated:
                for q in generated:
                    q['primary_lesson_id'] = ls['id']
                    q['primary_lesson_title'] = ls['title']
                ids = db.bulk_create_questions(generated)
                for j, q in enumerate(generated):
                    q['id'] = ids[j]

            all_questions.extend(generated)

        return {
            'questions': all_questions,
            'count': len(all_questions),
            'solo_distribution': {'unistructural': len(all_questions)},
            'lessons_processed': len(lesson_summaries),
            'pages_targeted': pages_targeted_total,
            'los_targeted': los_targeted_total,
            'status': 200,
        }
