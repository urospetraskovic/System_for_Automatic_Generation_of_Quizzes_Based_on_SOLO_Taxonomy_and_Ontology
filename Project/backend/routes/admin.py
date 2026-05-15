"""Admin routes — LLM cache management."""

import traceback
from flask import Blueprint, jsonify

from core import llm_cache

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


@admin_bp.route("/llm-cache/stats", methods=["GET"])
def cache_stats():
    try:
        return jsonify(llm_cache.stats()), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/llm-cache", methods=["DELETE"])
def cache_clear():
    try:
        deleted = llm_cache.clear()
        return jsonify({"cleared": deleted}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
