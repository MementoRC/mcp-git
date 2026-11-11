"""Cursor pagination shared by every Projects (v2) connection (#352).

Truncation policy: never silent. After ``MAX_PAGES`` pages with more still
available, ``ProjectError`` is raised instead of returning a partial list.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

__all__ = ["MAX_PAGES", "ProjectError", "drain_connection"]

MAX_PAGES = 50


class ProjectError(Exception):
    """A user-facing Projects failure (reported as an error envelope)."""


def _next_cursor(conn: dict[str, Any]) -> str | None:
    info = conn.get("pageInfo") or {}
    return info.get("endCursor") if info.get("hasNextPage") else None


async def drain_connection(
    first: dict[str, Any],
    fetch_page: Callable[[str], Awaitable[dict[str, Any]]],
    what: str,
) -> list[dict[str, Any]]:
    """All nodes of a connection, given its first page and a cursor fetcher.

    Makes no extra call when ``first`` has no next page. Raises
    ``ProjectError`` rather than truncating past ``MAX_PAGES`` pages.
    """
    nodes = list(first.get("nodes") or [])
    cursor = _next_cursor(first)
    pages = 1
    while cursor:
        if pages >= MAX_PAGES:
            raise ProjectError(
                f"{what} exceed {MAX_PAGES} pages; refusing to return a truncated list."
            )
        page = await fetch_page(cursor)
        nodes.extend(page.get("nodes") or [])
        cursor = _next_cursor(page)
        pages += 1
    return nodes
