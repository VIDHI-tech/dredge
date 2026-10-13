"""
User Tree Builder for mongo_graph.
Builds a compact identity index: per-user summaries and traversable
mention records, stored in MongoDB collections for lazy exploration.

Uses temporary MongoDB collections for intermediate data so that
Python RAM stays near-constant regardless of database size.

Two-phase approach:
  Phase 1  -- stream docs, extract identity info + mentions in a single pass.
  Merge    -- server-side aggregation to find transitive identity groups,
              then bulk-update both temp records and mentions with resolved keys.
  Materialize -- aggregate temp records for user summaries (no second DB scan).
"""

import asyncio
import hashlib
import uuid
import base64
import json
import time
import re
import os
from collections import defaultdict
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from pymongo import UpdateOne as _UpdateOne


# ---------------------------------------------------------------- constants
# Fields considered as user identity (used to group records into user nodes)
IDENTITY_FIELDS = {
    "name", "candidateName", "FullName", "first_name", "last_name",
    "FirstName", "LastName", "Name", "knownAs", "Full Name", "full_name",
    "Voter Name", "VoterName",
}

# Fields that act as secondary unique IDs (used for merge + grouping)
SECONDARY_ID_FIELDS = {
    "email", "phoneNumber", "phone", "VoterID", "primaryRef",
    "Voter ID", "voter id", "voter_id", "ContributionID",
    "primary_ref", "contribution_id",
    "externalAccountId", "external_account_id",
    "username", "userName",
    "googleEmail", "emailAuthEmail",
}

# Location / disambiguator fields (used for identity keys and grouping)
DISAMBIG_FIELDS = {
    "city", "City", "state", "State", "stateCode",
    "jurisdiction", "district", "zip", "Zip", "ZIP",
    "address", "Address",
}

# ---------------------------------------------------------------- link strength
# Strong identity links: exact identifiers that reliably identify a person
STRONG_ID_FIELDS = {
    "email", "phoneNumber", "phone", "VoterID", "primaryRef",
    "Voter ID", "voter id", "voter_id", "ContributionID",
    "externalAccountId", "external_account_id",
    "googleEmail", "emailAuthEmail",
}

# Medium identity links
MEDIUM_ID_FIELDS = {"username", "userName"}

# Weak / context links: scoped location-style fields
CONTEXT_LINK_FIELDS = {
    "city", "City", "state", "State", "stateCode",
    "country", "Country", "countryCode", "CountryCode",
    "jurisdiction", "district", "zip", "Zip", "ZIP",
    "address", "Address", "mailingAddress",
    "registeredState", "EmpAddress", "EmpCityStZip", "CityStZip",
}

# Path-segment hints that signal a child field is a location/context link
_LOCATION_PATH_HINTS = {"location", "address", "geo", "place"}
_DOCUMENT_SCOPE = "document"

# Hard ignore safety rails for non-traversable document-style fields
_IGNORE_FIELD_KEYS = {
    "timestamp", "timestamps", "createdat", "updatedat", "deletedat",
    "seenat", "respondedat", "description", "summary", "content", "body",
    "message", "html", "markdown", "text", "rawtext", "note", "notes",
    "comment", "comments",
}
_IGNORE_PATH_HINTS = {
    "timestamp", "timestamps", "created", "updated", "description",
    "summary", "content", "message", "markdown", "html",
}
_PERSON_LOCATION_SCOPES = {"person.location"}
_PERSON_IDENTITY_SCOPES = {"person.identity"}

_CANONICAL_ID_KEY_OVERRIDES = {
    "email": "email",
    "googleemail": "email",
    "emailauthemail": "email",
    "phone": "phone",
    "phonenumber": "phone",
    "username": "username",
    "externalaccountid": "external_account_id",
    "externalaccount": "external_account_id",
    "voterid": "voter_id",
    "contributionid": "contribution_id",
    "primaryref": "primary_ref",
}
_CANONICAL_LOCATION_KEY_OVERRIDES = {
    "city": "city",
    "state": "state",
    "statecode": "state_code",
    "country": "country",
    "countrycode": "country_code",
    "jurisdiction": "jurisdiction",
    "district": "district",
    "zip": "zip",
    "address": "address",
}


