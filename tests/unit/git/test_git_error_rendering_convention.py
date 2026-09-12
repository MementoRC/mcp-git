"""Enumerating structural guard for the bare-git-error-rendering convention.

Issue #219 established a convention: every ``except GitCommandError`` handler
that reports a FAILED OPERATION must surface git's bare stderr/stdout via
``clean_git_error_text``/``_clean_git_error_text``, never GitPython's
decorated ``CommandError.__str__`` (the ``Cmd('git') failed due to: ...`` /
``cmdline:`` / ``stderr: '...'`` envelope).

``test_git_error_rendering_bare_message.py`` only *samples* this convention
(one handler per module). A sampled guard is exactly what let the convention
drift across #215 -> #219: new handlers were added, or existing ones edited,
without the sample being updated, and nothing failed. This guard instead
*enumerates*: it walks the AST of every module under
``src/mcp_server_git/git/`` (recursively -- ``rglob``, so a handler added in
a nested subpackage is not a blind spot) at test time, finds every handler
that catches ``GitCommandError``, and requires each one to either render via
the shared helper or be justified in the ``_PREDICATE_HANDLERS`` allowlist
below. Any new non-compliant handler -- added tomorrow, in a file this test
has never seen -- fails immediately instead of silently slipping through.

A single function can contain BOTH a predicate handler (a pure existence/
support test with nothing to render) and a rendering handler for a genuinely
failed operation -- ``git_reset`` in ``_staging_ops.py`` is exactly this
case. Keying the allowlist by ``(file, function)`` alone would therefore
over-exempt: if someone later strips ``clean_git_error_text`` from that
function's OUTER handler, the key still matches and the guard would wrongly
stay green. Each allowlist entry therefore also carries a body
**fingerprint** -- a substring of the predicate handler's own
``ast.unparse``'d body -- and a handler is only exempted when BOTH its key
AND that fingerprint match. `test_over_exemption_is_caught_...` below is the
proof this actually discriminates between the two handlers in one function.
"""

from __future__ import annotations

from ._error_rendering_ast import (
    _GIT_SRC_DIR,
    _PREDICATE_HANDLERS,
    collect_from_source,
    discover_handlers,
    find_violations,
)

_REQUIRED_MODULES = {
    "_remote_ops.py",
    "_staging_ops.py",
    "_commit_ops.py",
    "_diff_ops.py",
    "_branch_ops.py",
    "_rebase_ops.py",
    "_tag_ops.py",
    "_config_ops.py",
    "_submodule_ops.py",
    "operations_extended.py",
    "merge_ops.py",
}

# A synthetic stand-in for `_staging_ops.py`'s `git_reset`: one handler that
# genuinely matches the allowlisted predicate fingerprint ("does not
# exist"), plus a second, unrelated non-rendering handler in the SAME
# function that does NOT -- simulating someone stripping
# `clean_git_error_text` from the real outer handler. Used only to prove the
# fingerprint check discriminates between the two (HOLE 1).
_BROKEN_GIT_RESET_SOURCE = """
def git_reset(repo, mode=None, target=None, files=None):
    if target:
        try:
            repo.git.rev_parse(target)
        except GitCommandError:
            return f"Target '{target}' does not exist"
    try:
        repo.git.reset()
    except GitCommandError as e:
        return f"Reset failed: {e}"
"""


class TestGitCommandErrorHandlersRenderBareText:
    """Every non-predicate `except GitCommandError` handler must render
    bare git stderr/stdout via `clean_git_error_text`."""

    def test_all_handlers_render_or_are_allowlisted_when_walking_src(self) -> None:
        violations = find_violations(discover_handlers())

        if violations:
            details = "\n".join(
                f"  - {h.file}:{h.lineno} in `{h.function}()`" for h in violations
            )
            raise AssertionError(
                "Found `except GitCommandError` handler(s) that report a "
                "failed operation without rendering bare git text via "
                "`clean_git_error_text`:\n"
                f"{details}\n\n"
                "Fix by either:\n"
                "  1. Rendering the error via "
                "`clean_git_error_text(e.stderr, 'stderr')` (or 'stdout'), or\n"
                "  2. If this handler is a predicate (an existence/support "
                "test that never reports a failed op), add "
                '`(filename, function_name): (fingerprint, "reason")` to '
                "`_PREDICATE_HANDLERS` in this test file, where fingerprint "
                "is a substring unique to THIS handler's body."
            )

    def test_predicate_allowlist_entries_match_exactly_one_handler_each(
        self,
    ) -> None:
        """Each allowlist entry must match exactly one discovered
        non-rendering handler: zero means stale (the handler was fixed or
        removed -- delete the entry); more than one means the fingerprint is
        too loose to discriminate between handlers sharing that key."""
        handlers = discover_handlers()

        match_counts: dict[tuple[str, str], int] = {}
        for key, (fingerprint, _reason) in _PREDICATE_HANDLERS.items():
            match_counts[key] = sum(
                1
                for h in handlers
                if h.key == key
                and not h.renders()
                and h.matches_fingerprint(fingerprint)
            )

        bad = {key: count for key, count in match_counts.items() if count != 1}

        assert not bad, (
            "`_PREDICATE_HANDLERS` entries must each match exactly one "
            f"non-rendering handler; got {bad} (key -> match count). A "
            "count of 0 means the handler was fixed/removed (delete the "
            "entry); a count > 1 means the fingerprint is too loose."
        )

    def test_discovery_finds_expected_handler_volume_and_module_coverage(
        self,
    ) -> None:
        """Vacuity guard: a refactor that breaks the AST walk (e.g. wrong
        path, wrong node type) must not make this suite trivially pass."""
        handlers = discover_handlers()

        assert len(handlers) >= 40, (
            f"Expected at least 40 `except GitCommandError` handlers under "
            f"{_GIT_SRC_DIR}, found {len(handlers)}. Did the AST walk break?"
        )

        covered_files = {h.file for h in handlers}
        missing = _REQUIRED_MODULES - covered_files
        assert not missing, (
            f"Expected handlers to be discovered in {sorted(missing)} but "
            "none were found there. Did the AST walk break?"
        )

    def test_over_exemption_is_caught_when_key_matches_but_fingerprint_does_not(
        self,
    ) -> None:
        """Proof for HOLE 1: a (file, function) key alone is not enough to
        exempt a handler. Feed the collector a synthetic `_staging_ops.py`
        shaped `git_reset` containing the real allowlisted predicate handler
        PLUS a second, broken, non-rendering handler in that same function
        (standing in for someone stripping `clean_git_error_text` from the
        real outer handler). Only the fingerprint-matching one may be
        exempted; the other must be reported as a violation despite sharing
        the allowlisted key."""
        handlers = collect_from_source(_BROKEN_GIT_RESET_SOURCE, "_staging_ops.py")
        assert len(handlers) == 2, "fixture drifted -- expected exactly 2 handlers"

        violations = find_violations(handlers)

        assert len(violations) == 1, (
            f"Expected exactly one violation (the broken outer handler), "
            f"got {len(violations)}: {[(h.lineno, h.body) for h in violations]}"
        )
        assert "Reset failed" in violations[0].body
        assert "does not exist" not in violations[0].body
