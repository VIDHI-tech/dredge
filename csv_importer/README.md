# CSV Importer

Converts CSV files into structured JSON documents for storage in MongoDB.

## Architecture

/

```
API (upload) → S3 → [queue:csvs] → Pipeline Worker → [queue:csv_chunks] → Unified Processor → [queue:csv_merges] → Pipeline Worker → S3
```

## Components

| File                 | Role                                                                   |
| -------------------- | ---------------------------------------------------------------------- |
| `main.py`            | FastAPI upload/status/result endpoints (mounted at `/csv` via gateway) |
| `worker_pipeline.py` | Combined chunker + merger worker                                       |
| `storage.py`         | DigitalOcean Spaces (S3) operations                                    |
| `queue_client.py`    | Redis queue operations                                                 |

## Running (Standalone)

```bash
# API only
python -m csv_importer.main

# Pipeline worker (chunker + merger)
python -m csv_importer.worker_pipeline
```

> **Note:** In production, use `gateway.py` and `unified_processor.py` from the project root instead.

## Processing Flow

1. **Upload**: CSV streamed to temp file in 8MB chunks → uploaded to S3 → job enqueued
2. **Chunking**: CSV downloaded to temp file → read in 10K-row chunks via pandas → chunks uploaded to S3
3. **Processing**: Each chunk parsed with pandas → NaN cleaned → JSON saved
4. **Merging**: All processed chunks streamed into single JSON → S3 cleanup
