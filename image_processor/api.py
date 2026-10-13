from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Query, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import List
import os
import uuid
from pathlib import Path
import time

# Add parent to path
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from image_processor.storage import DigitalOceanSpaces
from image_processor.queue_client import QueueClient
from pymongo import MongoClient
from auth.auth_utils import get_current_user
from dotenv import load_dotenv, find_dotenv

# Load root .env
load_dotenv(find_dotenv())

app = FastAPI()

# MongoDB Configuration
MONGO_URI = os.getenv("MONGO_URI")
mongo_client = MongoClient(MONGO_URI)

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

app.mount("/static", StaticFiles(directory=static_dir), name="static")

queue = QueueClient()
storage = DigitalOceanSpaces()

@app.get("/")
async def read_index():
    index_path = static_dir / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding='utf-8'))
    return HTMLResponse(content="<h1>Image Processor API</h1><p>index.html not found in static/</p>")

@app.post("/upload")
async def upload_image(files: List[UploadFile] = File(...), current_user: dict = Depends(get_current_user)):
    # Backpressure: reject if queue is saturated
    MAX_QUEUE_DEPTH = 100
    if queue.queue_depth("queue:images") > MAX_QUEUE_DEPTH:
        raise HTTPException(503, "Server is busy processing files. Please try again later.")
    
    results = []
    
    for file in files:
        # Validate image mime type
        if not file.content_type.startswith("image/"):
            results.append({"filename": file.filename, "status": "error", "detail": "Only Image files are allowed."})
            continue
        
        doc_id = str(uuid.uuid4())
        print(f"Receiving upload: {file.filename} -> {doc_id}")
        
        tmp_path = None
        try:
            # Get extension
            _, ext = os.path.splitext(file.filename)
            if not ext: ext = ".jpg"
            
            # Stream upload to temp file in 8MB chunks (never load full file into RAM)
            import tempfile as _tempfile
            with _tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp_path = tmp.name
                while chunk := await file.read(8 * 1024 * 1024):
                    tmp.write(chunk)
            
            # Stream temp file to S3
            storage.upload_image_file(doc_id, tmp_path, ext)
            
            # Enqueue Job
            queue.enqueue_image(doc_id, file.filename, user_id=current_user["user_id"])
            
            results.append({"doc_id": doc_id, "status": "queued", "filename": file.filename})
            
        except Exception as e:
            print(f"Error uploading {file.filename}: {e}")
            results.append({"filename": file.filename, "status": "error", "detail": str(e)})
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

@app.get("/result/{doc_id}")
async def get_result(doc_id: str, current_user: dict = Depends(get_current_user)):
    _require_doc_ownership(doc_id, current_user)
    result = storage.get_result(doc_id)
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    return result

@app.get("/list-processed")
async def list_processed(current_user: dict = Depends(get_current_user)):
    try:
        user_id = current_user["user_id"]
        owned_ids = set(queue.list_doc_ids_for_user(user_id))
        all_docs = storage.list_processed_documents()
        docs = [d for d in all_docs if d in owned_ids]
        return {"documents": docs}
    except Exception as e:
        print(f"Error listing documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
                "source_type": "image_processor",
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
