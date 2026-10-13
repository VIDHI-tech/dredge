"""
Query classifier — routes queries to either the fast converter (simple)
or the multi-step analyst agent (analytical).

Uses a lightweight LLM call for ambiguous cases, with keyword heuristics
as a fast path to avoid unnecessary LLM calls.
"""

import os
import json
from groq import AsyncGroq
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

# Use a fast, small model for classification
CLASSIFIER_MODEL = os.getenv("TEXT_MODEL_ID", "qwen/qwen3-32b")

# Keywords that strongly signal analytical queries
_ANALYTICAL_SIGNALS = {
    "likely", "probably", "predict", "analyze", "analysis",
    "pattern", "patterns", "correlation", "correlate",
    "compare", "comparison", "trend", "trends",
    "relationship between", "why do", "why does", "why are",
    "what causes", "who supports", "who opposes",
    "similar to", "related to", "associated with",
    "most common", "least common", "average",
    "breakdown", "distribution", "summarize", "summary",
    "insight", "insights", "infer", "inference",
    "sentiment", "opinion", "preference",
    "cross-reference", "across",
}

# Keywords that strongly signal simple/direct queries
_SIMPLE_SIGNALS = {
    "show me", "list all", "list the", "get all", "find all",
    "where", "filter", "sort by", "order by",
    "count", "how many", "top", "first", "last",
    "greater than", "less than", "equal to",
    "between", "before", "after",
}


async def classify_query(text: str) -> str:
    """
    Classify a query as 'simple' or 'analytical'.
    Returns 'simple' or 'analytical'.
    """
    lower = text.lower().strip()

    # Fast path: check for strong analytical signals
    for signal in _ANALYTICAL_SIGNALS:
        if signal in lower:
            return "analytical"

    # Fast path: check for strong simple signals with no analytical overlap
    for signal in _SIMPLE_SIGNALS:
        if signal in lower:
            return "simple"

    # Ambiguous — use LLM to classify
    try:
        client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
        response = await client.chat.completions.create(
            model=CLASSIFIER_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Classify the user's query about a database as either "
                        "'simple' or 'analytical'.\n\n"
                        "simple = direct data lookup, filtering, counting, sorting. "
                        "Can be answered with a single MongoDB query.\n\n"
                        "analytical = requires reasoning, inference, correlation, "
                        "cross-referencing multiple data sources, or subjective "
                        "interpretation of data.\n\n"
                        "Return ONLY the JSON: {\"type\": \"simple\"} or {\"type\": \"analytical\"}"
                    ),
                },
                {"role": "user", "content": text},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            max_tokens=200,
        )
        result = json.loads(response.choices[0].message.content)
        return result.get("type", "simple")
    except Exception as e:
        print(f"[Router] Classification failed, defaulting to simple: {e}")
        return "simple"
