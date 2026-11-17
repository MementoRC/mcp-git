"""Pattern matching for ``discover_tools`` (#355)."""

from typing import Any


def tool_matches(pattern: str, tool: Any) -> bool:
    """True when *pattern* is empty or hits the tool's name or any keyword.

    Matching is a case-insensitive substring test; descriptions are not searched.
    """
    if not pattern or not pattern.strip():
        return True
    needle = pattern.lower()
    return needle in tool.name.lower() or any(
        needle in keyword.lower() for keyword in getattr(tool, "keywords", ())
    )
