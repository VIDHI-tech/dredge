"""
Tree Builder for mongo_graph sunburst visualization.
Builds a hierarchical tree structure:
  Center: Database
  Ring 1: LLM-identified concepts (or field groups)
  Ring 2: Field paths within each concept
  Ring 3: Unique values, sized by frequency

Uses temporary MongoDB collections for aggregation so that RAM stays
constant regardless of database size.  The final tree JSON is streamed
directly to a temp file — Python RAM stays at ~1-5 MB regardless of
how many unique values exist.
"""

import asyncio
import json
import os
import re
import tempfile
import uuid
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId


# Minimal hard-coded noise filter for fields that always clutter the sunburst
# regardless of database.  Dynamic per-database exclusions come from the LLM
# via the `sunburst_excluded_fields` parameter of build_sunburst_tree().
_BASE_EXCLUDED_FIELDS = {"_id", "objectid"}


class TreeBuilder:
    def __init__(self, uri: str, cache=None):
        self.client = AsyncIOMotorClient(uri)
        self.cache = cache

    # ------------------------------------------------------------------ helpers
    def _extract_dicts_from_data(self, data):
        """Recursively unwrap nested lists and 'schema' wrappers to yield dict items."""
        if isinstance(data, dict):
            if "data" in data and isinstance(data["data"], list) and "schema" in data:
                yield from self._extract_dicts_from_data(data["data"])
            else:
                yield data
        elif isinstance(data, list):
            for item in data:
                yield from self._extract_dicts_from_data(item)

    def _flatten_doc(self, doc, prefix=""):
        """Recursively flatten a dict into (key, value) scalar pairs."""
        pairs = []
        for k, v in doc.items():
            if k == "_id":
                continue
            full_key = f"{prefix}.{k}" if prefix else k

            if isinstance(v, dict):
                pairs.extend(self._flatten_doc(v, full_key))
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        pairs.extend(self._flatten_doc(item, full_key))
                    elif isinstance(item, (str, int, float, bool)):
                        pairs.append((full_key, item))
            elif isinstance(v, (str, int, float, bool)):
                pairs.append((full_key, v))
            elif isinstance(v, ObjectId):
                pairs.append((full_key, str(v)))
        return pairs

    def _serialize_doc(self, doc):
        """Convert a MongoDB document to a JSON-serializable dict."""
        out = {}
        for k, v in doc.items():
            if isinstance(v, ObjectId):
                out[k] = str(v)
            elif isinstance(v, dict):
                out[k] = self._serialize_doc(v)
            elif isinstance(v, list):
                out[k] = [self._serialize_doc(i) if isinstance(i, dict)
                          else str(i) if isinstance(i, ObjectId)
                          else i
                          for i in v]
            else:
                out[k] = v
        return out

    # -------------------------------------------------------------- main build
    async def build_sunburst_tree(self, target_db_name: str = None,
                                   field_mappings: dict = None,
                                   sunburst_excluded_fields: set = None,
                                   force_refresh: bool = False,
                                   target_collections: list = None):
        """
        Builds a hierarchical tree for sunburst visualization.

        Uses a temp MongoDB collection to hold flattened pairs, then
        runs server-side $group aggregation.  The tree JSON is streamed
        directly to a temp file so Python RAM stays at ~1-5 MB.

        Returns the path to the temp JSON file (caller must delete it).
        """
        field_mappings = field_mappings or {}
        # Merge LLM-derived exclusions with the base hard-coded set.
        # NOTE: these exclusions apply ONLY to the sunburst visualization.
        # query_by_field() (click-to-query) uses raw documents and is unaffected.
        excluded_for_display = _BASE_EXCLUDED_FIELDS | (sunburst_excluded_fields or set())

        # ---- determine target db ----
        if not target_db_name:
            db_names = await self.client.list_database_names()
            valid_dbs = [d for d in db_names
                         if d not in ['admin', 'local', 'config']]
            if not valid_dbs:
                # Tiny tree — write directly, no streaming needed
                empty = {"name": "empty", "children": []}
                tmp = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".json", delete=False, encoding="utf-8")
                json.dump(empty, tmp)
                tmp.close()
                return tmp.name
            target_db_name = valid_dbs[0]

        db = self.client[target_db_name]
        all_collections = await db.list_collection_names()

        # Exclude internal/temp collections from the scan
        EXCLUDE_PREFIXES = ("_tmp_", "mg_", "_meta")
        collections = [c for c in all_collections
                       if not c.startswith(EXCLUDE_PREFIXES)]

        # Restrict to specific collections when requested (supports merged buckets)
        if target_collections:
            allowed = set(target_collections)
            collections = [c for c in collections if c in allowed]

        # Clean up any leftover temp collections from crashed builds
        for c in all_collections:
            if c.startswith("_tmp_sunburst_") or c.startswith("_tmp_ut_rec_"):
                try:
                    await db.drop_collection(c)
                    print(f"[TreeBuilder] Cleaned up stale temp collection: {c}")
                except Exception:
                    pass

        # Temp collection for flattened pairs
        tmp_name = f"_tmp_sunburst_{uuid.uuid4().hex[:10]}"
        tmp_col = db[tmp_name]

        try:
            # ---- Phase 1: stream docs → flatten → write pairs to temp ----
            # No sample docs (smr) — click queries MongoDB live via /api/query-field
            print(f"[TreeBuilder] Phase 1: Flattening docs into temp collection '{tmp_name}'...")
            BATCH_SIZE = 1000
            write_buf = []

            # --- DEBUG LIMIT ---
            # To remove this limit before deploying, set DEBUG_LIMIT to None
            DEBUG_LIMIT = None
            docs_processed = 0

            for col_name in collections:
                if DEBUG_LIMIT and docs_processed >= DEBUG_LIMIT:
                    break

                cursor = db[col_name].find({}, batch_size=500)
                async for doc in cursor:
                    if DEBUG_LIMIT and docs_processed >= DEBUG_LIMIT:
                        break

                    data_content = doc.get("data", doc)

                    rows = []
                    if isinstance(data_content, dict):
                        rows.append(data_content)
                    elif isinstance(data_content, list):
                        rows.extend(self._extract_dicts_from_data(data_content))
                    else:
                        continue

                    docs_processed += 1

                    for row in rows:
                        pairs = self._flatten_doc(row)
                        if not pairs:
                            continue

                        # Clip redundant wrappers
                        clippable = ["data.", "data.N."]
                        clipped_pairs = []
                        for k, v in pairs:
                            final_k = k
                            for p in clippable:
                                if final_k.startswith(p):
                                    final_k = final_k[len(p):]
                                    break
                            clipped_pairs.append((final_k, v))
                        pairs = clipped_pairs

                        for key, val in pairs:
                            val_str = str(val).strip()
                            if not val_str or val_str.lower() in ("none", "null", "", "0"):
                                continue
                            if len(val_str) > 100:
                                continue

                            # Drop fields that add noise without insight
                            short = key.split(".")[-1] if "." in key else key
                            if short.lower() in excluded_for_display:
                                continue

                            concept = field_mappings.get(key, key.split(".")[0])
                            short_field = key.split(".")[-1] if "." in key else key

                            write_buf.append({
                                "c": concept,
                                "f": short_field,
                                "v": val_str,
                                "col": col_name,
                            })

                            if len(write_buf) >= BATCH_SIZE:
                                await tmp_col.insert_many(write_buf, ordered=False)
                                write_buf.clear()

            # Flush remaining
            if write_buf:
                await tmp_col.insert_many(write_buf, ordered=False)
                write_buf.clear()

            # ---- Phase 1b: create sparse indexes on queried field paths ----
            # field_mappings keys are the original full paths (e.g. "data.state",
            # "data.N.jurisdiction").  Normalise them to MongoDB dot notation and
            # create one sparse background index per path on every source
            # collection.  These indexes persist after the build so that every
            # subsequent query_by_field() call is index-backed instead of doing
            # a full collection scan.
            if field_mappings:
                index_paths = set()
                for mapped_field in field_mappings:
                    norm = re.sub(r'\.(?:N|\d+)(?=\.|$)', '', mapped_field)
                    if norm:
                        index_paths.add(norm)

                if index_paths:
                    print(f"[TreeBuilder] Phase 1b: Creating {len(index_paths)} "
                          f"field indexes on {len(collections)} collection(s)...")
                    for col_name in collections:
                        for path in index_paths:
                            try:
                                await db[col_name].create_index(
                                    [(path, 1)],
                                    sparse=True,
                                    background=True,
                                    name=f"sb_qi_{path.replace('.', '_')}",
                                )
                            except Exception:
                                # Non-fatal: index may already exist or path invalid
                                pass
                    print("[TreeBuilder] Field indexes created.")

            # ---- Phase 2: server-side aggregation ----
            print(f"[TreeBuilder] Phase 2: Aggregating counts (server-side)...")
            agg_pipeline = [
                {"$group": {
                    "_id": {"c": "$c", "f": "$f", "v": "$v"},
                    "count": {"$sum": 1},
                    "cols": {"$addToSet": "$col"},
                }},
                {"$sort": {"_id.c": 1, "_id.f": 1, "count": -1}},
            ]

            # ---- Phase 3: stream aggregation → write tree JSON to temp file ----
            print(f"[TreeBuilder] Phase 3: Streaming tree JSON to temp file...")
            tmp_json = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8")

            try:
                w = tmp_json.write
                w(f'{{"name":{json.dumps(target_db_name)},"children":[')

                cur_concept = None
                cur_field = None
                first_concept = True
                first_field = True
                first_value = True

                async for doc in tmp_col.aggregate(agg_pipeline, allowDiskUse=True):
                    triplet = doc["_id"]
                    concept = triplet["c"]
                    field = triplet["f"]
                    val_str = triplet["v"]
                    count = doc["count"]
                    cols = doc["cols"]

                    # ---- concept boundary ----
                    if concept != cur_concept:
                        if cur_field is not None:
                            w("]}") # close prev field
                        if cur_concept is not None:
                            w("]}") # close prev concept
                        if not first_concept:
                            w(",")
                        concept_name = concept.replace("_", " ").title()
                        w(f'{{"name":{json.dumps(concept_name)},'
                          f'"concept_key":{json.dumps(concept)},"children":[')
                        cur_concept = concept
                        cur_field = None
                        first_concept = False
                        first_field = True

                    # ---- field boundary ----
                    if field != cur_field:
                        if cur_field is not None:
                            w("]}") # close prev field
                        if not first_field:
                            w(",")
                        w(f'{{"name":{json.dumps(field)},"children":[')
                        cur_field = field
                        first_field = False
                        first_value = True

                    # ---- value node ----
                    if not first_value:
                        w(",")
                    display = val_str[:30] + "\u2026" if len(val_str) > 30 else val_str
                    val_node = {
                        "name": display,
                        "full_value": val_str,
                        "value": count,
                        "collections": cols,
                    }
                    w(json.dumps(val_node, default=str))
                    first_value = False

                # Close all open brackets
                if cur_field is not None:
                    w("]}") # close last field
                if cur_concept is not None:
                    w("]}") # close last concept
                w("]}") # close root

                tmp_json.close()
                print(f"[TreeBuilder] Tree written to {tmp_json.name}")
                return tmp_json.name

            except Exception:
                tmp_json.close()
                os.unlink(tmp_json.name)
                raise

        finally:
            # ---- Cleanup: drop temp collection ----
            await db.drop_collection(tmp_name)
            print(f"[TreeBuilder] Cleaned up temp collection '{tmp_name}'")

    # --------------------------------------------------------- schema summary
    def _extract_keys_recursive(self, doc, prefix=""):
        keys = set()
        for k, v in doc.items():
            current_key = f"{prefix}.{k}" if prefix else k
            keys.add(current_key)
            if isinstance(v, dict):
                keys.update(self._extract_keys_recursive(v, current_key))
        return keys

    async def get_schema_summary(self, target_db_name: str = None):
        """Samples collections to find common keys."""
        keys = set()
        if not target_db_name:
            db_names = await self.client.list_database_names()
            valid_dbs = [d for d in db_names
                         if d not in ['admin', 'local', 'config']]
            if not valid_dbs:
                return []
            target_db_name = valid_dbs[0]

        db = self.client[target_db_name]
        all_cols = await db.list_collection_names()
        EXCLUDE_PREFIXES = ("_tmp_", "mg_", "_meta")
        cols = [c for c in all_cols if not c.startswith(EXCLUDE_PREFIXES)]
        for col in cols:
            cursor = db[col].find({}).limit(10)
            async for doc in cursor:
                data_content = doc.get("data", doc)
                if isinstance(data_content, dict):
                    keys.update(self._extract_keys_recursive(data_content))
                elif isinstance(data_content, list):
                    for item in self._extract_dicts_from_data(data_content):
                        keys.update(self._extract_keys_recursive(item))
        if '_id' in keys:
            keys.remove('_id')
        return sorted(list(keys))

    async def query_by_field(self, db_name, field, value=None,
                              field_mappings=None, limit=200):
        """
        Search all collections for documents matching a field (and optionally a value).

        Uses LLM field_mappings to build a MongoDB $or query with the known full
        field paths so only matching documents are fetched from the server.
        Falls back to a full collection scan only when no mapping info exists.

        Returns a list of flattened row dicts with _collection and _id metadata.
        """
        field_mappings = field_mappings or {}

        # ---- collect full field paths for this field and its concept siblings ----
        target_concept = None
        exact_paths: set = set()
        equivalent_paths: set = set()

        for mapped_field, concept in field_mappings.items():
            short = mapped_field.split(".")[-1] if "." in mapped_field else mapped_field
            if short == field or mapped_field == field:
                target_concept = concept
                exact_paths.add(mapped_field)

        if target_concept:
            for mapped_field, concept in field_mappings.items():
                if concept == target_concept:
                    equivalent_paths.add(mapped_field)

        def _normalize_path(p: str) -> str:
            """Strip array-index placeholders (.N. or .0.) for MongoDB dot notation."""
            return re.sub(r'\.(?:N|\d+)(?=\.|$)', '', p)

        def _build_flat(pairs, col_name, doc_id):
            flat = {"_collection": col_name, "_id": doc_id}
            seen: set = set()
            for key, val in pairs:
                short_key = key.split(".")[-1] if "." in key else key
                if short_key not in seen:
                    flat[short_key] = str(val)[:200]
                    seen.add(short_key)
            return flat

        db = self.client[db_name]
        all_collections = await db.list_collection_names()
        EXCLUDE_PREFIXES = ("_tmp_", "mg_", "_meta")
        collections = [c for c in all_collections
                       if not c.startswith(EXCLUDE_PREFIXES)]

        results = []

        async def _fetch_col(col_name: str, query: dict, col_limit: int) -> list:
            """Fetch up to col_limit docs from one collection matching query."""
            col_results = []
            cursor = db[col_name].find(
                query, limit=col_limit, batch_size=min(col_limit, 500)
            )
            async for doc in cursor:
                data_content = doc.get("data", doc)
                doc_id = str(doc.get("_id", ""))
                rows: list = []
                if isinstance(data_content, dict):
                    rows.append(data_content)
                elif isinstance(data_content, list):
                    rows.extend(self._extract_dicts_from_data(data_content))
                for row in rows:
                    pairs = self._flatten_doc(row)
                    if pairs:
                        col_results.append(_build_flat(pairs, col_name, doc_id))
                        if len(col_results) >= col_limit:
                            return col_results
            return col_results

        # Short field name (last path segment) — used as a plain MongoDB field
        # for documents where the field is NOT nested (e.g. {"Name": "CHON WONG"}
        # instead of {"data": [{"Name": "CHON WONG"}]}).
        short_field = field.split(".")[-1] if "." in field else field

        if exact_paths or equivalent_paths:
            # ---- Fast path: push the filter down to MongoDB ----
            # Use exact paths for value queries; all paths for field-exists queries.
            query_paths = exact_paths if (value is not None and exact_paths) \
                else (exact_paths | equivalent_paths)
            norm_paths = {_normalize_path(p) for p in query_paths}

            # Always also search by the plain short name and the common data.
            # wrapper so flat documents are found even when the LLM recorded a
            # deeper path (e.g. "data.N.Name" → "data.Name" while the actual
            # document stores it at root level as just "Name").
            norm_paths |= {short_field, f"data.{short_field}"}

            if value is not None:
                val_str = str(value).strip()
                or_clauses = [{p: val_str} for p in norm_paths]
                # Also match stored numeric values (e.g. year stored as int)
                try:
                    val_num = float(val_str)
                    val_int = int(val_num)
                    numeric = val_int if val_int == val_num else val_num
                    or_clauses += [{p: numeric} for p in norm_paths]
                except (ValueError, OverflowError):
                    pass
            else:
                or_clauses = [{p: {"$exists": True}}
                              for p in norm_paths]

            mongo_query = ({"$or": or_clauses} if len(or_clauses) > 1
                           else or_clauses[0])

            # Query all collections in parallel
            batches = await asyncio.gather(
                *[_fetch_col(col, mongo_query, limit) for col in collections]
            )
            for batch in batches:
                results.extend(batch)
                if len(results) >= limit:
                    break
            results = results[:limit]

            # If every MongoDB-query attempt returned nothing, fall through to
            # the full-scan fallback so nested/unusual structures are still found.
            if not results:
                exact_paths = set()  # force fallback branch below
                equivalent_paths = set()

        if not exact_paths and not equivalent_paths:
            # ---- Fallback: full document scan ----
            # Reached when: (a) no field_mappings existed, or (b) the fast-path
            # MongoDB queries all returned 0 results (path mismatch).
            # We iterate every document so deeply nested / unusually structured
            # fields are still found.  Short-circuit per collection once we hit
            # the result limit.
            match_fields = {field, short_field}
            target_val = str(value).strip().lower() if value is not None else None

            def _match_row_scan(pairs):
                for key, val in pairs:
                    short_key = key.split(".")[-1] if "." in key else key
                    if short_key in match_fields or key in match_fields:
                        if target_val is None:
                            return True
                        if str(val).strip().lower() == target_val:
                            return True
                return False

            async def _scan_col(col_name: str) -> list:
                col_results = []
                # No cursor-level limit: we need to find the document even if
                # it is record #50000 in a large collection.
                cursor = db[col_name].find({}, batch_size=500)
                async for doc in cursor:
                    data_content = doc.get("data", doc)
                    doc_id = str(doc.get("_id", ""))
                    rows = []
                    if isinstance(data_content, dict):
                        rows.append(data_content)
                    elif isinstance(data_content, list):
                        rows.extend(self._extract_dicts_from_data(data_content))
                    for row in rows:
                        pairs = self._flatten_doc(row)
                        if pairs and _match_row_scan(pairs):
                            col_results.append(_build_flat(pairs, col_name, doc_id))
                            if len(col_results) >= limit:
                                return col_results
                return col_results

            batches = await asyncio.gather(*[_scan_col(col) for col in collections])
            for batch in batches:
                results.extend(batch)
                if len(results) >= limit:
                    break
            results = results[:limit]

        return results

    async def get_document(self, db_name, collection, doc_id):
        """Fetch a single document."""
        from bson import ObjectId as OID
        db = self.client[db_name]
        doc = await db[collection].find_one({"_id": OID(doc_id)})
        if doc:
            return self._serialize_doc(doc)
        return None
