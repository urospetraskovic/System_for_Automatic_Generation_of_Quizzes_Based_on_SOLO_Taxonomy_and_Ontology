"""
In-process background-job runner with progress reporting.

Why not Celery? Because for a single-process Flask dev server, a thread pool
plus an in-memory dict is enough. Jobs do not survive a backend restart —
that's fine; this is a UX fix (don't freeze the user on a 30-second HTTP
request), not a durability story.

Job lifecycle:
  pending -> running -> (succeeded | failed | cancelled)

A job's `runner` callable receives a `report_progress` function it can call
to push status updates. Anything it returns becomes the job's result.
"""

import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Callable, Dict, Optional


_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bgjob")
_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def _now() -> str:
    return datetime.utcnow().isoformat()


def _set(job_id: str, **updates: Any) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(updates)
            _jobs[job_id]["updated_at"] = _now()


def _make_reporter(job_id: str) -> Callable[..., None]:
    def report(message: Optional[str] = None, current: Optional[int] = None,
               total: Optional[int] = None, **extra: Any) -> None:
        progress: Dict[str, Any] = {}
        with _jobs_lock:
            if job_id not in _jobs:
                return
            progress = dict(_jobs[job_id].get("progress") or {})
        if message is not None:
            progress["message"] = message
        if current is not None:
            progress["current"] = current
        if total is not None:
            progress["total"] = total
        if extra:
            progress.update(extra)
        _set(job_id, progress=progress)
    return report


def submit(kind: str, runner: Callable[[Callable[..., None]], Any]) -> str:
    """
    Submit a job. `runner` is called with a progress-reporter callable and
    can return any JSON-serializable value.

    The job inherits the active LLM provider from the calling request, since
    background threads cannot read `g.llm_provider` themselves. Without this
    capture, a user who selected "anthropic" in the UI would still see every
    background generation call hit Ollama (the default).
    """
    # Capture the provider choice while we are still inside the request thread.
    provider_name: Optional[str] = None
    try:
        from flask import g, has_request_context
        if has_request_context():
            provider_name = getattr(g, "llm_provider", None)
    except Exception:
        pass

    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id,
            "kind": kind,
            "status": "pending",
            "progress": {},
            "result": None,
            "error": None,
            "provider": provider_name,
            "created_at": _now(),
            "updated_at": _now(),
        }

    def _wrapped() -> None:
        # Pin the provider on this worker thread so every call_llm() inside
        # `runner` sees the user's chosen provider, not the env-var default.
        from core.llm_provider import set_thread_provider, clear_thread_provider
        if provider_name:
            set_thread_provider(provider_name)
            print(f"[Job:{kind}:{job_id}] Using provider: {provider_name}", flush=True)

        _set(job_id, status="running")
        try:
            result = runner(_make_reporter(job_id))
            _set(job_id, status="succeeded", result=result)
        except Exception as e:
            print(f"[Job:{kind}:{job_id}] FAILED: {e}")
            traceback.print_exc()
            _set(job_id, status="failed", error=str(e))
        finally:
            clear_thread_provider()

    _executor.submit(_wrapped)
    return job_id


def get(job_id: str) -> Optional[Dict[str, Any]]:
    with _jobs_lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def list_recent(limit: int = 20) -> list:
    with _jobs_lock:
        jobs = list(_jobs.values())
    jobs.sort(key=lambda j: j.get("updated_at", ""), reverse=True)
    return [
        {k: v for k, v in j.items() if k != "result"}
        for j in jobs[:limit]
    ]
