"""AST-walking machinery for the test patch-target namespace guard.

Shared by ``test_patch_target_namespace_convention.py``. Split out to keep
both modules under the project's per-file line budget; this module has no
tests of its own (no ``test_`` prefix, so pytest does not collect it).

See the guard test's module docstring for the full rationale (issue #249:
why a split import namespace lets a ``patch()`` silently miss, and why the
guard enumerates every test module instead of sampling).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent

_PKG = "mcp_server_git"
_SRC_ROOT = "src"

# Built by concatenation rather than spelled as literals so this module's own
# source carries no string the collector would pick up as a patch target.
# Belt and braces: the walk also skips the two guard files by name below.
SRC_PREFIX = f"{_SRC_ROOT}.{_PKG}."
BARE_PREFIX = f"{_PKG}."

SRC = "src"
BARE = "bare"

# The guard's own two modules. Both necessarily contain namespaced strings
# (these prefixes, and the synthetic fixtures in the test), which are
# machinery rather than patch targets and must not be mistaken for the
# convention they police.
_SELF_MODULES = frozenset(
    {
        "_patch_namespace_ast.py",
        "test_patch_target_namespace_convention.py",
    }
)

# Violation kinds, reported by `find_violations`.
MIXED_TARGETS = "mixed-targets"
MIXED_IMPORTS = "mixed-imports"
MISMATCH = "mismatch"
UNANCHORED = "unanchored"
DECLARED_MISMATCH = "declared-mismatch"

# Test modules that carry namespaced target strings but import no package
# code at all, so nothing inside the file pins which namespace is intended.
# Each must DECLARE its namespace here (issue #249) rather than rely on
# matching its neighbours by convention. Keyed by path relative to `tests/`,
# mapped to (declared_namespace, reason).
_UNANCHORED_MODULES: dict[str, tuple[str, str]] = {
    "integration/conftest.py": (
        SRC,
        "fixtures-only module with no import of package code; the suites "
        "beneath it (github/, azure/) are src-namespaced, and a conftest "
        "getting this wrong would silently unpatch every test under it",
    ),
}


def namespace_of(dotted: str) -> str | None:
    """Namespace of a dotted module path as written in an ``import``.

    A bare package name with no trailing component still anchors a file, so
    ``mcp_server_git`` and ``src.mcp_server_git`` both count here.
    """
    if dotted == f"{_SRC_ROOT}.{_PKG}" or dotted.startswith(SRC_PREFIX):
        return SRC
    if dotted == _PKG or dotted.startswith(BARE_PREFIX):
        return BARE
    return None


def target_namespace_of(text: str) -> str | None:
    """Namespace of a *quoted* module path -- a ``patch()`` target, an
    ``importlib`` name, a ``sys.modules`` key.

    Unlike `namespace_of`, a trailing component is required: the package
    name alone cannot name something to patch, so it is not a target.
    """
    if text.startswith(SRC_PREFIX):
        return SRC
    if text.startswith(BARE_PREFIX):
        return BARE
    return None


@dataclass(frozen=True)
class Occurrence:
    lineno: int
    namespace: str
    text: str


@dataclass(frozen=True)
class Module:
    """A test module's namespace evidence: what it imports, what it names in
    strings."""

    path: str  # relative to tests/, posix-style
    imports: tuple[Occurrence, ...]
    targets: tuple[Occurrence, ...]

    @property
    def import_namespaces(self) -> frozenset[str]:
        return frozenset(occurrence.namespace for occurrence in self.imports)

    @property
    def target_namespaces(self) -> frozenset[str]:
        return frozenset(occurrence.namespace for occurrence in self.targets)

    @property
    def is_anchored(self) -> bool:
        """True when the file's own imports pin a namespace."""
        return bool(self.import_namespaces)


