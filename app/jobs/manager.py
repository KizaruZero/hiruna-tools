"""Background job system.

Downloads run in a worker thread pool — never blocking the HTTP request.
Each job produces one temp file that auto-expires after FILE_RETENTION_HOURS.
A sweeper thread deletes expired files and prunes finished job records.

Everything is in-process and local-first: no Redis, no database.
"""
from __future__ import annotations

import os
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from app.config import settings

# Job statuses
QUEUED = "queued"
RUNNING = "running"
DONE = "done"
FAILED = "failed"


@dataclass
class Job:
    id: str
    kind: str                      # "download"
    label: str                     # human-readable, e.g. video title
    status: str = QUEUED
    progress: float = 0.0          # 0..1
    downloaded_bytes: int = 0
    total_bytes: Optional[int] = None
    filename: str = ""             # suggested download filename
    file_path: str = ""            # absolute temp path (internal)
    error: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    def to_dict(self, public: bool = True) -> dict:
        d = {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "status": self.status,
            "progress": round(self.progress, 3),
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "filename": self.filename,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }
        if not public:
            d["file_path"] = self.file_path
        return d


class JobManager:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mt-job")
        self._tmpdir = os.path.join(settings.data_dir, "tmp")
        os.makedirs(self._tmpdir, exist_ok=True)
        self._sweeper = threading.Thread(target=self._sweep_loop, daemon=True)
        self._sweeper.start()

    # -- public API -----------------------------------------------------
    def submit(self, kind: str, label: str, filename: str,
               fn: Callable[[str, Callable[[int, Optional[int]], None]], None]) -> Job:
        """Enqueue work. fn(dest_path, progress_cb) does the real download."""
        job_id = uuid.uuid4().hex
        safe_name = _safe_filename(filename) or f"download-{job_id[:8]}"
        dest = os.path.join(self._tmpdir, f"{job_id}-{safe_name}")
        job = Job(id=job_id, kind=kind, label=label, filename=safe_name,
                  file_path=dest)
        with self._lock:
            self._jobs[job_id] = job
        self._pool.submit(self._run, job_id, fn, dest)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    # -- internals -------------------------------------------------------
    def _run(self, job_id: str, fn, dest: str) -> None:
        job = self.get(job_id)
        if not job:
            return
        job.status = RUNNING
        started = time.monotonic()

        def progress(downloaded: int, total: Optional[int]) -> None:
            job.downloaded_bytes = downloaded
            job.total_bytes = total
            if total:
                job.progress = min(1.0, downloaded / total)
            # Hard stop on runaway jobs.
            if time.monotonic() - started > settings.max_job_seconds:
                raise TimeoutError("Processing took too long — job stopped.")

        try:
            fn(dest, progress)
            size = os.path.getsize(dest)
            if size > settings.max_file_mb * 1024 * 1024:
                os.remove(dest)
                raise ValueError(
                    f"Result is {size / 1048576:.0f} MB, over the "
                    f"{settings.max_file_mb} MB limit."
                )
            job.status = DONE
            job.progress = 1.0
        except Exception as e:  # noqa: BLE001 - surfaced as message
            job.status = FAILED
            job.error = str(e)[:500] or "Download failed."
            try:
                if os.path.exists(dest):
                    os.remove(dest)
            except OSError:
                pass
        finally:
            now = datetime.now(timezone.utc)
            job.finished_at = now
            job.expires_at = now + timedelta(hours=settings.file_retention_hours)

    def _sweep_loop(self) -> None:
        while True:
            time.sleep(settings.cleanup_interval_seconds)
            self.sweep()

    def sweep(self) -> int:
        """Delete expired files + prune old job records. Returns files removed."""
        now = datetime.now(timezone.utc)
        removed = 0
        with self._lock:
            ids = list(self._jobs.keys())
        for job_id in ids:
            job = self.get(job_id)
            if not job or not job.finished_at:
                continue
            if job.expires_at and now >= job.expires_at:
                try:
                    if job.file_path and os.path.exists(job.file_path):
                        os.remove(job.file_path)
                        removed += 1
                except OSError:
                    pass
                with self._lock:
                    self._jobs.pop(job_id, None)
        # Belt and braces: remove stray files older than 2x retention.
        cutoff = time.time() - settings.file_retention_hours * 7200
        try:
            for name in os.listdir(self._tmpdir):
                p = os.path.join(self._tmpdir, name)
                try:
                    if os.path.isfile(p) and os.path.getmtime(p) < cutoff:
                        os.remove(p)
                        removed += 1
                except OSError:
                    pass
        except OSError:
            pass
        return removed

    def stats(self) -> dict:
        with self._lock:
            jobs = list(self._jobs.values())
        by_status: dict[str, int] = {}
        for j in jobs:
            by_status[j.status] = by_status.get(j.status, 0) + 1
        try:
            disk = shutil.disk_usage(self._tmpdir)
            total, free = disk.total, disk.free
        except OSError:
            total, free = 0, 0
        return {
            "jobs_total": len(jobs),
            "jobs_by_status": by_status,
            "tmpdir": self._tmpdir,
            "disk_total_bytes": total,
            "disk_free_bytes": free,
        }


def _safe_filename(name: str) -> str:
    """Strip path components and unsafe characters from a filename."""
    name = os.path.basename(name).strip()
    keep = []
    for ch in name:
        if ch.isalnum() or ch in (" ", ".", "-", "_", "(", ")", "[", "]"):
            keep.append(ch)
    clean = "".join(keep).strip().strip(".")
    return clean[:120]


manager = JobManager()
