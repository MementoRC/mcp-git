"""The conftest meta_path finder rejects the double-import namespace (#272)."""

import importlib

import pytest

_FORBIDDEN_MODULE = "src" + ".mcp_server_git.github.issues"


def test_import_module_raises_import_error_when_src_prefixed_name_requested() -> None:
    with pytest.raises(ImportError, match="#272"):
        importlib.import_module(_FORBIDDEN_MODULE)


def test_import_returns_module_when_canonical_name_requested() -> None:
    import mcp_server_git.github.issues as issues

    assert issues.__name__ == "mcp_server_git.github.issues"
