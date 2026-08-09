"""Shared server metadata used by every transport's ``server_info`` tool.

The lean server and the HTTP server each used to build this payload
independently, which let their domain counts drift apart and disagree with
``discover_tools`` (issue #196).
"""

from __future__ import annotations

from typing import Any

# Keep in sync with [project] version in pyproject.toml. The sync is asserted
# by tests/unit/test_server_metadata.py.
__version__ = "0.6.3"

_DOMAIN_DESCRIPTIONS = {
    "git": "Local git operations",
    "github": "GitHub API",
    "azure": "Azure DevOps",
}


def get_version() -> str:
    """Return the installed distribution version, falling back to ``__version__``.

    A source checkout has no installed distribution metadata; that case used to
    report ``"unknown"``, which made bug reports impossible to pin to a release
    (issue #196).
    """
    try:
        from importlib.metadata import version

        return version("mcp-server-git")
    except Exception:
        return __version__


def domain_counts(tool_registry: dict[str, Any]) -> dict[str, int]:
    """Count registered tools per domain, from the registry ``discover_tools`` reads."""
    counts = dict.fromkeys(_DOMAIN_DESCRIPTIONS, 0)
    for tool_def in tool_registry.values():
        if tool_def.domain in counts:
            counts[tool_def.domain] += 1
    return counts


def build_server_info(tool_registry: dict[str, Any], transport: str) -> dict[str, Any]:
    """Build the ``server_info`` payload with live, registry-derived tool counts."""
    counts = domain_counts(tool_registry)
    return {
        "name": "mcp-git",
        "version": get_version(),
        "description": "MCP server for Git, GitHub, and Azure DevOps operations",
        "repository": "https://github.com/MementoRC/mcp-git",
        "issues": "https://github.com/MementoRC/mcp-git/issues",
        "documentation": "https://github.com/MementoRC/mcp-git#readme",
        "support": {
            "bug_reports": "https://github.com/MementoRC/mcp-git/issues/new?template=bug_report.md",
            "feature_requests": "https://github.com/MementoRC/mcp-git/issues/new?template=feature_request.md",
        },
        "domains": {
            domain: f"{description} ({counts[domain]} tools)"
            for domain, description in _DOMAIN_DESCRIPTIONS.items()
        },
        "total_tools": len(tool_registry),
        "transport": transport,
        "protocol_version": "2024-11-05",
    }
