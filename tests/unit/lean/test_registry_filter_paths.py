"""Registry wiring for git_filter_paths (#283, part 3)."""

import inspect
from unittest.mock import Mock

from mcp_server_git.lean.interface import GitLeanInterface

_REGISTRY = GitLeanInterface(
    git_service=Mock(), github_service=Mock(), azure_service=Mock()
).tool_registry

_PARAMS = {
    "repo_path",
    "paths",
    "invert",
    "all_refs",
    "branch",
    "prune_empty",
    "dry_run",
    "allow_with_remote",
    "gpg_sign",
    "backup_path",
}


def _closure_cell(tool, name):
    func = getattr(tool.implementation, "__wrapped__", tool.implementation)
    cells = dict(zip(func.__code__.co_freevars, func.__closure__, strict=True))
    return cells[name].cell_contents


def test_registry_registers_filter_paths_as_index_mutating_when_loaded():
    tool = _REGISTRY["git_filter_paths"]

    assert tool.domain == "git"
    assert _closure_cell(tool, "mutates_index") is True


def test_registry_advertises_filter_paths_params_when_schema_read():
    tool = _REGISTRY["git_filter_paths"]
    props = tool.schema["properties"]

    assert set(props) == _PARAMS
    assert props["prune_empty"]["default"] is True
    assert set(tool.schema["required"]) == {"repo_path", "paths"}
    op = _closure_cell(tool, "op_func")
    assert _PARAMS - {"repo_path"} <= set(inspect.signature(op).parameters)
