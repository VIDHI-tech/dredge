"""
Redis-based job manager for smart_query analytical tasks.
Tracks background analysis jobs so the frontend can poll for completion.
"""

import json
import time
from typing import Optional, Any
from cache_utils import RedisCache


class QueryJobManager:
    KEY_PREFIX = "sq_job"

    def __init__(self):
        cache = RedisCache()
        self.r = cache.r

    def _key(self, job_id: str) -> str:
        return f"{self.KEY_PREFIX}:{job_id}"

    def create_job(
        self, job_id: str, conversation_id: str, message_id: str,
        user_id: str, db_name: str
    ):
        key = self._key(job_id)
        self.r.hset(key, mapping={
            "status": "processing",
            "conversation_id": conversation_id,
            "message_id": message_id,
            "user_id": user_id,
            "db_name": db_name,
            "created_at": str(time.time()),
        })

    def complete_job(self, job_id: str, result: dict):
        key = self._key(job_id)
        self.r.hset(key, mapping={
            "status": "complete",
            "result": json.dumps(result, default=str),
        })

    def fail_job(self, job_id: str, error: str):
        key = self._key(job_id)
        self.r.hset(key, mapping={
            "status": "error",
            "error": error,
        })

    def get_status(self, job_id: str) -> Optional[dict]:
        data = self.r.hgetall(self._key(job_id))
        return data if data else None

    def get_result(self, job_id: str) -> Optional[dict]:
        raw = self.r.hget(self._key(job_id), "result")
        if raw:
            return json.loads(raw)
        return None

    def get_job_user(self, job_id: str) -> Optional[str]:
        return self.r.hget(self._key(job_id), "user_id")