def _positive_int_from_env(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


SOURCE_CURSOR_BATCH_SIZE = _positive_int_from_env(
    "MG_IDENTITY_SOURCE_CURSOR_BATCH_SIZE", 500
)

# ---------------------------------------------------------------- debug limit
# Set to a positive int to cap documents processed (for fast debugging).
# Set to None for production.
DEBUG_LIMIT = None

# ---------------------------------------------------------------- index collections
if DEBUG_LIMIT:
    BUILDS_COL = "mg_debug_builds"
    USERS_COL = "mg_debug_users"
    MENTIONS_COL = "mg_debug_mentions"
else:
    BUILDS_COL = "mg_identity_builds"
    USERS_COL = "mg_identity_users"
    MENTIONS_COL = "mg_identity_mentions"
INCOMPLETE_BUILD_STATUSES = ("building", "paused")
RESUMABLE_PHASES = {"merging", "materializing", "indexing"}

# Keywords in LLM concept names that signal "this field is an identity field"
_IDENTITY_CONCEPT_HINTS = {"name", "person", "identity", "individual"}

# Parent path segments that mean the nested field is NOT about the primary person
_NON_PERSON_PARENTS = {
    "employer", "organization", "company", "committee", "org",
    "recipient", "vendor", "payee", "donor", "sponsor",
}


class UserTreeBuilder:
    def __init__(self, uri: str, cache=None):
        self.client = AsyncIOMotorClient(uri)
        self.cache = cache

    def _node_cache_key(self, db_name: str, build_id: str, user_key: str) -> str:
        uk_hash = hashlib.md5(user_key.encode()).hexdigest()[:16]
        return f"usertree:{db_name}:{build_id}:node:{uk_hash}"

    def _expand_cache_key(self, db_name: str, build_id: str, user_key: str,
                          role: str, scope: str, norm_value: str,
                          cursor: str | None) -> str:
        payload = f"{user_key}|{role}|{scope}|{norm_value}|{cursor or ''}"
        ph = hashlib.md5(payload.encode()).hexdigest()[:16]
        return f"usertree:{db_name}:{build_id}:expand:{ph}"

    def _total_cache_key(self, db_name: str, build_id: str) -> str:
        return f"usertree:{db_name}:{build_id}:total"

    # ---------------------------------------------------------------- helpers
    def _extract_dicts(self, data):
        """Recursively unwrap nested lists and 'schema' wrappers to yield dict items."""
        if isinstance(data, dict):
            if "data" in data and isinstance(data["data"], list) and "schema" in data:
                yield from self._extract_dicts(data["data"])
            else:
                yield data
        elif isinstance(data, list):
            for item in data:
                yield from self._extract_dicts(item)

    def _flatten_doc(self, doc, prefix=""):
        """Recursively flatten a dict into (key, short_key, value) tuples."""
        pairs = []
        for k, v in doc.items():
            if k == "_id":
                continue
            full_key = f"{prefix}.{k}" if prefix else k
            short_key = k

            if isinstance(v, dict):
                pairs.extend(self._flatten_doc(v, full_key))
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        pairs.extend(self._flatten_doc(item, full_key))
                    elif isinstance(item, (str, int, float, bool)):
                        pairs.append((full_key, short_key, item))
            elif isinstance(v, (str, int, float, bool)):
                pairs.append((full_key, short_key, v))
            elif isinstance(v, ObjectId):
                pairs.append((full_key, short_key, str(v)))
        return pairs

    # --------------------------------------------------------- doc preprocessing
    def _preprocess_doc(self, doc, array_rules, prefix=""):
        """Transform a document using LLM-provided array rules before flattening.

        For selection arrays (e.g. poll options with isSelected), this extracts
        the selected value(s) and emits them as a new scalar field, replacing
        the raw array. This way the flattener sees the meaningful value instead
        of every option + a boolean selector.
        """
        if not isinstance(doc, dict):
            return doc

        result = {}
        for k, v in doc.items():
            if k == "_id":
                result[k] = v
                continue

            full_path = f"{prefix}.{k}" if prefix else k

            if isinstance(v, list) and v and isinstance(v[0], dict):
                # Check LLM array rules for this path
                rule = self._find_array_rule(full_path, array_rules)
                if rule and rule.get("pattern") == "selection":
                    selected = self._apply_selection_rule(v, rule)
                    if selected:
                        emit_as = rule.get("emit_as", f"{k}_selected")
                        emit_key = (emit_as.rsplit(".", 1)[-1]
                                    if "." in emit_as else emit_as)
                        if len(selected) == 1:
                            result[emit_key] = selected[0]
                        else:
                            result[emit_key] = selected
                        # Don't emit the raw array at all — it's been resolved
                        continue

                # No rule — recurse into each array item
                processed = []
                for item in v:
                    if isinstance(item, dict):
                        processed.append(
                            self._preprocess_doc(item, array_rules, full_path))
                    else:
                        processed.append(item)
                result[k] = processed

            elif isinstance(v, dict):
                result[k] = self._preprocess_doc(v, array_rules, full_path)
            else:
                result[k] = v

        return result

    @classmethod
    def _find_array_rule(cls, full_path, array_rules):
        """Find an LLM array rule matching this document path."""
        if not array_rules:
            return None
        # Exact match
        if full_path in array_rules:
            return array_rules[full_path]
        # Normalize: strip common prefixes, lowercase, collapse .N.
        norm = full_path.lower().replace(".n.", ".")
        for prefix in ("data.", "data.n."):
            if norm.startswith(prefix):
                norm = norm[len(prefix):]
                break
        for rule_path, rule in array_rules.items():
            rp = rule_path.lower().replace(".n.", ".")
            for prefix in ("data.", "data.n."):
                if rp.startswith(prefix):
                    rp = rp[len(prefix):]
                    break
            if norm == rp:
                return rule
        return None

    @staticmethod
    def _apply_selection_rule(items, rule):
        """Extract selected values from an array using an LLM rule."""
        selector = rule.get("selector_field")
        selector_val = rule.get("selector_value", True)
        value_field = rule.get("value_field")
        if not selector or not value_field:
            return None

        selected = []
        for item in items:
            if not isinstance(item, dict):
                continue
            item_sel = item.get(selector)
            # Flexible truthy comparison
            matches = False
            if isinstance(selector_val, bool):
                if isinstance(item_sel, bool):
                    matches = item_sel == selector_val
                elif isinstance(item_sel, str):
                    matches = item_sel.lower() == str(selector_val).lower()
            else:
                matches = str(item_sel).strip().lower() == str(selector_val).strip().lower()

            if matches:
                label = item.get(value_field)
                if label is not None:
                    selected.append(str(label).strip())

        return selected if selected else None

    # --------------------------------------------------------- LLM-aware fields
    @staticmethod
    def _normalize_field_path(field_path):
        parts = [part for part in str(field_path or "").split(".") if part and part not in {"data", "N"}]
        return ".".join(parts)

    @classmethod
    def _lookup_by_field_path(cls, full_key, mapping):
        if not mapping:
            return None
        if full_key in mapping:
            return mapping[full_key]
        normalized = cls._normalize_field_path(full_key)
        if normalized in mapping:
            return mapping[normalized]
        return None

    @classmethod
    def _with_normalized_field_keys(cls, mapping):
        if not mapping:
            return {}
        enriched = dict(mapping)
        for field_path, value in mapping.items():
            normalized = cls._normalize_field_path(field_path)
            if normalized and normalized not in enriched:
                enriched[normalized] = value
        return enriched

    def _effective_identity_fields(self, field_mappings, field_semantics=None):
        extra = set()

        for field_path, semantic in (field_semantics or {}).items():
            if semantic.get("role") == "identity_name":
                short = self._normalize_field_path(field_path).split(".")[-1]
                if short:
                    extra.add(short)

        for field_path, concept in field_mappings.items():
            concept_lower = str(concept).lower()
            if any(hint in concept_lower for hint in _IDENTITY_CONCEPT_HINTS):
                short = self._normalize_field_path(field_path).split(".")[-1]
                if short:
                    extra.add(short)
        return IDENTITY_FIELDS | extra

    # --------------------------------------------------------- path helpers
    @staticmethod
    def _is_non_person_parent(full_key):
        parts = full_key.split(".")
        if len(parts) < 2:
            return False
        for part in parts[:-1]:
            if part.lower() in _NON_PERSON_PARENTS:
                return True
        return False

    @staticmethod
    def _normalize_token(value):
        return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

    def _semantic_scope(self, full_key, field_semantics=None):
        semantic = self._lookup_by_field_path(full_key, field_semantics)
        return semantic.get("scope", "") if semantic else ""

    def _semantic_role(self, full_key, field_semantics=None):
        semantic = self._lookup_by_field_path(full_key, field_semantics)
        return semantic.get("role", "") if semantic else ""

    def _semantic_concept(self, full_key, field_semantics=None):
        semantic = self._lookup_by_field_path(full_key, field_semantics)
        return semantic.get("concept", "") if semantic else ""

    def _allows_person_identity(self, full_key, field_semantics=None):
        scope = self._semantic_scope(full_key, field_semantics)
        if scope:
            return scope in _PERSON_IDENTITY_SCOPES
        return not self._is_non_person_parent(full_key)

    def _allows_person_location(self, full_key, field_semantics=None):
        scope = self._semantic_scope(full_key, field_semantics)
        if scope:
            return scope in _PERSON_LOCATION_SCOPES
        return not self._is_non_person_parent(full_key)

    def _canonical_secondary_id_key(self, full_key, short_key, field_semantics=None):
        semantic = self._lookup_by_field_path(full_key, field_semantics)
        normalized = self._normalize_token(short_key)
        if normalized in _CANONICAL_ID_KEY_OVERRIDES:
            return _CANONICAL_ID_KEY_OVERRIDES[normalized]

        concept = self._normalize_token(semantic.get("concept", "") if semantic else "")
        if concept in _CANONICAL_ID_KEY_OVERRIDES:
            return _CANONICAL_ID_KEY_OVERRIDES[concept]
        if concept:
            return semantic["concept"]
        return short_key

    def _canonical_location_key(self, short_key):
        normalized = self._normalize_token(short_key)
        return _CANONICAL_LOCATION_KEY_OVERRIDES.get(normalized)

    def _should_hard_ignore_field(self, full_key, short_key):
        key = self._normalize_token(short_key)
        if key in _IGNORE_FIELD_KEYS:
            return True
        full_lower = str(full_key or "").lower()
        return any(hint in full_lower for hint in _IGNORE_PATH_HINTS)

    # --------------------------------------------------------- identity helpers
    def _get_identity_name(self, pairs, identity_fields=None, field_mappings=None,
                           field_semantics=None):
        id_fields = identity_fields or IDENTITY_FIELDS

        if field_semantics:
            for full_key, short_key, val in pairs:
                if self._semantic_role(full_key, field_semantics) != "identity_name":
                    continue
                if not self._allows_person_identity(full_key, field_semantics):
                    continue
                val_str = str(val).strip()
                if val_str and len(val_str) > 1:
                    return val_str

        if field_mappings:
            for full_key, short_key, val in pairs:
                concept = self._lookup_by_field_path(full_key, field_mappings)
                if not concept:
                    continue
                if any(hint in str(concept).lower() for hint in _IDENTITY_CONCEPT_HINTS):
                    if not self._allows_person_identity(full_key, field_semantics):
                        continue
                    val_str = str(val).strip()
                    if val_str and len(val_str) > 1:
                        return val_str

        for full_key, short_key, val in pairs:
            if short_key in id_fields:
                if not self._allows_person_identity(full_key, field_semantics):
                    continue
                val_str = str(val).strip()
                if val_str and len(val_str) > 1:
                    return val_str

        return "Unknown User"

    def _get_secondary_ids(self, pairs, field_semantics=None):
        ids = {}
        for full_key, short_key, val in pairs:
            semantic = self._lookup_by_field_path(full_key, field_semantics)
            role = semantic.get("role", "") if semantic else ""
            strength = semantic.get("strength", "") if semantic else ""
            is_llm_identity = role == "identity" and strength in {"strong", "medium"}
            if short_key not in SECONDARY_ID_FIELDS and not is_llm_identity:
                continue
            if not self._allows_person_identity(full_key, field_semantics):
                continue
            val_str = str(val).strip()
            if val_str and val_str.lower() not in ("none", "null", ""):
                ids[self._canonical_secondary_id_key(full_key, short_key, field_semantics)] = val_str
        return ids

    def _get_location(self, pairs, field_semantics=None):
        loc = {}
        for full_key, short_key, val in pairs:
            canonical = self._canonical_location_key(short_key)
            if not canonical:
                continue
            if not self._allows_person_location(full_key, field_semantics):
                continue
            val_str = str(val).strip()
            if val_str and val_str.lower() not in ("none", "null", ""):
                loc[canonical] = val_str
        return loc

    def _build_identity_key(self, name, sec_ids, location, fallback_hash=None):
        parts = [name]
        has_id = False

        for id_type, id_val in sorted(sec_ids.items()):
            parts.append(f"{id_type}={id_val}")
            has_id = True

        if location:
            loc_key, loc_val = next(iter(sorted(location.items())))
            parts.append(f"{loc_key}={loc_val}")
            has_id = True

        if name == "Unknown User" and not has_id:
            parts.append(f"hash={fallback_hash or 'unknown'}")

        return "|".join(parts)

    def _build_display_name(self, name, identity_key, all_keys_by_name):
        siblings = all_keys_by_name.get(name, [])
        if len(siblings) <= 1:
            return name

        parts = identity_key.split("|")[1:]
        if parts:
            for p in parts:
                if any(p.startswith(f"{f}=") for f in SECONDARY_ID_FIELDS):
                    return f"{name} ({p.split('=', 1)[1]})"
            val = parts[0].split("=", 1)[1] if "=" in parts[0] else parts[0]
            return f"{name} ({val})"

        idx = siblings.index(identity_key) + 1
        return f"{name} #{idx}"

    # --------------------------------------------------------- link classification
    def _classify_field(self, full_key, short_key, field_semantics=None):
        """Classify a field as (strength, role, scope) or (None, None, None).

        Strong identity links: email, phone, government/voter IDs, etc.
        Medium identity links: username.
        Weak/context links: scoped location-style fields.
        """
        if self._should_hard_ignore_field(full_key, short_key):
            return None, None, None

        semantic = self._lookup_by_field_path(full_key, field_semantics)

        if short_key in STRONG_ID_FIELDS:
            if not self._allows_person_identity(full_key, field_semantics):
                return None, None, None
            scope = semantic.get("scope") if semantic and semantic.get("scope") else "person.identity"
            return "strong", "identity", scope
        if short_key in MEDIUM_ID_FIELDS:
            if not self._allows_person_identity(full_key, field_semantics):
                return None, None, None
            scope = semantic.get("scope") if semantic and semantic.get("scope") else "person.identity"
            return "medium", "identity", scope

        if semantic:
            role = semantic.get("role")
            strength = semantic.get("strength")
            if role == "ignore":
                return None, None, None
            if role == "identity_name":
                return None, None, None
            if role in {"identity", "context"} and strength in {"strong", "medium", "weak"}:
                return strength, role, semantic.get("scope") or self._compute_scope(full_key)

        # Everything else becomes a weak context leaf node
        return "weak", "context", self._compute_scope(full_key)

    @staticmethod
    def _normalize_value(value, strength):
        """Normalize value for matching. Preserves display value separately."""
        val = str(value).strip()
        if not val:
            return val
        if strength == "strong":
            # emails: lowercase trimmed
            if "@" in val:
                return val.lower().strip()
            # phones: digits only
            digits = re.sub(r'\D', '', val)
            if len(digits) >= 7:
                return digits
            # other IDs: trimmed case-folded
            return val.strip().lower()
        # medium and weak: case-fold
        return val.strip().lower()

    @staticmethod
    def _compute_scope(full_key):
        """Compute scope from full field path.

        voter.location.city -> 'voter.location'
        employer.address.city -> 'employer.address'
        city -> ''
        """
        parts = full_key.rsplit(".", 1)
        return parts[0] if len(parts) > 1 else ""

    # --------------------------------------------------------- cursor helpers
    @staticmethod
    def _encode_cursor(*args):
        return base64.urlsafe_b64encode(json.dumps(list(args)).encode()).decode()

    @staticmethod
    def _decode_cursor(cursor):
        return json.loads(base64.urlsafe_b64decode(cursor.encode()))

    @staticmethod
    def _build_metadata_response(build_id, created_at, total_users,
                                 total_mentions, status="completed"):
        return {
            "build_id": build_id,
            "total_users": total_users,
            "total_mentions": total_mentions,
            "page_size": 100,
            "sort": "alphabetical",
            "status": status,
            "created_at": created_at,
        }

    async def _find_latest_incomplete_build(self, db, owner_user_id,
                                            target_db_name, use_llm):
        return await db[BUILDS_COL].find_one(
            {
                "owner_user_id": owner_user_id,
                "db_name": target_db_name,
                "use_llm": use_llm,
                "status": {"$in": list(INCOMPLETE_BUILD_STATUSES)},
            },
            sort=[("created_at", -1)],
        )

    async def _get_resumable_build_doc(self, db, owner_user_id,
                                       target_db_name, use_llm):
        doc = await self._find_latest_incomplete_build(
            db, owner_user_id, target_db_name, use_llm
        )
        if not doc:
            return None

        phase = str(doc.get("phase", "")).strip().lower()
        tmp_rec_name = str(doc.get("tmp_rec_name", "")).strip()
        if phase not in RESUMABLE_PHASES or not tmp_rec_name:
            return None

        tmp_exists = bool(
            await db.list_collection_names(filter={"name": tmp_rec_name})
        )
        if not tmp_exists:
            return None

        return doc

    async def get_resumable_build(self, target_db_name: str, owner_user_id: str,
                                  use_llm: bool):
        db = self.client[target_db_name]
        doc = await self._get_resumable_build_doc(
            db, owner_user_id, target_db_name, use_llm
        )
        if not doc:
            return None

        return {
            "build_id": doc["build_id"],
            "phase": doc.get("phase", "building"),
            "created_at": doc.get("created_at"),
        }

    async def list_resumable_builds(self, target_db_name: str):
        db = self.client[target_db_name]
        docs = await db[BUILDS_COL].find(
            {
                "status": {"$in": list(INCOMPLETE_BUILD_STATUSES)},
                "phase": {"$in": list(RESUMABLE_PHASES)},
            },
            {"build_id": 1, "owner_user_id": 1, "use_llm": 1,
             "phase": 1, "created_at": 1, "tmp_rec_name": 1},
        ).to_list(100)

        resumable = []
        for doc in docs:
            tmp_rec_name = str(doc.get("tmp_rec_name", "")).strip()
            if not tmp_rec_name:
                continue
            tmp_exists = bool(
                await db.list_collection_names(filter={"name": tmp_rec_name})
            )
            if not tmp_exists:
                continue
            resumable.append(doc)

        return resumable

    async def _cleanup_incomplete_build(self, db, build_doc, reason=""):
        build_id = build_doc["build_id"]
        tmp_rec_name = str(build_doc.get("tmp_rec_name", "")).strip()

        if tmp_rec_name:
            await db.drop_collection(tmp_rec_name)
            # Drop any sub-temp collections from merge/materialize phases
            for suffix in ("_merges", "_users", "_ncnt"):
                await db.drop_collection(f"{tmp_rec_name}{suffix}")
        await db[USERS_COL].delete_many({"build_id": build_id})
        await db[MENTIONS_COL].delete_many({"build_id": build_id})
        await db[BUILDS_COL].update_one(
            {"build_id": build_id},
            {"$set": {
                "status": "error",
                "phase": "discarded",
                "last_error": reason[:1000] if reason else "discarded",
                "updated_at": time.time(),
            }},
        )

    # -------------------------------------------------------------- main build
    async def build_identity_index(self, target_db_name: str, owner_user_id: str,
                                   build_id: str, field_mappings: dict = None,
                                   field_semantics: dict = None,
                                   preprocessing_rules: dict = None,
                                   force_refresh: bool = False):
        """
        Build identity index. Materializes traversable data into three
        MongoDB collections for lazy exploration.

        Phase 1 -- extract identity info + mentions in one DB pass.
        Merge   -- server-side aggregation finds transitive identity groups;
                   bulk-updates both temp records and mentions.
        Materialize -- aggregate temp records for user summaries.

        Returns compact build metadata (no full tree).
        """
        field_mappings = self._with_normalized_field_keys(field_mappings or {})
        field_semantics = self._with_normalized_field_keys(field_semantics or {})
        preprocessing_rules = preprocessing_rules or {}
        array_rules = preprocessing_rules.get("array_rules", {})
        use_llm = bool(field_mappings or field_semantics)

        db = self.client[target_db_name]
        now = time.time()
        created_at = now
        tmp_rec_name = ""
        tmp_rec = None
        current_phase = ""
        total_records = 0
        total_mentions = 0
        total_users = 0
        collections = []
        cleanup_tmp_rec = False
        resumed = False

        if not force_refresh and not DEBUG_LIMIT:
            resumable = await self._get_resumable_build_doc(
                db, owner_user_id, target_db_name, use_llm
            )
            if resumable:
                resumed = True
                build_id = resumable["build_id"]
                created_at = resumable.get("created_at", now)
                tmp_rec_name = resumable["tmp_rec_name"]
                tmp_rec = db[tmp_rec_name]
                current_phase = str(resumable.get("phase", "merging")).strip().lower()
                total_records = int(resumable.get("total_records") or 0)
                total_mentions = int(resumable.get("total_mentions") or 0)
                total_users = int(resumable.get("total_users") or 0)

                if not total_records:
                    total_records = await tmp_rec.count_documents({})
                if not total_mentions:
                    total_mentions = await db[MENTIONS_COL].count_documents(
                        {"build_id": build_id}
                    )
                if current_phase == "indexing" and not total_users:
                    total_users = await db[USERS_COL].count_documents(
                        {"build_id": build_id}
                    )

                await db[BUILDS_COL].update_one(
                    {"build_id": build_id},
                    {"$set": {
                        "status": "building",
                        "phase": current_phase,
                        "updated_at": time.time(),
                    }},
                )
                print(
                    f"[IdentityIndex] Resuming build {build_id} from phase "
                    f"'{current_phase}' using '{tmp_rec_name}'..."
                )

        if not resumed:
            incomplete = await self._find_latest_incomplete_build(
                db, owner_user_id, target_db_name, use_llm
            )
            if incomplete:
                await self._cleanup_incomplete_build(
                    db,
                    incomplete,
                    "Previous incomplete build could not be resumed and was replaced.",
                )

            if not force_refresh and not DEBUG_LIMIT:
                existing = await db[BUILDS_COL].find_one(
                    {"owner_user_id": owner_user_id, "db_name": target_db_name,
                     "status": "completed", "use_llm": use_llm},
                    sort=[("created_at", -1)],
                )
                if existing:
                    print(f"[IdentityIndex] Reusing existing build {existing['build_id']}")
                    return self._build_metadata_response(
                        existing["build_id"],
                        existing.get("created_at"),
                        existing.get("total_users", 0),
                        existing.get("total_mentions", 0),
                    )

            all_collections = await db.list_collection_names()
            collections = [c for c in all_collections
                           if not c.startswith("mg_identity_")
                           and not c.startswith("mg_debug_")
                           and not c.startswith("_tmp_")
                           and not c.startswith("system.")
                           and not c.startswith("_meta")]

            await db[BUILDS_COL].update_many(
                {"owner_user_id": owner_user_id, "db_name": target_db_name,
                 "status": "completed"},
                {"$set": {"status": "expired"}},
            )

            uid = uuid.uuid4().hex[:10]
            tmp_rec_name = f"_tmp_ut_rec_{uid}"
            tmp_rec = db[tmp_rec_name]
            current_phase = "extracting"
            await db[BUILDS_COL].insert_one({
                "build_id": build_id,
                "owner_user_id": owner_user_id,
                "db_name": target_db_name,
                "use_llm": use_llm,
                "status": "building",
                "phase": current_phase,
                "created_at": now,
                "updated_at": now,
                "expires_at": now + 86400 * 7,
                "tmp_rec_name": tmp_rec_name,
                "total_users": 0,
                "total_mentions": 0,
                "total_records": 0,
            })

        try:
            BATCH = 1000

            if current_phase == "extracting":
                id_fields = self._effective_identity_fields(
                    field_mappings, field_semantics
                )

                print(
                    f"[IdentityIndex] Phase 1: Extracting identities into "
                    f"'{tmp_rec_name}'..."
                )

                # Create compound index for mention upserts before extraction
                # so each upsert is an indexed lookup rather than a full scan.
                await db[MENTIONS_COL].create_index([
                    ("build_id", 1), ("owner_user_id", 1), ("user_key", 1),
                    ("role", 1), ("scope", 1), ("field_path", 1), ("norm_value", 1),
                ], background=True)

                write_buf = []
                mention_buf = []

                docs_processed = 0

                for col_name in collections:
                    if DEBUG_LIMIT and docs_processed >= DEBUG_LIMIT:
                        break

                    cursor = db[col_name].find({}, batch_size=SOURCE_CURSOR_BATCH_SIZE)
                    async for doc in cursor:
                        if DEBUG_LIMIT and docs_processed >= DEBUG_LIMIT:
                            break

                        data_content = doc.get("data", doc)
                        doc_id = str(doc.get("_id", ""))
                        rows = list(self._extract_dicts(data_content))
                        if not rows and isinstance(data_content, dict):
                            rows = [data_content]

                        docs_processed += 1

                        for row_idx, row in enumerate(rows):
                            # Smart preprocessing: resolve selection arrays etc.
                            if array_rules:
                                row = self._preprocess_doc(row, array_rules)
                            pairs = self._flatten_doc(row)
                            if not pairs:
                                continue

                            name = self._get_identity_name(
                                pairs, id_fields, field_mappings, field_semantics
                            )
                            sec_ids = self._get_secondary_ids(pairs, field_semantics)
                            location = self._get_location(pairs, field_semantics)

                            fallback_hash = hashlib.md5(
                                f"{col_name}:{doc_id}:{row_idx}".encode()
                            ).hexdigest()[:10]
                            ik = self._build_identity_key(
                                name, sec_ids, location, fallback_hash
                            )

                            sec_id_keys = [f"{k}:{v}" for k, v in sec_ids.items()]
                            name_addr = None
                            name_email = None
                            if name != "Unknown User":
                                addr = location.get("address")
                                if addr:
                                    name_addr = f"{name}|{addr}"
                                email = sec_ids.get("email")
                                if email:
                                    name_email = f"{name}|{email}"

                            write_buf.append({
                                "ik": ik,
                                "n": name,
                                "si": sec_ids,
                                "sik": sec_id_keys,
                                "na": name_addr,
                                "ne": name_email,
                                "col": col_name,
                                "did": doc_id,
                                "ri": row_idx,
                            })
                            total_records += 1

                            if len(write_buf) >= BATCH:
                                await tmp_rec.insert_many(write_buf, ordered=False)
                                write_buf.clear()

                            seen = set()
                            for full_key, short_key, val in pairs:
                                if short_key in id_fields:
                                    continue
                                strength, role, scope = self._classify_field(
                                    full_key, short_key, field_semantics
                                )
                                if strength is None:
                                    continue
                                val_str = str(val).strip()
                                if not val_str or val_str.lower() in ("none", "null", "", "0"):
                                    continue
                                if len(val_str) > 200:
                                    continue
                                norm = self._normalize_value(val_str, strength)
                                if not norm:
                                    continue
                                dedup = f"{ik}:{role}:{scope}:{full_key}:{norm}"
                                if dedup in seen:
                                    continue
                                seen.add(dedup)

                                # Pre-aggregate: upsert one doc per unique
                                # (user_key, role, scope, field_path, norm_value)
                                # accumulating doc_count, collections, doc_ids.
                                mention_buf.append(_UpdateOne(
                                    {
                                        "build_id": build_id,
                                        "owner_user_id": owner_user_id,
                                        "user_key": ik,
                                        "role": role,
                                        "scope": scope,
                                        "field_path": full_key,
                                        "norm_value": norm,
                                    },
                                    {
                                        "$setOnInsert": {
                                            "display_value": val_str[:100],
                                            "strength": strength,
                                        },
                                        "$inc": {"doc_count": 1},
                                        "$addToSet": {
                                            "collections": col_name,
                                            "doc_ids": doc_id,
                                        },
                                    },
                                    upsert=True,
                                ))

                                if len(mention_buf) >= BATCH:
                                    await db[MENTIONS_COL].bulk_write(
                                        mention_buf, ordered=False
                                    )
                                    mention_buf.clear()

                if write_buf:
                    await tmp_rec.insert_many(write_buf, ordered=False)
                if mention_buf:
                    await db[MENTIONS_COL].bulk_write(mention_buf, ordered=False)

                # Count unique pre-aggregated mention groups (not raw occurrences)
                total_mentions = await db[MENTIONS_COL].count_documents(
                    {"build_id": build_id}
                )

                if total_records == 0:
                    await db[BUILDS_COL].update_one(
                        {"build_id": build_id},
                        {"$set": {
                            "status": "completed",
                            "phase": "completed",
                            "total_users": 0,
                            "total_mentions": 0,
                            "total_records": 0,
                            "updated_at": time.time(),
                        }},
                    )
                    cleanup_tmp_rec = True
                    return self._build_metadata_response(
                        build_id, created_at, 0, 0
                    )

                print(f"[IdentityIndex]   {total_records} records extracted")
                await tmp_rec.create_index("ik")
                current_phase = "merging"
                await db[BUILDS_COL].update_one(
                    {"build_id": build_id},
                    {"$set": {
                        "phase": current_phase,
                        "total_records": total_records,
                        "total_mentions": total_mentions,
                        "updated_at": time.time(),
                    }},
                )

            if current_phase == "merging":
                print("[IdentityIndex] Merge: Finding transitive identity groups...")

                # -- Phase 2a: write overlaps into a temp merges collection --
                tmp_merges_name = f"{tmp_rec_name}_merges"
                tmp_merges = db[tmp_merges_name]
                await tmp_merges.drop()

                merge_buf = []

                async def _flush_merges():
                    nonlocal merge_buf
                    if merge_buf:
                        await tmp_merges.bulk_write([
                            # Use $min so the smallest canonical wins across
                            # all three aggregation passes
                            _UpdateOne(
                                {"_id": doc["_id"]},
                                {"$min": {"c": doc["c"]}},
                                upsert=True,
                            ) for doc in merge_buf
                        ], ordered=False)
                        merge_buf = []

                # Helper – emit merge docs from one overlap aggregation
                async def _collect_overlaps(pipeline):
                    nonlocal merge_buf
                    async for doc in tmp_rec.aggregate(pipeline, allowDiskUse=True):
                        iks = doc["iks"]
                        canonical = min(iks)
                        for ik in iks:
                            if ik != canonical:
                                merge_buf.append({"_id": ik, "c": canonical})
                                if len(merge_buf) >= BATCH:
                                    await _flush_merges()

                await _collect_overlaps([
                    {"$unwind": "$sik"},
                    {"$group": {"_id": "$sik", "iks": {"$addToSet": "$ik"}}},
                    {"$match": {"iks.1": {"$exists": True}}},
                ])
                await _collect_overlaps([
                    {"$match": {"na": {"$ne": None}}},
                    {"$group": {"_id": "$na", "iks": {"$addToSet": "$ik"}}},
                    {"$match": {"iks.1": {"$exists": True}}},
                ])
                await _collect_overlaps([
                    {"$match": {"ne": {"$ne": None}}},
                    {"$group": {"_id": "$ne", "iks": {"$addToSet": "$ik"}}},
                    {"$match": {"iks.1": {"$exists": True}}},
                ])
                await _flush_merges()

                # -- Phase 2b: resolve transitive chains with $graphLookup --
                # Single server-side pass follows full chains (A->B->C->D)
                # without iterative Python round-trips.
                print("[IdentityIndex] Merge: Resolving transitive chains with $graphLookup...")
                tmp_resolved_name = f"{tmp_merges_name}_resolved"
                await db.drop_collection(tmp_resolved_name)

                await tmp_merges.aggregate([
                    {
                        "$graphLookup": {
                            "from": tmp_merges_name,
                            "startWith": "$c",
                            "connectFromField": "c",
                            "connectToField": "_id",
                            "as": "_chain",
                            "maxDepth": 50,
                            "depthField": "_depth",
                        }
                    },
                    {
                        # Walk the chain to find the deepest element's canonical
                        # (the deepest hop's "c" is the ultimate root).
                        "$project": {
                            "_id": 1,
                            "_root": {
                                "$reduce": {
                                    "input": "$_chain",
                                    "initialValue": {"_depth": -1, "c": "$c"},
                                    "in": {
                                        "$cond": [
                                            {"$gt": ["$$this._depth", "$$value._depth"]},
                                            {"_depth": "$$this._depth", "c": "$$this.c"},
                                            "$$value",
                                        ]
                                    },
                                }
                            },
                        }
                    },
                    {
                        "$project": {
                            "_id": 1,
                            "c": "$_root.c",
                        }
                    },
                    # Only write docs where the resolved canonical differs
                    {"$match": {"$expr": {"$ne": ["$_id", "$c"]}}},
                    {
                        "$merge": {
                            "into": tmp_resolved_name,
                            "whenMatched": "replace",
                            "whenNotMatched": "insert",
                        }
                    },
                ], allowDiskUse=True).to_list(None)

                # Apply resolved canonicals back to tmp_merges in batches
                updates = []
                async for doc in db[tmp_resolved_name].find():
                    updates.append(_UpdateOne(
                        {"_id": doc["_id"]},
                        {"$set": {"c": doc["c"]}},
                    ))
                    if len(updates) >= BATCH:
                        await tmp_merges.bulk_write(updates, ordered=False)
                        updates = []
                if updates:
                    await tmp_merges.bulk_write(updates, ordered=False)

                await db.drop_collection(tmp_resolved_name)

                # -- Phase 2c: apply merges in batches from temp collection --
                # Stream sorted by canonical so we can batch $in updates per
                # target without grouping into a single BSON doc (16 MB limit).
                merge_count = await tmp_merges.count_documents({})
                if merge_count:
                    cur_canonical = None
                    old_iks_buf = []

                    async def _flush_merge_group(new_ik, old_iks):
                        await tmp_rec.update_many(
                            {"ik": {"$in": old_iks}},
                            {"$set": {"ik": new_ik}},
                        )
                        # Pre-aggregated mentions: stream old docs, group them,
                        # upsert into the canonical user_key, then delete old docs.
                        merged = {}
                        async for m in db[MENTIONS_COL].find(
                            {"build_id": build_id, "user_key": {"$in": old_iks}}
                        ):
                            mkey = (m["role"], m["scope"], m["field_path"], m["norm_value"])
                            if mkey not in merged:
                                merged[mkey] = {
                                    "display_value": m.get("display_value", m.get("norm_value", "")),
                                    "strength": m.get("strength", "weak"),
                                    "doc_count": 0,
                                    "collections": set(),
                                    "doc_ids": set(),
                                }
                            e = merged[mkey]
                            e["doc_count"] += m.get("doc_count", 1)
                            e["collections"].update(m.get("collections", []))
                            e["doc_ids"].update(m.get("doc_ids", []))

                        if merged:
                            upserts = []
                            for (role, scope, field_path, norm_value), e in merged.items():
                                upserts.append(_UpdateOne(
                                    {
                                        "build_id": build_id,
                                        "owner_user_id": owner_user_id,
                                        "user_key": new_ik,
                                        "role": role,
                                        "scope": scope,
                                        "field_path": field_path,
                                        "norm_value": norm_value,
                                    },
                                    {
                                        "$setOnInsert": {
                                            "display_value": e["display_value"],
                                            "strength": e["strength"],
                                        },
                                        "$inc": {"doc_count": e["doc_count"]},
                                        "$addToSet": {
                                            "collections": {"$each": list(e["collections"])},
                                            "doc_ids": {"$each": list(e["doc_ids"])},
                                        },
                                    },
                                    upsert=True,
                                ))
                                if len(upserts) >= BATCH:
                                    await db[MENTIONS_COL].bulk_write(upserts, ordered=False)
                                    upserts = []
                            if upserts:
                                await db[MENTIONS_COL].bulk_write(upserts, ordered=False)

                        await db[MENTIONS_COL].delete_many(
                            {"build_id": build_id, "user_key": {"$in": old_iks}}
                        )

                    async for doc in tmp_merges.find().sort("c"):
                        if doc["c"] != cur_canonical:
                            if old_iks_buf:
                                await _flush_merge_group(cur_canonical, old_iks_buf)
                            cur_canonical = doc["c"]
                            old_iks_buf = []
                        old_iks_buf.append(doc["_id"])
                        if len(old_iks_buf) >= BATCH:
                            await _flush_merge_group(cur_canonical, old_iks_buf)
                            old_iks_buf = []
                    if old_iks_buf:
                        await _flush_merge_group(cur_canonical, old_iks_buf)

                    print(f"[IdentityIndex]   Merged {merge_count} identity keys")

                await db.drop_collection(tmp_merges_name)

                print(f"[IdentityIndex]   {total_mentions} mentions extracted")
                current_phase = "materializing"
                await db[BUILDS_COL].update_one(
                    {"build_id": build_id},
                    {"$set": {
                        "phase": current_phase,
                        "total_mentions": total_mentions,
                        "updated_at": time.time(),
                    }},
                )

            # ============================================================
            # MATERIALIZE -- aggregate tmp_rec for user summaries
            # No second DB scan needed — mentions already written in Phase 1
            # ============================================================
            if current_phase == "materializing":
                print("[IdentityIndex] Materializing user summaries...")
                await db[USERS_COL].delete_many({"build_id": build_id})

                # -- Step 1: aggregate tmp_rec into a temp users collection --
                tmp_users_name = f"{tmp_rec_name}_users"
                tmp_users = db[tmp_users_name]
                await tmp_users.drop()

                await tmp_rec.aggregate([
                    {"$group": {
                        "_id": "$ik",
                        "names": {"$addToSet": "$n"},
                        "sec_ids": {"$mergeObjects": "$si"},
                        "collections": {"$addToSet": "$col"},
                        "record_count": {"$sum": 1},
                    }},
                    {"$merge": {
                        "into": tmp_users_name,
                        "whenMatched": "replace",
                        "whenNotMatched": "insert",
                    }},
                ], allowDiskUse=True).to_list(None)

                # -- Step 2: build name-count lookup (small: one doc per name) --
                # Pick the best name per user, then count how many users share it.
                tmp_name_counts_name = f"{tmp_rec_name}_ncnt"
                tmp_name_counts = db[tmp_name_counts_name]
                await tmp_name_counts.drop()

                await tmp_users.aggregate([
                    {"$project": {
                        "name": {
                            "$let": {
                                "vars": {
                                    "real": {
                                        "$filter": {
                                            "input": "$names",
                                            "cond": {"$ne": ["$$this", "Unknown User"]},
                                        }
                                    }
                                },
                                "in": {
                                    "$cond": {
                                        "if": {"$gt": [{"$size": "$$real"}, 0]},
                                        "then": {"$arrayElemAt": ["$$real", 0]},
                                        "else": "Unknown User",
                                    }
                                },
                            }
                        }
                    }},
                    # Only store the count — no $push of iks (avoids 16 MB doc limit)
                    {"$group": {"_id": "$name", "cnt": {"$sum": 1}}},
                    {"$match": {"cnt": {"$gt": 1}}},
                    {"$merge": {
                        "into": tmp_name_counts_name,
                        "whenMatched": "replace",
                        "whenNotMatched": "insert",
                    }},
                ], allowDiskUse=True).to_list(None)

                # Build a set of ambiguous names (cnt > 1).
                # Bounded by number of colliding names, not total users.
                ambiguous_names = set()
                async for nc in tmp_name_counts.find():
                    ambiguous_names.add(nc["_id"])

                await db.drop_collection(tmp_name_counts_name)

                # -- Step 3: stream temp users, write to final collection --
                # Track a running counter per ambiguous name for the rare
                # fallback case where identity_key has no secondary ID fields.
                name_counters = defaultdict(int)
                user_buf = []
                total_users = 0
                async for doc in tmp_users.find():
                    ik = doc["_id"]
                    name = "Unknown User"
                    for n in doc.get("names", []):
                        if n != "Unknown User":
                            name = n
                            break
                    merged_sec_ids = doc.get("sec_ids") or {}

                    # Disambiguation: only needed if name is shared
                    if name in ambiguous_names:
                        parts = ik.split("|")[1:]
                        if parts:
                            display_name = name
                            for p in parts:
                                if any(p.startswith(f"{f}=")
                                       for f in SECONDARY_ID_FIELDS):
                                    display_name = f"{name} ({p.split('=', 1)[1]})"
                                    break
                            else:
                                val = (parts[0].split("=", 1)[1]
                                       if "=" in parts[0] else parts[0])
                                display_name = f"{name} ({val})"
                        else:
                            name_counters[name] += 1
                            display_name = f"{name} #{name_counters[name]}"
                    else:
                        display_name = name

                    sort_name = display_name.lower()
                    identifiers = {k: str(v) for k, v in merged_sec_ids.items()}

                    user_buf.append({
                        "build_id": build_id,
                        "owner_user_id": owner_user_id,
                        "user_key": ik,
                        "display_name": display_name,
                        "sort_name": sort_name,
                        "identifiers": identifiers,
                        "record_count": doc["record_count"],
                        "collection_count": len(doc.get("collections", [])),
                        "preview": {
                            "collections": list(doc.get("collections", []))[:5],
                        },
                    })

                    if len(user_buf) >= BATCH:
                        await db[USERS_COL].insert_many(user_buf, ordered=False)
                        total_users += len(user_buf)
                        user_buf.clear()

                if user_buf:
                    await db[USERS_COL].insert_many(user_buf, ordered=False)
                    total_users += len(user_buf)

                await db.drop_collection(tmp_users_name)
                del ambiguous_names
                print(f"[IdentityIndex]   {total_users} users materialized")
                current_phase = "indexing"
                await db[BUILDS_COL].update_one(
                    {"build_id": build_id},
                    {"$set": {
                        "phase": current_phase,
                        "total_users": total_users,
                        "updated_at": time.time(),
                    }},
                )

            if current_phase == "indexing":
                print("[IdentityIndex] Creating indexes...")
                await db[USERS_COL].create_index(
                    [("owner_user_id", 1), ("build_id", 1),
                     ("sort_name", 1), ("user_key", 1)]
                )
                await db[MENTIONS_COL].create_index(
                    [("owner_user_id", 1), ("build_id", 1),
                     ("role", 1), ("scope", 1),
                     ("norm_value", 1), ("user_key", 1)]
                )
                await db[MENTIONS_COL].create_index(
                    [("owner_user_id", 1), ("build_id", 1),
                     ("user_key", 1), ("role", 1), ("scope", 1)]
                )
                await db[BUILDS_COL].create_index(
                    [("owner_user_id", 1), ("db_name", 1), ("status", 1)]
                )

                await db[BUILDS_COL].update_one(
                    {"build_id": build_id},
                    {"$set": {
                        "status": "completed",
                        "phase": "completed",
                        "total_users": total_users,
                        "total_mentions": total_mentions,
                        "updated_at": time.time(),
                    }},
                )

                expired = await db[BUILDS_COL].find(
                    {"owner_user_id": owner_user_id, "db_name": target_db_name,
                     "status": "expired"},
                ).to_list(100)
                for exp in expired:
                    eid = exp["build_id"]
                    await db[USERS_COL].delete_many({"build_id": eid})
                    await db[MENTIONS_COL].delete_many({"build_id": eid})
                    await db[BUILDS_COL].delete_one({"build_id": eid})
                if expired:
                    print(f"[IdentityIndex]   Cleaned up {len(expired)} expired builds")

                cleanup_tmp_rec = True
                print(f"[IdentityIndex] Build {build_id} completed: "
                      f"{total_users} users, {total_mentions} mentions")

                return self._build_metadata_response(
                    build_id, created_at, total_users, total_mentions
                )

        except Exception as exc:
            resumable_failure = current_phase in RESUMABLE_PHASES
            await db[BUILDS_COL].update_one(
                {"build_id": build_id},
                {"$set": {
                    "status": "paused" if resumable_failure else "error",
                    "phase": current_phase or "error",
                    "last_error": str(exc)[:2000],
                    "updated_at": time.time(),
                }},
            )
            if not resumable_failure:
                await db[USERS_COL].delete_many({"build_id": build_id})
                await db[MENTIONS_COL].delete_many({"build_id": build_id})
                cleanup_tmp_rec = True
            raise
        finally:
            if cleanup_tmp_rec and tmp_rec_name:
                await db.drop_collection(tmp_rec_name)
                for suffix in ("_merges", "_users", "_ncnt"):
                    await db.drop_collection(f"{tmp_rec_name}{suffix}")
                print(f"[IdentityIndex] Cleaned up temp collection '{tmp_rec_name}'")

    # -------------------------------------------------------------- queries
    async def get_explorer_page(self, target_db_name: str, owner_user_id: str,
                                build_id: str, cursor: str = None,
                                limit: int = 100):
        """Paginated alphabetical user list for the explorer."""
        limit = min(limit, 1000)
        db = self.client[target_db_name]

        query = {
            "owner_user_id": owner_user_id,
            "build_id": build_id,
        }

        if cursor:
            sort_name, user_key = self._decode_cursor(cursor)
            query["$or"] = [
                {"sort_name": {"$gt": sort_name}},
                {"sort_name": sort_name, "user_key": {"$gt": user_key}},
            ]

        docs = await db[USERS_COL].find(
            query, {"_id": 0, "owner_user_id": 0}
        ).sort(
            [("sort_name", 1), ("user_key", 1)]
        ).limit(limit + 1).to_list(limit + 1)

        has_more = len(docs) > limit
        items = docs[:limit]

        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = self._encode_cursor(last["sort_name"], last["user_key"])

        total_key = self._total_cache_key(target_db_name, build_id)
        total = self.cache.get(total_key) if self.cache else None
        if total is None:
            total = await db[USERS_COL].count_documents({
                "owner_user_id": owner_user_id,
                "build_id": build_id,
            })
            if self.cache:
                self.cache.set(total_key, total)

        return {
            "build_id": build_id,
            "items": items,
            "next_cursor": next_cursor,
            "total_users": total,
            "limit": limit,
        }

    async def search_users(self, target_db_name: str, owner_user_id: str,
                           build_id: str, query: str, limit: int = 50):
        """Full-text prefix search across all identity-tree users by display name.

        Searches the `name` field in mg_identity_users using a case-insensitive
        regex so the user can find anyone regardless of pagination position.
        """
        limit = min(limit, 200)
        db = self.client[target_db_name]
        regex = {"$regex": query, "$options": "i"}
        docs = await db[USERS_COL].find(
            {
                "owner_user_id": owner_user_id,
                "build_id": build_id,
                "display_name": regex,
            },
            {"_id": 0, "owner_user_id": 0},
        ).sort([("sort_name", 1), ("user_key", 1)]).limit(limit).to_list(limit)
        return {"build_id": build_id, "items": docs, "total_found": len(docs), "query": query}

    # ---- sibling merge helpers (id + label detection) ----
    _SIBLING_ID_HINTS = {"id", "code", "ref", "number", "key", "num"}
    _SIBLING_LABEL_HINTS = {"name", "title", "label", "detail"}

    @classmethod
    def _sibling_field_type(cls, short_key):
        """Return 'id', 'label', or None based on field name."""
        lower = short_key.lower()
        # Exact match: field IS the hint word (e.g. "title", "id")
        if lower in cls._SIBLING_ID_HINTS:
            return "id"
        if lower in cls._SIBLING_LABEL_HINTS:
            return "label"
        # Compound: poll_id, pollId, transaction_title, etc.
        if "_" in lower:
            suffix = lower.rsplit("_", 1)[1]
            if suffix in cls._SIBLING_ID_HINTS:
                return "id"
            if suffix in cls._SIBLING_LABEL_HINTS:
                return "label"
        for h in cls._SIBLING_ID_HINTS:
            if lower.endswith(h) and len(lower) > len(h):
                return "id"
        for h in cls._SIBLING_LABEL_HINTS:
            if lower.endswith(h) and len(lower) > len(h):
                return "label"
        return None

    @classmethod
    def _field_stem(cls, short_key):
        """Extract stem. Returns None for bare hint words (e.g. 'title' -> None)."""
        lower = short_key.lower()
        all_hints = cls._SIBLING_ID_HINTS | cls._SIBLING_LABEL_HINTS
        if lower in all_hints:
            return None  # bare word, match by parent path instead
        if "_" in lower:
            parts = lower.rsplit("_", 1)
            if parts[1] in all_hints:
                return parts[0]
        for h in sorted(all_hints, key=len, reverse=True):
            if lower.endswith(h) and len(lower) > len(h):
                return lower[:-len(h)]
        return lower

    async def get_user_node(self, target_db_name: str, owner_user_id: str,
                            build_id: str, user_key: str):
        """Return user root node plus grouped first-level identity/context links."""
        if self.cache:
            cached = self.cache.get(self._node_cache_key(target_db_name, build_id, user_key))
            if cached is not None:
                return cached

        db = self.client[target_db_name]

        user_doc = await db[USERS_COL].find_one({
            "owner_user_id": owner_user_id,
            "build_id": build_id,
            "user_key": user_key,
        }, {"_id": 0})

        if not user_doc:
            return None

        # Fetch pre-aggregated mention docs — one per unique
        # (role, scope, field_path, norm_value) group for this user.
        # Exclude doc_ids from projection: for users with many documents these
        # arrays can be huge (one ObjectId per doc occurrence), which causes
        # BSON size issues and O(groups×doc_ids) memory blow-up in composite
        # folding. Composite folding is skipped when doc_ids are absent.
        raw_mentions = await db[MENTIONS_COL].find({
            "owner_user_id": owner_user_id,
            "build_id": build_id,
            "user_key": user_key,
        }, {"_id": 0, "doc_ids": 0}).to_list(length=5000)

        # Build groups dict directly from pre-aggregated docs.
        # doc_ids intentionally left empty — composite folding is a UX
        # enhancement and is safely skipped when doc_ids are not fetched.
        groups = {}
        for m in raw_mentions:
            gkey = (m["role"], m["scope"], m["field_path"], m["norm_value"])
            groups[gkey] = {
                "role": m["role"],
                "scope": m["scope"],
                "field_path": m["field_path"],
                "norm_value": m["norm_value"],
                "display_value": m.get("display_value", m.get("norm_value", "")),
                "strength": m.get("strength", "weak"),
                "doc_count": m.get("doc_count", 1),
                "collections": set(m.get("collections", [])),
                "doc_ids": set(),  # not fetched — avoids large-data 500 errors
            }

        # --- Dynamic sibling merging (e.g. poll_id + poll_title) ---
        parent_ids = defaultdict(list)     # parent -> [(gkey, stem)]
        parent_labels = defaultdict(list)  # parent -> [(gkey, stem)]

        for gkey, g in groups.items():
            fp = g["field_path"]
            short = fp.rsplit(".", 1)[-1] if "." in fp else fp
            parent = fp.rsplit(".", 1)[0] if "." in fp else ""
            ftype = self._sibling_field_type(short)
            if ftype == "id":
                parent_ids[parent].append((gkey, self._field_stem(short)))
            elif ftype == "label":
                parent_labels[parent].append((gkey, self._field_stem(short)))

        merged_away = set()
        for parent in set(parent_ids) & set(parent_labels):
            used_labels = set()
            for id_gkey, id_stem in parent_ids[parent]:
                best_label = None
                # First: match by stem (poll_id <-> poll_title)
                if id_stem is not None:
                    for label_gkey, label_stem in parent_labels[parent]:
                        if label_gkey not in used_labels and label_stem == id_stem:
                            best_label = label_gkey
                            break
                # Fallback: bare label word at same parent (pollId <-> title)
                if best_label is None:
                    for label_gkey, label_stem in parent_labels[parent]:
                        if label_gkey not in used_labels and label_stem is None:
                            best_label = label_gkey
                            break
                if best_label:
                    id_g = groups[id_gkey]
                    label_g = groups[best_label]
                    if id_g["doc_ids"] & label_g["doc_ids"]:
                        id_g["display_value"] = f"{label_g['display_value']} ({id_g['display_value']})"
                        merged_away.add(best_label)
                        used_labels.add(best_label)

        # --- Document-scoped composite folding ---
        # Fold context mentions into identity nodes when they come from the
        # exact same documents (subset check).  This turns scattered fields
        # like poll.pollId + poll.selectedOption + type + voteId into a single
        # enriched identity node with attributes.
        doc_to_gkeys = defaultdict(set)
        for gkey, g in groups.items():
            if gkey in merged_away:
                continue
            for did in g["doc_ids"]:
                doc_to_gkeys[did].add(gkey)

        composites = defaultdict(list)   # identity_gkey -> [attr dicts]
        folded_gkeys = set()             # context gkeys absorbed into a composite

        for gkey, g in groups.items():
            if gkey in merged_away or g["role"] != "identity":
                continue

            # Collect all gkeys that share at least one doc with this identity
            candidate_gkeys = set()
            for did in g["doc_ids"]:
                candidate_gkeys.update(doc_to_gkeys[did])
            candidate_gkeys.discard(gkey)
            candidate_gkeys -= merged_away

            for cand_gkey in candidate_gkeys:
                cand = groups[cand_gkey]
                if cand["role"] != "context":
                    continue
                # Only fold if the context mention's docs are a subset of
                # this identity's docs — meaning the attribute always
                # co-occurs with this specific identity value.
                if not cand["doc_ids"].issubset(g["doc_ids"]):
                    continue
                composites[gkey].append({
                    "field_path": cand["field_path"],
                    "display_value": cand["display_value"],
                    "norm_value": cand["norm_value"],
                    "scope": cand["scope"],
                })
                folded_gkeys.add(cand_gkey)

        # Fetch related_user_count for all active groups in ONE round-trip.
        # Previously this was one distinct() call per group (N round-trips).
        related_counts: dict = {}
        active_groups = [g for gkey, g in groups.items() if gkey not in merged_away]
        if active_groups:
            # Deduplicate (role, scope, norm_value) tuples across groups.
            seen_rsn: set = set()
            or_clauses = []
            for g in active_groups:
                rsn = (g["role"], g["scope"], g["norm_value"])
                if rsn not in seen_rsn:
                    seen_rsn.add(rsn)
                    or_clauses.append({
                        "role": g["role"],
                        "scope": g["scope"],
                        "norm_value": g["norm_value"],
                    })

            rel_pipeline = [
                {"$match": {
                    "owner_user_id": owner_user_id,
                    "build_id": build_id,
                    "user_key": {"$ne": user_key},
                    "$or": or_clauses,
                }},
                # Dedup per user_key first — same norm_value can appear via
                # multiple field_paths in pre-aggregated docs.
                {"$group": {
                    "_id": {
                        "role": "$role",
                        "scope": "$scope",
                        "norm_value": "$norm_value",
                        "user_key": "$user_key",
                    }
                }},
                # Count distinct users per (role, scope, norm_value).
                {"$group": {
                    "_id": {
                        "role": "$_id.role",
                        "scope": "$_id.scope",
                        "norm_value": "$_id.norm_value",
                    },
                    "count": {"$sum": 1},
                }},
            ]
            async for doc in db[MENTIONS_COL].aggregate(
                rel_pipeline, allowDiskUse=True
            ):
                key = (doc["_id"]["role"], doc["_id"]["scope"], doc["_id"]["norm_value"])
                related_counts[key] = doc["count"]

        # Build children lists with related user counts
        identity_children = []
        context_children = []

        for gkey, g in groups.items():
            if gkey in merged_away:
                continue

            related_user_count = related_counts.get(
                (g["role"], g["scope"], g["norm_value"]), 0
            )

            node = {
                "type": "related_value",
                "role": g["role"],
                "strength": g["strength"],
                "scope": g["scope"],
                "field_path": g["field_path"],
                "norm_value": g["norm_value"],
                "display_value": g["display_value"],
                "related_user_count": related_user_count,
                "doc_count": g["doc_count"],
                "collections": list(g["collections"]),
                "expandable": related_user_count > 0,
            }

            if g["role"] == "identity":
                if gkey in composites:
                    node["attributes"] = composites[gkey]
                identity_children.append(node)
            else:
                # Skip folded context nodes that have 0 related users —
                # they only exist as attributes on their parent composite.
                # Keep folded nodes that DO have related users so they
                # remain navigable as standalone context links.
                if gkey in folded_gkeys and related_user_count == 0:
                    continue
                context_children.append(node)

        result_groups = []
        if identity_children:
            result_groups.append({
                "type": "identity_group",
                "label": "Identity Links",
                "children": identity_children,
            })
        if context_children:
            result_groups.append({
                "type": "context_group",
                "label": "Context Links",
                "children": context_children,
            })

        result = {**user_doc, "groups": result_groups}
        if self.cache:
            self.cache.set(
                self._node_cache_key(target_db_name, build_id, user_key),
                result,
            )
        return result

    async def expand_mention(self, target_db_name: str, owner_user_id: str,
                             build_id: str, user_key: str,
                             role: str, scope: str, norm_value: str,
                             cursor: str = None, limit: int = 50):
        """Return related users for an expanded identity/context link."""
        limit = min(limit, 100)

        if self.cache:
            ck = self._expand_cache_key(target_db_name, build_id, user_key,
                                        role, scope, norm_value, cursor)
            cached = self.cache.get(ck)
            if cached is not None:
                return cached

        db = self.client[target_db_name]

        base_match = {
            "owner_user_id": owner_user_id,
            "build_id": build_id,
            "role": role,
            "scope": scope,
            "norm_value": norm_value,
            "user_key": {"$ne": user_key},
        }

        if cursor:
            cursor_key = self._decode_cursor(cursor)[0]
            base_match["user_key"] = {"$ne": user_key, "$gt": cursor_key}

        # Aggregate distinct related users.
        # With pre-aggregated mentions, doc_count is stored per doc and
        # collections is already an array — flatten with $reduce after $group.
        pipeline = [
            {"$match": base_match},
            {"$group": {
                "_id": "$user_key",
                "strength": {"$first": "$strength"},
                "all_collections": {"$push": "$collections"},
                "doc_count": {"$sum": "$doc_count"},
            }},
            {"$project": {
                "strength": 1,
                "doc_count": 1,
                "collections": {
                    "$reduce": {
                        "input": "$all_collections",
                        "initialValue": [],
                        "in": {"$setUnion": ["$$value", "$$this"]},
                    }
                },
            }},
            {"$sort": {"_id": 1}},
            {"$limit": limit + 1},
        ]

        results = []
        async for doc in db[MENTIONS_COL].aggregate(pipeline, allowDiskUse=True):
            results.append(doc)

        has_more = len(results) > limit
        results = results[:limit]

        # Batch fetch user summaries
        user_map = {}
        if results:
            user_keys = [r["_id"] for r in results]
            user_docs = await db[USERS_COL].find({
                "owner_user_id": owner_user_id,
                "build_id": build_id,
                "user_key": {"$in": user_keys},
            }, {"_id": 0}).to_list(len(user_keys))
            user_map = {d["user_key"]: d for d in user_docs}

        items = []
        for r in results:
            uk = r["_id"]
            udoc = user_map.get(uk, {})
            items.append({
                "type": "related_user",
                "user_key": uk,
                "display_name": udoc.get("display_name", uk),
                "identifiers": udoc.get("identifiers", {}),
                "record_count": udoc.get("record_count", 0),
                "collection_count": udoc.get("collection_count", 0),
                "strength": r["strength"],
                "scope": scope,
                "doc_count": r["doc_count"],
                "collections": r["collections"],
            })

        next_cursor = None
        if has_more and items:
            next_cursor = self._encode_cursor(items[-1]["user_key"])

        # Total related users (without cursor filter)
        count_pipeline = [
            {"$match": {
                "owner_user_id": owner_user_id,
                "build_id": build_id,
                "role": role,
                "scope": scope,
                "norm_value": norm_value,
                "user_key": {"$ne": user_key},
            }},
            {"$group": {"_id": "$user_key"}},
            {"$count": "total"},
        ]
        count_result = await db[MENTIONS_COL].aggregate(count_pipeline).to_list(1)
        total = count_result[0]["total"] if count_result else 0

        result = {
            "items": items,
            "next_cursor": next_cursor,
            "total": total,
        }
        if self.cache:
            self.cache.set(
                self._expand_cache_key(target_db_name, build_id, user_key,
                                       role, scope, norm_value, cursor),
                result,
            )
        return result

    async def warm_cache(self, target_db_name: str, owner_user_id: str,
                         build_id: str, top_n: int = 50):
        """Pre-warm Redis cache for the top N users by record count.

        Prioritises high-record users (most likely to be opened first).
        Remaining users are still cached lazily on first access.
        """
        if not self.cache:
            return

        print(f"[Cache] Pre-warming top {top_n} identity nodes for build {build_id}...")
        db = self.client[target_db_name]

        # Cache total user count
        total = await db[USERS_COL].count_documents({
            "owner_user_id": owner_user_id,
            "build_id": build_id,
        })
        self.cache.set(self._total_cache_key(target_db_name, build_id), total)

        # Fetch top N users sorted by record_count descending
        top_users = [
            doc["user_key"]
            async for doc in db[USERS_COL].find(
                {"owner_user_id": owner_user_id, "build_id": build_id},
                {"user_key": 1, "_id": 0},
            ).sort("record_count", -1).limit(top_n)
        ]

        sem = asyncio.Semaphore(10)
        warmed = 0
        errors = 0

        async def _warm_one(user_key: str):
            nonlocal warmed, errors
            async with sem:
                try:
                    await self.get_user_node(
                        target_db_name, owner_user_id, build_id, user_key
                    )
                    warmed += 1
                except Exception as e:
                    errors += 1
                    print(f"[Cache] Warm error for user {user_key!r}: {e}")

        await asyncio.gather(*[_warm_one(uk) for uk in top_users])
        print(f"[Cache] Pre-warm done: {warmed}/{len(top_users)} nodes cached"
              + (f", {errors} errors" if errors else ""))

    async def get_latest_build(self, target_db_name: str, owner_user_id: str,
                               use_llm: bool = None):
        """Get the latest completed build metadata for this owner/db."""
        db = self.client[target_db_name]

        query = {
            "owner_user_id": owner_user_id,
            "db_name": target_db_name,
            "status": "completed",
        }
        if use_llm is not None:
            query["use_llm"] = use_llm

        doc = await db[BUILDS_COL].find_one(
            query, {"_id": 0},
            sort=[("created_at", -1)],
        )
        if not doc:
            return None

        return {
            "build_id": doc["build_id"],
            "total_users": doc.get("total_users", 0),
            "total_mentions": doc.get("total_mentions", 0),
            "page_size": 100,
            "sort": "alphabetical",
            "status": doc["status"],
            "created_at": doc.get("created_at"),
            "use_llm": doc.get("use_llm"),
        }
