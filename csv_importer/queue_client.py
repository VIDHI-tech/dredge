import os
import redis
import json
import time
from dotenv import load_dotenv

from pathlib import Path
# Load .env from the same directory
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

# Redis Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

class QueueClient:
    def __init__(self):
        self.r = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            decode_responses=True
        )
        print(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")

    def enqueue_csv(self, doc_id: str, filename: str, user_id: str = ""):
        """Push a CSV processing job to the queue."""
        job = {"doc_id": doc_id, "filename": filename, "timestamp": time.time()}
        self.r.rpush("queue:csvs", json.dumps(job))
        # Initialize status
        mapping = {
            "status": "queued",
            "total_chunks": 0,
            "processed_chunks": 0,
            "phase": "init",
        }
        if user_id:
            mapping["user_id"] = user_id
        self.r.hset(f"status:csv:{doc_id}", mapping=mapping)
        print(f"Enqueued CSV: {doc_id}")

    def pop_csv_job(self):
        """Pop a CSV job from the queue (blocking)."""
        item = self.r.blpop("queue:csvs", timeout=5)
        if item:
            return json.loads(item[1])
        return None

    def enqueue_chunk(self, doc_id: str, chunk_index: int, chunk_path: str):
        """Push a chunk processing job."""
        job = {
            "doc_id": doc_id, 
            "chunk_index": chunk_index, 
            "chunk_path": chunk_path
        }
        self.r.rpush("queue:csv_chunks", json.dumps(job))

    def pop_chunk_job(self):
        """Pop a chunk job."""
        item = self.r.blpop("queue:csv_chunks", timeout=5)
        if item:
            return json.loads(item[1])
        return None

    def enqueue_merge(self, doc_id: str):
        """Push a merge job."""
        job = {"doc_id": doc_id}
        self.r.rpush("queue:csv_merges", json.dumps(job))
        self.r.hset(f"status:csv:{doc_id}", "phase", "merging")

    def pop_merge_job(self):
        """Pop a merge job."""
        item = self.r.blpop("queue:csv_merges", timeout=5)
        if item:
            return json.loads(item[1])
        return None

    def set_total_chunks(self, doc_id: str, total: int):
        self.r.hset(f"status:csv:{doc_id}", "total_chunks", total)
        self.r.hset(f"status:csv:{doc_id}", "phase", "processing")

    def increment_processed_chunks(self, doc_id: str):
        """Increment processed count and return (new_count, total_count)."""
        new_count = self.r.hincrby(f"status:csv:{doc_id}", "processed_chunks", 1)
        total = int(self.r.hget(f"status:csv:{doc_id}", "total_chunks") or 0)
        return new_count, total

    def update_status(self, doc_id: str, status: str):
        self.r.hset(f"status:csv:{doc_id}", "status", status)
    
    def get_status(self, doc_id: str):
        return self.r.hgetall(f"status:csv:{doc_id}")

    def get_doc_owner(self, doc_id: str) -> str:
        """Return the user_id that owns this doc, or empty string if unknown."""
        return self.r.hget(f"status:csv:{doc_id}", "user_id") or ""

    def list_doc_ids_for_user(self, user_id: str) -> list:
        """Return all doc_ids that belong to a given user."""
        result = []
        for key in self.r.scan_iter("status:csv:*", count=200):
            owner = self.r.hget(key, "user_id")
            if owner == user_id:
                doc_id = key.split("status:csv:", 1)[-1]
                result.append(doc_id)
        return result
