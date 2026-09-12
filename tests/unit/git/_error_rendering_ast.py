"""AST-walking machinery for the bare-git-error-rendering guard.

Shared by ``test_git_error_rendering_convention.py``. Split out to keep both
modules under the project's per-file line budget; this module has no tests
of its own (no ``test_`` prefix, so pytest does not collect it).

See the guard test's module docstring for the full rationale (why enumerate
instead of sample, and why the allowlist needs a body fingerprint in
addition to the ``(file, function)`` key).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

_GIT_SRC_DIR = Path(__file__).resolve().parents[3] / "src" / "mcp_server_git" / "git"

_RENDER_MARKER = "clean_git_error_text"  # matches both the public name and
# the `_clean_git_error_text` alias re-exported from operations_extended.py

# Handlers that use `except GitCommandError` as a PREDICATE (an existence/
# support test), never to report a failed operation, so they have nothing to
# render. Keyed by (module_filename, enclosing_function_name) -- not line
# number, which rots on every unrelated edit to the file -- mapped to
# (body_fingerprint, reason). `body_fingerprint` must be a substring of the
# specific handler's `ast.unparse`'d body (verified against the real
# unparsed text, not the original source spelling) so a second, unrelated,
# non-rendering handler sharing the same (file, function) key is NOT
# exempted by accident.
_PREDICATE_HANDLERS: dict[tuple[str, str], tuple[str, str]] = {
    ("_staging_ops.py", "_get_staged_file_set"): (
        "ls_files",
        "falls back to `git ls-files --cached` when there is no HEAD yet; "
        "the exception means 'nothing to diff against', not a failed op",
    ),
    ("_staging_ops.py", "git_reset"): (
        "does not exist",
        "rev_parse existence probe for `target`; used purely as a test of "
        "whether the ref exists, not to report a failed git command",
    ),
    ("merge_ops.py", "_read_blob"): (
        "return ('', False)",
        "a missing path on one side of a three-way merge is normal (added/"
        "deleted file), not an error -- returns present=False",
    ),
}


@dataclass(frozen=True)
class Handler:
    file: str
    lineno: int
    function: str
    body: str

    def renders(self) -> bool:
        return _RENDER_MARKER in self.body

    @property
    def key(self) -> tuple[str, str]:
        return (self.file, self.function)

    def matches_fingerprint(self, fingerprint: str) -> bool:
        return fingerprint in self.body

    def is_allowlisted(self) -> bool:
        """True only when both the (file, function) key AND the entry's
        body fingerprint match -- a key match alone is not sufficient
        because a single function can contain both a predicate handler and
        a genuine rendering handler (see ``git_reset``)."""
        entry = _PREDICATE_HANDLERS.get(self.key)
        if entry is None:
            return False
        fingerprint, _reason = entry
        return self.matches_fingerprint(fingerprint)


def _mentions_git_command_error(type_node: ast.expr | None) -> bool:
    """True if an `except` clause's type expression names GitCommandError.

    Handles bare `except GitCommandError`, `except GitCommandError as e`, and
    tuple forms like `except (GitCommandError, ValueError)`.
    """
    if type_node is None:
        return False
    if isinstance(type_node, ast.Name):
        return type_node.id == "GitCommandError"
    if isinstance(type_node, ast.Attribute):
        return type_node.attr == "GitCommandError"
    if isinstance(type_node, ast.Tuple):
        return any(_mentions_git_command_error(elt) for elt in type_node.elts)
    return False


class HandlerCollector(ast.NodeVisitor):
    """Walks a module's AST, recording every GitCommandError handler along
    with the name of its nearest enclosing function (or "<module>")."""

    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.handlers: list[Handler] = []
        self._func_stack: list[str] = []

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._func_stack.append(node.name)
        self.generic_visit(node)
        self._func_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._visit_function(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:  # noqa: N802
        if _mentions_git_command_error(node.type):
            enclosing = self._func_stack[-1] if self._func_stack else "<module>"
            body = "\n".join(ast.unparse(stmt) for stmt in node.body)
            self.handlers.append(
                Handler(
                    file=self.filename,
                    lineno=node.lineno,
                    function=enclosing,
                    body=body,
                )
            )
        self.generic_visit(node)


def collect_from_source(source: str, filename: str) -> list[Handler]:
    """Parse *source* under *filename* and return its GitCommandError
    handlers. Shared by real-file discovery and the synthetic tests."""
    tree = ast.parse(source, filename=filename)
    collector = HandlerCollector(filename)
    collector.visit(tree)
    return collector.handlers


def discover_handlers() -> list[Handler]:
    """Walk every ``*.py`` under ``_GIT_SRC_DIR``, recursively (``rglob``),
    so a handler added in a nested subpackage is not a blind spot."""
    handlers: list[Handler] = []
    for path in sorted(_GIT_SRC_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        relative_name = str(path.relative_to(_GIT_SRC_DIR))
        handlers.extend(collect_from_source(path.read_text(), relative_name))
    return handlers


def find_violations(handlers: list[Handler]) -> list[Handler]:
    """Non-rendering handlers that are not exempted by a matching
    (key AND fingerprint) allowlist entry."""
    return [h for h in handlers if not h.renders() and not h.is_allowlisted()]
