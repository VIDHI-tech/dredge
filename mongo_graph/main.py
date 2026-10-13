import asyncio
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import os
import sys
import gc
import time
import uuid
import traceback as tb_module
import json
import orjson
from dotenv import load_dotenv, find_dotenv

# Add parent to path for auth import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth.auth_utils import get_current_user
from cache_utils import RedisCache

# Load root .env
load_dotenv(find_dotenv())

from .tree_builder import TreeBuilder
from .user_tree_builder import UserTreeBuilder, DEBUG_LIMIT as _UTB_DEBUG_LIMIT
from .schema_manager import SchemaManager
from .llm_analyzer import LLMAnalyzer
from .job_manager import GraphJobManager

# Configuration
MONGO_URI = os.getenv("MONGO_URI")

# Global instances
cache = RedisCache()
tree_builder = TreeBuilder(MONGO_URI, cache=cache)
user_tree_builder = UserTreeBuilder(MONGO_URI, cache=cache)
schema_manager = SchemaManager(tree_builder.client, cache=cache)
llm_analyzer = LLMAnalyzer(cache=cache)

# Persisted field mappings from the last graph build (used by query endpoint)
_last_field_mappings = {}
GRAPH_RESULT_TYPES = ("sunburst", "usertree")
GRAPH_RESULT_KEY_PREFIX = "graph_latest"

# Job manager for async graph builds
job_manager = GraphJobManager(cache.r)

# Global build lock — only one heavy build runs at a time; others queue.
_build_lock = asyncio.Lock()

app = FastAPI(title="Mongo Graph")


async def _resume_incomplete_identity_builds():
    try:
        resumed = 0
        db_names = await tree_builder.client.list_database_names()
        valid_dbs = [d for d in db_names if d not in ("admin", "local", "config")]

        for db_name in valid_dbs:
            resumable_builds = await user_tree_builder.list_resumable_builds(db_name)
            for build in resumable_builds:
                build_id = build["build_id"]
                user_id = build.get("owner_user_id")
                if not user_id:
                    continue

                use_llm = bool(build.get("use_llm"))
                job_manager.create_job(
                    build_id,
                    "usertree",
                    db_name,
                    use_llm,
                    False,
                    user_id=user_id,
                )
                job_manager.update_status(build_id, "building_index")
                asyncio.create_task(
                    _run_graph_job(
                        build_id,
                        "usertree",
                        db_name,
                        user_id,
                        use_llm,
                        False,
                    )
                )
                resumed += 1

        if resumed:
            print(f"[Startup] Resumed {resumed} incomplete identity build(s).")
    except Exception as e:
        print(f"[Startup] Failed to resume incomplete identity builds: {e}")


@app.on_event("startup")
async def startup():
    print(f"Connecting to MongoDB at {MONGO_URI}...")
    try:
        await tree_builder.client.admin.command('ping')
        print("MongoDB Connected Successfully!")
        # await _resume_incomplete_identity_builds()
    except Exception as e:
        print(f"Error connecting to MongoDB: {e}")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models
class GraphRequest(BaseModel):
    target_db: str = "test"
    use_llm: bool = True
    force_refresh: bool = False
    collection: Optional[str] = None  # single bucket name or "b1+b2" for merged

class QueryRequest(BaseModel):
    db: str = "test"
    field: str
    value: Optional[str] = None
    concept: Optional[str] = None

class SchemaRequest(BaseModel):
    force_refresh: bool = False

class CacheClearRequest(BaseModel):
    target: str = "all"  # "sunburst", "usertree", "schema", "llm", or "all"

class NodeInsightRequest(BaseModel):
    field: str
    value: str

class ExpandRequest(BaseModel):
    build_id: str
    user_key: str
    node_type: Optional[str] = None
    scope: str = ""
    field_path: Optional[str] = None
    norm_value: str
    role: str = "identity"
    cursor: Optional[str] = None
    limit: int = 50

# Endpoints
@app.get("/api/databases")
async def get_databases(current_user: dict = Depends(get_current_user)):
    """Returns a list of available databases."""
    return {"databases": [current_user["db_name"]]}

