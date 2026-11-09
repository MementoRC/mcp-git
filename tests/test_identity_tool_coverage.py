"""Convention guard (#342): every GitHub tool can be mapped to a repo identity.

``identity_scope`` keys only on ``repo_owner``/``repo_name``; a GitHub tool
without both would silently run with the owner's ``GITHUB_TOKEN`` even on a
repo mapped to another identity.
"""

from unittest.mock import MagicMock

from mcp_server_git.lean.interface import GitLeanInterface

# Tools that legitimately have no target repo (account-level, or the repo does
# not exist yet) and therefore run with the owner token by design.
ACCOUNT_LEVEL: frozenset[str] = frozenset(
    {
        "github_create_repo",  # creates a new repo; no repo to map yet
    }
)


def _github_tools() -> dict[str, set[str]]:
    """Tool name -> parameters, for every tool that calls the GitHub API."""
    iface = GitLeanInterface(MagicMock(), MagicMock(), MagicMock())
    return {
        name: set(tool.schema.get("properties", {}))
        for name, tool in iface.tool_registry.items()
        if tool.domain == "github" or name == "azure_get_logs_for_check_run"
    }


def test_registry_github_tools_accept_repo_owner_and_name_when_not_account_level():
    tools = _github_tools()
    assert len(tools) > 50  # guards against an accidentally empty enumeration
    missing = sorted(
        name
        for name, props in tools.items()
        if name not in ACCOUNT_LEVEL and not {"repo_owner", "repo_name"} <= props
    )
    assert missing == []


def test_account_level_allowlist_names_registered_tools_when_enumerated():
    assert ACCOUNT_LEVEL <= set(_github_tools())
