"""Convention guard: no "❌" string literal outside ``fail(...)``.

Every failure must go through ``fail(...)`` so the execute_tool envelope
reports status "error" (issue #271). A failure text held in a constant or
variable escapes a "no bare ``return "❌..."``" rule, so the guard flags any
str literal (or f-string) whose leading text is "❌" unless it is an argument
of ``fail(...)``. The guard discovers every module under
``src/mcp_server_git/`` by walking the package, so new modules are covered
automatically. Every module is checked.

Escape hatches, all explicit:

* Direct arguments of ``logger.x(...)`` / ``logging.x(...)`` are skipped.
* ``PENDING_PATHS``: relpath prefixes (POSIX, relative to the package root;
  directories end with "/") exempt while a migration is in flight. It is
  empty now that #271 is complete; the mechanism remains for future
  migrations.
* ``ALLOWLIST``: ``(relpath, enclosing function or "<module>")`` -> reason
  for literals that are legitimately not failure results. Entries that no
  longer match a real hit fail the staleness test.
"""

import ast
from pathlib import Path

import pytest

import mcp_server_git

_MARK = "❌"
_LOG_OWNERS = {"logger", "logging"}
_PACKAGE_ROOT = Path(mcp_server_git.__file__).resolve().parent

# Modules exempt while a future migration is in flight. Directory entries end
# with "/". Empty: every module is checked.
PENDING_PATHS: set[str] = set()

# {(relpath, enclosing function or "<module>"): reason}.
_EMOJI_REASON = "regex pattern that strips/rewrites ❌ in LLM output, not a result"
_MARKER_REASON = "status marker glyph rendered in a line, not a failure result"
ALLOWLIST: dict[tuple[str, str], str] = {
    ("utils/content_optimization.py", "__init__"): _EMOJI_REASON,
    ("github/check_markers.py", "<module>"): _MARKER_REASON,
    ("github/check_markers.py", "bool_marker"): _MARKER_REASON,
    ("github/_pr_format.py", "<module>"): "review state marker glyph, not a result",
    ("github/_pr_format.py", "failing_run_header"): (
        "heading line for a failing check run inside a successful report"
    ),
    ("github/issue_search.py", "github_bulk_update_issues"): (
        "per-item failure lines inside a partial-success summary"
    ),
}


def _leads_with_mark(node: ast.AST) -> bool:
    if isinstance(node, ast.JoinedStr):
        node = node.values[0] if node.values else node
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.lstrip().startswith(_MARK)
    )


def _is_call_to(node: ast.AST, owners: set[str]) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        func = func.value
    return isinstance(func, ast.Name) and func.id in owners


def _is_fail_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "fail"
    )


def _is_log_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and _is_call_to(node, _LOG_OWNERS)


def _mark_hits(source: str, relpath: str) -> list[tuple[str, str]]:
    """Return (relpath, enclosing function) for each ❌ literal outside fail()."""
    hits: list[tuple[str, str]] = []

    def visit(node: ast.AST, func: str, in_fail: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                visit(child, child.name, in_fail)
                continue
            if _leads_with_mark(child):
                if not (in_fail or _is_log_call(node)):
                    hits.append((relpath, func))
                continue  # parts of a larger JoinedStr are not separate hits
            visit(child, func, in_fail or _is_fail_call(child))

    visit(ast.parse(source), "<module>", False)
    return hits


def _path_hits(path: Path) -> list[tuple[str, str]]:
    return _mark_hits(path.read_text(encoding="utf-8"), _relpath(path))


def _discovered_files() -> list[Path]:
    return sorted(_PACKAGE_ROOT.rglob("*.py"))


def _relpath(path: Path) -> str:
    return path.relative_to(_PACKAGE_ROOT).as_posix()


def _is_pending(relpath: str, pending: set[str] | None = None) -> bool:
    entries = PENDING_PATHS if pending is None else pending
    return any(relpath == p or relpath.startswith(p) for p in entries)


_CHECKED_FILES = [p for p in _discovered_files() if not _is_pending(_relpath(p))]


@pytest.mark.parametrize("path", _CHECKED_FILES, ids=_relpath)
def test_module_has_no_mark_literal_outside_fail_when_not_pending(path):
    unexpected = [hit for hit in _path_hits(path) if hit not in ALLOWLIST]
    assert unexpected == []


def test_discovery_includes_issue_modules_when_scanning_package():
    relpaths = {_relpath(p) for p in _CHECKED_FILES}
    assert relpaths
    assert {"git/_staging_ops.py", "git/_branch_ops.py", "github/pr.py"} <= relpaths


def test_allowlist_matches_real_hits_when_entries_exist():
    found = {hit for p in _discovered_files() for hit in _path_hits(p)}
    stale = set(ALLOWLIST) - found
    assert stale == set()


def test_detector_flags_constant_outside_fail_when_wrapped_or_not():
    bare = '_X = "❌ boom"\n\ndef op():\n    return _X\n'
    wrapped = '_X = fail("❌ boom")\n\ndef op():\n    return _X\n'
    logged = 'def op():\n    logger.error("❌ boom")\n    return fail(f"❌ {1}")\n'
    padded = '_X = "\\n❌ boom"\n'
    assert _mark_hits(bare, "m.py") == [("m.py", "<module>")]
    assert _mark_hits(padded, "m.py") == [("m.py", "<module>")]
    assert _mark_hits(wrapped, "m.py") == []
    assert _mark_hits(logged, "m.py") == []


def test_pending_paths_exist_when_listed():
    missing = [
        entry
        for entry in sorted(PENDING_PATHS)
        if not (
            (_PACKAGE_ROOT / entry).is_dir()
            if entry.endswith("/")
            else (_PACKAGE_ROOT / entry).is_file()
        )
    ]
    assert missing == []


def test_is_pending_matches_exact_file_and_directory_prefix_when_listed():
    pending = {"azure/", "git/_x.py"}
    assert _is_pending("azure/api.py", pending)
    assert _is_pending("git/_x.py", pending)
    assert not _is_pending("git/_x.pyc", {"git/_y.py"})
    assert not _is_pending("github/security.py", pending)
    assert not _is_pending("azure/api.py")
