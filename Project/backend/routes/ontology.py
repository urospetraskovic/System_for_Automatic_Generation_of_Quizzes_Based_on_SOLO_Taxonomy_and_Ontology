"""Ontology generation, export, and knowledge-base routes."""

import traceback

from flask import Blueprint, request, jsonify, make_response

from repository import db
from core import content_parser
from services import ontology_manager

ontology_bp = Blueprint('ontology', __name__, url_prefix='/api')


def _ontology_filename(lesson, lesson_id, extension):
    """Build a download filename for an ontology export."""
    file_name = lesson.get('filename', lesson.get('title', f'Lesson_{lesson_id}'))
    if file_name.endswith('.pdf'):
        file_name = file_name[:-4]
    return f'ontology_{file_name}.{extension}'


# ---------- Lesson-scoped ontology (relationships table) ----------

@ontology_bp.route('/lessons/<int:lesson_id>/ontology', methods=['GET'])
def get_lesson_ontology(lesson_id):
    """Get the domain ontology (relationships) for a lesson."""
    try:
        relationships = db.get_relationships_for_lesson(lesson_id)
        return jsonify({'relationships': relationships}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ontology_bp.route('/lessons/<int:lesson_id>/ontology/clear', methods=['POST'])
def clear_ontology(lesson_id):
    """Clear all ontology relationships for a lesson."""
    try:
        lesson = db.get_lesson(lesson_id)
        if not lesson:
            return jsonify({'error': 'Lesson not found'}), 404

        relationships = db.get_relationships_for_lesson(lesson_id)
        cleared_count = 0

        for rel in relationships:
            try:
                db.delete_relationship(rel['id'])
                cleared_count += 1
            except Exception:
                pass

        print(f"[API] Cleared {cleared_count} ontology relationships for lesson {lesson_id}")

        return jsonify({
            'message': 'Ontology cleared successfully',
            'cleared_count': cleared_count
        }), 200
    except Exception as e:
        print(f"[API] Error clearing ontology: {str(e)}")
        return jsonify({'error': str(e)}), 500


@ontology_bp.route('/lessons/<int:lesson_id>/ontology/generate', methods=['POST'])
def generate_ontology(lesson_id):
    """Generate ontology relationships based on current sections and learning objects."""
    try:
        lesson = db.get_lesson(lesson_id, include_content=True)
        if not lesson:
            return jsonify({'error': 'Lesson not found'}), 404

        if not lesson.get('raw_content'):
            return jsonify({'error': 'Lesson has no content to extract relationships from'}), 400

        all_sections = db.get_sections_for_lesson(lesson_id)
        all_los = []
        lo_title_to_id = {}

        for s in all_sections:
            section_los = db.get_learning_objects_for_section(s['id'])
            all_los.extend(section_los)
            for lo in section_los:
                lo_title_to_id[lo['title']] = lo['id']

        if not all_los:
            return jsonify({
                'message': 'No learning objects to create ontology from. Parse the lesson first.',
                'regenerated_count': 0
            }), 400

        print(f"[API] Regenerating ontology for lesson: {lesson['title']}")
        print(f"[API] Found {len(all_los)} learning objects")

        ontology_rels = content_parser.extract_ontology_relationships(
            lesson['raw_content'],
            all_los,
            lesson['title'],
            sections=all_sections,
        )

        print(f"[API] AI returned {len(ontology_rels)} potential relationships")

        existing_rels = db.get_relationships_for_lesson(lesson_id)
        for rel in existing_rels:
            try:
                db.delete_relationship(rel['id'])
            except Exception:
                pass

        db_rels = []
        for rel in ontology_rels:
            source_id = lo_title_to_id.get(rel['source'])
            target_id = lo_title_to_id.get(rel['target'])
            print(f"[API] Checking rel: {rel['source']} -> {rel['target']} (source_id={source_id}, target_id={target_id})")
            if source_id and target_id:
                db_rels.append({
                    'source_id': source_id,
                    'target_id': target_id,
                    'relationship_type': rel['type'],
                    'description': rel.get('description')
                })

        print(f"[API] Saving {len(db_rels)} relationships to database")
        if db_rels:
            db.bulk_create_relationships(db_rels)

        return jsonify({
            'message': 'Ontology generated successfully',
            'generated_count': len(db_rels)
        }), 200
    except Exception as e:
        print(f"[API] Error generating ontology: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@ontology_bp.route('/relationships/<int:rel_id>', methods=['DELETE'])
def delete_relationship(rel_id):
    """Delete a specific relationship."""
    try:
        db.delete_relationship(rel_id)
        return jsonify({'message': 'Relationship deleted successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ontology_bp.route('/lessons/<int:lesson_id>/ontology/export/owl', methods=['GET'])
def export_ontology_owl(lesson_id):
    """Export lesson ontology as OWL (RDF/XML format)."""
    try:
        lesson = db.get_lesson(lesson_id)
        if not lesson:
            return jsonify({'error': 'Lesson not found'}), 404

        owl_content = ontology_manager.export_lesson_ontology(lesson_id, fmt='xml')
        file_name = _ontology_filename(lesson, lesson_id, 'owl')

        response = make_response(owl_content)
        response.headers['Content-Type'] = 'application/rdf+xml'
        response.headers['Content-Disposition'] = f'attachment; filename="{file_name}"'
        return response, 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ontology_bp.route('/lessons/<int:lesson_id>/ontology/export/turtle', methods=['GET'])
def export_ontology_turtle(lesson_id):
    """Export lesson ontology as Turtle format."""
    try:
        lesson = db.get_lesson(lesson_id)
        if not lesson:
            return jsonify({'error': 'Lesson not found'}), 404

        turtle_content = ontology_manager.export_lesson_ontology(lesson_id, fmt='turtle')
        file_name = _ontology_filename(lesson, lesson_id, 'ttl')

        response = make_response(turtle_content)
        response.headers['Content-Type'] = 'text/turtle'
        response.headers['Content-Disposition'] = f'attachment; filename="{file_name}"'
        return response, 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------- Knowledge-base ontology (seed TBox + DB ABox) ----------

@ontology_bp.route('/ontology/stats', methods=['GET'])
def get_ontology_stats():
    """Get statistics about the knowledge base ontology."""
    try:
        stats = ontology_manager.get_ontology_stats()
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ontology_bp.route('/ontology/export', methods=['GET'])
def export_full_ontology():
    """Export the complete knowledge base ontology (seed + all database content)."""
    try:
        course_id = request.args.get('course_id', type=int)
        format_type = request.args.get('format', 'owl')

        owl_content = ontology_manager.export_full_ontology(course_id=course_id, fmt='xml')

        if format_type == 'download':
            response = make_response(owl_content)
            response.headers['Content-Type'] = 'application/rdf+xml'
            filename = f'knowledge_base_course_{course_id}.owl' if course_id else 'knowledge_base_full.owl'
            response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response, 200

        return jsonify({
            'ontology': owl_content,
            'stats': ontology_manager.get_ontology_stats()
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ontology_bp.route('/ontology/export/course/<int:course_id>', methods=['GET'])
def export_course_ontology(course_id):
    """Export ontology for a specific course."""
    try:
        owl_content = ontology_manager.export_full_ontology(course_id=course_id, fmt='xml')

        response = make_response(owl_content)
        response.headers['Content-Type'] = 'application/rdf+xml'
        response.headers['Content-Disposition'] = f'attachment; filename="knowledge_base_course_{course_id}.owl"'
        return response, 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ontology_bp.route('/ontology/export/lesson/<int:lesson_id>', methods=['GET'])
def export_lesson_knowledge_ontology(lesson_id):
    """Export the complete (seed + lesson individuals) ontology for a single lesson."""
    try:
        owl_content = ontology_manager.export_lesson_ontology(lesson_id=lesson_id, fmt='xml')

        response = make_response(owl_content)
        response.headers['Content-Type'] = 'application/rdf+xml'
        response.headers['Content-Disposition'] = f'attachment; filename="knowledge_base_lesson_{lesson_id}.owl"'
        return response, 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ontology_bp.route('/ontology/save', methods=['POST'])
def save_ontology_to_file():
    """Save the knowledge base ontology to a file on the server."""
    try:
        course_id = request.json.get('course_id') if request.json else None
        file_path = ontology_manager.save_knowledge_base(course_id=course_id)

        return jsonify({
            'message': 'Knowledge base saved successfully',
            'file_path': file_path,
            'stats': ontology_manager.get_ontology_stats()
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
