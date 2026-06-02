"""LLM provider control + cost-tracker routes."""

import traceback

from flask import Blueprint, jsonify, request

from core.llm_provider import (
    available_providers,
    get_spend_snapshot,
    reset_spend,
)

llm_bp = Blueprint('llm', __name__, url_prefix='/api/llm')


@llm_bp.route('/providers', methods=['GET'])
def list_providers():
    """Return every LLM provider this install can route to, plus whether the
    user has the credentials to use it (e.g. ANTHROPIC_API_KEY set)."""
    try:
        return jsonify({'providers': available_providers()}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@llm_bp.route('/spend', methods=['GET'])
def get_spend():
    """Return the per-provider token / cost counters since process start
    (or since the last DELETE /api/llm/spend). Used by the TopBar cost
    widget to show how much the session has used."""
    try:
        return jsonify(get_spend_snapshot()), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@llm_bp.route('/spend', methods=['DELETE'])
def clear_spend():
    """Reset the spend counters. Optional ?provider=anthropic to clear only
    one provider."""
    try:
        provider = request.args.get('provider')
        reset_spend(provider)
        return jsonify({'ok': True}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
