"""
Unit tests for git_commit allow_empty flag.

Tests verify:
- GitCommit model defaults allow_empty to False
- allow_empty=True adds --allow-empty to subprocess command
- allow_empty=False (default) does NOT add --allow-empty
"""

from unittest.mock import MagicMock, call, patch

import pytest

from mcp_server_git.git.models import GitCommit
from mcp_server_git.git.operations import git_commit


class TestGitCommitModel:
    """Tests for GitCommit pydantic model allow_empty field."""

    def test_allow_empty_defaults_to_false(self):
        """allow_empty field should default to False."""
        model = GitCommit(repo_path="/tmp/repo", message="test commit")
        assert model.allow_empty is False

    def test_allow_empty_can_be_set_to_true(self):
        """allow_empty field should accept True."""
        model = GitCommit(repo_path="/tmp/repo", message="test commit", allow_empty=True)
        assert model.allow_empty is True

    def test_allow_empty_field_description(self):
        """allow_empty field should have a meaningful description."""
        field_info = GitCommit.model_fields["allow_empty"]
        assert field_info.description is not None
        assert len(field_info.description) > 0


class TestGitCommitAllowEmpty:
    """Tests for allow_empty flag in git_commit operation."""

    def _make_mock_repo(self, key_id: str = "TESTKEY123") -> MagicMock:
        mock_repo = MagicMock()
        mock_repo.working_dir = "/tmp/test_repo"
        mock_repo.config_reader.return_value.get_value.return_value = key_id
        return mock_repo

    def _make_subprocess_results(self, commit_returncode: int = 0):
        """Return (commit_result, rev_parse_result) mocks."""
        commit_result = MagicMock()
        commit_result.returncode = commit_returncode
        commit_result.stdout = "1 file changed"
        commit_result.stderr = ""

        rev_parse_result = MagicMock()
        rev_parse_result.returncode = 0
        rev_parse_result.stdout = "abc12345\n"

        return commit_result, rev_parse_result

    @patch("mcp_server_git.git.operations.subprocess.run")
    @patch("mcp_server_git.git.security.enforce_secure_git_config")
    def test_allow_empty_true_adds_flag_to_command(
        self, mock_security, mock_run
    ):
        """allow_empty=True must add --allow-empty before --gpg-sign in cmd."""
        mock_security.return_value = "✅ secure"
        commit_result, rev_parse_result = self._make_subprocess_results()
        mock_run.side_effect = [commit_result, rev_parse_result]

        mock_repo = self._make_mock_repo()
        git_commit(mock_repo, message="empty commit", allow_empty=True)

        commit_call_args = mock_run.call_args_list[0]
        cmd = commit_call_args[0][0]
        assert "--allow-empty" in cmd

    @patch("mcp_server_git.git.operations.subprocess.run")
    @patch("mcp_server_git.git.security.enforce_secure_git_config")
    def test_allow_empty_false_does_not_add_flag(
        self, mock_security, mock_run
    ):
        """allow_empty=False (default) must NOT add --allow-empty to cmd."""
        mock_security.return_value = "✅ secure"
        commit_result, rev_parse_result = self._make_subprocess_results()
        mock_run.side_effect = [commit_result, rev_parse_result]

        mock_repo = self._make_mock_repo()
        git_commit(mock_repo, message="normal commit", allow_empty=False)

        commit_call_args = mock_run.call_args_list[0]
        cmd = commit_call_args[0][0]
        assert "--allow-empty" not in cmd

    @patch("mcp_server_git.git.operations.subprocess.run")
    @patch("mcp_server_git.git.security.enforce_secure_git_config")
    def test_allow_empty_default_does_not_add_flag(
        self, mock_security, mock_run
    ):
        """Calling git_commit without allow_empty must not add --allow-empty."""
        mock_security.return_value = "✅ secure"
        commit_result, rev_parse_result = self._make_subprocess_results()
        mock_run.side_effect = [commit_result, rev_parse_result]

        mock_repo = self._make_mock_repo()
        git_commit(mock_repo, message="default commit")

        commit_call_args = mock_run.call_args_list[0]
        cmd = commit_call_args[0][0]
        assert "--allow-empty" not in cmd

    @patch("mcp_server_git.git.operations.subprocess.run")
    @patch("mcp_server_git.git.security.enforce_secure_git_config")
    def test_allow_empty_flag_position_before_gpg_sign(
        self, mock_security, mock_run
    ):
        """--allow-empty must appear before --gpg-sign= in the command."""
        mock_security.return_value = "✅ secure"
        commit_result, rev_parse_result = self._make_subprocess_results()
        mock_run.side_effect = [commit_result, rev_parse_result]

        mock_repo = self._make_mock_repo()
        git_commit(mock_repo, message="empty commit", allow_empty=True)

        cmd = mock_run.call_args_list[0][0][0]
        allow_empty_idx = cmd.index("--allow-empty")
        gpg_idx = next(i for i, arg in enumerate(cmd) if arg.startswith("--gpg-sign="))
        assert allow_empty_idx < gpg_idx

    @patch("mcp_server_git.git.operations.subprocess.run")
    @patch("mcp_server_git.git.security.enforce_secure_git_config")
    def test_allow_empty_combined_with_amend(
        self, mock_security, mock_run
    ):
        """allow_empty=True and amend=True should both appear in command."""
        mock_security.return_value = "✅ secure"
        commit_result, rev_parse_result = self._make_subprocess_results()
        mock_run.side_effect = [commit_result, rev_parse_result]

        mock_repo = self._make_mock_repo()
        git_commit(mock_repo, message="amend empty", amend=True, allow_empty=True)

        cmd = mock_run.call_args_list[0][0][0]
        assert "--amend" in cmd
        assert "--allow-empty" in cmd
