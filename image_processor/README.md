# Image Processor

Extracts structured data from images using LLM vision APIs with schema inference.

## Architecture

```/
API (upload) → S3 → [queue:images] → Pipeline Worker → [queue:image_chunks] → Unified Processor → [queue:image_merges] → Pipeline Worker → S3
```

## Components

| File                 | Role                                                                     |
| -------------------- | ------------------------------------------------------------------------ |
| `api.py`             | FastAPI upload/status/result endpoints (mounted at `/image` via gateway) |
| `worker_pipeline.py` | Combined chunker + merger worker                                         |
| `llm_engine.py`      | Groq LLM vision calls for schema inference and data extraction           |
| `extractor.py`       | JSON validation/parsing of LLM responses                                 |
| `image_loader.py`    | Image loading and base64 conversion                                      |
| `storage.py`         | DigitalOcean Spaces (S3) operations                                      |
| `queue_client.py`    | Redis queue operations                                                   |

## Running (Standalone)

```bash
# API only
python -m image_processor.api

# Pipeline worker (chunker + merger)
python -m image_processor.worker_pipeline
```

> **Note:** In production, use `gateway.py` and `unified_processor.py` from the project root instead.

## Processing Flow

1. **Upload**: Image streamed to temp file → uploaded to S3 → job enqueued
2. **Chunking**: Image downloaded → base64 encoded for LLM vision API → schema inferred → 1 image = 1 chunk
3. **Processing**: Image sent to Groq vision LLM with schema → structured JSON saved
4. **Merging**: Processed results assembled into final JSON → S3 cleanup
