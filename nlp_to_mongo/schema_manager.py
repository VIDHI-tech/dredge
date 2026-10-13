import json
import os
from collections import defaultdict
from typing import Dict, List, Any
from datetime import datetime
from .utils import get_database


SCHEMA_VERSION = 3


class SchemaManager:
    def __init__(self, cache=None):
        self.cache = cache

    async def get_schema(self, collection_name: str, db_name: str = "test") -> Dict[str, Any]:
        db = get_database(db_name)
        collection = db[collection_name]
        current_count = await collection.estimated_document_count()
        cache_key = f"nlp_schema:v{SCHEMA_VERSION}:{db_name}.{collection_name}"

        if self.cache:
            cached = self.cache.get(cache_key)
            if cached and cached.get("doc_count") == current_count:
                return cached["schema"]

        print(f"Schema cache stale for '{collection_name}'. Refreshing...")
        return await self.refresh_schema(collection_name, db_name=db_name)

    async def refresh_schema(self, collection_name: str, db_name: str = "test") -> Dict[str, Any]:
        """
        Scans documents to build schema with clean, queryable field paths.

        Uses smart sampling (same strategy as mongo_graph):
          - Small collections (<=500 docs): scan all
          - Large collections: 1 representative doc per unique top-level
            key shape (server-side aggregation) + 100 random samples

        Handles three document structures:
          A) "data": [[{record}, ...]]       — double-nested array (PDF processor)
          B) "data": [{key: [...]}]           — array of objects with nested arrays
          C) Top-level arrays/objects         — e.g. candidates: [...] (unwrapped data)
        """
        db = get_database(db_name)
        collection = db[collection_name]

        fields_info: Dict[str, Dict] = defaultdict(
            lambda: {"types": set(), "examples": set(), "data_roots": set()}
        )
        doc_count = await collection.estimated_document_count()

        if doc_count <= 500:
            # Small collection — scan everything
            async for doc in collection.find({}, batch_size=500):
                self._process_doc(doc, fields_info)
        else:
            # Phase 1: one representative doc per unique top-level key shape
            # Runs entirely on MongoDB server — minimal network transfer
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
            async for doc in collection.aggregate(shape_pipeline, allowDiskUse=True):
                self._process_doc(doc, fields_info)

            # Phase 2: random sample for diverse example values
            async for doc in collection.aggregate([{"$sample": {"size": 100}}]):
                self._process_doc(doc, fields_info)

        # Build final schema
        final_schema = {}
        for field in sorted(fields_info.keys()):
            info = fields_info[field]
            valid_examples = [ex for ex in info["examples"] if ex is not None and ex != ""]
            detected_type = self._resolve_type(info["types"])
            final_schema[field] = {
                "type": detected_type,
                "examples": list(valid_examples)[:3],
                "data_roots": list(info["data_roots"]),
            }

        self.cache_entry = {
            "doc_count": doc_count,
            "schema": final_schema,
            "last_updated": datetime.now().isoformat(),
        }

        cache_key = f"nlp_schema:v{SCHEMA_VERSION}:{db_name}.{collection_name}"
        if self.cache:
            self.cache.set(cache_key, self.cache_entry)

        return final_schema

    def _process_doc(self, doc: dict, fields_info: Dict):
        """Extract field info from a single document, handling all structure variants."""
        # --- Handle "data" field ---
        data = doc.get("data")
        if isinstance(data, list):
            for outer_item in data:
                if isinstance(outer_item, list):
                    for inner_item in outer_item:
                        if isinstance(inner_item, dict):
                            self._extract_fields(inner_item, fields_info, prefix="", data_root="data")
                elif isinstance(outer_item, dict):
                    inner_data = outer_item.get("data")
                    if inner_data is not None and isinstance(inner_data, list):
                        for inner_array in inner_data:
                            if isinstance(inner_array, list):
                                for record in inner_array:
                                    if isinstance(record, dict):
                                        self._extract_fields(record, fields_info, prefix="", data_root="data")
                            elif isinstance(inner_array, dict):
                                self._extract_fields(inner_array, fields_info, prefix="", data_root="data")
                    else:
                        self._extract_fields(outer_item, fields_info, prefix="", data_root="data")

        # --- Handle top-level fields ---
        skip_keys = {"_id", "doc_id", "timestamp", "source_type", "data", "schema"}
        for k, v in doc.items():
            if k in skip_keys:
                continue
            if isinstance(v, list):
                self._extract_array(v, fields_info, k, data_root=k)
            elif isinstance(v, dict):
                self._extract_fields(v, fields_info, prefix=k, data_root=k)
            else:
                info = fields_info[k]
                info["types"].add(type(v).__name__)
                info["data_roots"].add(k)
                if len(info["examples"]) < 10:
                    info["examples"].add(v)

    def get_schema_summary(self, schema: Dict[str, Any]) -> str:
        lines = ["Field Path | Type | Example Values | Data Root", "--- | --- | --- | ---"]
        for field, info in schema.items():
            if isinstance(info, dict) and "type" in info:
                ftype = info["type"]
                examples = info.get("examples", [])
                roots = info.get("data_roots", [])
            else:
                ftype = "Unknown"
                examples = info if isinstance(info, list) else []
                roots = []
            ex_str = ", ".join([str(e) for e in examples[:3]])
            root_str = ", ".join(roots) if roots else "?"
            lines.append(f"{field} | {ftype} | {ex_str} | {root_str}")
        return "\n".join(lines)

    def get_data_roots(self, schema: Dict[str, Any]) -> set:
        """Return all unique data_roots used across the schema."""
        roots = set()
        for info in schema.values():
            if isinstance(info, dict):
                for r in info.get("data_roots", []):
                    roots.add(r)
        return roots

    def _resolve_type(self, type_set: set) -> str:
        type_map = {
            "int": "Number",
            "float": "Number",
            "str": "String",
            "bool": "Boolean",
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

    def _extract_fields(self, doc: Any, fields_info: Dict, prefix: str = "", data_root: str = ""):
        """
        Recursively extract field paths from a document.
        Produces clean paths without numeric array indices.
        For arrays, we traverse into items but DON'T append the index to the path.
        """
        if isinstance(doc, dict):
            for k, v in doc.items():
                if k in ("_id", "$schema"):
                    continue
                new_key = f"{prefix}.{k}" if prefix else k

                if isinstance(v, dict):
                    self._extract_fields(v, fields_info, new_key, data_root)
                elif isinstance(v, list):
                    self._extract_array(v, fields_info, new_key, data_root)
                else:
                    info = fields_info[new_key]
                    info["types"].add(type(v).__name__)
                    info["data_roots"].add(data_root)
                    if len(info["examples"]) < 10:
                        info["examples"].add(v)

    def _extract_array(self, arr: list, fields_info: Dict, prefix: str, data_root: str):
        """
        Handle arrays by traversing items WITHOUT appending numeric indices.
        This produces paths like 'candidates.party' instead of 'candidates.0.party',
        which map correctly to MongoDB's array traversal with dot notation after $unwind.
        """
        for item in arr:
            if isinstance(item, dict):
                self._extract_fields(item, fields_info, prefix, data_root)
            elif isinstance(item, list):
                self._extract_array(item, fields_info, prefix, data_root)
            else:
                # Leaf values in an array (e.g., aliases.knownAs = ["Mike A.", ...])
                info = fields_info[prefix]
                info["types"].add(type(item).__name__)
                info["data_roots"].add(data_root)
                if len(info["examples"]) < 10:
                    info["examples"].add(item)
