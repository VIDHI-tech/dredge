"""
Tool implementations for the smart analyst agent.
Each tool is a callable that the agent can invoke via function-calling.
Includes identity index tools for cross-referencing user data.
"""

import json
from typing import Any
from .utils import get_database
from .excluded_collections import filter_user_collections

# Max rows returned per tool call to keep LLM context manageable
MAX_TOOL_RESULTS = 100


# ---- Tool definitions for LLM function-calling ----

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_collections",
            "description": "List all user data collections in the database. Returns collection names.",
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_schema",
            "description": (
                "Get the schema of a collection: field names, types, and example values. "
                "Use this to understand what data is available before querying."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "collection_name": {
                        "type": "string",
                        "description": "Name of the collection to inspect",
                    }
                },
                "required": ["collection_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_aggregation",
            "description": (
                "Run a MongoDB aggregation pipeline on a collection. "
                "Use this to query, filter, group, and analyze data. "
                "Returns up to 100 result documents."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "collection_name": {
                        "type": "string",
                        "description": "Name of the collection to query",
                    },
                    "pipeline": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "MongoDB aggregation pipeline stages",
                    },
                },
                "required": ["collection_name", "pipeline"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_field_distribution",
            "description": (
                "Get the distribution of unique values for a field in a collection. "
                "Returns value counts sorted by frequency. Useful for understanding "
                "data before building analytical queries."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "collection_name": {
                        "type": "string",
                        "description": "Name of the collection",
                    },
                    "field_path": {
                        "type": "string",
                        "description": "Dot-notation field path (e.g., 'data.Party')",
                    },
                },
                "required": ["collection_name", "field_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_identity_index",
            "description": (
                "Search the identity index for users matching criteria. "
                "The identity index links data about the same person across all documents. "
                "Returns user keys, names, and summary info. "
                "Only available if an identity index has been built for this database."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "object",
                        "description": (
                            "MongoDB query filter for mg_identity_users collection. "
                            "Useful fields: display_name, identity_key, summary.cities, "
                            "summary.total_mentions. Use $regex for partial name matches."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 50)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_mentions",
            "description": (
                "Get all data mentions linked to a specific user from the identity index. "
                "Returns all documents/records associated with this person across all sources. "
                "Use this to see a user's full profile: poll responses, donations, registrations, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_key": {
                        "type": "string",
                        "description": "The identity key of the user (from search_identity_index results)",
                    },
                },
                "required": ["user_key"],
            },
        },
    },
]


class ToolExecutor:
    """Executes tools against MongoDB for a specific user database."""

    def __init__(self, db_name: str, schema_cache: dict = None):
        self.db_name = db_name
        self.db = get_database(db_name)
        self.schema_cache = schema_cache or {}

    async def execute(self, tool_name: str, args: dict) -> Any:
        handler = getattr(self, f"_tool_{tool_name}", None)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}
        try:
            return await handler(**args)
        except Exception as e:
            return {"error": f"Tool {tool_name} failed: {str(e)}"}

    async def _tool_list_collections(self) -> list[str]:
        all_names = await self.db.list_collection_names()
        return filter_user_collections(all_names)

    async def _tool_get_schema(self, collection_name: str) -> dict:
        # Try to use cached NLP schema first
        from nlp_to_mongo.schema_manager import SchemaManager
        from cache_utils import RedisCache
        sm = SchemaManager(cache=RedisCache())
        schema = await sm.get_schema(collection_name, db_name=self.db_name)
        # Trim to essential info for LLM context
        trimmed = {}
        for field, info in schema.items():
            if isinstance(info, dict):
                trimmed[field] = {
                    "type": info.get("type", "Unknown"),
                    "examples": info.get("examples", [])[:3],
                    "data_roots": info.get("data_roots", []),
                }
            else:
                trimmed[field] = info
        return trimmed

    async def _tool_run_aggregation(
        self, collection_name: str, pipeline: list
    ) -> list:
        cursor = self.db[collection_name].aggregate(pipeline, allowDiskUse=True)
        results = []
        async for doc in cursor:
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])
            results.append(doc)
            if len(results) >= MAX_TOOL_RESULTS:
                break
        return results

    async def _tool_get_field_distribution(
        self, collection_name: str, field_path: str
    ) -> list:
        pipeline = [
            {"$unwind": f"${field_path.split('.')[0]}"}
            if "." in field_path
            else {"$match": {}},
            {
                "$group": {
                    "_id": f"${field_path}",
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"count": -1}},
            {"$limit": 50},
            {
                "$project": {
                    "_id": 0,
                    "value": "$_id",
                    "count": 1,
                }
            },
        ]
        cursor = self.db[collection_name].aggregate(pipeline, allowDiskUse=True)
        results = []
        async for doc in cursor:
            results.append(doc)
        return results

    async def _tool_search_identity_index(
        self, query: dict, limit: int = 50
    ) -> list:
        col = self.db["mg_identity_users"]
        # Check if identity index exists
        count = await col.estimated_document_count()
        if count == 0:
            return {"error": "No identity index found. Build one from the Graph page first."}
        cursor = col.find(query).limit(min(limit, MAX_TOOL_RESULTS))
        results = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            results.append(doc)
        return results

    async def _tool_get_user_mentions(self, user_key: str) -> list:
        col = self.db["mg_identity_mentions"]
        count = await col.estimated_document_count()
        if count == 0:
            return {"error": "No identity index found. Build one from the Graph page first."}
        cursor = col.find({"resolved_key": user_key}).limit(MAX_TOOL_RESULTS)
        results = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            results.append(doc)
        return results

    async def check_identity_index_available(self) -> bool:
        try:
            count = await self.db["mg_identity_users"].estimated_document_count()
            return count > 0
        except Exception:
            return False
