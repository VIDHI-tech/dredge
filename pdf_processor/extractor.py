import json
import re
from .llm_engine import ModelEngine


_engine = None

def get_engine():
    global _engine
    if _engine is None:
        _engine = ModelEngine()
    return _engine


def repair_json(json_str):
    """Refines JSON string to fix common LLM errors."""
    json_str = json_str.strip()
    # Balance braces/brackets
    diff = json_str.count('{') - json_str.count('}')
    if diff > 0: json_str += '}' * diff
    diff_b = json_str.count('[') - json_str.count(']')
    if diff_b > 0: json_str += ']' * diff_b
    # Fix trailing commas
    json_str = re.sub(r',(\s*[\]\}])', r'\1', json_str)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


def clean_json_response(response_text):
    """Extracts JSON block from text."""
    response_text = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL)
    response_text = re.sub(r'```json\s*', '', response_text)
    response_text = re.sub(r'```', '', response_text)
    response_text = response_text.strip()
    match = re.search(r'(\{.*\}|\[.*\])', response_text, re.DOTALL)
    if match: response_text = match.group(0)
    return response_text


def validate_and_parse_json(text):
    text = clean_json_response(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return repair_json(text)


def deep_merge(base, update):
    """
    recursively merges update into base.
    - Lists are concatenated.
    - Objects are merged recursively.
    - Scalars in 'update' overwrite 'base' only if 'base' is empty/null.
    """
    if isinstance(base, list) and isinstance(update, list):
         # Deduplicate if possible, or just extend
         # For safety, just extend. We can dedup later.
         base.extend(update)
         return base
    
    if isinstance(base, dict) and isinstance(update, dict):
        for k, v in update.items():
            if k in base:
                base[k] = deep_merge(base[k], v)
            else:
                base[k] = v
        return base
    
    # Scalar merge strategy:
    # If base is empty/None, take update.
    # Otherwise keep base (assuming Page 1 has valid header info).
    if not base and update:
        return update
    
    return base

