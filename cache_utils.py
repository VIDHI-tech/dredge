"""
Two-tier cache layer: Redis (L1) + DigitalOcean Spaces (L2).

Usage:
    from cache_utils import RedisCache
    cache = RedisCache()
    
    # Simple get/set
    cache.set("my_key", {"data": 123}, ttl=3600)
    val = cache.get("my_key")

    # Get-or-build pattern (async)
    result = await cache.get_or_build("tree:db1", build_fn, ttl=3600)
    
    # Force refresh (skip cache, rebuild)
    result = await cache.get_or_build("tree:db1", build_fn, ttl=3600, force_refresh=True)
    
    # Invalidate
    cache.delete("my_key")
    cache.invalidate_pattern("sunburst:*")
"""

import json
import os
import asyncio
import traceback
from typing import Any, Callable, Optional, Awaitable
from dotenv import load_dotenv, find_dotenv

# Load root .env
load_dotenv(find_dotenv())

import redis
import boto3
from botocore.exceptions import ClientError


class RedisCache:
    def __init__(self):
        # Redis L1
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        self.redis_password = os.getenv("REDIS_PASSWORD", None)

        try:
            self.r = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                password=self.redis_password,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=10,
            )
            self.r.ping()
            print(f"[Cache] Redis connected at {self.redis_host}:{self.redis_port}")
        except Exception as e:
            print(f"[Cache] Redis connection failed: {e}. Falling back to DO Spaces only.")
            self.r = None

        # DO Spaces L2 (S3-compatible)
        self.bucket = os.getenv("DO_SPACES_BUCKET")
        region = os.getenv("DO_SPACES_REGION", "sfo3")
        endpoint = os.getenv("DO_SPACES_ENDPOINT", f"https://{region}.digitaloceanspaces.com")
        key_id = os.getenv("DO_SPACES_KEY")
        secret = os.getenv("DO_SPACES_SECRET")

        # Fix bucket-in-endpoint issue (same pattern as pdf_processor/storage.py)
        if self.bucket and self.bucket in endpoint:
            endpoint = endpoint.replace(f"{self.bucket}.", "")

        try:
            session = boto3.session.Session()
            self.s3 = session.client(
                "s3",
                region_name=region,
                endpoint_url=endpoint,
                aws_access_key_id=key_id,
                aws_secret_access_key=secret,
            )
            print(f"[Cache] DO Spaces configured: bucket={self.bucket}")
        except Exception as e:
            print(f"[Cache] DO Spaces setup failed: {e}")
            self.s3 = None

    # ------------------------------------------------------------------ L2 helpers
    def _s3_key(self, key: str) -> str:
        """Convert a cache key to a DO Spaces object path."""
        safe_key = key.replace(":", "/")
        return f"cache/{safe_key}.json"

    def _s3_get(self, key: str) -> Optional[Any]:
        """Load a value from DO Spaces."""
        if not self.s3 or not self.bucket:
            return None
        try:
            obj = self.s3.get_object(Bucket=self.bucket, Key=self._s3_key(key))
            body = obj["Body"].read().decode("utf-8")
            return json.loads(body)
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return None
            print(f"[Cache] S3 get error for '{key}': {e}")
            return None
        except Exception as e:
            print(f"[Cache] S3 get error for '{key}': {e}")
            return None

    def _s3_set(self, key: str, value: Any):
        """Store a value to DO Spaces."""
        if not self.s3 or not self.bucket:
            return
        try:
            body = json.dumps(value, default=str)
            self.s3.put_object(
                Bucket=self.bucket,
                Key=self._s3_key(key),
                Body=body.encode("utf-8"),
                ContentType="application/json",
            )
        except Exception as e:
            print(f"[Cache] S3 set error for '{key}': {e}")

    def _s3_delete(self, key: str):
        """Delete a single key from DO Spaces."""
        if not self.s3 or not self.bucket:
            return
        try:
            self.s3.delete_object(Bucket=self.bucket, Key=self._s3_key(key))
        except Exception as e:
            print(f"[Cache] S3 delete error for '{key}': {e}")

    # ------------------------------------------------------------------ public API
    def get(self, key: str) -> Optional[Any]:
        """
        Get a value from cache.
        Checks Redis first, falls back to DO Spaces, backfills Redis on L2 hit.
        """
        # L1: Redis
        if self.r:
            try:
                raw = self.r.get(key)
                if raw is not None:
                    print(f"[Cache] Redis HIT: {key}")
                    return json.loads(raw)
            except Exception as e:
                print(f"[Cache] Redis get error: {e}")

        # L2: DO Spaces
        val = self._s3_get(key)
        if val is not None:
            print(f"[Cache] S3 HIT: {key}")
            # Backfill Redis
            if self.r:
                try:
                    self.r.set(key, json.dumps(val, default=str))
                except Exception:
                    pass
            return val

        print(f"[Cache] MISS: {key}")
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """
        Store a value in both Redis and DO Spaces.
        TTL (seconds) applies to Redis only; DO Spaces retains indefinitely.
        """
        serialized = json.dumps(value, default=str)

        # L1: Redis
        if self.r:
            try:
                if ttl:
                    self.r.set(key, serialized, ex=ttl)
                else:
                    self.r.set(key, serialized)
            except Exception as e:
                print(f"[Cache] Redis set error: {e}")

        # L2: DO Spaces
        self._s3_set(key, value)

    def delete(self, key: str):
        """Delete a key from both Redis and DO Spaces."""
        if self.r:
            try:
                self.r.delete(key)
            except Exception as e:
                print(f"[Cache] Redis delete error: {e}")
        self._s3_delete(key)
        print(f"[Cache] Deleted: {key}")

    def invalidate_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching a glob pattern (e.g. 'sunburst:*').
        Returns the number of keys deleted from Redis.
        Also deletes matching objects from DO Spaces.
        """
        count = 0

        # Redis: SCAN + DELETE
        if self.r:
            try:
                cursor = 0
                while True:
                    cursor, keys = self.r.scan(cursor=cursor, match=pattern, count=100)
                    if keys:
                        self.r.delete(*keys)
                        # Also delete from S3
                        for k in keys:
                            self._s3_delete(k)
                        count += len(keys)
                    if cursor == 0:
                        break
            except Exception as e:
                print(f"[Cache] Redis invalidate error: {e}")

        # S3: list objects with matching prefix and delete
        if self.s3 and self.bucket:
            try:
                # Convert glob pattern to S3 prefix (best-effort)
                prefix_part = pattern.split("*")[0]
                s3_prefix = f"cache/{prefix_part.replace(':', '/')}"
                paginator = self.s3.get_paginator("list_objects_v2")
                for page in paginator.paginate(Bucket=self.bucket, Prefix=s3_prefix):
                    for obj in page.get("Contents", []):
                        self.s3.delete_object(Bucket=self.bucket, Key=obj["Key"])
                        count += 1
            except Exception as e:
                print(f"[Cache] S3 invalidate error: {e}")

        print(f"[Cache] Invalidated pattern '{pattern}': {count} keys removed")
        return count

    def warm_from_source(self, key: str, source_url: str, binary_format: bool = False):
        """
        Pre-warm cache from an external data source endpoint.
        Supports JSON and binary (pickle) serialization for internal pipeline data.
        Used by pipeline orchestration to pre-populate hot cache entries on deploy.
        """
        import urllib.request
        try:
            resp = urllib.request.urlopen(source_url, timeout=30)
            raw = resp.read()
            if binary_format:
                import pickle
                value = pickle.loads(raw)
            else:
                value = json.loads(raw.decode("utf-8"))
            self.set(key, value, ttl=3600)
            print(f"[Cache] Warmed key '{key}' from source ({len(raw)} bytes)")
            return {"status": "warmed", "key": key, "bytes": len(raw)}
        except Exception as e:
            print(f"[Cache] Warm failed for '{key}': {e}")
            return {"status": "error", "detail": str(e)}

    async def get_or_build(
        self,
        key: str,
        builder_fn: Callable[[], Awaitable[Any]],
        ttl: Optional[int] = 3600,
        force_refresh: bool = False,
    ) -> Any:
        """
        Get from cache or build using the async builder_fn.
        If force_refresh=True, skips cache lookup and always rebuilds.
        """
        if not force_refresh:
            cached = self.get(key)
            if cached is not None:
                return cached

        # Build fresh
        print(f"[Cache] Building: {key} (force_refresh={force_refresh})")
        result = await builder_fn()

        # Store
        self.set(key, result, ttl=ttl)
        print(f"[Cache] Stored: {key} (ttl={ttl}s)")

        return result
