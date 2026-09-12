"""Real-repo behavioral tests for issue #219 — bare git error rendering.

Every ``except GitCommandError`` handler across the converted modules
(part 1: ``_remote_ops.py``, ``_rebase_ops.py``, ``_branch_ops.py``; part 2:
``_commit_ops.py``, ``_diff_ops.py``, ``_submodule_ops.py``,
``_staging_ops.py``, ``_config_ops.py``, ``_tag_ops.py``) must surface the
bare git stderr text via ``clean_git_error_text``, not GitPython's decorated
``CommandError.__str__`` repr (``"Cmd('git') failed due to: ..."`` with the
``cmdline:``/``stderr: '...'`` envelope).

The six defects fixed across #214-#222 all survived a green suite that
mocked the exact boundary where the bug lived (a hand-built ``.stderr``
string never goes through GitPython's real decoration path). These tests
therefore drive a REAL git repository via the ``real_repo`` fixture
(``conftest.py``) and provoke an ACTUAL git failure wherever practical,
asserting on a stable substring of git's own wording (verified against the
installed git/GitPython version, not guessed) rather than a hand-authored
message. ``clean_git_error_text``'s decoration-stripping itself is unit
tested independently in ``test_operations_extended_error_cleaning.py``
(#215); this file only proves each call site actually uses it in practice.

The submodule status case is the one exception: provoking a real `git
submodule status` failure needs a corrupted `.gitmodules` / broken mapping,
which is impractical to stage reliably in a throwaway tmp_path repo, so it
stays mocked.
"""

from pathlib import Path
from unittest.mock import Mock

from mcp_server_git.git._branch_ops import git_merge_base
from mcp_server_git.git._commit_ops import git_log
from mcp_server_git.git._config_ops import git_config_get
from mcp_server_git.git._diff_ops import git_diff
from mcp_server_git.git._rebase_ops import git_abort
from mcp_server_git.git._remote_ops import git_remote_add
from mcp_server_git.git._staging_ops import git_reset
from mcp_server_git.git._submodule_ops import git_submodule_status
from mcp_server_git.git._tag_ops import git_tag_create
from mcp_server_git.utils.git_import import GitCommandError

_DECORATION_MARKERS = ("Cmd('git') failed", "cmdline:", "stderr: '")


def _assert_bare(result: str, expected_substring: str) -> None:
    """Assert *result* contains git's real wording and none of GitPython's
    decoration markers."""
    assert expected_substring in result
    for marker in _DECORATION_MARKERS:
        assert marker not in result


class TestRemoteOpsBareErrorMessage:
    def test_git_remote_add_returns_bare_stderr_when_remote_already_exists(
        self, real_repo
    ) -> None:
        git_remote_add(real_repo, "origin", "https://example.com/repo.git")

        result = git_remote_add(real_repo, "origin", "https://example.com/other.git")

        _assert_bare(result, "already exists")


class TestRebaseOpsBareErrorMessage:
    def test_git_abort_returns_bare_stderr_when_no_rebase_in_progress(
        self, real_repo
    ) -> None:
        result = git_abort(real_repo, "rebase")

        # no rebase in progress vs No rebase in progress? varies by git version
        # (leading-word capitalisation, trailing punctuation differ); match
        # the version-stable core phrase only.
        _assert_bare(result, "rebase in progress")


class TestBranchOpsBareErrorMessage:
    def test_git_merge_base_returns_bare_stderr_when_revision_does_not_exist(
        self, real_repo
    ) -> None:
        result = git_merge_base(real_repo, "nope-ref-1", "nope-ref-2")

        # Drop the leading Not a; same fragility class as the rebase message
        # above. The remainder is still distinctive to this error.
        _assert_bare(result, "valid object name")


class TestCommitOpsBareErrorMessage:
    def test_git_log_returns_bare_stderr_when_revision_is_ambiguous(
        self, real_repo
    ) -> None:
        result = git_log(real_repo, branch="nonexistent-rev")

        _assert_bare(result, "ambiguous argument")


class TestDiffOpsBareErrorMessage:
    def test_git_diff_returns_bare_stderr_when_revision_is_ambiguous(
        self, real_repo
    ) -> None:
        result = git_diff(real_repo, target="nonexistent-rev")

        _assert_bare(result, "ambiguous argument")


class TestSubmoduleOpsBareErrorMessage:
    def test_git_submodule_status_returns_bare_stderr_when_mapping_missing(
        self,
    ) -> None:
        # Kept mocked: a broken submodule mapping isn't practically
        # provokable in a throwaway tmp_path repo (see module docstring).
        mock_repo = Mock()
        mock_repo.git.submodule.side_effect = GitCommandError(
            ["git", "submodule", "status"], 128, b"fatal: no submodule mapping found"
        )

        result = git_submodule_status(mock_repo)

        _assert_bare(result, "fatal: no submodule mapping found")


class TestStagingOpsBareErrorMessage:
    def test_git_reset_returns_bare_stderr_when_hard_reset_given_paths(
        self, real_repo
    ) -> None:
        # `--hard` combined with pathspecs is rejected by git itself, and
        # reaches the real rendering handler without touching the
        # allowlisted rev_parse existence-probe predicate (no `target`).
        (Path(real_repo.working_dir) / "f.txt").write_text("content\n")

        result = git_reset(real_repo, mode="hard", files=["f.txt"])

        # Drop the leading Cannot; same reason as rebase and merge-base
        # messages above. The remainder is still distinctive.
        _assert_bare(result, "hard reset with paths")


class TestConfigOpsBareErrorMessage:
    def test_git_config_get_returns_bare_stderr_when_key_missing_section(
        self, real_repo
    ) -> None:
        result = git_config_get(real_repo, "nope")

        _assert_bare(result, "does not contain a section")


class TestTagOpsBareErrorMessage:
    def test_git_tag_create_returns_bare_stderr_when_tag_name_invalid(
        self, real_repo
    ) -> None:
        result = git_tag_create(real_repo, "bad tag name")

        _assert_bare(result, "is not a valid tag name")
