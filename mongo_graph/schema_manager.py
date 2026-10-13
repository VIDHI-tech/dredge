"""
Schema Manager for mongo_graph.
Scans all collections in a database and builds a cached schema with
field paths, types, and sample values — similar to nlp_to_mongo's approach.
"""

import json
import os
import re
from collections import defaultdict
from typing import Dict, Any, List
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId


class SchemaManager:
    def __init__(self, client: AsyncIOMotorClient, cache=None):
        self.client = client
        self.cache = cache
        self.local_cache: Dict[str, Any] = {}  # in-memory fallback only
        self.clippable = ["data.", "data.N."]

    def _clip_path(self, path: str) -> str:
        """Removes redundant wrappers like 'extracted_data.' from the path."""
        for p in self.clippable:
            if path.startswith(p):
                return path[len(p):]
        return path

    # ---------------------------------------------------------- public interface
    async def get_full_schema(self, db_name: str, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Returns the schema for every collection in a database.
        Uses Redis+DO Spaces cache when doc counts haven't changed.
        """
        db = self.client[db_name]
        all_collections = await db.list_collection_names()
        # Skip internal/temp collections created by the identity index builder
        collections = [c for c in all_collections
                       if not c.startswith("mg_identity_")
                       and not c.startswith("mg_debug_")
                       and not c.startswith("_tmp_")
                       and not c.startswith("system.")
                       and not c.startswith("_meta")]
        result = {}

        for col_name in collections:
            collection = db[col_name]
            current_count = await collection.estimated_document_count()

            cache_key = f"mg_schema:{db_name}.{col_name}"

            if not force_refresh and self.cache:
                cached = self.cache.get(cache_key)
                if cached and cached.get("doc_count") == current_count:
                    result[col_name] = cached
                    continue

            print(f"  Schema cache stale for '{db_name}.{col_name}'. Refreshing...")
            schema = await self._scan_collection(collection)
            entry = {
                "doc_count": current_count,
                "schema": schema,
                "last_updated": datetime.now().isoformat(),
            }
            if self.cache:
                self.cache.set(cache_key, entry)
            result[col_name] = entry

        return result

    def format_schema_for_llm(self, full_schema: Dict[str, Any]) -> str:
        """
        Creates a human-readable table listing all fields across all collections,
        suitable for sending to the LLM.
        """
        lines = ["Collection | Field Path | Type | Example Values",
                 "--- | --- | --- | ---"]

        for col_name, col_info in full_schema.items():
            schema = col_info.get("schema", {})
            for field, info in schema.items():
                if isinstance(info, dict) and "type" in info:
                    ftype = info["type"]
                    examples = info.get("examples", [])
                else:
                    ftype = "Unknown"
                    examples = []
                ex_str = ", ".join([repr(e) for e in examples[:3]])
                lines.append(f"{col_name} | {field} | {ftype} | {ex_str}")

        return "\n".join(lines)

    # ---------------------------------------------------------- internal scanning
    async def _scan_collection(self, collection) -> Dict[str, Any]:
        """Scan a collection efficiently by grouping docs with identical
        top-level fields and only extracting from unique shapes.

        Phase 1 – server-side aggregation groups every document by its
        top-level key set (via $objectToArray) and returns one full
        representative document per unique shape.  This runs entirely
        on the MongoDB server so no bulk data transfer happens.

        Phase 2 – a small random sample (100 docs) is also scanned to
        catch nested-field variations and gather diverse example values.

        Array indices are normalized to 'N' so the dict stays compact."""
        raw_fields: Dict[str, Dict] = defaultdict(
            lambda: {"types": set(), "examples": set()}
        )
        doc_count = await collection.estimated_document_count()

        # --- DEBUG LIMIT ---
        # To remove this limit before deploying, set DEBUG_LIMIT to None
        DEBUG_LIMIT = None
        if DEBUG_LIMIT:
            async for doc in collection.find({}).limit(DEBUG_LIMIT):
                self._extract_fields(doc, raw_fields)
        elif doc_count <= 500:
            # Small collection — just scan everything
            async for doc in collection.find({}, batch_size=500):
                self._extract_fields(doc, raw_fields)
        else:
            # Phase 1: one representative doc per unique top-level key set
            shape_pipeline = [
                {"$addFields": {
                    "_shape": {"$map": {
                        "input": {"$objectToArray": "$$ROOT"},
                        "as": "f",
                        "in": "$$f.k",
                    }}
                }},
                {"$group": {
                    "_id": "$_shape",
                    "doc": {"$first": "$$ROOT"},
                }},
                {"$replaceRoot": {"newRoot": "$doc"}},
                {"$project": {"_shape": 0}},
            ]
            async for doc in collection.aggregate(
                shape_pipeline, allowDiskUse=True
            ):
                self._extract_fields(doc, raw_fields)

            # Phase 2: extra random sample for nested variation & examples
            async for doc in collection.aggregate(
                [{"$sample": {"size": 100}}]
            ):
                self._extract_fields(doc, raw_fields)

        # Build final schema — paths are already normalized
        final_schema: Dict[str, Any] = {}
        for field in sorted(raw_fields.keys()):
            info = raw_fields[field]
            valid_examples = [ex for ex in info["examples"]
                              if ex is not None and ex != ""]
            detected_type = self._resolve_type(info["types"])
            final_schema[field] = {
                "type": detected_type,
                "examples": list(valid_examples)[:3],
            }

        return final_schema

    # ---------------------------------------------------------- field extraction
    def _extract_fields(self, doc: Any, fields_info: Dict, prefix: str = ""):
        if isinstance(doc, dict):
            for k, v in doc.items():
                if k == "_id":
                    continue
                new_key = f"{prefix}.{k}" if prefix else k
                if isinstance(v, dict):
                    self._extract_fields(v, fields_info, new_key)
                elif isinstance(v, list):
                    self._extract_array(v, fields_info, new_key)
                else:
                    final_key = self._clip_path(new_key)
                    info = fields_info[final_key]
                    info["types"].add(type(v).__name__)
                    if len(info["examples"]) < 5:
                        info["examples"].add(v)
        elif isinstance(doc, list):
            self._extract_array(doc, fields_info, prefix)

    def _extract_array(self, arr: list, fields_info: Dict, prefix: str):
        """Handle arrays by normalizing indices to 'N' to prevent dict explosion.
        e.g., data.0.Party and data.1.Party both become data.N.Party."""
        for i, item in enumerate(arr):
            # Use 'N' instead of actual index to keep paths compact
            normalized_prefix = f"{prefix}.N" if prefix else "N"
            if isinstance(item, dict):
                self._extract_fields(item, fields_info, normalized_prefix)
            elif isinstance(item, list):
                self._extract_array(item, fields_info, normalized_prefix)
            else:
                final_path = self._clip_path(normalized_prefix)
                info = fields_info[final_path]
                info["types"].add(type(item).__name__)
                if len(info["examples"]) < 5:
                    info["examples"].add(item)

    # ---------------------------------------------------------- sample documents
    async def get_sample_documents(self, db_name: str,
                                   max_per_collection: int = 3) -> str:
        """Collect a few sample documents per collection, formatted for LLM
        document pattern analysis.  Long values and deep nesting are truncated
        so the output stays within reasonable token limits."""
        db = self.client[db_name]
        all_collections = await db.list_collection_names()
        collections = [c for c in all_collections
                       if not c.startswith(("mg_identity_", "mg_debug_",
                                            "_tmp_", "system.", "_meta"))]

        parts: List[str] = []
        for col_name in collections:
            docs: List[dict] = []
            async for doc in db[col_name].find({}).limit(max_per_collection):
                docs.append(self._truncate_for_llm(doc))
            if not docs:
                continue
            parts.append(f"### Collection: {col_name}")
            for i, doc in enumerate(docs, 1):
                doc_json = json.dumps(doc, indent=2, default=str)
                # Hard-cap per-document to avoid blowing up the prompt
                if len(doc_json) > 4000:
                    doc_json = doc_json[:4000] + "\n  ... (truncated)"
                parts.append(f"Document {i}:\n```json\n{doc_json}\n```")

        return "\n\n".join(parts)

    def _truncate_for_llm(self, doc, max_str_len=150, max_array_items=4,
                           depth=0, max_depth=6):
        """Recursively truncate a MongoDB document for LLM consumption."""
        if depth > max_depth:
            return "..."

        if isinstance(doc, dict):
            out = {}
            for k, v in doc.items():
                if k == "_id":
                    out[k] = str(v)
                    continue
                out[k] = self._truncate_for_llm(
                    v, max_str_len, max_array_items, depth + 1, max_depth)
            return out

        if isinstance(doc, list):
            truncated = [
                self._truncate_for_llm(
                    item, max_str_len, max_array_items, depth + 1, max_depth)
                for item in doc[:max_array_items]
            ]
            if len(doc) > max_array_items:
                truncated.append(f"... ({len(doc) - max_array_items} more)")
            return truncated

        if isinstance(doc, ObjectId):
            return str(doc)

        if isinstance(doc, str) and len(doc) > max_str_len:
            return doc[:max_str_len] + "..."

        return doc

    # ---------------------------------------------------------- helpers
    def _resolve_type(self, type_set: set) -> str:
        type_map = {
            "int": "Number", "float": "Number",
            "str": "String", "bool": "Boolean",
            "NoneType": "Null",
        }
        mapped = set()
        for t in type_set:
            mapped.add(type_map.get(t, t))
        if len(mapped) > 1:
            mapped.discard("Null")
        if len(mapped) == 1:
            return mapped.pop()
        elif mapped:
            return " | ".join(sorted(mapped))
        return "Unknown"
