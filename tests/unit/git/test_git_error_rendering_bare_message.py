"""Guard tests for issue #219 — bare git error rendering.

Every ``except GitCommandError`` handler across the converted modules
(part 1: ``_remote_ops.py``, ``_rebase_ops.py``, ``_branch_ops.py``; part 2:
``_commit_ops.py``, ``_diff_ops.py``, ``_submodule_ops.py``,
``_staging_ops.py``, ``_config_ops.py``, ``_tag_ops.py``) must surface the
bare git stderr text via ``clean_git_error_text``, not GitPython's decorated
``CommandError.__str__`` repr (``"Cmd('git') failed due to: ..."`` with the
``cmdline:``/``stderr: '...'`` envelope).

These tests construct ``GitCommandError`` through its real ``__init__`` (not
by hand-setting ``.stderr``) so the decoration GitPython applies is
reproduced faithfully -- mirroring the pattern from #215's regression tests
in ``test_operations_extended_error_cleaning.py``.
"""

from unittest.mock import Mock

from mcp_server_git.git._branch_ops import git_merge_base
from mcp_server_git.git._commit_ops import git_log
from mcp_server_git.git._config_ops import git_config_get
from mcp_server_git.git._diff_ops import git_diff
from mcp_server_git.git._rebase_ops import git_abort
from mcp_server_git.git._remote_ops import git_remote_add
from mcp_server_git.git._staging_ops import git_reset
from mcp_server_git.git._submodule_ops import git_submodule_status
from mcp_server_git.git._tag_ops import git_tag_list
from mcp_server_git.utils.git_import import GitCommandError

_DECORATION_MARKERS = ("Cmd('git') failed", "cmdline:", "stderr: '")


class TestRemoteOpsBareErrorMessage:
    def test_git_remote_add_renders_bare_stderr(self) -> None:
        mock_repo = Mock()
        mock_repo.git.remote.side_effect = GitCommandError(
            ["git", "remote", "add"], 128, b"fatal: remote origin already exists."
        )

        result = git_remote_add(mock_repo, "origin", "https://example.com/repo.git")

        assert "fatal: remote origin already exists." in result
        for marker in _DECORATION_MARKERS:
            assert marker not in result


class TestRebaseOpsBareErrorMessage:
    def test_git_abort_renders_bare_stderr(self) -> None:
        mock_repo = Mock()
        mock_repo.git.rebase.side_effect = GitCommandError(
            ["git", "rebase", "--abort"], 128, b"fatal: no rebase in progress"
        )

        result = git_abort(mock_repo, "rebase")

        assert "fatal: no rebase in progress" in result
        for marker in _DECORATION_MARKERS:
            assert marker not in result


class TestBranchOpsBareErrorMessage:
    def test_git_merge_base_renders_bare_stderr(self) -> None:
        mock_repo = Mock()
        mock_repo.git.merge_base.side_effect = GitCommandError(
            ["git", "merge-base"], 1, b"fatal: Not a valid object name nope"
        )

        result = git_merge_base(mock_repo, "nope", "also-nope")

        assert "fatal: Not a valid object name nope" in result
        for marker in _DECORATION_MARKERS:
            assert marker not in result


class TestCommitOpsBareErrorMessage:
    def test_git_log_renders_bare_stderr(self) -> None:
        mock_repo = Mock()
        mock_repo.git.log.side_effect = GitCommandError(
            ["git", "log"], 128, b"fatal: bad revision 'nope'"
        )

        result = git_log(mock_repo)

        assert "fatal: bad revision 'nope'" in result
        for marker in _DECORATION_MARKERS:
            assert marker not in result


class TestDiffOpsBareErrorMessage:
    def test_git_diff_renders_bare_stderr(self) -> None:
        mock_repo = Mock()
        mock_repo.git.diff.side_effect = GitCommandError(
            ["git", "diff"], 128, b"fatal: ambiguous argument 'nope'"
        )

        result = git_diff(mock_repo)

        assert "fatal: ambiguous argument 'nope'" in result
        for marker in _DECORATION_MARKERS:
            assert marker not in result


class TestSubmoduleOpsBareErrorMessage:
    def test_git_submodule_status_renders_bare_stderr(self) -> None:
        mock_repo = Mock()
        mock_repo.git.submodule.side_effect = GitCommandError(
            ["git", "submodule", "status"], 128, b"fatal: no submodule mapping found"
        )

        result = git_submodule_status(mock_repo)

        assert "fatal: no submodule mapping found" in result
        for marker in _DECORATION_MARKERS:
            assert marker not in result


class TestStagingOpsBareErrorMessage:
    def test_git_reset_renders_bare_stderr(self) -> None:
        mock_repo = Mock()
        mock_repo.git.reset.side_effect = GitCommandError(
            ["git", "reset"], 128, b"fatal: ambiguous argument 'HEAD'"
        )

        result = git_reset(mock_repo)

        assert "fatal: ambiguous argument 'HEAD'" in result
        for marker in _DECORATION_MARKERS:
            assert marker not in result


class TestConfigOpsBareErrorMessage:
    def test_git_config_get_renders_bare_stderr(self) -> None:
        mock_repo = Mock()
        mock_repo.git.config.side_effect = GitCommandError(
            ["git", "config"], 1, b"error: key does not contain a section: nope"
        )

        result = git_config_get(mock_repo, "nope")

        assert "error: key does not contain a section: nope" in result
        for marker in _DECORATION_MARKERS:
            assert marker not in result


class TestTagOpsBareErrorMessage:
    def test_git_tag_list_renders_bare_stderr(self) -> None:
        mock_repo = Mock()
        mock_repo.git.tag.side_effect = GitCommandError(
            ["git", "tag"], 128, b"fatal: not a git repository"
        )

        result = git_tag_list(mock_repo)

        assert "fatal: not a git repository" in result
        for marker in _DECORATION_MARKERS:
            assert marker not in result
