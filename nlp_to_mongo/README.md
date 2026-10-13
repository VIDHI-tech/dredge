# NLP to Mongo

Natural language to MongoDB query converter. Translates user questions into aggregation pipelines using LLM + schema context.

## Components

| File | Role |
|------|------|
| `main.py` | FastAPI endpoints for query conversion and execution (mounted at `/nlp` via gateway) |
| `converter.py` | LLM-based natural language → MongoDB pipeline conversion |
| `schema_manager.py` | Schema introspection with field types and examples |
| `models.py` | Pydantic request/response models |
| `utils.py` | Database connection helpers |

## Running (Standalone)

```bash
python -m uvicorn nlp_to_mongo.main:app --host 0.0.0.0 --port 8002 --reload
```

> **Note:** In production, this is mounted at `/nlp` via `gateway.py`.

## Key Features

- **Schema-aware**: Samples documents to learn field paths, types, and data roots
- **Multi-root handling**: Supports `data[]`, top-level arrays, and nested structures
- **Pagination**: Built-in `$skip`/`$limit` for paginated results
- **Field path prefixing**: Automatically prefixes fields based on document structure
