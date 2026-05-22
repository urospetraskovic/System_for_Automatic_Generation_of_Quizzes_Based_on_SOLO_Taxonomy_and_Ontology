"""
Embedding service backed by Ollama's /api/embeddings endpoint.

Why Ollama and not sentence-transformers?
  We already require Ollama for question generation, so reusing the same
  server adds zero deps (no torch install). The user just needs to
  `ollama pull nomic-embed-text` (≈270 MB) once.

Why our own SQLite cache?
  Embeddings are deterministic per (model, text). Hitting Ollama for the
  same string twice is wasted latency. We persist embeddings in a small
  table next to the existing llm_cache.

Graceful degradation:
  If the configured embedding model is not pulled or Ollama is down,
  `embed_text` returns None. Callers (mcq_lint) treat that as "skip the
  embedding-based checks" rather than crashing.
"""

import hashlib
import json
import math
import os
from typing import List, Optional

import requests
from sqlalchemy import text

from config import OLLAMA_BASE_URL
from models import engine

EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

_TABLE_READY = False


def _ensure_table() -> None:
    global _TABLE_READY
    if _TABLE_READY:
        return
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS embedding_cache ("
            "  cache_key TEXT PRIMARY KEY,"
            "  model TEXT NOT NULL,"
            "  vector TEXT NOT NULL,"
            "  created_at TEXT NOT NULL"
            ")"
        ))
        conn.commit()
    _TABLE_READY = True


def _key(model: str, content: str) -> str:
    h = hashlib.sha256(f"{model}||{content}".encode("utf-8")).hexdigest()
    return h


def _cache_get(model: str, content: str) -> Optional[List[float]]:
    _ensure_table()
    h = _key(model, content)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT vector FROM embedding_cache WHERE cache_key = :k"),
            {"k": h},
        ).fetchone()
    if row:
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            return None
    return None


def _cache_put(model: str, content: str, vector: List[float]) -> None:
    from datetime import datetime
    _ensure_table()
    h = _key(model, content)
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT OR REPLACE INTO embedding_cache "
                "(cache_key, model, vector, created_at) "
                "VALUES (:k, :m, :v, :t)"
            ),
            {
                "k": h,
                "m": model,
                "v": json.dumps(vector),
                "t": datetime.utcnow().isoformat(),
            },
        )
        conn.commit()


def embed_text(content: str, *, timeout: int = 30) -> Optional[List[float]]:
    """Return an embedding vector for `content`, or None on failure.

    None signals to callers that embedding-based checks should be skipped
    (model not pulled, Ollama down, network error, …).
    """
    if not content or not content.strip():
        return None
    cached = _cache_get(EMBED_MODEL, content)
    if cached is not None:
        return cached
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": content},
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None
        vec = resp.json().get("embedding")
        if not isinstance(vec, list) or not vec:
            return None
        _cache_put(EMBED_MODEL, content, vec)
        return vec
    except Exception:
        return None


def cosine_similarity(a: List[float], b: List[float]) -> Optional[float]:
    """Cosine similarity, or None if either vector is unusable."""
    if not a or not b or len(a) != len(b):
        return None
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return None
    return dot / (na * nb)
