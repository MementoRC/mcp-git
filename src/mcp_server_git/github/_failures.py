"""Shared failure builders for GitHub ops (issue #271)."""

from __future__ import annotations

from typing import Any

from mcp_server_git.utils.tool_failure import ToolFailure, fail


async def http_failure(action: str, response: Any) -> ToolFailure:
    """Failure for an unexpected HTTP status, quoting status and body."""
    error_text = await response.text()
    return fail(f"❌ Failed to {action}: {response.status} - {error_text}")
