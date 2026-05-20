"""
Unit tests for git_push delete and refspec options (issue #173).

Verifies mutual-exclusion guards and flag construction for remote branch
deletion and raw refspec forms. The implementation in _remote_ops.py is
the source of truth.
"""

from unittest.mock import MagicMock

import pytest

from mcp_server_git.git.models import GitPush
from mcp_server_git.git.operations import git_push


@pytest.fixture()
def mock_repo() -> MagicMock:
    """Minimal repo mock: SSH remote URL bypasses GitHub HTTPS auth branch."""
    repo = MagicMock()
    repo.active_branch.name = "feature/x"
    repo.remote.return_value.url = "git@github.com:owner/repo.git"
    repo.git.push.return_value = ""
    return repo


# ---------------------------------------------------------------------------
# delete=True — happy path
# ---------------------------------------------------------------------------


def test_delete_remote_branch_calls_push_with_delete_flag(
    mock_repo: MagicMock,
) -> None:
    result = git_push(mock_repo, branch="feature-branch", delete=True)

    mock_repo.git.push.assert_called_with("origin", "--delete", "feature-branch")
    assert result.startswith("✅")
    assert "feature-branch" in result


# ---------------------------------------------------------------------------
# delete=True — validation errors
# ---------------------------------------------------------------------------


def test_delete_with_force_raises_validation_error(mock_repo: MagicMock) -> None:
    result = git_push(mock_repo, branch="feature-branch", delete=True, force=True)

    assert result.startswith("❌")
    assert "force" in result
    mock_repo.git.push.assert_not_called()


def test_delete_with_force_with_lease_raises_validation_error(
    mock_repo: MagicMock,
) -> None:
    result = git_push(
        mock_repo, branch="feature-branch", delete=True, force_with_lease=True
    )

    assert result.startswith("❌")
    assert "force" in result
    mock_repo.git.push.assert_not_called()


def test_delete_without_branch_raises_validation_error(mock_repo: MagicMock) -> None:
    result = git_push(mock_repo, delete=True)

    assert result.startswith("❌")
    assert "branch" in result
    mock_repo.git.push.assert_not_called()


def test_delete_with_set_upstream_raises_validation_error(
    mock_repo: MagicMock,
) -> None:
    result = git_push(
        mock_repo, branch="feature-branch", delete=True, set_upstream=True
    )

    assert result.startswith("❌")
    mock_repo.git.push.assert_not_called()


def test_delete_with_refspec_raises_validation_error(mock_repo: MagicMock) -> None:
    result = git_push(
        mock_repo, branch="feature-branch", delete=True, refspec=":feature-branch"
    )

    assert result.startswith("❌")
    mock_repo.git.push.assert_not_called()


# ---------------------------------------------------------------------------
# refspec form — happy path
# ---------------------------------------------------------------------------


def test_refspec_form_calls_push_with_raw_refspec(mock_repo: MagicMock) -> None:
    result = git_push(mock_repo, refspec="src:dst")

    mock_repo.git.push.assert_called_with("origin", "src:dst")
    assert result.startswith("✅")
    assert "src:dst" in result


def test_refspec_delete_colon_form_calls_push(mock_repo: MagicMock) -> None:
    result = git_push(mock_repo, refspec=":old-branch")

    mock_repo.git.push.assert_called_with("origin", ":old-branch")
    assert result.startswith("✅")


# ---------------------------------------------------------------------------
# refspec — validation errors
# ---------------------------------------------------------------------------


def test_refspec_with_branch_raises_validation_error(mock_repo: MagicMock) -> None:
    result = git_push(mock_repo, branch="feature-branch", refspec="src:dst")

    assert result.startswith("❌")
    assert "branch" in result
    mock_repo.git.push.assert_not_called()


def test_refspec_with_set_upstream_raises_validation_error(
    mock_repo: MagicMock,
) -> None:
    result = git_push(mock_repo, refspec="src:dst", set_upstream=True)

    assert result.startswith("❌")
    mock_repo.git.push.assert_not_called()


