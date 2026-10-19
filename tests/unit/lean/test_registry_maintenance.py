"""Registry wiring for git_reflog_expire and git_gc (#283, item 6)."""

import inspect
from unittest.mock import Mock

import pytest

from mcp_server_git.lean.interface import GitLeanInterface

_REGISTRY = GitLeanInterface(
    git_service=Mock(), github_service=Mock(), azure_service=Mock()
).tool_registry

_PARAMS = {
    "git_reflog_expire": {
        "repo_path",
        "expire",
        "expire_unreachable",
        "include_stash",
        "dry_run",
    },
    "git_gc": {"repo_path", "prune", "aggressive", "dry_run"},
}


def _closure_cell(tool, name):
    func = getattr(tool.implementation, "__wrapped__", tool.implementation)
    cells = dict(zip(func.__code__.co_freevars, func.__closure__, strict=True))
    return cells[name].cell_contents


@pytest.mark.parametrize("name", sorted(_PARAMS))
def test_registry_advertises_exact_params_and_dry_run_default_when_schema_read(name):
    tool = _REGISTRY[name]
    props = tool.schema["properties"]

    assert tool.domain == "git"
    assert set(props) == _PARAMS[name]
    assert props["dry_run"]["default"] is True
    assert set(tool.schema.get("required", [])) == {"repo_path"}
    op = _closure_cell(tool, "op_func")
    assert _PARAMS[name] - {"repo_path"} == set(inspect.signature(op).parameters) - {
        "repo"
    }


@pytest.mark.parametrize("name", sorted(_PARAMS))
def test_registry_describes_destructive_dry_run_when_description_read(name):
    description = _REGISTRY[name].description

    assert "DESTRUCTIVE when dry_run=false" in description
    assert "dry_run defaults to true" in description
    assert _closure_cell(_REGISTRY[name], "mutates_index") is False


def test_registry_describes_stash_exclusion_when_reflog_expire_read():
    assert "refs/stash is excluded by default" in (
        _REGISTRY["git_reflog_expire"].description
    )
