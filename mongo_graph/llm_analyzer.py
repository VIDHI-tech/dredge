"""
LLM Field Relationship Analyzer for mongo_graph.
Sends the full database schema to the LLM and asks it to identify groups
of semantically equivalent fields across all collections/documents.

Also performs document-level pattern analysis (selection arrays, noise
fields, semantic groupings) by examining sample documents.
"""

import os
import json
import hashlib
from typing import Dict, Any, List
from groq import AsyncGroq
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())


MODEL_ID = "openai/gpt-oss-120b"
LLM_ANALYSIS_CACHE_VERSION = "v5"
_ROLE_VALUES = {"identity_name", "identity", "context", "ignore", "record_id"}
_STRENGTH_VALUES = {"strong", "medium", "weak", "none"}
_PERSON_HINTS = {"person", "identity", "individual", "candidate", "voter", "user", "profile"}
_NON_PERSON_HINTS = {"employer", "employment", "company", "organization", "org", "committee", "vendor"}
_IDENTITY_NAME_HINTS = {"name", "full_name", "person_name", "candidate_name", "voter_name"}
_PERSON_ID_HINTS = {
    # Person-level identifiers: shared across records for the same person —
    # kept in sunburst because they allow cross-record grouping.
    "email", "phone", "mobile", "telephone",
    "externalaccount", "external_account", "primaryref",
    "username", "user_name", "handle", "screen_name",
    "government_id", "govt_id",
}
_LOCATION_HINTS = {
    "location", "city", "state", "zip", "zipcode", "postal", "address",
    "jurisdiction", "district", "geo", "place",
}
# Record-level unique IDs: one value per record, never shared across records.
# These clutter the sunburst with cardinality-1 slices and are excluded from display.
_RECORD_ID_SUFFIXES = (
    "id", "uid", "uuid", "guid", "key", "ref", "token", "code",
    "serial", "sequence", "seq", "num", "number",
)
_RECORD_ID_HINTS = {
    "vote", "voteid", "vote_id", "trialcastid", "trialcast_id",
    "transactionid", "transaction_id",
    "sessionid", "session_id",
    "orderid", "order_id", "recordid", "record_id",
    "invoiceid", "invoice_id", "batchid", "batch_id",
    "correlationid", "correlation_id", "traceid", "trace_id",
    "requestid", "request_id", "submissionid", "submission_id",
}


