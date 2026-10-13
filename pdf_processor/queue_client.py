import os
import redis
import json
import time
from dotenv import load_dotenv

load_dotenv()

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

    def enqueue_pdf(self, doc_id: str, filename: str, user_id: str = ""):
        """Push a PDF processing job to the queue."""
        job = {"doc_id": doc_id, "filename": filename, "timestamp": time.time()}
        self.r.rpush("queue:pdfs", json.dumps(job))
        # Initialize status with 24h TTL
        mapping = {
            "status": "queued",
            "total_chunks": 0,
            "processed_chunks": 0,
            "phase": "init",
        }
        if user_id:
            mapping["user_id"] = user_id
        self.r.hset(f"status:{doc_id}", mapping=mapping)
        self.r.expire(f"status:{doc_id}", 86400)  # auto-expire after 24h
        print(f"Enqueued PDF: {doc_id}")

    def pop_pdf_job(self):
        """Pop a PDF job from the queue (blocking)."""
        # blpop returns tuple (key, value)
        item = self.r.blpop("queue:pdfs", timeout=5)
        if item:
            return json.loads(item[1])
        return None

    def enqueue_chunk(self, doc_id: str, chunk_index: int, chunk_path: str, schema_path: str):
        """Push a chunk processing job."""
        job = {
            "doc_id": doc_id, 
            "chunk_index": chunk_index, 
            "chunk_path": chunk_path,
            "schema_path": schema_path
        }
        self.r.rpush("queue:chunks", json.dumps(job))

    def pop_chunk_job(self):
        """Pop a chunk job."""
        item = self.r.blpop("queue:chunks", timeout=5)
        if item:
            return json.loads(item[1])
        return None

    def enqueue_merge(self, doc_id: str, schema_path: str):
        """Push a merge job."""
        job = {"doc_id": doc_id, "schema_path": schema_path}
        self.r.rpush("queue:merges", json.dumps(job))
        self.r.hset(f"status:{doc_id}", "phase", "merging")

    def pop_merge_job(self):
        """Pop a merge job."""
        item = self.r.blpop("queue:merges", timeout=5)
        if item:
            return json.loads(item[1])
        return None

    def set_total_chunks(self, doc_id: str, total: int):
        self.r.hset(f"status:{doc_id}", "total_chunks", total)
        self.r.hset(f"status:{doc_id}", "phase", "processing")

    def increment_processed_chunks(self, doc_id: str):
        """Increment processed count and return (new_count, total_count)."""
        new_count = self.r.hincrby(f"status:{doc_id}", "processed_chunks", 1)
        total = int(self.r.hget(f"status:{doc_id}", "total_chunks") or 0)
        return new_count, total

    def update_status(self, doc_id: str, status: str):
        self.r.hset(f"status:{doc_id}", "status", status)
    
    def get_status(self, doc_id: str):
        return self.r.hgetall(f"status:{doc_id}")

    def get_doc_owner(self, doc_id: str) -> str:
        """Return the user_id that owns this doc, or empty string if unknown."""
        return self.r.hget(f"status:{doc_id}", "user_id") or ""

    def list_doc_ids_for_user(self, user_id: str) -> list:
        """Return all doc_ids that belong to a given user."""
        result = []
        for key in self.r.scan_iter("status:*", count=200):
            # Skip keys that belong to other processors (csv, image)
            if key.startswith("status:csv:") or key.startswith("status:image:"):
                continue
            owner = self.r.hget(key, "user_id")
            if owner == user_id:
                doc_id = key[len("status:"):]
                result.append(doc_id)
        return result

    def queue_depth(self, queue_name: str) -> int:
        """Returns the current length of a queue (for backpressure checks)."""
        return self.r.llen(queue_name)
