"""Enumerating structural guard for the test patch-target namespace convention.

``pyproject.toml`` sets ``pythonpath = ['src']``, so both
``src.mcp_server_git.X`` and ``mcp_server_git.X`` import successfully -- as
TWO DISTINCT module objects, each with its own attributes. A test that
imports a function from one namespace while patching a target string in the
other patches a module that is not the one under test: the patch silently
does nothing, the real collaborator runs, and the test still passes
(issue #249).

There were zero mismatches when this guard was written. The two conventions
cluster by area -- ``github/`` and ``azure/`` are ``src.``-namespaced,
``git/``, ``lean/`` and ``transport/`` are bare -- rather than by rule, so
"match the neighbouring file" was the only thing keeping them consistent: an
unwritten convention enforced by nothing. A test author copying a fixture
across that boundary would produce a passing test that asserts nothing, with
no signal anywhere. This guard is prevention, not repair.

It *enumerates* rather than samples, in the spirit of #244's registry
contract: it walks the AST of every ``*.py`` under ``tests/`` at test time
(recursively -- ``rglob``), collects the namespace of each module's package
imports and of every string naming a package module, and requires the two to
agree. A file added tomorrow is covered with no edit here.

Only ONE file is genuinely unanchored -- carrying namespaced strings while
importing no package code, so nothing in it pins a namespace:
``integration/conftest.py``. #249 also listed ``lean/test_main.py``, but that
file imports ``mcp_server_git.lean.__main__`` inside its test functions; the
walk descends into function bodies, so those imports anchor it and it needs
no declaration. Rather than exempt the unanchored file,
``_UNANCHORED_MODULES`` makes it DECLARE its namespace, which is then still
checked against its strings -- a bare exemption would have left the likeliest
first casualty unguarded, and a ``conftest.py`` getting this wrong would
silently unpatch every test beneath it.

``TestGuardDiscriminatesWhenModulesAreSyntheticallyBroken`` below is the
proof that each arm of the check actually fires, rather than the suite
passing because the walk found nothing.
"""

from __future__ import annotations

from ._patch_namespace_ast import (
    _UNANCHORED_MODULES,
    BARE,
    DECLARED_MISMATCH,
    MISMATCH,
    MIXED_IMPORTS,
    MIXED_TARGETS,
    SRC,
    UNANCHORED,
    collect_from_source,
    discover_modules,
    find_violations,
)

# Floors set below the volume measured when this guard was written (~29
# modules carrying targets, ~336 occurrences, 22 of them src-namespaced) with
# margin, so ordinary churn does not trip them but a broken walk -- wrong
# root, wrong node type, prefix typo -- does.
_MIN_MODULES_SCANNED = 85
_MIN_MODULES_WITH_TARGETS = 25
_MIN_TARGET_OCCURRENCES = 300
_MIN_MODULES_PER_NAMESPACE = 4

_SYNTHETIC_PATH = "unit/synthetic/test_thing.py"

_CONSISTENT_SOURCE = """
from mcp_server_git.git.operations import git_status

def test_status():
    with patch("mcp_server_git.git.operations._run"):
        git_status()
"""

_MISMATCHED_SOURCE = """
from mcp_server_git.git.operations import git_status

def test_status():
    with patch("src.mcp_server_git.git.operations._run"):
        git_status()
"""

_MIXED_TARGETS_SOURCE = """
from mcp_server_git.git.operations import git_status

PATCH_TARGET = "src.mcp_server_git.git.operations._run"

def test_status():
    with patch("mcp_server_git.git.operations._other"):
        git_status()
"""

_MIXED_IMPORTS_SOURCE = """
from mcp_server_git.git.operations import git_status
from src.mcp_server_git.github.client import GitHubClient

def test_status():
    with patch("mcp_server_git.git.operations._run"):
        git_status()
"""

_UNANCHORED_SOURCE = """
import pytest

@pytest.fixture
def patched_run():
    with patch("src.mcp_server_git.git.operations._run") as run:
        yield run
"""

_FUNCTION_LOCAL_IMPORT_SOURCE = """
def test_status():
    from mcp_server_git.lean.__main__ import main

    with patch("mcp_server_git.lean.__main__._run"):
        main()
"""


