from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Query, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from pathlib import Path
import pandas as pd
import io
import json
import math
import uuid
import time
import os
import sys
from pymongo import MongoClient
from dotenv import load_dotenv, find_dotenv

# Load root .env
load_dotenv(find_dotenv())

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth.auth_utils import get_current_user

from .storage import DigitalOceanSpaces
from .queue_client import QueueClient

app = FastAPI(title="CSV to MongoDB JSON Converter")

# MongoDB Configuration
MONGO_URI = os.getenv("MONGO_URI")
mongo_client = MongoClient(MONGO_URI)

storage = DigitalOceanSpaces()
queue = QueueClient()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files
static_dir = Path(__file__).parent / "static"
if not static_dir.exists():
    static_dir.mkdir()

def clean_nan(value):
    """
    Recursively replace NaN/Infinity with None (which becomes null in JSON).
    """
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
    return value

@app.post("/convert")
async def convert_csv(files: List[UploadFile] = File(...), current_user: dict = Depends(get_current_user)):
    results = []
    
    for file in files:
        if not file.filename.lower().endswith('.csv'):
            results.append({"filename": file.filename, "status": "error", "detail": "File must be a CSV"})
            continue
        
        doc_id = str(uuid.uuid4())
        print(f"Receiving CSV upload: {file.filename} -> {doc_id}")

        tmp_path = None
        try:
            # Stream upload to temp file in 8MB chunks (never load full CSV into RAM)
            import tempfile as _tempfile
            with _tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
                tmp_path = tmp.name
                while chunk := await file.read(8 * 1024 * 1024):
                    tmp.write(chunk)
            
            # Stream temp file to S3
            storage.upload_csv_file(doc_id, tmp_path)

            # Enqueue Job
            queue.enqueue_csv(doc_id, file.filename, user_id=current_user["user_id"])
            
            results.append({"doc_id": doc_id, "status": "queued", "filename": file.filename})
            
        except Exception as e:
            print(f"Error processing CSV {file.filename}: {e}")
            results.append({"filename": file.filename, "status": "error", "detail": f"Error processing CSV: {str(e)}"})
        finally:
            # Always clean up temp file
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    return {"results": results}

def _require_doc_ownership(doc_id: str, current_user: dict):
    """Raise 403 if the current user does not own this doc_id.

    Docs created before user_id tracking was added have no owner stored —
    those are allowed through so existing jobs aren't broken.
    """
    owner = queue.get_doc_owner(doc_id)
    if owner and owner != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied")


@app.get("/status/{doc_id}")
async def get_status(doc_id: str, current_user: dict = Depends(get_current_user)):
    _require_doc_ownership(doc_id, current_user)
    status = queue.get_status(doc_id)
    if not status:
        return {"status": "unknown"}
    return status

@app.get("/list-processed")
async def list_processed(current_user: dict = Depends(get_current_user)):
    try:
        user_id = current_user["user_id"]
        # Only return doc_ids owned by this user (tracked via Redis)
        owned_ids = set(queue.list_doc_ids_for_user(user_id))
        # Cross-reference with what's actually in S3 (some may still be processing)
        all_docs = storage.list_processed_documents()
        docs = [d for d in all_docs if d in owned_ids]
        return {"documents": docs}
    except Exception as e:
        print(f"Error listing documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/result/{doc_id}")
async def get_result(doc_id: str, current_user: dict = Depends(get_current_user)):
    _require_doc_ownership(doc_id, current_user)
    result = storage.get_result(doc_id)
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    return result

@app.post("/save-to-mongo/{doc_id}")
async def save_to_mongo(
    doc_id: str,
    request: Request,
    bucket: str = Query("test1", description="Target collection/bucket name"),
    current_user: dict = Depends(get_current_user),
):
    _require_doc_ownership(doc_id, current_user)
    try:
        db_name = current_user["db_name"]
        db = mongo_client[db_name]
        collection = db[bucket]

        data = await request.json()
        
        if not isinstance(data, list):
            data = [data]
            
        if not data:
            return {"status": "success", "inserted_ids": [], "message": "No data to insert"}
            
        documents = []
        for item in data:
            doc = {
                "doc_id": doc_id,
                "timestamp": time.time(),
                "source_type": "csv_importer",
                **(item if isinstance(item, dict) else {"data": item}),
            }
            documents.append(doc)
        
        # Insert as multiple documents
        result = collection.insert_many(documents)
        
        # Cleanup: Delete the processed JSON from S3 now that it's in MongoDB
        storage.delete_result(doc_id)
        print(f"[{doc_id}] Saved to MongoDB and cleaned up S3 JSON.")
        
        return {"status": "success", "inserted_ids": [str(id) for id in result.inserted_ids]}
    except Exception as e:
        print(f"Error saving to MongoDB: {e}")
        raise HTTPException(status_code=500, detail=str(e))

app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
