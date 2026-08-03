"""In-memory job registry for the web UI's long tasks.

Download, transcribe, detect, and render can each take minutes - too long for
one HTTP request. A job runs on a background thread; the UI creates it, gets an
id back immediately, and polls ``GET /api/jobs/<id>`` for progress. Single
process, single user - no queue, no persistence needed.
"""
from __future__ import annotations

import itertools
import threading
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

QUEUED, RUNNING, DONE, ERROR = "queued", "running", "done", "error"


@dataclass
class Job:
    id: str
    kind: str
    status: str = QUEUED
    progress: float = 0.0            # 0..1
    message: str = ""
    result: Any = None
    error: str | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update(self, progress: float | None = None, message: str | None = None) -> None:
        with self._lock:
            if progress is not None:
                self.progress = max(0.0, min(1.0, progress))
            if message is not None:
                self.message = message

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "id": self.id, "kind": self.kind, "status": self.status,
                "progress": round(self.progress, 3), "message": self.message,
                "result": self.result, "error": self.error,
            }


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._counter = itertools.count(1)
        self._lock = threading.Lock()

    def create(self, kind: str) -> Job:
        with self._lock:
            job = Job(id=f"job{next(self._counter)}", kind=kind)
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def run(self, job: Job, fn: Callable[[Job], Any], *, background: bool = True) -> Job:
        """Run ``fn(job)`` and capture its return as the job result. ``fn`` may
        call ``job.update(...)`` as it goes. Exceptions become job.error rather
        than crashing the server. ``background=False`` runs inline (tests)."""
        def target() -> None:
            job.status = RUNNING
            try:
                job.result = fn(job)
                job.progress = 1.0
                job.status = DONE
            except Exception as e:  # noqa: BLE001 - a failed job must not kill the server
                job.error = f"{type(e).__name__}: {e}"
                job.message = "".join(
                    traceback.format_exception_only(type(e), e)
                ).strip()[:300]
                job.status = ERROR

        if background:
            threading.Thread(target=target, daemon=True).start()
        else:
            target()
        return job
