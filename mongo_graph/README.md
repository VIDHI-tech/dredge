# Mongo Graph

Interactive graph visualization of MongoDB data using LLM-powered field analysis and sunburst trees.

## Components

| File | Role |
|------|------|
| `main.py` | FastAPI endpoints for graph building and querying (mounted at `/graph` via gateway) |
| `tree_builder.py` | Builds hierarchical sunburst tree from MongoDB collections |
| `user_tree_builder.py` | Builds user identity trees |
| `schema_manager.py` | MongoDB schema introspection and caching |
| `llm_analyzer.py` | LLM-based field relationship analysis |

## Running (Standalone)

```bash
python -m uvicorn mongo_graph.main:app --host 0.0.0.0 --port 8001 --reload
```

> **Note:** In production, this is mounted at `/graph` via `gateway.py`.

## Key Features

- **Sunburst visualization**: Hierarchical tree — Database → Concepts → Fields → Values
- **LLM field analysis**: Groups semantically equivalent fields across collections
- **Redis caching**: Schema and tree results cached with 1-hour TTL
- **Cross-collection search**: Query by field/value across all collections with LLM-mapped equivalents
