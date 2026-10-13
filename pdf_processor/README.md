# PDF Processor

Extracts structured data from PDF documents using LLM-powered schema inference and chunk-based processing.

## Architecture

```/
API (upload) → S3 → [queue:pdfs] → Pipeline Worker → [queue:chunks] → Unified Processor → [queue:merges] → Pipeline Worker → S3
```

## Components

| File                 | Role                                                                   |
| -------------------- | ---------------------------------------------------------------------- |
| `api.py`             | FastAPI upload/status/result endpoints (mounted at `/pdf` via gateway) |
| `worker_pipeline.py` | Combined chunker + merger worker                                       |
| `llm_engine.py`      | Groq LLM calls for schema inference and data extraction                |
| `chunker.py`         | Text chunking with overlap                                             |
| `extractor.py`       | JSON validation/parsing of LLM responses                               |
| `pdf_loader.py`      | PDF text extraction via pdfplumber                                     |
| `storage.py`         | DigitalOcean Spaces (S3) operations                                    |
| `queue_client.py`    | Redis queue operations                                                 |

## Running (Standalone)

```bash
# API only
python -m pdf_processor.api

# Pipeline worker (chunker + merger)
python -m pdf_processor.worker_pipeline
```

> **Note:** In production, use `gateway.py` and `unified_processor.py` from the project root instead.

## Processing Flow

1. **Upload**: PDF streamed to temp file → uploaded to S3 → job enqueued
2. **Chunking**: PDF downloaded to disk → pages processed incrementally (1 page in RAM at a time) → text chunks uploaded to S3
3. **Processing**: Each chunk sent to Groq LLM with inferred schema → structured JSON saved
4. **Merging**: All processed chunks streamed into single JSON → S3 cleanup