@app.get("/api/schema")
async def get_schema(current_user: dict = Depends(get_current_user)):
    """Returns a list of potential keys (columns) found in the database."""
    db_name = current_user["db_name"]
    try:
        keys = await tree_builder.get_schema_summary(target_db_name=db_name)
        return {"keys": list(keys)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/schema-cache")
async def get_schema_cache(current_user: dict = Depends(get_current_user)):
    """Returns the full schema cache for all collections in the database."""
    db_name = current_user["db_name"]
    try:
        full_schema = await schema_manager.get_full_schema(db_name)
        return {
            "db": db_name,
            "collections": list(full_schema.keys()),
            "schema": full_schema,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _run_schema_job(job_id: str, db_name: str, force_refresh: bool):
    """Background task that fetches the full schema cache."""
    try:
        job_manager.update_status(job_id, "schema")
        print(f"[Job {job_id}] Building schema cache for {db_name}...")
        full_schema = await schema_manager.get_full_schema(
            db_name, force_refresh=force_refresh
        )
        result = {
            "db": db_name,
            "collections": list(full_schema.keys()),
            "schema": full_schema,
        }
        job_manager.complete_job(job_id, result)
        print(f"[Job {job_id}] Schema cache built successfully.")
    except Exception:
        error_msg = tb_module.format_exc()
        print(f"[Job {job_id}] Schema job failed: {error_msg}")
        job_manager.fail_job(job_id, error_msg)


@app.post("/api/schema-cache")
async def build_schema_cache(request: SchemaRequest, background_tasks: BackgroundTasks,
                             current_user: dict = Depends(get_current_user)):
    """Kicks off an async schema cache build. Returns a job_id for polling."""
    job_id = str(uuid.uuid4())
    db_name = current_user["db_name"]
    job_manager.create_job(
        job_id,
        "schema",
        db_name,
        False,
        request.force_refresh,
        user_id=current_user["user_id"],
    )
    background_tasks.add_task(_run_schema_job, job_id, db_name, request.force_refresh)
    return {"job_id": job_id, "status": "queued"}

def _cleanup_graph_files(db_name: str, prefix: str = "graph_results"):
    """Delete all old graph result files for a user's database from DO Spaces."""
    if not cache.s3 or not cache.bucket:
        return 0
    s3_prefix = f"{prefix}/{db_name}/"
    deleted = 0
    try:
        paginator = cache.s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=cache.bucket, Prefix=s3_prefix):
            for obj in page.get("Contents", []):
                cache.s3.delete_object(Bucket=cache.bucket, Key=obj["Key"])
                deleted += 1
        if deleted:
            print(f"[Cleanup] Deleted {deleted} old graph files under {s3_prefix}")
    except Exception as e:
        print(f"[Cleanup] Error cleaning {s3_prefix}: {e}")
    return deleted


def _delete_s3_key(s3_key: str, job_id: str = ""):
    """Delete a single file from DO Spaces. Used to remove the previous build after a successful rebuild."""
    if not cache.s3 or not cache.bucket or not s3_key:
        return
    try:
        cache.s3.delete_object(Bucket=cache.bucket, Key=s3_key)
        print(f"[Job {job_id}] Deleted previous build from DO Spaces: {s3_key}")
    except Exception as e:
        print(f"[Job {job_id}] Warning: could not delete old build {s3_key}: {e}")


def _graph_variant(use_llm: bool) -> str:
    return "llm" if use_llm else "plain"


def _latest_graph_key(user_id: str, job_type: str, use_llm: bool) -> str:
    return f"{GRAPH_RESULT_KEY_PREFIX}:{user_id}:{job_type}:{_graph_variant(use_llm)}"


def _clear_latest_graph_records(user_id: str, job_type: Optional[str] = None) -> int:
    cleared = 0
    job_types = (job_type,) if job_type else GRAPH_RESULT_TYPES
    for current_job_type in job_types:
        for use_llm in (True, False):
            key = _latest_graph_key(user_id, current_job_type, use_llm)
            if cache.get(key) is not None:
                cache.delete(key)
                cleared += 1
    return cleared


def _store_latest_graph_result(
    user_id: str,
    db_name: str,
    job_type: str,
    use_llm: bool,
    job_id: str,
    result: Optional[dict] = None,
    result_url: Optional[str] = None,
):
    record = {
        "job_id": job_id,
        "job_type": job_type,
        "db_name": db_name,
        "user_id": user_id,
        "use_llm": use_llm,
        "updated_at": time.time(),
    }
    if result_url:
        record["result_url"] = result_url
    else:
        record["result"] = result
    cache.set(_latest_graph_key(user_id, job_type, use_llm), record)


def _get_latest_graph_record(user_id: str, job_type: str, use_llm: Optional[bool]) -> Optional[dict]:
    if use_llm is not None:
        exact = cache.get(_latest_graph_key(user_id, job_type, use_llm))
        if exact is not None:
            return exact
        return cache.get(_latest_graph_key(user_id, job_type, not use_llm))

    candidates = []
    for variant in (True, False):
        record = cache.get(_latest_graph_key(user_id, job_type, variant))
        if record is not None:
            candidates.append(record)
    if not candidates:
        return None
    return max(candidates, key=lambda item: float(item.get("updated_at", 0)))


def _load_result_from_spaces(s3_key: str) -> dict:
    if not cache.s3 or not cache.bucket:
        raise HTTPException(status_code=500, detail="Storage not configured")
    try:
        obj = cache.s3.get_object(Bucket=cache.bucket, Key=s3_key)
        return orjson.loads(obj["Body"].read())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve data: {str(e)}")


def _job_owned_by_current_user(job_id: str, current_user: dict) -> bool:
    job_user_id = job_manager.get_job_user_id(job_id)
    if job_user_id:
        return job_user_id == current_user["user_id"]
    job_db = job_manager.get_job_db_name(job_id)
    return job_db == current_user["db_name"]


def _upload_result_to_spaces(data: dict, db_name: str, job_id: str,
                             job_type: str, use_llm: bool) -> str:
    """Serialize with orjson and upload to DO Spaces. Returns the S3 key."""
    json_bytes = orjson.dumps(data, default=str)
    s3_key = f"graph_results/{db_name}/{job_type}/{_graph_variant(use_llm)}/{job_id}.json"
    if cache.s3 and cache.bucket:
        cache.s3.put_object(
            Bucket=cache.bucket,
            Key=s3_key,
            Body=json_bytes,
            ContentType="application/json",
        )
        print(f"[Job {job_id}] Uploaded {len(json_bytes):,} bytes to DO Spaces: {s3_key}")
    else:
        print(f"[Job {job_id}] WARNING: No DO Spaces configured, falling back to Redis")
        # Fallback: store in Redis if no S3 (dev mode)
        job_manager.complete_job(job_id, data)
        return ""
    del json_bytes
    gc.collect()
    return s3_key


def _upload_tree_file_to_spaces(tree_path: str, field_groups: list,
                                db_name: str, job_id: str,
                                job_type: str, use_llm: bool) -> str:
    """Stream-upload a tree JSON file wrapped with field_groups to DO Spaces.

    Combines {"tree": <tree_file>, "field_groups": [...]} without loading
    the full tree into Python RAM.  Returns the S3 key, or "" on fallback.
    """
    s3_key = f"graph_results/{db_name}/{job_type}/{_graph_variant(use_llm)}/{job_id}.json"

    # Build a combined temp file: {"tree": <tree>, "field_groups": [...]}
    combined_path = tree_path + ".combined.json"
    total_bytes = 0
    try:
        with open(combined_path, "wb") as out:
            out.write(b'{"tree":')
            with open(tree_path, "rb") as tree_f:
                while True:
                    chunk = tree_f.read(65536)
                    if not chunk:
                        break
                    out.write(chunk)
                    total_bytes += len(chunk)
            fg_bytes = orjson.dumps(field_groups, default=str)
            out.write(b',"field_groups":')
            out.write(fg_bytes)
            out.write(b'}')
            total_bytes += len(fg_bytes) + 20  # approx overhead

        if cache.s3 and cache.bucket:
            with open(combined_path, "rb") as f:
                cache.s3.upload_fileobj(
                    f, cache.bucket, s3_key,
                    ExtraArgs={"ContentType": "application/json"},
                )
            print(f"[Job {job_id}] Streamed ~{total_bytes:,} bytes to DO Spaces: {s3_key}")
            return s3_key
        else:
            # Dev fallback: load into memory for Redis (unavoidable without S3)
            print(f"[Job {job_id}] WARNING: No DO Spaces, loading tree for Redis fallback")
            with open(combined_path, "rb") as f:
                data = orjson.loads(f.read())
            job_manager.complete_job(job_id, data)
            del data
            gc.collect()
            return ""
    finally:
        # Clean up combined file
        try:
            os.unlink(combined_path)
        except OSError:
            pass


async def _run_graph_job(job_id: str, job_type: str, db_name: str, user_id: str,
                         use_llm: bool, force_refresh: bool, collection: str = None):
    """Background task that runs the graph/user-tree build pipeline.

    Only one build runs at a time. If the lock is held by another job,
    this one stays in "queued" status until its turn.
    """
    global _last_field_mappings

    if _build_lock.locked():
        print(f"[Job {job_id}] Waiting in queue (another build is running)...")

    async with _build_lock:
        try:
            field_mappings = {}
            field_semantics = {}
            field_groups = []
            sunburst_excluded = set()

            preprocessing_rules = {}

            if use_llm:
                job_manager.update_status(job_id, "schema")
                print(f"[Job {job_id}] Step 1/3: Building schema cache...")
                full_schema = await schema_manager.get_full_schema(
                    db_name, force_refresh=force_refresh
                )

                job_manager.update_status(job_id, "llm_analysis")
                print(f"[Job {job_id}] Step 2/3: Analyzing fields with AI...")
                schema_table = schema_manager.format_schema_for_llm(full_schema)
                field_groups = await llm_analyzer.analyze_field_relationships(
                    schema_table, db_name
                )
                field_mappings = llm_analyzer.build_field_mapping(field_groups)
                field_semantics = llm_analyzer.build_field_semantics(field_groups)
                all_field_names = [
                    field
                    for col_info in full_schema.values()
                    for field in col_info.get("schema", {})
                ]
                sunburst_excluded = llm_analyzer.build_sunburst_excluded_fields(
                    field_groups, all_field_names
                )
                print(
                    f"[Job {job_id}]   {len(field_mappings)} field mappings, "
                    f"{len(field_semantics)} field semantics from {len(field_groups)} groups, "
                    f"{len(sunburst_excluded)} fields excluded from sunburst display"
                )

                if job_type == "sunburst":
                    _last_field_mappings = field_mappings
                    if cache and field_mappings:
                        cache.set(f"mg_field_mappings:{db_name}", field_mappings)

                # For user-tree builds: run document pattern analysis to detect
                # selection arrays, noise fields, and semantic relationships
                if job_type == "usertree":
                    print(f"[Job {job_id}]   Running document pattern analysis...")
                    sample_docs = await schema_manager.get_sample_documents(db_name)
                    pattern_analysis = await llm_analyzer.analyze_document_patterns(
                        sample_docs, db_name
                    )
                    print(f"[Job {job_id}]   Raw LLM pattern_analysis: {json.dumps(pattern_analysis, default=str)[:2000]}")
                    preprocessing_rules = llm_analyzer.build_preprocessing_rules(
                        pattern_analysis
                    )
                    print(
                        f"[Job {job_id}]   {len(preprocessing_rules.get('array_rules', {}))} "
                        f"array rules from pattern analysis"
                    )
                    print(f"[Job {job_id}]   array_rules keys: {list(preprocessing_rules.get('array_rules', {}).keys())}")
                    del sample_docs, pattern_analysis

                del full_schema, schema_table
                gc.collect()

            if job_type == "sunburst":
                job_manager.update_status(job_id, "building_tree")
                print(f"[Job {job_id}] Step 3/3: Building sunburst tree...")
                target_cols = [c.strip() for c in collection.split("+")] if collection else None
                tree_path = await tree_builder.build_sunburst_tree(
                    target_db_name=db_name,
                    field_mappings=field_mappings,
                    sunburst_excluded_fields=sunburst_excluded if use_llm else None,
                    force_refresh=force_refresh,
                    target_collections=target_cols,
                )

                # Capture previous build's S3 key before overwriting the record
                old_record = _get_latest_graph_record(user_id, job_type, use_llm)
                old_s3_key = old_record.get("result_url") if old_record else None

                # Stream-upload tree file + field_groups to DO Spaces
                job_manager.update_status(job_id, "uploading")
                print(f"[Job {job_id}] Streaming result to DO Spaces...")
                try:
                    s3_key = _upload_tree_file_to_spaces(
                        tree_path, field_groups, db_name, job_id, job_type, use_llm,
                    )
                finally:
                    # Always clean up the temp tree file
                    try:
                        os.unlink(tree_path)
                    except OSError:
                        pass

                if s3_key:
                    job_manager.complete_job_with_url(job_id, s3_key)
                    _store_latest_graph_result(
                        user_id, db_name, job_type, use_llm, job_id, result_url=s3_key,
                    )
                    # Delete previous build only after new one is safely stored
                    if old_s3_key and old_s3_key != s3_key:
                        _delete_s3_key(old_s3_key, job_id)
                else:
                    _store_latest_graph_result(
                        user_id, db_name, job_type, use_llm, job_id,
                    )

                gc.collect()
            else:
                # usertree: build identity index (materializes to MongoDB)
                job_manager.update_status(job_id, "building_index")
                print(f"[Job {job_id}] Step 3/3: Building identity index...")
                build_id = job_id  # reuse job_id as build_id
                metadata = await user_tree_builder.build_identity_index(
                    target_db_name=db_name,
                    owner_user_id=user_id,
                    build_id=build_id,
                    field_mappings=field_mappings,
                    field_semantics=field_semantics,
                    preprocessing_rules=preprocessing_rules,
                    force_refresh=force_refresh,
                )

                # Store compact metadata in Redis (no S3 upload)
                job_manager.complete_job(job_id, metadata)
                _store_latest_graph_result(
                    user_id, db_name, job_type, use_llm, job_id, result=metadata,
                )

                # Flush stale identity-tree cache entries then pre-warm the new build
                cache.invalidate_pattern(f"usertree:{db_name}:*")
                asyncio.create_task(
                    user_tree_builder.warm_cache(db_name, user_id, build_id)
                )

            print(f"[Job {job_id}] Completed successfully.")
        except Exception:
            error_msg = tb_module.format_exc()
            print(f"[Job {job_id}] Failed: {error_msg}")
            job_manager.fail_job(job_id, error_msg)


@app.post("/api/graph")
async def build_graph(request: GraphRequest, background_tasks: BackgroundTasks,
                      current_user: dict = Depends(get_current_user)):
    """Kicks off an async sunburst tree build. Returns a job_id for polling."""
    job_id = str(uuid.uuid4())
    db_name = current_user["db_name"]
    user_id = current_user["user_id"]
    job_manager.create_job(
        job_id,
        "sunburst",
        db_name,
        request.use_llm,
        request.force_refresh,
        user_id=user_id,
    )
    background_tasks.add_task(_run_graph_job, job_id, "sunburst", db_name,
                              user_id, request.use_llm, request.force_refresh,
                              request.collection)
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/graph/status/{job_id}")
async def get_job_status(job_id: str, current_user: dict = Depends(get_current_user)):
    """Poll the status of a graph-building job."""
    status = job_manager.get_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    if not _job_owned_by_current_user(job_id, current_user):
        raise HTTPException(status_code=403, detail="Access denied")
    response = {"job_id": job_id, "status": status.get("status", "unknown")}
    if status.get("status") == "completed":
        # Check if result is stored as a URL (streamed) or inline (legacy/schema)
        result_url = status.get("result_url")
        if result_url:
            response["result_url"] = f"/api/graph/data/{job_id}"
        else:
            response["result"] = job_manager.get_result(job_id)
    elif status.get("status") == "error":
        response["error"] = status.get("error", "Unknown error")
    return response


@app.get("/api/graph/active")
async def get_active_jobs(current_user: dict = Depends(get_current_user)):
    """Return all queued/in-progress jobs for the current user.

    Frontend should call this on page load to re-attach to any
    pending builds the user started before closing their browser.
    """
    user_id = current_user["user_id"]
    jobs = job_manager.get_active_jobs(user_id)
    return {"jobs": jobs}


@app.get("/api/graph/latest/{job_type}")
async def get_latest_graph(job_type: str, use_llm: Optional[bool] = None,
                           current_user: dict = Depends(get_current_user)):
    """Return the most recent completed graph/tree for the signed-in user.

    For usertree: returns compact explorer metadata (no full tree).
    For sunburst: returns full tree data (from Redis or DO Spaces).
    """
    if job_type not in GRAPH_RESULT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid graph type")

    # For usertree, try MongoDB build metadata first
    if job_type == "usertree":
        build_meta = await user_tree_builder.get_latest_build(
            target_db_name=current_user["db_name"],
            owner_user_id=current_user["user_id"],
            use_llm=use_llm,
        )
        if build_meta:
            return {
                "job_id": build_meta["build_id"],
                "job_type": "usertree",
                "use_llm": build_meta.get("use_llm"),
                "updated_at": build_meta.get("created_at"),
                "result": build_meta,
            }

    # Fallback to Redis/S3 record (sunburst always uses this path)
    record = _get_latest_graph_record(current_user["user_id"], job_type, use_llm)
    if not record:
        raise HTTPException(status_code=404, detail="No saved graph found")

    if record.get("user_id") not in (None, current_user["user_id"]):
        raise HTTPException(status_code=403, detail="Access denied")
    if record.get("db_name") not in (None, current_user["db_name"]):
        raise HTTPException(status_code=403, detail="Access denied")

    result = record.get("result")
    job_id = record.get("job_id")

    # If result is stored in S3, return the URL instead of loading into memory
    # (the frontend will stream it via /api/graph/data/{job_id})
    if result is None:
        s3_key = record.get("result_url")
        if not s3_key:
            raise HTTPException(status_code=404, detail="Saved result data not found")
        return {
            "job_id": job_id,
            "job_type": record.get("job_type", job_type),
            "use_llm": record.get("use_llm"),
            "updated_at": record.get("updated_at"),
            "result_url": f"/api/graph/data/{job_id}",
        }

    return {
        "job_id": job_id,
        "job_type": record.get("job_type", job_type),
        "use_llm": record.get("use_llm"),
        "updated_at": record.get("updated_at"),
        "result": result,
    }


@app.get("/api/graph/data/{job_id}")
async def get_graph_data(job_id: str, current_user: dict = Depends(get_current_user)):
    """
    Authenticated streaming proxy for graph result data.
    Verifies the requesting user owns the job before serving.
    """
    # Verify job exists
    status = job_manager.get_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    if not _job_owned_by_current_user(job_id, current_user):
        raise HTTPException(status_code=403, detail="Access denied")

    # Get the S3 key
    s3_key = job_manager.get_result_url(job_id)
    if not s3_key:
        # Fallback: try inline result (legacy/small jobs)
        result = job_manager.get_result(job_id)
        if result:
            return result
        raise HTTPException(status_code=404, detail="Result data not found")

    # Stream from DO Spaces
    if not cache.s3 or not cache.bucket:
        raise HTTPException(status_code=500, detail="Storage not configured")

    try:
        obj = cache.s3.get_object(Bucket=cache.bucket, Key=s3_key)
        body = obj["Body"]

        def stream_s3():
            for chunk in body.iter_chunks(chunk_size=65536):
                yield chunk

        return StreamingResponse(
            stream_s3(),
            media_type="application/json",
            headers={"Content-Type": "application/json"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve data: {str(e)}")

@app.get("/api/document/{collection}/{doc_id}")
async def get_document(collection: str, doc_id: str, current_user: dict = Depends(get_current_user)):
    """Fetch a single document's full data."""
    db_name = current_user["db_name"]
    try:
        doc = await tree_builder.get_document(db_name, collection, doc_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return doc
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/query-field")
async def query_field(request: QueryRequest, current_user: dict = Depends(get_current_user)):
    """
    Query all collections for documents matching a field (and optional value).
    Uses LLM field mappings to match equivalent field names across collections.
    """
    try:
        db_name = current_user["db_name"]
        field_maps = _last_field_mappings or (cache.get(f"mg_field_mappings:{db_name}") or {})
        rows = await tree_builder.query_by_field(
            db_name=db_name,
            field=request.field,
            value=request.value,
            field_mappings=field_maps,
        )
        # Collect all unique keys across rows for table headers
        all_keys = []
        seen = set()
        for row in rows:
            for k in row:
                if k not in seen:
                    seen.add(k)
                    all_keys.append(k)
        return {
            "rows": rows,
            "columns": all_keys,
            "total": len(rows),
            "equivalent_fields": list(
                {k.split('.')[-1] for k, v in field_maps.items()
                 if v == field_maps.get(request.field, '__none__')}
            ) if request.field in field_maps else [request.field],
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/node-insight")
async def node_insight(request: NodeInsightRequest, current_user: dict = Depends(get_current_user)):
    """
    Use LLM to generate a smart, structured summary of an entity/value
    by examining the matching documents.
    """
    try:
        db_name = current_user["db_name"]
        field_maps = _last_field_mappings or (cache.get(f"mg_field_mappings:{db_name}") or {})
        # Fetch matching documents (reuse query_by_field)
        rows = await tree_builder.query_by_field(
            db_name=db_name,
            field=request.field,
            value=request.value,
            field_mappings=field_maps,
            limit=10,
        )
        if not rows:
            return {
                "entity_type": "Unknown",
                "title": request.value,
                "summary": f"No documents found for {request.field} = {request.value}",
                "properties": [],
                "related_entities": [],
            }
        # Ask LLM to summarize
        insight = await llm_analyzer.summarize_node(
            field=request.field,
            value=request.value,
            documents=rows,
            db_name=db_name,
        )
        return insight
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/user-tree")
async def build_user_tree(request: GraphRequest, background_tasks: BackgroundTasks,
                          current_user: dict = Depends(get_current_user)):
    """Kicks off an async user identity tree build. Returns a job_id for polling."""
    db_name = current_user["db_name"]
    user_id = current_user["user_id"]
    resumable = None
    if not request.force_refresh and not _UTB_DEBUG_LIMIT:
        resumable = await user_tree_builder.get_resumable_build(
            target_db_name=db_name,
            owner_user_id=user_id,
            use_llm=request.use_llm,
        )

    job_id = resumable["build_id"] if resumable else str(uuid.uuid4())
    if resumable:
        existing_job = job_manager.get_status(job_id)
        if existing_job and existing_job.get("status") not in ("completed", "error"):
            return {
                "job_id": job_id,
                "status": existing_job.get("status", resumable.get("phase", "building_index")),
                "resumed": True,
            }

    job_manager.create_job(
        job_id,
        "usertree",
        db_name,
        request.use_llm,
        request.force_refresh,
        user_id=user_id,
    )
    background_tasks.add_task(_run_graph_job, job_id, "usertree", db_name,
                              user_id, request.use_llm, request.force_refresh)
    response_status = resumable.get("phase", "queued") if resumable else "queued"
    return {"job_id": job_id, "status": response_status, "resumed": bool(resumable)}

# ─── Identity Explorer endpoints ─────────────────────────────────────────

@app.get("/api/user-tree/search")
async def explorer_search(build_id: str, q: str,
                          limit: int = 50,
                          current_user: dict = Depends(get_current_user)):
    """Search identity-tree users by display name across all pages."""
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required")
    db_name = current_user["db_name"]
    user_id = current_user["user_id"]
    result = await user_tree_builder.search_users(
        target_db_name=db_name,
        owner_user_id=user_id,
        build_id=build_id,
        query=q.strip(),
        limit=limit,
    )
    return result


@app.get("/api/user-tree/page")
async def explorer_page(build_id: str, cursor: Optional[str] = None,
                        limit: int = 1000,
                        current_user: dict = Depends(get_current_user)):
    """Paginated alphabetical user list for the identity explorer."""
    db_name = current_user["db_name"]
    user_id = current_user["user_id"]
    result = await user_tree_builder.get_explorer_page(
        target_db_name=db_name,
        owner_user_id=user_id,
        build_id=build_id,
        cursor=cursor,
        limit=limit,
    )
    if not result or not result.get("items") and not cursor:
        raise HTTPException(status_code=404, detail="Build not found or empty")
    return result


@app.get("/api/user-tree/node/{build_id}/{user_key:path}")
async def explorer_node(build_id: str, user_key: str,
                        current_user: dict = Depends(get_current_user)):
    """Return user root node plus grouped identity/context links."""
    db_name = current_user["db_name"]
    user_id = current_user["user_id"]
    try:
        result = await user_tree_builder.get_user_node(
            target_db_name=db_name,
            owner_user_id=user_id,
            build_id=build_id,
            user_key=user_key,
        )
    except Exception as e:
        import traceback as tb_mod
        tb_mod.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    if not result:
        raise HTTPException(status_code=404, detail="User not found in this build")
    return result


@app.post("/api/user-tree/expand")
async def explorer_expand(request: ExpandRequest,
                          current_user: dict = Depends(get_current_user)):
    """Expand a node to show related users for a given identity/context link."""
    db_name = current_user["db_name"]
    user_id = current_user["user_id"]
    result = await user_tree_builder.expand_mention(
        target_db_name=db_name,
        owner_user_id=user_id,
        build_id=request.build_id,
        user_key=request.user_key,
        role=request.role,
        scope=request.scope,
        norm_value=request.norm_value,
        cursor=request.cursor,
        limit=request.limit,
    )
    return result


@app.post("/api/cache/clear")
async def clear_cache(request: CacheClearRequest, current_user: dict = Depends(get_current_user)):
    """
    Clear cache entries by target type.
    Targets: "sunburst", "usertree", "schema", "llm", or "all".
    Also cleans up graph result files from DO Spaces.
    """
    db_name = current_user["db_name"]
    user_id = current_user["user_id"]
    cleared = 0

    patterns = {
        "sunburst": f"sunburst:{db_name}:*",
        "usertree": f"usertree:{db_name}:*",
        "schema": f"mg_schema:{db_name}.*",
        "llm": "llm_analysis:*",
    }

    if request.target == "all":
        for pattern in patterns.values():
            cleared += cache.invalidate_pattern(pattern)
        cleared += _clear_latest_graph_records(user_id)
        # Also delete all graph result files from DO Spaces
        cleared += _cleanup_graph_files(db_name)
    elif request.target in patterns:
        cleared = cache.invalidate_pattern(patterns[request.target])
        # Delete graph result files for sunburst/usertree clears
        if request.target in ("sunburst", "usertree"):
            cleared += _clear_latest_graph_records(user_id, request.target)
            cleared += _cleanup_graph_files(db_name)
    else:
        raise HTTPException(status_code=400, detail=f"Invalid target: {request.target}. Use: sunburst, usertree, schema, llm, or all")

    return {"status": "success", "target": request.target, "keys_cleared": cleared}

# Mount Static Files (Frontend)
static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)

app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("mongo_graph.main:app", host="0.0.0.0", port=8001, reload=True)
