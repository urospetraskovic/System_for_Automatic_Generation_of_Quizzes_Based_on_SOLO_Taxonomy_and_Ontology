"""Application configuration constants and folder bootstrapping."""

import os

from dotenv import load_dotenv

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))

# Load .env once for the whole backend.
load_dotenv(os.path.join(BACKEND_DIR, '.env'))

UPLOAD_FOLDER = os.path.join(BACKEND_DIR, 'uploads')
LESSON_FOLDER = os.path.join(BACKEND_DIR, 'lessons')

ALLOWED_EXTENSIONS = {'pdf'}
MAX_FILE_SIZE = 30 * 1024 * 1024  # 30 MB

# ----- Ollama (single source of truth for every backend module) -----
# Both OLLAMA_URL (used by chatbot historically) and OLLAMA_BASE_URL are
# accepted so existing .env files keep working.
OLLAMA_BASE_URL = (
    os.getenv('OLLAMA_BASE_URL')
    or os.getenv('OLLAMA_URL')
    or 'http://127.0.0.1:11435'
)
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'qwen2.5:14b-instruct-q4_K_M')


def ensure_folders():
    """Create upload/lesson folders if they don't already exist."""
    for folder in (UPLOAD_FOLDER, LESSON_FOLDER):
        os.makedirs(folder, exist_ok=True)


def apply_to(app):
    """Apply config values to a Flask app instance."""
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.config['LESSON_FOLDER'] = LESSON_FOLDER
    app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE
