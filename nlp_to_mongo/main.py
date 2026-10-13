from fastapi import FastAPI, HTTPException, Depends, Request
import traceback
from dotenv import load_dotenv
import os
from .models import QueryRequest, QueryResponse, RefreshSchemaRequest
from .converter import QueryConverter
from .schema_manager import SchemaManager

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth.auth_utils import get_current_user
from cache_utils import RedisCache

from pathlib import Path
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

# Module-level initialization (works both standalone and when mounted via gateway)
cache = RedisCache()
converter = QueryConverter()
schema_manager = SchemaManager(cache=cache)
print("NLP to Mongo Service initialized.")

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from .utils import get_database

app = FastAPI(title="NLP to Mongo")

# Mount static files
app.mount("/static", StaticFiles(directory="nlp_to_mongo"), name="static")

@app.get("/")
async def read_index():
    import os
    index_path = os.path.join(os.path.dirname(__file__), 'index.html')
    return FileResponse(index_path)

@app.post("/convert", response_model=QueryResponse)
async def convert_query(request: QueryRequest, current_user: dict = Depends(get_current_user)):
    if not request.collection:
        raise HTTPException(status_code=400, detail="Collection name is required")

    # Use the user's db_name from JWT token
    db_name = current_user["db_name"]

    MAX_RETRIES = 2

    try:
        # converter.convert() now ALWAYS returns a pipeline (list)
        pipeline = await converter.convert(request.text, request.collection, db_name=db_name)
        results = None
        total_count = None

        if request.execute:
            db = get_database(db_name)
            collection = db[request.collection]

            for attempt in range(1 + MAX_RETRIES):
                try:
                    skip = (request.page - 1) * request.page_size
                    results = []
                    total_count = None

                    # Get total count via a count pipeline (strip any $skip/$limit first)
                    count_pipeline = [s for s in pipeline if "$limit" not in s and "$skip" not in s]
                    count_pipeline.append({"$count": "total"})
                    try:
                        count_result = await collection.aggregate(count_pipeline).to_list(1)
                        total_count = count_result[0]["total"] if count_result else 0
                    except Exception:
                        total_count = None  # Count may fail for complex pipelines

                    # Add pagination stages
                    paginated_pipeline = [s for s in pipeline if "$limit" not in s and "$skip" not in s]
                    paginated_pipeline.append({"$skip": skip})
                    paginated_pipeline.append({"$limit": request.page_size})

                    cursor = collection.aggregate(paginated_pipeline)

                    async for doc in cursor:
                        if '_id' in doc:
                            doc['_id'] = str(doc['_id'])
                        results.append(doc)

                    break  # success

                except Exception as exec_err:
                    if attempt < MAX_RETRIES:
                        print(f"[nlp_to_mongo] Pipeline attempt {attempt+1} failed: {exec_err}")
                        print("[nlp_to_mongo] Retrying with error feedback to LLM...")
                        pipeline = await converter.retry_with_error(
                            text=request.text,
                            collection_name=request.collection,
                            db_name=db_name,
                            failed_pipeline=pipeline,
                            error_msg=str(exec_err),
                        )
                    else:
                        raise

        return QueryResponse(
            mongo_query=pipeline,
            explanation="Generated aggregation pipeline from schema context.",
            results=results,
            total_count=total_count,
            page=request.page,
            page_size=request.page_size
        )
    except Exception as e:
        with open("server_error.log", "w") as f:
            traceback.print_exc(file=f)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/schema/{collection_name}")
async def get_schema(collection_name: str, current_user: dict = Depends(get_current_user)):
    """Returns the cached schema for a collection (with types and examples)."""
    db_name = current_user["db_name"]
    try:
        schema = await schema_manager.get_schema(collection_name, db_name=db_name)
        summary = schema_manager.get_schema_summary(schema)
        return {"collection": collection_name, "schema": schema, "summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/refresh-schema")
async def refresh_schema(request: RefreshSchemaRequest, current_user: dict = Depends(get_current_user)):
    db_name = current_user["db_name"]
    try:
        updated_schema = await schema_manager.refresh_schema(request.collection, db_name=db_name)
        return {"status": "success", "field_count": len(updated_schema)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/cache/warm")
async def warm_cache_entry(request: Request, current_user: dict = Depends(get_current_user)):
    """Pre-warm schema/query cache from pipeline output endpoint.
    Used by orchestration layer after batch pipeline runs complete."""
    body = await request.json()
    cache_key = body.get("cache_key", "")
    source_url = body.get("source_url", "")
    fmt = body.get("format", "json")
    if not cache_key or not source_url:
        raise HTTPException(status_code=400, detail="cache_key and source_url are required")
    result = cache.warm_from_source(cache_key, source_url, binary_format=(fmt == "binary"))
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("nlp_to_mongo.main:app", host="0.0.0.0", port=8002, reload=True)