class _NamespaceCollector(ast.NodeVisitor):
    """Records every package import and every string naming a package module.

    Every such string is held to the file's namespace regardless of how it is
    used: a ``patch()`` argument, a ``PATCH_TARGET`` constant, an
    ``importlib.import_module`` name and a ``sys.modules`` key all resolve a
    module by name, so all of them can miss the module under test.

    ``generic_visit`` descends into function bodies, so a function-local
    ``import`` anchors its module just as a top-level one does.
    """

    def __init__(self) -> None:
        self.imports: list[Occurrence] = []
        self.targets: list[Occurrence] = []

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            namespace = namespace_of(alias.name)
            if namespace is not None:
                self.imports.append(Occurrence(node.lineno, namespace, alias.name))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        # `level > 0` is a relative import (`from .helpers import x`), which
        # names no absolute namespace and so anchors nothing.
        if node.level == 0 and node.module is not None:
            namespace = namespace_of(node.module)
            if namespace is not None:
                self.imports.append(Occurrence(node.lineno, namespace, node.module))
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:  # noqa: N802
        if isinstance(node.value, str):
            namespace = target_namespace_of(node.value)
            if namespace is not None:
                self.targets.append(Occurrence(node.lineno, namespace, node.value))
        self.generic_visit(node)


def collect_from_source(source: str, path: str) -> Module:
    """Parse *source* under *path* and return its namespace evidence. Shared
    by real-file discovery and the synthetic tests."""
    tree = ast.parse(source, filename=path)
    collector = _NamespaceCollector()
    collector.visit(tree)
    return Module(
        path=path,
        imports=tuple(collector.imports),
        targets=tuple(collector.targets),
    )


def discover_modules() -> list[Module]:
    """Walk every ``*.py`` under ``tests/``, recursively (``rglob``), so a
    module added tomorrow in a nested suite is not a blind spot."""
    modules: list[Module] = []
    for path in sorted(_TESTS_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(_TESTS_DIR).as_posix()
        if relative in _SELF_MODULES:
            continue
        modules.append(collect_from_source(path.read_text(), relative))
    return modules


@dataclass(frozen=True)
class Violation:
    path: str
    kind: str
    detail: str


def _describe(occurrences: tuple[Occurrence, ...]) -> str:
    first = occurrences[0]
    return f"line {first.lineno}: {first.text!r}"


def check_module(
    module: Module,
    allowlist: dict[str, tuple[str, str]] | None = None,
) -> Violation | None:
    """The convention, as a single decision over one module's evidence."""
    entries = _UNANCHORED_MODULES if allowlist is None else allowlist

    target_namespaces = module.target_namespaces
    if not target_namespaces:
        return None  # nothing resolved by name; nothing to get wrong

    if len(target_namespaces) > 1:
        return Violation(
            module.path,
            MIXED_TARGETS,
            f"names package modules in BOTH namespaces "
            f"({sorted(target_namespaces)}); {_describe(module.targets)}",
        )

    (target_namespace,) = target_namespaces

    if not module.is_anchored:
        entry = entries.get(module.path)
        if entry is None:
            return Violation(
                module.path,
                UNANCHORED,
                f"uses the {target_namespace!r} namespace in strings but "
                f"imports no package code, so nothing in the file pins it; "
                f"{_describe(module.targets)}",
            )
        declared, _reason = entry
        if declared != target_namespace:
            return Violation(
                module.path,
                DECLARED_MISMATCH,
                f"declares the {declared!r} namespace in "
                f"`_UNANCHORED_MODULES` but its strings use "
                f"{target_namespace!r}; {_describe(module.targets)}",
            )
        return None

    import_namespaces = module.import_namespaces
    if len(import_namespaces) > 1:
        return Violation(
            module.path,
            MIXED_IMPORTS,
            f"imports package code through BOTH namespaces "
            f"({sorted(import_namespaces)}), so its patch targets cannot "
            f"match both; {_describe(module.imports)}",
        )

    if target_namespace not in import_namespaces:
        (import_namespace,) = import_namespaces
        return Violation(
            module.path,
            MISMATCH,
            f"imports via {import_namespace!r} but names package modules "
            f"via {target_namespace!r}, so the patched module is not the "
            f"one under test; {_describe(module.targets)}",
        )

    return None


def find_violations(
    modules: list[Module],
    allowlist: dict[str, tuple[str, str]] | None = None,
) -> list[Violation]:
    violations = (check_module(module, allowlist) for module in modules)
    return [violation for violation in violations if violation is not None]
