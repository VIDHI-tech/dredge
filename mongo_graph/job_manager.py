"""
Redis-based job state manager for async graph-building tasks.
Stores job status and results in Redis hashes with auto-expiry.
"""

import json
import time
from typing import Any, Dict, Optional


class GraphJobManager:
    """Manages graph-building job state in Redis hashes."""

    KEY_PREFIX = "graph_job"
    # No TTL — jobs persist until explicitly replaced by a new build

    def __init__(self, redis_client):
        self.r = redis_client

    def _key(self, job_id: str) -> str:
        return f"{self.KEY_PREFIX}:{job_id}"

    def create_job(self, job_id: str, job_type: str, db_name: str,
                   use_llm: bool, force_refresh: bool,
                   user_id: Optional[str] = None):
        key = self._key(job_id)
        self.r.delete(key)
        mapping = {
            "status": "queued",
            "job_type": job_type,
            "db_name": db_name,
            "use_llm": json.dumps(use_llm),
            "force_refresh": json.dumps(force_refresh),
            "created_at": str(time.time()),
        }
        if user_id:
            mapping["user_id"] = user_id
        self.r.hset(key, mapping=mapping)

    def update_status(self, job_id: str, status: str):
        key = self._key(job_id)
        self.r.hset(key, "status", status)

    def complete_job(self, job_id: str, result: Any):
        key = self._key(job_id)
        self.r.hset(key, mapping={
            "status": "completed",
            "result": json.dumps(result, default=str),
        })

    def complete_job_with_url(self, job_id: str, result_url: str):
        """Mark job completed, storing only a URL to the result file (not the full data)."""
        key = self._key(job_id)
        self.r.hset(key, mapping={
            "status": "completed",
            "result_url": result_url,
        })

    def fail_job(self, job_id: str, error: str):
        key = self._key(job_id)
        self.r.hset(key, mapping={
            "status": "error",
            "error": error,
        })

    def get_status(self, job_id: str) -> Optional[Dict[str, str]]:
        data = self.r.hgetall(self._key(job_id))
        return data if data else None

    def get_result(self, job_id: str) -> Optional[Any]:
        raw = self.r.hget(self._key(job_id), "result")
        if raw:
            return json.loads(raw)
        return None

    def get_result_url(self, job_id: str) -> Optional[str]:
        """Get the DO Spaces URL for a streamed result."""
        return self.r.hget(self._key(job_id), "result_url")

    def get_job_db_name(self, job_id: str) -> Optional[str]:
        """Get the db_name associated with a job (for ownership verification)."""
        return self.r.hget(self._key(job_id), "db_name")

    def get_job_user_id(self, job_id: str) -> Optional[str]:
        """Get the user_id associated with a job when available."""
        return self.r.hget(self._key(job_id), "user_id")

    def get_active_jobs(self, user_id: str) -> list:
        """Return all non-terminal jobs (queued/running) for a given user."""
        active = []
        for key in self.r.scan_iter(f"{self.KEY_PREFIX}:*", count=200):
            data = self.r.hgetall(key)
            if not data:
                continue
            if data.get("user_id") != user_id:
                continue
            status = data.get("status", "")
            if status in ("completed", "error"):
                continue
            job_id = key.rsplit(":", 1)[-1]
            active.append({
                "job_id": job_id,
                "job_type": data.get("job_type", ""),
                "status": status,
                "db_name": data.get("db_name", ""),
                "created_at": data.get("created_at", ""),
            })
        return active
