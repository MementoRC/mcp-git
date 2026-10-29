"""Registry wiring for the #283 safe additions: tools, params, mutates flag."""

import inspect
from unittest.mock import Mock

import pytest

from mcp_server_git.lean.interface import GitLeanInterface

_REGISTRY = GitLeanInterface(
    git_service=Mock(), github_service=Mock(), azure_service=Mock()
).tool_registry


def _closure_cell(tool, name):
    func = getattr(tool.implementation, "__wrapped__", tool.implementation)
    cells = dict(zip(func.__code__.co_freevars, func.__closure__, strict=True))
    return cells[name].cell_contents


@pytest.mark.parametrize("name", ["git_bundle_create", "git_bundle_verify"])
def test_registry_registers_bundle_tool_as_read_only_when_loaded(name):
    tool = _REGISTRY[name]

    assert tool.domain == "git"
    assert _closure_cell(tool, "mutates_index") is False


def test_registry_advertises_bundle_create_params_when_schema_read():
    props = _REGISTRY["git_bundle_create"].schema["properties"]

    assert {"repo_path", "output_path", "refs", "overwrite"} <= set(props)
    assert props["refs"]["default"] == ["--all"]


@pytest.mark.parametrize(
    ("tool", "params"),
    [
        ("git_commit", {"author", "date", "reuse_message_from"}),
        ("git_cherry_pick", {"gpg_sign", "mainline"}),
        ("git_checkout", {"orphan", "allow_overwrite_ignored"}),
        (
            "git_merge",
            {"allow_overwrite_ignored", "source", "no_commit", "no_ff", "ff_only"},
        ),
        ("git_pull", {"ff_only"}),
    ],
)
def test_registry_advertises_new_params_when_schema_read(tool, params):
    assert params <= set(_REGISTRY[tool].schema["properties"])
    op = _closure_cell(_REGISTRY[tool], "op_func")
    assert params <= set(inspect.signature(op).parameters)


@pytest.mark.parametrize(
    "name", ["git_commit", "git_cherry_pick", "git_checkout", "git_merge"]
)
def test_registry_keeps_mutates_index_when_tool_gains_params(name):
    assert _closure_cell(_REGISTRY[name], "mutates_index") is True
