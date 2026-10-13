"""
Multi-step analyst agent powered by gpt-oss-120b via Groq.
Uses tool-calling to gather data, then reasons over it to answer
analytical questions with structured tabular output.
"""

import os
import json
import re
from groq import AsyncGroq, BadRequestError
from dotenv import load_dotenv, find_dotenv
from .tools import TOOL_DEFINITIONS, ToolExecutor

load_dotenv(find_dotenv())

MODEL_ID = "openai/gpt-oss-120b"
MAX_TOOL_ROUNDS = 6  # Max rounds of tool-calling before forcing a final answer
# Reasoning models consume tokens on internal thinking before producing output.
# Set a high limit so tool call JSON is never truncated mid-generation.
MAX_TOKENS = 16000


class AnalystAgent:
    def __init__(self, db_name: str, collection: str):
        self.client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
        self.db_name = db_name
        self.collection = collection
        self.tool_executor = ToolExecutor(db_name)

    async def analyze(
        self,
        user_query: str,
        schema_summary: str,
        conversation_context: list[dict] = None,
        identity_index_available: bool = False,
    ) -> dict:
        """
        Run multi-step analysis. Returns:
        {
            "analysis": str,           # Natural language answer
            "table": {"columns": [...], "rows": [...]},  # Structured data
            "methodology": str,        # How the answer was derived
        }
        """
        system_prompt = self._build_system_prompt(
            schema_summary, identity_index_available
        )

        messages = [{"role": "system", "content": system_prompt}]

        # Add conversation context for follow-up queries
        if conversation_context:
            for msg in conversation_context[-10:]:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"],
                })

        messages.append({"role": "user", "content": user_query})

        # Filter tools: remove identity tools if index not available
        tools = TOOL_DEFINITIONS
        if not identity_index_available:
            tools = [
                t for t in tools
                if t["function"]["name"] not in (
                    "search_identity_index", "get_user_mentions"
                )
            ]

        response_message = None
        tool_calls = None
        force_tool = False  # set True after a tool_use_failed to make model retry

        # Multi-turn tool-calling loop
        for round_num in range(MAX_TOOL_ROUNDS):
            try:
                response = await self.client.chat.completions.create(
                    model=MODEL_ID,
                    messages=messages,
                    tools=tools,
                    tool_choice="required" if force_tool else "auto",
                    temperature=0.1,
                    max_tokens=MAX_TOKENS,
                )
                force_tool = False
            except BadRequestError as e:
                error_info = (e.body or {}).get("error", {})
                if error_info.get("code") != "tool_use_failed":
                    raise
                error_msg = error_info.get("message", "tool_use_failed")
                failed_gen = error_info.get("failed_generation", "")
                print(f"  [Analyst] tool_use_failed: {error_msg} | {failed_gen}")
                messages.append({
                    "role": "user",
                    "content": (
                        f"Your last tool call was rejected with this error: \"{error_msg}\".\n"
                        f"The rejected output was:\n{failed_gen}\n\n"
                        "You MUST call the tool again with a corrected, valid JSON pipeline. "
                        "Do not answer directly — fix the JSON and retry the tool call."
                    ),
                })
                force_tool = True
                continue

            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls

            if not tool_calls:
                # No more tools needed — LLM has its final answer
                break

            # Process tool calls
            messages.append(response_message)
            for tool_call in tool_calls:
                fn_name = tool_call.function.name
                try:
                    fn_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    fn_args = {}

                print(f"  [Analyst] Tool call: {fn_name}({json.dumps(fn_args)[:200]})")
                result = await self.tool_executor.execute(fn_name, fn_args)

                # Truncate large results to keep context manageable
                result_str = json.dumps(result, default=str)
                if len(result_str) > 15000:
                    result_str = result_str[:15000] + "\n... (truncated, use more specific queries)"

                messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": fn_name,
                    "content": result_str,
                })

        # Final answer — ask LLM to produce structured output if it hasn't already
        if tool_calls or response_message is None:
            messages.append({
                "role": "user",
                "content": (
                    "Based on all the data you've gathered, provide your final answer now. "
                    "Follow the JSON output format specified in your instructions."
                ),
            })
            response_message = await self._call_for_text(messages, tools)

        # Parse the structured response
        return self._parse_response(response_message.content if response_message else None)

    def _build_system_prompt(
        self, schema_summary: str, identity_available: bool
    ) -> str:
        identity_section = ""
        if identity_available:
            identity_section = """
IDENTITY INDEX:
An identity index is available for this database. It links data about the same person
across all documents (poll responses, donations, registrations, etc.).
Use search_identity_index to find users, then get_user_mentions to see all their data.
This is extremely powerful for questions like "who supports X?" or "what do voters in city Y prefer?"
"""
        else:
            identity_section = """
IDENTITY INDEX:
No identity index is currently built. You can still answer questions by querying
collections directly with run_aggregation. For person-centric questions, try to
identify name/ID fields from the schema and use aggregation to group by them.
"""

        return f"""You are a data analyst for the Dredge platform. Your job is to answer user questions
about their MongoDB data by intelligently querying, cross-referencing, and analyzing it.

DATABASE: {self.db_name}
PRIMARY COLLECTION: {self.collection}

SCHEMA:
{schema_summary}

{identity_section}

APPROACH:
1. First understand what data is available (use get_schema or list_collections if needed)
2. Plan which queries will answer the question
3. Execute queries using the tools available
4. Reason over the results — infer, correlate, cross-reference
5. Provide a clear answer with supporting data

IMPORTANT RULES:
- For questions requiring inference (e.g., "who likely supports X?"), analyze ALL available
  evidence: poll responses, donations, party affiliations, location patterns, etc.
- Always ground your analysis in actual data. State what evidence supports your conclusions.
- If the data is insufficient to answer confidently, say so — don't fabricate.
- Use the identity index when available — it's far more powerful than raw queries for
  person-centric questions.
- Keep tool queries focused. Don't fetch entire collections — use filters and limits.

OUTPUT FORMAT:
Return a JSON object with exactly these fields:
{{
    "analysis": "Your natural language answer explaining findings and reasoning",
    "table": {{
        "columns": ["Column1", "Column2", ...],
        "rows": [["val1", "val2", ...], ...]
    }},
    "methodology": "Brief description of how you arrived at this answer (data sources used, logic applied)"
}}

The table should contain the most relevant structured data supporting your answer.
If no tabular data is appropriate, use {{"columns": [], "rows": []}}.
Return ONLY the JSON object, nothing else."""

    async def _call_for_text(self, messages: list, tools: list):
        """
        Call the LLM expecting a plain text/JSON response (no tool calls).
        If the model tries to call a tool anyway, feed the error back and retry.
        """
        for _ in range(3):
            try:
                response = await self.client.chat.completions.create(
                    model=MODEL_ID,
                    messages=messages,
                    tools=tools,
                    tool_choice="none",
                    temperature=0.1,
                    max_tokens=MAX_TOKENS,
                )
                return response.choices[0].message
            except BadRequestError as e:
                error_info = (e.body or {}).get("error", {})
                if error_info.get("code") != "tool_use_failed":
                    raise
                error_msg = error_info.get("message", "tool_use_failed")
                failed_gen = error_info.get("failed_generation", "")
                print(f"  [Analyst] _call_for_text tool_use_failed: {error_msg}")
                messages.append({
                    "role": "user",
                    "content": (
                        f"Tool calls are not allowed here. Your output was rejected: \"{error_msg}\".\n"
                        f"Rejected output:\n{failed_gen}\n\n"
                        "Please provide your final answer as plain JSON text without calling any tools."
                    ),
                })
        # Last resort: strip tool definitions so the model can't try
        response = await self.client.chat.completions.create(
            model=MODEL_ID,
            messages=messages,
            temperature=0.1,
            max_tokens=MAX_TOKENS,
        )
        return response.choices[0].message

    def _parse_response(self, content: str) -> dict:
        """Parse the LLM's response, handling both clean JSON and wrapped text."""
        if not content:
            return {
                "analysis": "No response generated.",
                "table": {"columns": [], "rows": []},
                "methodology": "",
            }

        # Strip thinking tags if present
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

        # Try to extract JSON from the response
        # First try: direct parse
        try:
            result = json.loads(content)
            return self._validate_response(result)
        except json.JSONDecodeError:
            pass

        # Second try: find JSON block in markdown
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group(1))
                return self._validate_response(result)
            except json.JSONDecodeError:
                pass

        # Third try: find any JSON object
        brace_start = content.find("{")
        brace_end = content.rfind("}")
        if brace_start != -1 and brace_end > brace_start:
            try:
                result = json.loads(content[brace_start : brace_end + 1])
                return self._validate_response(result)
            except json.JSONDecodeError:
                pass

        # Fallback: treat entire content as the analysis text
        return {
            "analysis": content,
            "table": {"columns": [], "rows": []},
            "methodology": "Direct LLM response (structured parsing failed)",
        }

    def _validate_response(self, result: dict) -> dict:
        """Ensure response has all required fields with correct types."""
        validated = {
            "analysis": result.get("analysis", ""),
            "table": result.get("table", {"columns": [], "rows": []}),
            "methodology": result.get("methodology", ""),
        }
        if not isinstance(validated["table"], dict):
            validated["table"] = {"columns": [], "rows": []}
        if "columns" not in validated["table"]:
            validated["table"]["columns"] = []
        if "rows" not in validated["table"]:
            validated["table"]["rows"] = []
        # Ensure all row values are strings for consistent frontend rendering
        validated["table"]["rows"] = [
            [str(cell) if cell is not None else "" for cell in row]
            for row in validated["table"]["rows"]
        ]
        return validated


async def generate_title(user_query: str) -> str:
    """Generate a short conversation title from the first user message."""
    try:
        client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
        response = await client.chat.completions.create(
            model=os.getenv("TEXT_MODEL_ID", "qwen/qwen3-32b"),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Generate a very short title (3-6 words) for a data analysis "
                        "conversation that starts with this query. Return ONLY the title, "
                        "no quotes, no punctuation at the end."
                    ),
                },
                {"role": "user", "content": user_query},
            ],
            temperature=0.3,
            max_tokens=20,
        )
        title = response.choices[0].message.content.strip()
        title = re.sub(r"<think>.*?</think>", "", title, flags=re.DOTALL).strip()
        return title[:60] if title else user_query[:50]
    except Exception:
        return user_query[:50]
