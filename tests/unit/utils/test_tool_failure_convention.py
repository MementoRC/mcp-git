"""Convention guard: migrated modules never return a bare "❌" string.

Every failure in a migrated module must go through ``fail(...)`` so the
execute_tool envelope reports status "error". Extend MIGRATED_MODULES as
more modules are migrated.
"""

import ast
from pathlib import Path

import pytest

from mcp_server_git.git import _stash_ops

MIGRATED_MODULES = (_stash_ops,)

_MARK = "❌"


def _bare_failure_returns(module_obj) -> list[int]:
    tree = ast.parse(Path(module_obj.__file__).read_text(encoding="utf-8"))
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            text = value.value
        elif isinstance(value, ast.JoinedStr) and value.values:
            first = value.values[0]
            is_const = isinstance(first, ast.Constant)
            text = first.value if is_const and isinstance(first.value, str) else ""
        else:
            continue
        if text.startswith(_MARK):
            lines.append(node.lineno)
    return lines


@pytest.mark.parametrize("module_obj", MIGRATED_MODULES, ids=lambda m: m.__name__)
def test_module_returns_no_bare_failure_string_when_migrated(module_obj):
    assert _bare_failure_returns(module_obj) == []