class LLMAnalyzer:
    def __init__(self, cache=None):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set in environment")
        self.client = AsyncGroq(api_key=api_key)
        self.cache = cache

    # --------------------------------------------------------- main analysis
    async def analyze_field_relationships(
        self, schema_table: str, db_name: str
    ) -> List[Dict[str, Any]]:
        """
        Ask the LLM to identify groups of semantically equivalent fields
        across all collections in the database.

        Returns a list like:
        [
            {
                "concept": "party_affiliation",
                "fields": ["data.0.0.Party", "data.0.0.candidate.partyAffiliation", ...]
            },
            ...
        ]
        """
        # Check cache — use schema_table hash as key
        hash_hex = hashlib.md5(schema_table.encode()).hexdigest()
        cache_key = f"llm_analysis:{LLM_ANALYSIS_CACHE_VERSION}:{hash_hex}"

        if self.cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                print("  Using cached LLM field analysis.")
                return cached

        print("  Sending schema to LLM for field relationship analysis...")

        system_prompt = f"""You are a data analyst. You are given the schema of a MongoDB database "{db_name}" that contains multiple collections. Each collection stores documents with different field structures (from different data sources like PDFs, CSVs, etc.).

Your task: Identify groups of fields across ALL collections that represent the SAME real-world concept, even though they may have different names or nesting structures.

This output is used for two features:
1. merging equivalent fields for graphing
2. classifying fields for an identity explorer

DATABASE SCHEMA:
{schema_table}

INSTRUCTIONS:
1. Look at the field names and example values carefully.
2. Group fields that represent the same concept. For example:
   - "Party", "partyAffiliation", "affiliatedParty", "party" all represent political party affiliation
   - "FullName", "candidate.name", "candidateName", "Name" all represent a person's name
   - "City", "candidate.city", "contributions.City" all represent a city
3. Only group fields that truly share the same semantic meaning. Do NOT group fields that happen to have similar names but different meanings.
4. Keep entity scope separate. Example: fields for a person's city should NOT be grouped with an employer or organization city. "voter.location.city" and "employer.address.city" should end up in different groups/scopes.
5. Include the FULL field path as shown in the schema (e.g., "data.0.0.Party" not just "Party").
6. Each field should appear in at most ONE group.
7. Normally only create groups where there are 2+ fields that share a concept. Exception: create a single-field group (with role "record_id") for any lone field that clearly looks like a per-record unique identifier — e.g., a field named "vote", "ballot", "submission", "tracing_id", or any field whose example values look like auto-generated codes or IDs with no repeated values across records.
8. For each group, add explorer semantics:
   - "role": one of "identity_name", "identity", "context", "ignore", or "record_id"
   - "strength": one of "strong", "medium", "weak", or "none"
   - "scope": a semantic scope like "person.identity", "person.location", "employment.location", "organization.location", or "document"
9. Use "identity_name" only for fields that represent the primary person's name (e.g. name, full_name, FullName).
10. Use "identity" for person-level identifiers that are SHARED across records for the same person: email, phone, username, external account IDs. These repeat across records so they are useful in visualizations.
11. Use "record_id" for fields that are UNIQUE PER RECORD and cannot be shared across records: vote IDs, transaction IDs, session IDs, order IDs, UUIDs, serial numbers, batch IDs, submission IDs, and any other auto-generated record-level identifiers. These are high-cardinality with no analytical value in a graph.
12. Use "context" for navigable but weaker relationship fields like city/state/address.
13. Use "ignore" for fields that have no analytical value: timestamps, booleans flags, checksums, internal status codes.
    NOTE: descriptive text fields like "description", "notes", "summary" should be "context", not "ignore" — they can be meaningful.

OUTPUT FORMAT:
Return a JSON object with a single key "field_groups" containing an array of objects. Each object has:
- "concept": a short snake_case label for the concept (e.g., "party_affiliation", "person_name", "city")
- "role": one of "identity_name", "identity", "context", "ignore", or "record_id"
- "strength": one of "strong", "medium", "weak", or "none"
- "scope": one of the semantic scopes described above
- "fields": array of full field paths that belong to this concept group

Return ONLY the JSON object, nothing else."""

        analysis_succeeded = False
        try:
            response = await self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "Analyze the schema and identify semantically equivalent field groups. Return ONLY valid JSON."},
                ],
                model=MODEL_ID,
                temperature=0.0,
                max_tokens=16384,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content

            # Clean up potential markdown wrappers
            if "```" in content:
                content = content.split("```")[1]
                if content.lower().startswith("json"):
                    content = content[4:]

            result = json.loads(content.strip())
            if not isinstance(result, dict):
                raise ValueError("LLM response was not a JSON object")

            field_groups = result.get("field_groups", [])
            if not isinstance(field_groups, list):
                raise ValueError("LLM response field_groups was not a list")
            analysis_succeeded = True
        except Exception as e:
            print(f"  [LLMAnalyzer] Failed to parse JSON or connect: {e}")
            if 'content' in locals():
                print(f"  [LLMAnalyzer] Raw output: {content}")
            field_groups = []

        if self.cache and analysis_succeeded:
            self.cache.set(cache_key, field_groups)

        print(f"  LLM identified {len(field_groups)} semantic field groups.")
        return field_groups

    # ------------------------------------------------- document pattern analysis
    async def analyze_document_patterns(
        self, sample_docs: str, db_name: str
    ) -> Dict[str, Any]:
        """
        Analyze sample documents to identify array patterns and semantic
        relationships that can't be detected from schema alone.

        Returns:
        {
            "array_rules": [...],    # How to handle arrays (selection, etc.)
            "field_notes": {...},    # Semantic notes about fields
        }
        """
        hash_hex = hashlib.md5(sample_docs.encode()).hexdigest()
        cache_key = f"llm_patterns:{LLM_ANALYSIS_CACHE_VERSION}:{hash_hex}"

        if self.cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                print("  Using cached LLM document pattern analysis.")
                return cached

        print("  Sending sample documents to LLM for pattern analysis...")

        system_prompt = f"""You are an expert data analyst examining sample documents from the MongoDB database "{db_name}".

Your task: Analyze the STRUCTURE and SEMANTICS of these documents to identify patterns that will help build an intelligent relationship graph between users/entities.

SAMPLE DOCUMENTS:
{sample_docs}

ANALYZE THE FOLLOWING:

## 1. Selection/Choice Arrays
Look for arrays of objects where one or more items are "selected" or "chosen" by the user.

Common patterns:
- Poll/survey options: array items with a boolean like "isSelected", "selected", "checked", "chosen", "isChosen", "is_selected" where true means the user picked that option
- The meaningful value is usually in a sibling field like "text", "name", "title", "label", "value", "option", "answer"
- Multiple selections may be possible

For EACH such array, provide a rule to extract the meaningful selected value(s).

## 2. Semantic Field Notes
For key fields, describe what they represent and how they should be treated in a person-relationship graph:
- Which fields represent a user's CHOICE or OPINION (most interesting for grouping)
- Which fields are DEMOGRAPHIC (location, gender, age — useful but common)
- Which fields are IDENTIFIERS (email, username, account IDs — for linking same person)
- Which fields represent the SUBJECT being responded to (poll question, topic — good for grouping by shared interest)

OUTPUT FORMAT:
Return a JSON object:
{{
  "array_rules": [
    {{
      "array_path": "poll.options",
      "pattern": "selection",
      "description": "Poll options where isSelected marks the user's choice",
      "selector_field": "isSelected",
      "selector_value": true,
      "value_field": "text",
      "emit_as": "poll.selectedOption"
    }}
  ],
  "field_notes": {{
    "poll.selectedOption": "The text of the user's chosen poll answer — high-value grouping field",
    "poll.pollId": "Unique poll identifier — groups users who answered the same poll",
    "voter.location.city": "User's city — demographic grouping field"
  }}
}}

IMPORTANT:
- Use the ACTUAL field paths from the documents above, not generic examples
- For array_rules, the array_path should be the path to the array field itself (e.g., "poll.options"), not to items within it
- selector_value should be the actual value that indicates selection (usually true for booleans)
- value_field is the field within each array item that contains the meaningful label/text
- emit_as is the new field path where the selected value should appear after preprocessing
- Be thorough — examine ALL arrays in the documents for potential selection patterns
Return ONLY the JSON object, nothing else."""

        result = {"array_rules": [], "field_notes": {}}
        analysis_succeeded = False

        try:
            response = await self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "Analyze the sample documents and return the pattern analysis as JSON."},
                ],
                model=MODEL_ID,
                temperature=0.0,
                max_tokens=16384,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content

            if "```" in content:
                content = content.split("```")[1]
                if content.lower().startswith("json"):
                    content = content[4:]

            parsed = json.loads(content.strip())
            if not isinstance(parsed, dict):
                raise ValueError("LLM response was not a JSON object")

            result["array_rules"] = parsed.get("array_rules", [])
            result["field_notes"] = parsed.get("field_notes", {})
            analysis_succeeded = True

            print(f"  LLM identified {len(result['array_rules'])} array rules.")
        except Exception as e:
            print(f"  [LLMAnalyzer] Document pattern analysis failed: {e}")
            if 'content' in locals():
                print(f"  [LLMAnalyzer] Raw output: {content}")

        if self.cache and analysis_succeeded:
            self.cache.set(cache_key, result)

        return result

    # ------------------------------------------------- node insight summarization
    async def summarize_node(
        self, field: str, value: str, documents: list, db_name: str
    ) -> Dict[str, Any]:
        """
        Given a field/value pair and the matching documents, ask the LLM to
        produce a smart, structured summary of what this entity is.

        Returns:
        {
            "entity_type": "Poll" | "Trial" | "Person" | ...,
            "title": "human-readable title",
            "summary": "1-2 sentence description",
            "properties": [{"label": "...", "value": "..."}, ...],
            "related_entities": ["...", ...]
        }
        """
        # Build a compact representation of the docs (limit to avoid token blow-up)
        sample_docs = documents[:5]  # at most 5 docs
        docs_text = json.dumps(sample_docs, indent=2, default=str)
        # Truncate if extremely large
        if len(docs_text) > 12000:
            docs_text = docs_text[:12000] + "\n... (truncated)"

        # Check cache
        hash_hex = hashlib.md5(f"{db_name}:{field}:{value}:{docs_text[:2000]}".encode()).hexdigest()
        cache_key = f"node_insight:{LLM_ANALYSIS_CACHE_VERSION}:{hash_hex}"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached

        system_prompt = f"""You are an intelligent data analyst examining documents from the MongoDB database "{db_name}".

The user clicked on a node in a data visualization. The node represents:
- Field: "{field}"
- Value: "{value}"

Here are the matching documents that contain this field/value:
{docs_text}

Your task: Produce a smart, structured summary of what this entity/value represents.

INSTRUCTIONS:
1. Identify what TYPE of entity this is (e.g., "Poll", "Trial", "Person", "Organization", "Event", "Survey", "Campaign", etc.)
2. Extract a human-readable TITLE (the most meaningful name/label for this entity)
3. Write a brief SUMMARY (1-2 sentences describing what this is)
4. Extract KEY PROPERTIES - the most important/interesting attributes. For example:
   - For a poll: title, description, options/choices, creation date, response count
   - For a trial: name, phase, status, conditions, interventions
   - For a person: name, role, affiliations, contact info
   - For ANY entity: extract whatever fields are most informative and meaningful
5. Identify RELATED ENTITIES - other notable entities referenced in the documents (names, IDs, linked records)

Be smart about this - look at the FULL document structure, not just the clicked field. The goal is to give the user a rich understanding of what they clicked on.

OUTPUT FORMAT:
Return a JSON object:
{{
  "entity_type": "Poll",
  "title": "Best Programming Language 2024",
  "summary": "A community poll asking developers about their preferred programming language, with 5 options and 342 responses.",
  "properties": [
    {{"label": "Description", "value": "Vote for your favorite language"}},
    {{"label": "Options", "value": "Python, JavaScript, Rust, Go, TypeScript"}},
    {{"label": "Total Responses", "value": "342"}},
    {{"label": "Created", "value": "2024-01-15"}},
    {{"label": "Part of Trial", "value": "Developer Survey 2024"}}
  ],
  "related_entities": ["Developer Survey 2024", "Tech Community Forum"]
}}

IMPORTANT:
- Properties should be the most USEFUL and INTERESTING fields, not every field
- Keep property values concise (summarize arrays/lists rather than dumping raw data)
- If an option/choice was selected by users, mention which are popular if data shows it
- Adapt to ANY data shape - polls, trials, people, organizations, events, etc.
- Return ONLY the JSON object, nothing else"""

        result = {
            "entity_type": "Unknown",
            "title": value,
            "summary": f"A record where {field} = {value}",
            "properties": [],
            "related_entities": [],
        }

        try:
            response = await self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "Analyze the documents and return a structured summary as JSON."},
                ],
                model=MODEL_ID,
                temperature=0.0,
                max_tokens=4096,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            if "```" in content:
                content = content.split("```")[1]
                if content.lower().startswith("json"):
                    content = content[4:]

            parsed = json.loads(content.strip())
            if isinstance(parsed, dict):
                result["entity_type"] = parsed.get("entity_type", result["entity_type"])
                result["title"] = parsed.get("title", result["title"])
                result["summary"] = parsed.get("summary", result["summary"])
                result["properties"] = parsed.get("properties", [])
                result["related_entities"] = parsed.get("related_entities", [])

                if self.cache:
                    self.cache.set(cache_key, result)

        except Exception as e:
            print(f"  [LLMAnalyzer] Node insight failed: {e}")

        return result

    @staticmethod
    def build_preprocessing_rules(
        pattern_analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Convert the raw LLM pattern analysis into a compact dict that
        the tree builders use for document preprocessing.

        Returns:
        {
            "array_rules": {path: rule_dict, ...},
            "field_notes": {...},
        }
        """
        array_rules_list = pattern_analysis.get("array_rules", [])
        array_rules_map = {}
        for rule in array_rules_list:
            path = rule.get("array_path", "").strip()
            if path:
                # Store under multiple normalizations for robust matching
                array_rules_map[path] = rule
                # Also store without data prefix
                for prefix in ("data.", "data.N."):
                    if path.startswith(prefix):
                        array_rules_map[path[len(prefix):]] = rule

        return {
            "array_rules": array_rules_map,
            "field_notes": pattern_analysis.get("field_notes", {}),
        }

    def build_field_mapping(
        self, field_groups: List[Dict[str, Any]]
    ) -> Dict[str, str]:
        """
        Convert field_groups into a flat mapping:
            field_path -> canonical_key

        All fields in the same group map to the same canonical key (the concept name).
        This is used by the graph builder to merge nodes.
        """
        mapping = {}
        for group in field_groups:
            concept = group.get("concept", "unknown")
            for field in group.get("fields", []):
                mapping[field] = concept
        return mapping

    def build_sunburst_excluded_fields(
        self, field_groups: List[Dict[str, Any]], all_field_names: List[str] = None
    ) -> set:
        """
        Return a set of lowercased short field names to exclude from the
        sunburst visualization (not from click-to-query data retrieval).

        Only excludes role == "record_id": per-record unique identifiers
        (vote_id, transaction_id, session_id, UUIDs, etc.) that have
        cardinality-1 — every value appears exactly once, so they add no
        grouping insight and inflate the sunburst for nothing.

        Everything else is kept, including:
        - "identity_name": name, full_name
        - "identity": email, phone, username (shared across records per person)
        - "context": city, state, description
        - "ignore": timestamps, flags (shown but de-emphasised by the UI)

        all_field_names: optional list of all schema field paths; if provided,
        the _is_record_id heuristic is applied to any field NOT already in a
        LLM group (safety net for lone fields the LLM didn't create a group for).
        """
        excluded: set = set()
        grouped_fields: set = set()

        for group in field_groups:
            role = self._normalize_role(group.get("role"))
            inferred = self._infer_group_semantics(
                str(group.get("concept", "")),
                [str(f) for f in group.get("fields", []) if f],
            )
            effective_role = role or inferred["role"]

            for field in group.get("fields", []):
                grouped_fields.add(field)
                if effective_role == "record_id":
                    short = field.split(".")[-1] if "." in field else field
                    excluded.add(short.lower())

        # Heuristic fallback: apply _is_record_id to fields the LLM didn't group
        if all_field_names:
            for field in all_field_names:
                if field not in grouped_fields:
                    short = field.split(".")[-1] if "." in field else field
                    tokens = self._tokens_for_group(short, [field])
                    if self._is_record_id(tokens):
                        excluded.add(short.lower())

        return excluded

    @staticmethod
    def _normalize_role(role: Any) -> str:
        role_str = str(role or "").strip().lower()
        return role_str if role_str in _ROLE_VALUES else ""

    @staticmethod
    def _normalize_strength(strength: Any) -> str:
        strength_str = str(strength or "").strip().lower()
        return strength_str if strength_str in _STRENGTH_VALUES else ""

    @staticmethod
    def _normalize_scope(scope: Any) -> str:
        return str(scope or "").strip().lower()

    @staticmethod
    def _tokens_for_group(concept: str, fields: List[str]) -> str:
        return " ".join([concept or "", *fields]).lower()

    @staticmethod
    def _infer_scope_from_field(field_path: str, fallback_scope: str) -> str:
        path_lower = str(field_path or "").lower()

        if any(hint in path_lower for hint in _NON_PERSON_HINTS):
            if any(hint in path_lower for hint in _LOCATION_HINTS):
                if "employ" in path_lower:
                    return "employment.location"
                return "organization.location"
            if "employ" in path_lower:
                return "employment"
            return "organization"

        if any(hint in path_lower for hint in _LOCATION_HINTS):
            return "person.location"

        if any(hint in path_lower for hint in _PERSON_HINTS | _PERSON_ID_HINTS):
            return "person.identity"

        return fallback_scope or "document"

    @classmethod
    def _is_record_id(cls, tokens: str) -> bool:
        """Heuristic: is this group a per-record unique identifier?

        True when the concept/field names look like system-generated record-level
        IDs (vote_id, transaction_id, uuid, etc.) rather than person-level fields.
        Explicit person-level ID hints take priority and override this.
        """
        # Person-level IDs are never record IDs
        if any(hint in tokens for hint in _PERSON_ID_HINTS | _IDENTITY_NAME_HINTS):
            return False
        # Explicit record-ID keyword match
        if any(hint in tokens for hint in _RECORD_ID_HINTS):
            return True
        # Generic suffix heuristic: token ends with a record-ID suffix word
        # e.g. "sessionid", "tracekey", "batchref"
        token_words = tokens.replace("_", " ").split()
        return any(
            word.endswith(suffix) and word not in _PERSON_ID_HINTS
            for word in token_words
            for suffix in _RECORD_ID_SUFFIXES
            if len(word) > len(suffix)  # avoid matching bare "id" on short tokens
        )

    @classmethod
    def _infer_group_semantics(cls, concept: str, fields: List[str]) -> Dict[str, str]:
        tokens = cls._tokens_for_group(concept, fields)
        has_non_person = any(hint in tokens for hint in _NON_PERSON_HINTS)
        has_person = any(hint in tokens for hint in _PERSON_HINTS)

        # Record-level unique IDs: per-record, high-cardinality, no graph value
        if cls._is_record_id(tokens):
            return {"role": "record_id", "strength": "none", "scope": "document"}

        if any(hint in tokens for hint in _IDENTITY_NAME_HINTS):
            if has_non_person and not has_person:
                return {"role": "context", "strength": "weak", "scope": "document"}
            return {"role": "identity_name", "strength": "none", "scope": "person.identity"}

        if any(hint in tokens for hint in _PERSON_ID_HINTS):
            return {"role": "identity", "strength": "strong", "scope": "person.identity"}

        if any(hint in tokens for hint in _LOCATION_HINTS):
            if any(hint in tokens for hint in _NON_PERSON_HINTS):
                if "employ" in tokens:
                    return {"role": "context", "strength": "weak", "scope": "employment.location"}
                return {"role": "context", "strength": "weak", "scope": "organization.location"}
            return {"role": "context", "strength": "weak", "scope": "person.location"}

        return {"role": "context", "strength": "weak", "scope": "document"}

    def build_field_semantics(
        self, field_groups: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, str]]:
        """
        Convert field_groups into a flat mapping:
            field_path -> {concept, role, strength, scope}

        Supports both the new enriched LLM output and older cached output that
        only contains {concept, fields} by deriving semantics heuristically.
        """
        semantics: Dict[str, Dict[str, str]] = {}
        for group in field_groups:
            concept = str(group.get("concept", "unknown")).strip() or "unknown"
            fields = [str(field) for field in group.get("fields", []) if field]
            if not fields:
                continue

            inferred = self._infer_group_semantics(concept, fields)
            role = self._normalize_role(group.get("role")) or inferred["role"]
            strength = self._normalize_strength(group.get("strength")) or inferred["strength"]
            base_scope = self._normalize_scope(group.get("scope")) or inferred["scope"]

            for field in fields:
                semantics[field] = {
                    "concept": concept,
                    "role": role,
                    "strength": strength,
                    "scope": self._infer_scope_from_field(field, base_scope),
                }
        return semantics
