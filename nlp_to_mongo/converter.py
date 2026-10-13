import os
import json
from groq import Groq
from dotenv import load_dotenv
from .schema_manager import SchemaManager

from pathlib import Path
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

MODEL_ID = os.getenv("TEXT_MODEL_ID", "qwen/qwen3-32b")

class QueryConverter:
    def __init__(self):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.schema_manager = SchemaManager()

    async def convert(self, text: str, collection_name: str, db_name: str = "test") -> list:
        """
        Convert natural language to a MongoDB aggregation pipeline.
        Always returns a list (pipeline), never a plain dict filter.
        """
        schema, schema_context = await self._get_schema_context(collection_name, db_name)
        roots_list = sorted(self.schema_manager.get_data_roots(schema))

        messages = [
            {"role": "system", "content": self._build_system_prompt(collection_name, schema_context, roots_list)},
            {"role": "user", "content": text},
        ]

        response = self.client.chat.completions.create(
            messages=messages,
            model=MODEL_ID,
            temperature=0.0,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        result = json.loads(content)

        pipeline = self._build_pipeline(result, roots_list, collection_name)
        return pipeline

    async def retry_with_error(self, text: str, collection_name: str, db_name: str,
                               failed_pipeline: list, error_msg: str) -> list:
        """
        Re-ask the LLM to generate a corrected pipeline after an execution error.
        Sends the original query, the failed pipeline, and the error so the LLM
        can work around the issue (e.g. avoid $facet, add $limit, etc.).
        """
        schema, schema_context = await self._get_schema_context(collection_name, db_name)
        roots_list = sorted(self.schema_manager.get_data_roots(schema))

        system_prompt = self._build_system_prompt(collection_name, schema_context, roots_list)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
            {"role": "assistant", "content": json.dumps({"pipeline_generated": failed_pipeline})},
            {"role": "user", "content": (
                f"The pipeline above failed with this MongoDB error:\n{error_msg}\n\n"
                "Please generate a corrected query that avoids this error. Tips:\n"
                "- If the error is about $facet exceeding the 100MB document size limit, "
                "avoid using $or across different data roots. Instead, pick the SINGLE most "
                "likely data root for the user's query and search only that root.\n"
                "- Add a $limit stage early in the pipeline if results could be very large.\n"
                "- Prefer simpler pipelines that avoid $facet entirely.\n"
                "Return ONLY the corrected JSON object."
            )},
        ]

        response = self.client.chat.completions.create(
            messages=messages,
            model=MODEL_ID,
            temperature=0.0,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        result = json.loads(content)

        pipeline = self._build_pipeline(result, roots_list, collection_name)
        return pipeline

    async def _get_schema_context(self, collection_name: str, db_name: str) -> tuple:
        """Return (schema, schema_context_string) for use in prompts."""
        schema = await self.schema_manager.get_schema(collection_name, db_name=db_name)

        schema_lines = []
        for field, info in schema.items():
            if isinstance(info, dict) and "type" in info:
                ftype = info["type"]
                examples = info.get("examples", [])
                roots = info.get("data_roots", [])
            else:
                ftype = "Unknown"
                examples = info if isinstance(info, list) else []
                roots = []
            ex_str = ", ".join([repr(e) for e in examples[:3]])
            root_str = "/".join(roots) if roots else "?"
            schema_lines.append(f"  {field}  ({ftype})  e.g. {ex_str}  [root: {root_str}]")

        fields_list = "\n".join(schema_lines)
        return schema, fields_list

    def _build_system_prompt(self, collection_name: str, fields_list: str, roots_list: list) -> str:
        """Build the system prompt for the LLM."""
        root_explanation = self._build_root_explanation(roots_list)

        return f"""You are a MongoDB aggregation pipeline generator. Convert the user's natural language request into a MongoDB **$match filter** for the collection "{collection_name}".

DOCUMENT STRUCTURE:
Documents in this collection may store data in different ways:
- Some have a nested "data" array requiring a "data." prefix.
- Some have top-level array fields (e.g., "candidates", "politicalParties") where fields are accessed as "arrayName.fieldName".
The field paths and prefix rules below tell you exactly how to reference each field.

AVAILABLE FIELDS (these are the ONLY valid field paths you may use):
{fields_list}

IMPORTANT — FIELD PATH PREFIX RULES:
{root_explanation}

CRITICAL RULES:
1. You MUST use ONLY the exact field paths listed above, prefixed with the correct data root as explained. Do NOT invent or guess field paths.
2. MULTI-PATH SEARCH: Different documents have DIFFERENT field structures. When the user asks about a concept (e.g., "party"), find ALL field paths that semantically match and combine them with "$or".
   For example, if the user asks "Find party Republican", and the schema has:
     candidate.partyAffiliation (e.g. 'Republican') [root: data]
     candidates.party (e.g. 'Republican') [root: data]
     Party (e.g. 'Republican') [root: data]
   Then the correct output is: {{"match": {{"$or": [{{"data.candidate.partyAffiliation": "Republican"}}, {{"data.candidates.party": "Republican"}}, {{"data.Party": "Republican"}}]}}}}
3. Match string values using the exact casing shown in examples. If examples show "Republican" (capitalized), use "Republican".
4. For numeric comparisons, use $gt, $lt, $gte, $lte as needed (e.g. "high value" → {{"$gt": 10000}}).
5. If the user asks to "list all", "show all", "get all", or makes a vague request, return: {{"match": {{}}}}
6. For sorting, grouping, counting, or top-N requests, return a "pipeline" array of additional stages AFTER the match.

OUTPUT FORMAT:
Return a JSON object with:
- "match": the $match filter object (REQUIRED — always include this)
- "pipeline": optional array of ADDITIONAL stages like $sort, $group, $limit (only if needed for sorting/grouping/counting)
- "project": optional object to select specific fields to return

Return ONLY the JSON object, nothing else."""

    def _build_root_explanation(self, roots: list) -> str:
        """Build explanation of how to prefix field paths based on data roots."""
        parts = []
        if "data" in roots:
            parts.append(
                '- Fields with [root: data] must be prefixed with "data." in the match filter.\n'
                '  Example: field "Party" → use "data.Party" in the filter.\n'
                '  Example: field "candidate.partyAffiliation" → use "data.candidate.partyAffiliation".'
            )
        # Handle dynamic array roots (e.g., "candidates", "politicalParties")
        dynamic_roots = [r for r in roots if r != "data"]
        if dynamic_roots:
            examples = []
            for r in dynamic_roots[:3]:
                examples.append(f'  - [root: {r}]: field paths already include "{r}." prefix, use as-is.')
            parts.append(
                '- Some fields are in top-level arrays. Their paths already include the array name:\n'
                + '\n'.join(examples) + '\n'
                '  Example: field "candidates.Party" [root: candidates] → use "candidates.Party".'
            )
        if not parts:
            parts.append('- Use field paths exactly as listed above in the match filter.')
        return "\n".join(parts)

    def _build_pipeline(self, llm_result: dict, data_roots: list, collection_name: str = None) -> list:
        """
        Build a complete aggregation pipeline from the LLM's output.
        Adds $unwind stages to flatten the nested array structures,
        then appends the $match and any additional stages.
        """
        match_filter = {}
        extra_stages = []
        project = None

        if isinstance(llm_result, dict):
            match_filter = llm_result.get("match", llm_result.get("filter", llm_result.get("query", {})))
            if not isinstance(match_filter, dict):
                match_filter = {}
            extra_stages = llm_result.get("pipeline", [])
            if not isinstance(extra_stages, list):
                extra_stages = []
            project = llm_result.get("project")

        # Determine which data roots are referenced in the match filter
        filter_str = json.dumps(match_filter)

        pipeline = []

        # Determine which roots are actually used in this query
        used_roots = set()
        for root in data_roots:
            if f'"{root}.' in filter_str:
                used_roots.add(root)

        # For empty match (list all) or no specific root detected,
        # default to "data" root to avoid $facet memory overflow.
        if not used_roots or match_filter == {}:
            default_root = "data" if "data" in data_roots else (list(data_roots)[0] if data_roots else "data")
            pipeline = self._build_single_root_pipeline(default_root, match_filter, extra_stages, project)
        elif len(used_roots) == 1:
            root = list(used_roots)[0]
            pipeline = self._build_single_root_pipeline(root, match_filter, extra_stages, project)
        else:
            # Multi-root: use $unionWith to stream results without 100MB $facet limit
            pipeline = self._build_multi_root_pipeline(used_roots, match_filter, extra_stages, project, collection_name)

        return pipeline

    def _build_single_root_pipeline(self, root: str, match_filter: dict, extra_stages: list, project: dict = None) -> list:
        """Build pipeline for a single data root."""
        pipeline = []

        # Add $unwind stages
        if root == "data":
            # Documents may have different "data" structures:
            #   A) data: [[{record}, ...]]              — direct double-nested array
            #   B) data: [{doc_id, schema, data: [[...]]}] — wrapper objects
            #   C) data: [{key: [...]}]                  — array of objects with nested arrays
            # Step 1: Unwind top-level data array
            pipeline.append({"$unwind": "$data"})
            # Step 2: If data is a wrapper object with inner "data" array, drill into it
            #         Otherwise keep data as-is (handles both arrays and plain objects)
            pipeline.append({"$addFields": {
                "data": {"$cond": {
                    "if": {"$and": [
                        {"$not": [{"$isArray": "$data"}]},
                        {"$isArray": "$data.data"}
                    ]},
                    "then": "$data.data",
                    "else": "$data"
                }}
            }})
            # Step 3: Unwind again (flattens [[records]] → [records] or keeps objects)
            pipeline.append({"$unwind": "$data"})
            # Step 4: One more unwind for double-nested arrays (no-op on objects)
            pipeline.append({"$unwind": "$data"})
        elif root != "data":
            # Dynamic array root (e.g., "candidates", "politicalParties")
            # Need single $unwind on the top-level array field
            pipeline.append({"$unwind": f"${root}"})

        # Add $match
        if match_filter:
            pipeline.append({"$match": match_filter})

        # Add extra stages (sort, group, limit, etc.)
        for stage in extra_stages:
            if isinstance(stage, dict):
                pipeline.append(stage)

        # Add $project if specified
        if project and isinstance(project, dict):
            pipeline.append({"$project": project})

        return pipeline

    def _build_multi_root_pipeline(self, roots: set, match_filter: dict, extra_stages: list, project: dict = None, collection_name: str = None) -> list:
        """
        Build pipeline for queries spanning multiple data roots.
        Uses $unionWith to stream results from each root separately,
        avoiding the 100MB $facet document size limit.
        """
        sorted_roots = sorted(roots)
        first_root = sorted_roots[0]

        # Build the primary pipeline from the first root
        pipeline = self._build_branch_for_root(first_root, match_filter)

        # Use $unionWith for each additional root — streams results
        # without materializing everything into a single document
        for root in sorted_roots[1:]:
            branch_pipeline = self._build_branch_for_root(root, match_filter)
            pipeline.append({
                "$unionWith": {
                    "coll": collection_name or "_self",
                    "pipeline": branch_pipeline,
                }
            })

        # Add extra stages (sort, group, limit, etc.)
        for stage in extra_stages:
            if isinstance(stage, dict):
                pipeline.append(stage)

        if project and isinstance(project, dict):
            pipeline.append({"$project": project})

        return pipeline

    def _build_branch_for_root(self, root: str, match_filter: dict) -> list:
        """Build unwind + match stages for a single data root branch."""
        branch = []
        if root == "data":
            branch.append({"$unwind": "$data"})
            branch.append({"$addFields": {
                "data": {"$cond": {
                    "if": {"$and": [
                        {"$not": [{"$isArray": "$data"}]},
                        {"$isArray": "$data.data"}
                    ]},
                    "then": "$data.data",
                    "else": "$data"
                }}
            }})
            branch.append({"$unwind": "$data"})
            branch.append({"$unwind": "$data"})
        else:
            branch.append({"$unwind": f"${root}"})

        root_match = self._filter_match_for_root(match_filter, root)
        if root_match:
            branch.append({"$match": root_match})

        branch.append({"$addFields": {"_data_root": root, "record": f"${root}"}})
        return branch

    def _filter_match_for_root(self, match_filter: dict, root: str) -> dict:
        """Filter a $match condition to only include fields from a specific root."""
        if not match_filter:
            return {}

        # Handle $or at top level
        if "$or" in match_filter:
            or_conditions = match_filter["$or"]
            filtered = [c for c in or_conditions if self._condition_uses_root(c, root)]
            if filtered:
                return {"$or": filtered} if len(filtered) > 1 else filtered[0]
            return {}

        # Handle $and at top level
        if "$and" in match_filter:
            and_conditions = match_filter["$and"]
            filtered = [c for c in and_conditions if self._condition_uses_root(c, root)]
            if filtered:
                return {"$and": filtered} if len(filtered) > 1 else filtered[0]
            return {}

        # Simple field conditions
        result = {}
        for k, v in match_filter.items():
            if k.startswith(f"{root}."):
                result[k] = v
        return result

    def _condition_uses_root(self, condition: dict, root: str) -> bool:
        """Check if a condition dict references a specific data root."""
        for key in condition:
            if key.startswith(f"{root}."):
                return True
        return False
