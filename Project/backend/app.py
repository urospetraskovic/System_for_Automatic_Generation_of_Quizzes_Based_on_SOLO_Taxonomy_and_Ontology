"""
SOLO Quiz Generator - Backend API entry point.

Builds the Flask app, wires up shared services, and registers all blueprints.
Routes are defined under the `routes/` package, business logic under `services/`.
"""

from flask import Flask, g, request
from flask_cors import CORS

import config
from repository import init_database
from models import Session
from core import SoloQuizGeneratorLocal as SoloQuizGenerator
from services.sparql_service import sparql_service
from services.chatbot_service import chatbot_service
from routes import register_routes


_ALLOWED_PROVIDERS = {"ollama", "anthropic"}


def _resolve_provider_from_request() -> str:
    """Pick the LLM provider for this request.

    Priority: `X-LLM-Provider` request header → `?provider=` query param →
    LLM_PROVIDER env var → "ollama" default. Unknown values fall through to
    the default so a bad client header can't break a request.
    """
    import os
    header = (request.headers.get("X-LLM-Provider") or "").strip().lower()
    if header in _ALLOWED_PROVIDERS:
        return header
    query = (request.args.get("provider") or "").strip().lower()
    if query in _ALLOWED_PROVIDERS:
        return query
    env = (os.getenv("LLM_PROVIDER") or "ollama").strip().lower()
    return env if env in _ALLOWED_PROVIDERS else "ollama"


def _bootstrap_services():
    """Initialise shared singletons (DB, SPARQL ontology, chatbot session)."""
    init_database()
    print("[STARTUP] Database initialized")

    # Instantiated for its side effects / so the service is loaded at startup,
    # in line with the historical app.py behaviour.
    SoloQuizGenerator()

    sparql_service.load_ontology()
    chatbot_service.set_db_session(Session())


def create_app():
    """Application factory."""
    app = Flask(__name__)
    # CORS must allow our own header so the frontend can drive provider choice.
    CORS(app, expose_headers=["X-LLM-Provider"], allow_headers=["*", "X-LLM-Provider"])

    config.ensure_folders()
    config.apply_to(app)

    @app.before_request
    def _set_provider_on_g():
        g.llm_provider = _resolve_provider_from_request()

    print("[STARTUP] Flask app initialized")

    _bootstrap_services()
    register_routes(app)

    print("[STARTUP] Starting SOLO Quiz Generator API...")
    return app


app = create_app()


if __name__ == '__main__':
    app.run(debug=True, host='localhost', port=5000)
