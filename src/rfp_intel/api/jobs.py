"""Extraction jobs started from the API: run in the background, one at a time (they share the
model quota), and recorded in SQLite so the history survives a server restart. A job that was
queued or running when the server stopped is marked failed on the next start, never left
looking active.
"""

import sqlite3
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from rfp_intel.api.schemas import Job
from rfp_intel.logs import get_logger
from rfp_intel.telemetry import new_run_id

log = get_logger(__name__)
INTERRUPTED = "interrupted: the server stopped before the run finished"
MAX_KEPT = 200


class JobStore:
    """Jobs as JSON rows in the project's SQLite file."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._conn:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS jobs ("
                " job_id TEXT PRIMARY KEY, submitted_at TEXT NOT NULL, data TEXT NOT NULL)"
            )

    def save(self, job: Job) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO jobs (job_id, submitted_at, data) VALUES (?, ?, ?)",
                (job.job_id, job.submitted_at.isoformat(), job.model_dump_json()),
            )

    def load(self) -> list[Job]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT data FROM jobs ORDER BY submitted_at DESC LIMIT ?", (MAX_KEPT,)
            ).fetchall()
        return [Job.model_validate_json(data) for (data,) in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class Jobs:
    def __init__(self, store: JobStore) -> None:
        self._store = store
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="extract")
        self._jobs: dict[str, Job] = {}
        for job in store.load():
            if job.status in ("queued", "running"):
                job.status, job.error = "failed", INTERRUPTED
                job.finished_at = job.finished_at or datetime.now(UTC)
                store.save(job)
            self._jobs[job.job_id] = job

    def submit(self, bid_id: str, work: Callable[[Job], None]) -> Job:
        job = Job(job_id=uuid4().hex[:12], bid_id=bid_id, run_id=new_run_id(),
                  submitted_at=datetime.now(UTC))  # fmt: skip
        self._update(job)
        self._pool.submit(self._run, job, work)
        return job

    def _update(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.job_id] = job
        self._store.save(job)

    def _run(self, job: Job, work: Callable[[Job], None]) -> None:
        job.status, job.started_at = "running", datetime.now(UTC)
        self._update(job)
        try:
            work(job)
            job.status = "succeeded"
        except Exception as exc:  # the job records the failure; the server keeps running
            log.exception("extract_job_failed", job_id=job.job_id, bid_id=job.bid_id)
            job.status, job.error = "failed", f"{type(exc).__name__}: {exc}"
        finally:
            job.finished_at = datetime.now(UTC)
            self._update(job)

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def all(self) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.submitted_at, reverse=True)

    def active_for(self, bid_id: str) -> Job | None:
        return next(
            (j for j in self.all() if j.bid_id == bid_id and j.status in ("queued", "running")),
            None,
        )

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
        self._store.close()
