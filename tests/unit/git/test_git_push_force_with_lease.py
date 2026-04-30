"""
Unit tests for git_push force-with-lease options (issue #161).

Verifies mutual-exclusion guards, flag construction, and plain-force
regression. The implementation in _remote_ops.py is the source of truth.
"""

from unittest.mock import MagicMock

import pytest

from mcp_server_git.git.operations import git_push


@pytest.fixture()
def mock_repo() -> MagicMock:
    """Minimal repo mock: SSH remote URL bypasses GitHub HTTPS auth branch."""
    repo = MagicMock()
    repo.active_branch.name = "feature/x"
    repo.remote.return_value.url = "git@github.com:owner/repo.git"
    repo.git.push.return_value = ""
    return repo


def test_git_push_rejects_force_and_force_with_lease_combined(
    mock_repo: MagicMock,
) -> None:
    result = git_push(mock_repo, force=True, force_with_lease=True)

    assert result.startswith("❌")
    assert "mutually exclusive" in result
    mock_repo.git.push.assert_not_called()


def test_git_push_rejects_force_with_lease_expect_without_force_with_lease(
    mock_repo: MagicMock,
) -> None:
    result = git_push(
        mock_repo, force_with_lease=False, force_with_lease_expect="abc123"
    )

    assert result.startswith("❌")
    assert "force_with_lease_expect requires force_with_lease=True" in result
    mock_repo.git.push.assert_not_called()


def test_git_push_plain_force_with_lease_passes_flag(mock_repo: MagicMock) -> None:
    git_push(mock_repo, force_with_lease=True)

    mock_repo.git.push.assert_called_once()
    args = mock_repo.git.push.call_args.args
    assert "--force-with-lease" in args


def test_git_push_force_with_lease_bare_sha_derives_refname(
    mock_repo: MagicMock,
) -> None:
    git_push(
        mock_repo,
        branch="feature/x",
        force_with_lease=True,
        force_with_lease_expect="deadbeef",
    )

    args = mock_repo.git.push.call_args.args
    assert "--force-with-lease=feature/x:deadbeef" in args


def test_git_push_force_with_lease_colon_form_passes_through(
    mock_repo: MagicMock,
) -> None:
    git_push(
        mock_repo,
        force_with_lease=True,
        force_with_lease_expect="refs/heads/foo:cafebabe",
    )

    args = mock_repo.git.push.call_args.args
    assert "--force-with-lease=refs/heads/foo:cafebabe" in args


def test_git_push_force_if_includes_combines_with_force_with_lease(
    mock_repo: MagicMock,
) -> None:
    git_push(mock_repo, force_with_lease=True, force_if_includes=True)

    args = mock_repo.git.push.call_args.args
    assert "--force-with-lease" in args
    assert "--force-if-includes" in args


def test_git_push_plain_force_passes_force_flag(mock_repo: MagicMock) -> None:
    git_push(mock_repo, force=True)

    args = mock_repo.git.push.call_args.args
    assert "--force" in args


def test_git_push_returns_success_string_on_ssh_push(mock_repo: MagicMock) -> None:
    result = git_push(mock_repo, branch="feature/x")

    assert result.startswith("✅")
    assert "feature/x" in result
