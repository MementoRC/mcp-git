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


# Owner-level resources (GitHub Projects): ``identity_scope`` maps them through
# ``owner`` + ``owner_type`` -> ``identity_for_owner``. Every registered
# ``github_project_*`` tool must be here and take all three parameters.
OWNER_PARAMS = {"owner", "owner_type", "project_number"}


def _owner_scoped(tools: dict[str, set[str]]) -> set[str]:
    return {name for name in tools if name.startswith("github_project_")}


def test_registry_github_tools_fall_in_exactly_one_scope_category_when_enumerated():
    tools = _github_tools()
    assert len(tools) > 50  # guards against an accidentally empty enumeration
    owner_scoped = _owner_scoped(tools)
    repo_scoped = {n for n, p in tools.items() if {"repo_owner", "repo_name"} <= p}
    categories = (repo_scoped, set(ACCOUNT_LEVEL), owner_scoped)
    for name in tools:
        assert sum(name in c for c in categories) == 1, name


def test_registry_github_tools_accept_repo_owner_and_name_when_not_account_level():
    tools = _github_tools()
    owner_scoped = _owner_scoped(tools)
    missing = sorted(
        name
        for name, props in tools.items()
        if name not in ACCOUNT_LEVEL
        and name not in owner_scoped
        and not {"repo_owner", "repo_name"} <= props
    )
    assert missing == []


def test_owner_scoped_tools_require_owner_type_and_project_number_when_enumerated():
    tools = _github_tools()
    owner_scoped = _owner_scoped(tools)
    assert len(owner_scoped) >= 4
    assert {
        "github_project_list_items",
        "github_project_get_fields",
        "github_project_set_item_field",
        "github_project_add_item",
    } <= owner_scoped
    assert [n for n in sorted(owner_scoped) if not OWNER_PARAMS <= tools[n]] == []


def test_account_level_allowlist_names_registered_tools_when_enumerated():
    assert ACCOUNT_LEVEL <= set(_github_tools())
