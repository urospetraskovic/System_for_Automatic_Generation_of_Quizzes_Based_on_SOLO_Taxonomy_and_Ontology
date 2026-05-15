"""
SQLite-backed cache for Ollama LLM responses.

Keyed by hash of (model, prompt, temperature, json_mode). A cache hit returns
the stored response immediately, skipping the network call. This is a huge
dev-time win: re-generating questions or re-parsing a lesson with the same
inputs is instant.

Callers can pass `use_cache=False` to bypass for a single call (e.g. when the
user explicitly wants a fresh generation with the same prompt).
"""

import hashlib
import json
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import text

from models import engine


_TABLE_READY = False


def _ensure_table() -> None:
    """Create the cache table on first use. Idempotent."""
    global _TABLE_READY
    if _TABLE_READY:
        return
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS llm_cache ("
            "  prompt_hash TEXT PRIMARY KEY,"
            "  model TEXT NOT NULL,"
            "  response TEXT NOT NULL,"
            "  created_at TEXT NOT NULL"
            ")"
        ))
        conn.commit()
    _TABLE_READY = True


def _key(model: str, prompt: str, temperature: float, json_mode: bool) -> str:
    blob = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "temperature": round(float(temperature), 4),
            "json_mode": bool(json_mode),
        },
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def get(model: str, prompt: str, temperature: float, json_mode: bool) -> Optional[str]:
    _ensure_table()
    h = _key(model, prompt, temperature, json_mode)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT response FROM llm_cache WHERE prompt_hash = :h"),
            {"h": h},
        ).fetchone()
    return row[0] if row else None


def put(model: str, prompt: str, temperature: float, json_mode: bool, response: str) -> None:
    if not response:
        return
    _ensure_table()
    h = _key(model, prompt, temperature, json_mode)
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT OR REPLACE INTO llm_cache "
                "(prompt_hash, model, response, created_at) "
                "VALUES (:h, :m, :r, :t)"
            ),
            {"h": h, "m": model, "r": response, "t": datetime.utcnow().isoformat()},
        )
        conn.commit()


def clear() -> int:
    _ensure_table()
    with engine.connect() as conn:
        result = conn.execute(text("DELETE FROM llm_cache"))
        conn.commit()
        return result.rowcount or 0


def stats() -> Dict[str, Any]:
    _ensure_table()
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM llm_cache")).scalar() or 0
        size_bytes = conn.execute(
            text("SELECT COALESCE(SUM(LENGTH(response)), 0) FROM llm_cache")
        ).scalar() or 0
    return {"entries": int(count), "size_bytes": int(size_bytes)}