# ---------------------------------------------------------------------------
# Pydantic model validator — matches handler behaviour
# ---------------------------------------------------------------------------


def test_model_delete_requires_branch() -> None:
    with pytest.raises(ValueError, match="branch"):
        GitPush(repo_path="/repo", delete=True)


def test_model_delete_with_force_raises() -> None:
    with pytest.raises(ValueError, match="force"):
        GitPush(repo_path="/repo", branch="feat", delete=True, force=True)


def test_model_refspec_with_branch_raises() -> None:
    with pytest.raises(ValueError, match="branch"):
        GitPush(repo_path="/repo", branch="feat", refspec="src:dst")


def test_model_refspec_with_set_upstream_raises() -> None:
    with pytest.raises(ValueError, match="set_upstream"):
        GitPush(repo_path="/repo", refspec="src:dst", set_upstream=True)


def test_model_valid_delete() -> None:
    model = GitPush(repo_path="/repo", branch="feat", delete=True)
    assert model.delete is True
    assert model.branch == "feat"


def test_model_valid_refspec() -> None:
    model = GitPush(repo_path="/repo", refspec="src:dst")
    assert model.refspec == "src:dst"


# ---------------------------------------------------------------------------
# dry_run=True — all push modes (issue #176)
# ---------------------------------------------------------------------------


class TestGitPushDryRun:
    def test_dry_run_false_does_not_append_flag(self, mock_repo: MagicMock) -> None:
        git_push(mock_repo, branch="feature", dry_run=False)

        mock_repo.git.push.assert_called_with("origin", "feature")

    def test_dry_run_with_normal_push_appends_flag(self, mock_repo: MagicMock) -> None:
        git_push(mock_repo, branch="feature", dry_run=True)

        mock_repo.git.push.assert_called_with("origin", "feature", "--dry-run")

    def test_dry_run_with_delete_appends_flag(self, mock_repo: MagicMock) -> None:
        git_push(mock_repo, branch="feature", delete=True, dry_run=True)

        mock_repo.git.push.assert_called_with("origin", "--delete", "feature", "--dry-run")

    def test_dry_run_with_refspec_appends_flag(self, mock_repo: MagicMock) -> None:
        git_push(mock_repo, refspec=":feature", dry_run=True)

        mock_repo.git.push.assert_called_with("origin", ":feature", "--dry-run")

    def test_dry_run_with_force_appends_flag(self, mock_repo: MagicMock) -> None:
        git_push(mock_repo, branch="feature", force=True, dry_run=True)

        call_args = mock_repo.git.push.call_args
        args = call_args.args
        assert "--force" in args
        assert "--dry-run" in args

    def test_dry_run_return_message_indicates_no_state_change(
        self, mock_repo: MagicMock
    ) -> None:
        result = git_push(mock_repo, branch="feature", dry_run=True)

        assert "dry-run" in result

    def test_dry_run_delete_return_message_indicates_no_state_change(
        self, mock_repo: MagicMock
    ) -> None:
        result = git_push(mock_repo, branch="feature", delete=True, dry_run=True)

        assert "dry-run" in result

    def test_dry_run_refspec_return_message_indicates_no_state_change(
        self, mock_repo: MagicMock
    ) -> None:
        result = git_push(mock_repo, refspec=":feature", dry_run=True)

        assert "dry-run" in result

    def test_model_dry_run_field_defaults_false(self) -> None:
        model = GitPush(repo_path="/repo", branch="feature")
        assert model.dry_run is False

    def test_model_dry_run_compatible_with_delete(self) -> None:
        model = GitPush(repo_path="/repo", branch="feature", delete=True, dry_run=True)
        assert model.dry_run is True
        assert model.delete is True

    def test_model_dry_run_compatible_with_refspec(self) -> None:
        model = GitPush(repo_path="/repo", refspec=":feature", dry_run=True)
        assert model.dry_run is True
        assert model.refspec == ":feature"
