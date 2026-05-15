"""
Async background-job routes.

POST /api/jobs/generate-questions   -> 202 + {job_id}, runs in thread pool.
GET  /api/jobs/<id>                 -> {status, progress, result?, error?}
GET  /api/jobs                      -> recent jobs (for debugging)

The frontend polls GET /api/jobs/<id> while status is 'running' and shows
the `progress.message` and `progress.current/total` from the runner.
"""

import traceback
from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from services import QuestionService
from services.jobs import submit, get as get_job, list_recent
from schemas import GenerateQuestionsRequest


jobs_bp = Blueprint("jobs", __name__, url_prefix="/api/jobs")


@jobs_bp.route("/generate-questions", methods=["POST"])
def start_generate_questions():
    """Kick off question generation in the background and return a job id."""
    try:
        try:
            req = GenerateQuestionsRequest.model_validate(request.get_json(silent=True) or {})
        except ValidationError as ve:
            return jsonify({"error": "Invalid request body", "details": ve.errors()}), 422

        def runner(report):
            report(message="Loading lessons and ontology...", current=0, total=0)
            result = QuestionService.generate_questions(
                lesson_ids=req.lesson_ids,
                solo_levels=req.solo_levels,
                questions_per_level=req.questions_per_level,
                section_ids=req.section_ids,
                save_to_db=req.save_to_db,
                progress_cb=report,
            )
            status = result.pop("status", 200)
            # QuestionService returns {'error': ..., 'status': 4xx} for known
            # bad-input cases. Surface those as job failures, not successes,
            # so the frontend's poll loop hits the error branch.
            if status >= 400 or result.get("error"):
                raise RuntimeError(result.get("error") or f"Generation failed (status {status})")
            return result

        job_id = submit("generate-questions", runner)
        return jsonify({"job_id": job_id, "status": "pending"}), 202

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@jobs_bp.route("/<job_id>", methods=["GET"])
def get_job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job), 200


@jobs_bp.route("", methods=["GET"])
def list_jobs():
    return jsonify({"jobs": list_recent(limit=50)}), 200
