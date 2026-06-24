"""
Validation-result cache.

Every batch validation endpoint (lint, SOLO judge, CoVe, IOC, etc.) computes
a sizeable JSON report keyed by lesson_id. Without persistence those reports
live only in React state — close the browser, the headlines on the panels
go blank, and the user has to click "Run" again. This module persists the
reports to SQLite so:

    * panels rehydrate instantly when ContentViewer mounts,
    * the cache survives backend restarts,
    * the user can still force a fresh run via the existing "Re-run"
      button (which calls the route with ?fresh=true).

The cache table is created on first use (CREATE TABLE IF NOT EXISTS) and
sits alongside `llm_cache` and `embedding_cache`.

Schema:
    cache_key  TEXT PK   — "<metric_key>:<scope_type>:<scope_id>"
    metric_key TEXT      — "lint", "ioc", "ambiguity", ...
    scope_type TEXT      — "lesson" or "question" (only lesson today)
    scope_id   INTEGER   — lesson id (or question id later)
    payload    TEXT      — JSON dump of the report dict
    created_at TEXT      — ISO timestamp of last write
"""

import json
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import text

from models import engine

_TABLE_READY = False


def _ensure_table() -> None:
    global _TABLE_READY
    if _TABLE_READY:
        return
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS validation_cache ("
            "  cache_key TEXT PRIMARY KEY,"
            "  metric_key TEXT NOT NULL,"
            "  scope_type TEXT NOT NULL,"
            "  scope_id INTEGER NOT NULL,"
            "  payload TEXT NOT NULL,"
            "  created_at TEXT NOT NULL"
            ")"
        ))
        conn.commit()
    _TABLE_READY = True


def _key(metric_key: str, scope_type: str, scope_id: int) -> str:
    return f"{metric_key}:{scope_type}:{scope_id}"


def put(metric_key: str, scope_id: int, payload: Dict[str, Any],
        scope_type: str = "lesson") -> None:
    """Upsert a validation report into the cache."""
    _ensure_table()
    k = _key(metric_key, scope_type, scope_id)
    blob = json.dumps(payload, ensure_ascii=False, default=str)
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT OR REPLACE INTO validation_cache "
                "(cache_key, metric_key, scope_type, scope_id, payload, created_at) "
                "VALUES (:k, :m, :st, :sid, :p, :t)"
            ),
            {
                "k": k,
                "m": metric_key,
                "st": scope_type,
                "sid": scope_id,
                "p": blob,
                "t": datetime.utcnow().isoformat(),
            },
        )
        conn.commit()


def get(metric_key: str, scope_id: int,
        scope_type: str = "lesson") -> Optional[Dict[str, Any]]:
    """Return the cached report, or None if not cached."""
    _ensure_table()
    k = _key(metric_key, scope_type, scope_id)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT payload FROM validation_cache WHERE cache_key = :k"),
            {"k": k},
        ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except json.JSONDecodeError:
        return None


def get_all_for_lesson(lesson_id: int) -> Dict[str, Any]:
    """Return every cached report for the given lesson, keyed by metric.

    Empty dict if nothing is cached yet. Used by the GET /quality-cache
    endpoint to hydrate the QualityOverviewPanel on mount.
    """
    _ensure_table()
    out: Dict[str, Any] = {}
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT metric_key, payload, created_at FROM validation_cache "
                "WHERE scope_type = 'lesson' AND scope_id = :sid"
            ),
            {"sid": lesson_id},
        ).fetchall()
    for metric_key, payload, created_at in rows:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        # Surface the timestamp so the UI can show "cached on …".
        if isinstance(data, dict):
            data.setdefault("_cached_at", created_at)
        out[metric_key] = data
    return out


def invalidate_lesson(lesson_id: int, metric_key: Optional[str] = None) -> int:
    """Drop cached reports for a lesson, optionally narrowed to one metric.

    Returns the number of rows removed. Called by question CRUD routes
    when a lesson's question set changes, because most validation reports
    are no longer accurate once questions are added / edited / deleted.
    """
    _ensure_table()
    with engine.connect() as conn:
        if metric_key:
            res = conn.execute(
                text(
                    "DELETE FROM validation_cache "
                    "WHERE scope_type = 'lesson' AND scope_id = :sid "
                    "AND metric_key = :mk"
                ),
                {"sid": lesson_id, "mk": metric_key},
            )
        else:
            res = conn.execute(
                text(
                    "DELETE FROM validation_cache "
                    "WHERE scope_type = 'lesson' AND scope_id = :sid"
                ),
                {"sid": lesson_id},
            )
        conn.commit()
    return res.rowcount or 0


def invalidate_question(question_id: int) -> int:
    """When a question is edited or deleted, invalidate every lesson cache
    that might mention it. Cheaper than tracking per-question scope:
    just nuke whichever lessons own this question."""
    from models import Question, Session
    session = Session()
    try:
        q = session.query(Question).filter(Question.id == question_id).first()
        if not q:
            return 0
        affected_lessons = set()
        if q.primary_lesson_id:
            affected_lessons.add(q.primary_lesson_id)
        if q.secondary_lesson_id:
            affected_lessons.add(q.secondary_lesson_id)
    finally:
        session.close()
    total = 0
    for lid in affected_lessons:
        total += invalidate_lesson(lid)
    return total


def clear_all() -> int:
    _ensure_table()
    with engine.connect() as conn:
        res = conn.execute(text("DELETE FROM validation_cache"))
        conn.commit()
    return res.rowcount or 0
