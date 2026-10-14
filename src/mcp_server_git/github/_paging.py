"""Paging clamps and choice validation shared by the GitHub list/search ops."""

from __future__ import annotations

from collections.abc import Sequence

MAX_PER_PAGE = 100


def clamp_paging(per_page: int, page: int) -> tuple[int, int]:
    """Clamp ``per_page`` to 1..100 and ``page`` to >= 1 (GitHub API limits)."""
    return min(max(per_page, 1), MAX_PER_PAGE), max(page, 1)


def invalid_choice(name: str, value: str | None, allowed: Sequence[str]) -> str | None:
    """Return an error message when ``value`` is set but not in ``allowed``."""
    if value is None or value in allowed:
        return None
    return f"❌ Invalid {name} '{value}'. Must be one of: {', '.join(allowed)}"