class TestPatchTargetNamespaceConvention:
    """Every test module must resolve package modules by name through the
    same namespace it imports them from."""

    def test_all_test_modules_agree_on_one_namespace_when_walking_tests(self) -> None:
        violations = find_violations(discover_modules())

        if violations:
            details = "\n".join(
                f"  - {v.path} [{v.kind}]: {v.detail}" for v in violations
            )
            raise AssertionError(
                "Test module(s) name a package module through a namespace "
                "that does not match how the file imports it. Because "
                "`pythonpath = ['src']` makes `src.mcp_server_git` and "
                "`mcp_server_git` two distinct module objects, such a "
                "`patch()` patches a module that is not under test: it does "
                "nothing, the real collaborator runs, and the test still "
                f"passes (issue #249).\n{details}\n\n"
                "Fix by either:\n"
                "  1. Rewriting the string(s) to the namespace this file "
                "imports from, or\n"
                "  2. If the file imports no package code at all, declaring "
                "its namespace in `_UNANCHORED_MODULES` in "
                "`_patch_namespace_ast.py`, with a reason."
            )

    def test_unanchored_declarations_each_match_one_live_unanchored_module(
        self,
    ) -> None:
        """Staleness guard: an entry that no longer describes a live,
        still-unanchored module exempts nothing (or the wrong thing). If the
        module gains an import, its own imports pin the namespace and the
        entry must be deleted."""
        modules = {module.path: module for module in discover_modules()}

        stale: dict[str, str] = {}
        for path, (declared, _reason) in _UNANCHORED_MODULES.items():
            module = modules.get(path)
            if module is None:
                stale[path] = "no such module under tests/ -- delete this entry"
            elif not module.targets:
                stale[path] = (
                    "module no longer names a package module in any string "
                    "-- delete this entry"
                )
            elif module.is_anchored:
                stale[path] = (
                    "module now imports package code, so its own imports pin "
                    "the namespace -- delete this entry"
                )
            elif module.target_namespaces != {declared}:
                stale[path] = (
                    f"declares {declared!r} but its strings use "
                    f"{sorted(module.target_namespaces)}"
                )

        assert not stale, (
            "`_UNANCHORED_MODULES` entries must each describe exactly one "
            f"live, still-unanchored module: {stale}"
        )

    def test_discovery_finds_expected_module_and_target_volume(self) -> None:
        """Vacuity guard: a refactor that breaks the AST walk (wrong root,
        wrong node type, prefix typo) must not make this suite trivially
        pass."""
        modules = discover_modules()
        with_targets = [module for module in modules if module.targets]
        occurrences = sum(len(module.targets) for module in modules)

        assert len(modules) >= _MIN_MODULES_SCANNED, (
            f"expected at least {_MIN_MODULES_SCANNED} test modules under "
            f"tests/, walked {len(modules)} -- did the AST walk break?"
        )
        assert len(with_targets) >= _MIN_MODULES_WITH_TARGETS, (
            f"expected at least {_MIN_MODULES_WITH_TARGETS} modules naming a "
            f"package module in a string, found {len(with_targets)}"
        )
        assert occurrences >= _MIN_TARGET_OCCURRENCES, (
            f"expected at least {_MIN_TARGET_OCCURRENCES} namespaced strings "
            f"across tests/, found {occurrences}"
        )

        per_namespace = {
            namespace: sum(
                1 for module in with_targets if namespace in module.target_namespaces
            )
            for namespace in (SRC, BARE)
        }
        assert all(
            count >= _MIN_MODULES_PER_NAMESPACE for count in per_namespace.values()
        ), (
            f"expected both conventions to still be observed in tests/, got "
            f"{per_namespace}; a prefix matcher that recognises only one "
            "namespace would look green here"
        )


class TestGuardDiscriminatesWhenModulesAreSyntheticallyBroken:
    """Proof that each arm of the check fires on the shape it targets."""

    @staticmethod
    def _violations(
        source: str,
        allowlist: dict[str, tuple[str, str]] | None = None,
    ) -> list:
        module = collect_from_source(source, _SYNTHETIC_PATH)
        return find_violations([module], allowlist or {})

    def test_nothing_is_reported_when_imports_and_targets_agree(self) -> None:
        assert self._violations(_CONSISTENT_SOURCE) == []

    def test_mismatch_is_reported_when_module_imports_bare_but_patches_src(
        self,
    ) -> None:
        assert [v.kind for v in self._violations(_MISMATCHED_SOURCE)] == [MISMATCH]

    def test_mixed_targets_are_reported_when_one_module_uses_both_namespaces(
        self,
    ) -> None:
        assert [v.kind for v in self._violations(_MIXED_TARGETS_SOURCE)] == [
            MIXED_TARGETS
        ]

    def test_mixed_imports_are_reported_when_module_imports_both_namespaces(
        self,
    ) -> None:
        assert [v.kind for v in self._violations(_MIXED_IMPORTS_SOURCE)] == [
            MIXED_IMPORTS
        ]

    def test_unanchored_is_reported_when_module_has_no_declaration(self) -> None:
        assert [v.kind for v in self._violations(_UNANCHORED_SOURCE)] == [UNANCHORED]

    def test_nothing_is_reported_when_unanchored_module_declares_its_namespace(
        self,
    ) -> None:
        allowlist = {_SYNTHETIC_PATH: (SRC, "declared for this test")}
        assert self._violations(_UNANCHORED_SOURCE, allowlist) == []

    def test_declared_mismatch_is_reported_when_declaration_contradicts_targets(
        self,
    ) -> None:
        allowlist = {_SYNTHETIC_PATH: (BARE, "deliberately wrong")}
        assert [v.kind for v in self._violations(_UNANCHORED_SOURCE, allowlist)] == [
            DECLARED_MISMATCH
        ]

    def test_function_local_imports_anchor_a_module_like_lean_test_main(self) -> None:
        """#249 read ``lean/test_main.py`` as unanchored because its
        ``mcp_server_git`` imports sit inside test functions rather than at
        module level. The walk descends into function bodies, so those
        imports anchor it and no declaration is needed."""
        module = collect_from_source(_FUNCTION_LOCAL_IMPORT_SOURCE, _SYNTHETIC_PATH)

        assert module.is_anchored
        assert module.import_namespaces == {BARE}
        assert find_violations([module], {}) == []
