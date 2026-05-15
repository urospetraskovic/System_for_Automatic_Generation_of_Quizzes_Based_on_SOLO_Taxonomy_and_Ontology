"""
Shared test setup.

- Adds backend/ to sys.path so tests can `import core.prompt_lib` directly when
  run from the repo root (pytest discovers from there).
- Stubs `requests.get` so the ContentParser / SoloQuizGeneratorLocal module-load
  connection probes don't make real network calls (or wait 5s for Ollama).
"""

import os
import sys
from unittest.mock import patch

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Block real network calls during import-time Ollama probes.
_patcher = patch('requests.get', side_effect=ConnectionError('blocked in tests'))
_patcher.start()
