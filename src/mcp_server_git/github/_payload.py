"""Null-safe accessors for GitHub API payloads (pure, no I/O).

GitHub sends explicit ``null`` for absent objects, and ``x.get("user", {})``
only guards a *missing* key, not a ``null`` value.
"""

from __future__ import annotations

from typing import Any

BODY_PREVIEW_CHARS = 500


def body_preview(body: str) -> str:
    """Cut ``body`` to the shared preview length, adding ``...`` when cut."""
    ellipsis = "..." if len(body) > BODY_PREVIEW_CHARS else ""
    return f"{body[:BODY_PREVIEW_CHARS]}{ellipsis}"


def provided_fields(**fields: Any) -> dict[str, Any]:
    """Return ``fields`` without the ``None`` values, preserving order."""
    return {key: value for key, value in fields.items() if value is not None}


def obj_of(payload: dict[str, Any], key: str) -> dict[str, Any]:
    """Return ``payload[key]`` as a dict; ``{}`` when missing or null."""
    return payload.get(key) or {}


def login_of(payload: dict[str, Any], key: str = "user", default: str = "N/A") -> str:
    """Return the ``login`` of the object under ``key``, else ``default``."""
    return obj_of(payload, key).get("login", default)
