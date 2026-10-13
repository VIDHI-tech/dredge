"""
Dredge API Gateway
Mounts all 6 FastAPI sub-applications behind a single uvicorn process.
Each sub-app is accessible via its path prefix:
  /auth  → Auth Service
  /pdf   → PDF Processor API
  /image → Image Processor API
  /csv   → CSV Importer API
  /graph → Mongo Graph API
  /nlp   → NLP to Mongo API
"""
import os
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Create the gateway app
gateway = FastAPI(title="Dredge API Gateway")

# CORS on the gateway level
gateway.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@gateway.get("/health")
async def health():
    return {"status": "ok", "service": "dredge-gateway"}


# --- Mount sub-applications ----
# Each sub-app retains its own routes, middleware, and lifespan handlers.
# Requests to /pdf/upload are received by pdf_app as /upload.

from auth.main import app as auth_app
from pdf_processor.api import app as pdf_app
from image_processor.api import app as image_app
from csv_importer.main import app as csv_app
from mongo_graph.main import app as graph_app
from nlp_to_mongo.main import app as nlp_app
from smart_query.main import app as query_app

gateway.mount("/auth", auth_app)
gateway.mount("/pdf", pdf_app)
gateway.mount("/image", image_app)
gateway.mount("/csv", csv_app)
gateway.mount("/graph", graph_app)
gateway.mount("/nlp", nlp_app)
gateway.mount("/query", query_app)

print("Dredge Gateway: All sub-applications mounted.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("gateway:gateway", host="0.0.0.0", port=8000, reload=True)
