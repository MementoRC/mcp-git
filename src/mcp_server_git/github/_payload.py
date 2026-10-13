"""Null-safe accessors for GitHub API payloads (pure, no I/O).

GitHub sends explicit ``null`` for absent objects, and ``x.get("user", {})``
only guards a *missing* key, not a ``null`` value.
"""

from __future__ import annotations

from typing import Any


def obj_of(payload: dict[str, Any], key: str) -> dict[str, Any]:
    """Return ``payload[key]`` as a dict; ``{}`` when missing or null."""
    return payload.get(key) or {}


def login_of(payload: dict[str, Any], key: str = "user", default: str = "N/A") -> str:
    """Return the ``login`` of the object under ``key``, else ``default``."""
    return obj_of(payload, key).get("login", default)
