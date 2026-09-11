"""Regression tests for issue #215 — dead `isinstance(e.stderr, bytes)` branches.

`git.exc.CommandError.__init__` never exposes the raw stdout/stderr stream: it
always assigns `self.stderr = stderr and "\\n  stderr: '%s'" % safe_decode(stderr)
or ""`. `safe_decode` guarantees a `str`, so the `bytes` branch in
`isinstance(e.stderr, bytes) else e.stderr` is unreachable, and the surviving
`else` branch returns the DECORATED value — rendering messages like
"❌ Failed to add worktree: \\n  stderr: 'fatal: ...'" instead of the bare git
message.

These tests construct `GitCommandError` through its real `__init__` (not by
hand-setting `.stderr`) so the decoration is reproduced faithfully, then assert
the rendered message contains the bare git text and NOT the `stderr: '` envelope.
"""

from unittest.mock import Mock

from mcp_server_git.git.operations_extended import (
    git_restore,
    git_worktree_add,
)
from mcp_server_git.utils.git_import import GitCommandError


class TestGitRestoreErrorCleaning:
    def test_git_restore_renders_bare_stderr_without_envelope(self):
        mock_repo = Mock()
        mock_repo.git.restore.side_effect = GitCommandError(
            ["git", "restore"],
            128,
            b"fatal: pathspec 'missing.py' did not match any files",
        )

        result = git_restore(mock_repo, files=["missing.py"])

        assert "fatal: pathspec 'missing.py' did not match any files" in result
        assert "stderr: '" not in result


class TestGitWorktreeAddErrorCleaning:
    def test_git_worktree_add_renders_bare_stderr_without_envelope(self):
        mock_repo = Mock()
        mock_repo.git.worktree.side_effect = GitCommandError(
            ["git", "worktree", "add"], 128, b"fatal: boom"
        )

        result = git_worktree_add(mock_repo, worktree_path="/tmp/wt")

        assert "fatal: boom" in result
        assert "stderr: '" not in result
