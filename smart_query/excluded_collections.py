"""
Shared utility for filtering out system/internal collections from queries.
"""

SYSTEM_PREFIXES = (
    "_meta",
    "_tmp_",
    "mg_identity_",
    "mg_debug_",
    "system.",
    "dredge_",      # smart_query system collections (conversations, messages)
)


def is_user_collection(name: str) -> bool:
    """Returns True if the collection is a user data collection (not system)."""
    return not any(name.startswith(p) for p in SYSTEM_PREFIXES)


def filter_user_collections(names: list[str]) -> list[str]:
    """Filter a list of collection names to only user data collections."""
    return [n for n in names if is_user_collection(n)]
