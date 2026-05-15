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
    """
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id,
            "kind": kind,
            "status": "pending",
            "progress": {},
            "result": None,
            "error": None,
            "created_at": _now(),
            "updated_at": _now(),
        }

    def _wrapped() -> None:
        _set(job_id, status="running")
        try:
            result = runner(_make_reporter(job_id))
            _set(job_id, status="succeeded", result=result)
        except Exception as e:
            print(f"[Job:{kind}:{job_id}] FAILED: {e}")
            traceback.print_exc()
            _set(job_id, status="failed", error=str(e))

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
