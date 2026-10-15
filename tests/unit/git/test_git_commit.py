"""
Unit tests for git_commit allow_empty flag.

Tests verify:
- GitCommit model defaults allow_empty to False
- allow_empty=True adds --allow-empty to subprocess command
- allow_empty=False (default) does NOT add --allow-empty
"""

from unittest.mock import MagicMock, patch

from mcp_server_git.git._commit_runner import CommitProcessResult
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
        model = GitCommit(
            repo_path="/tmp/repo", message="test commit", allow_empty=True
        )
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

    def _commit_cmd(self, **kwargs) -> list[str]:
        """Run git_commit with the commit process mocked; return its argv."""
        rev_parse_result = MagicMock(returncode=0, stdout="abc12345\n")
        ok = CommitProcessResult(0, "1 file changed", "")
        with (
            patch(
                "mcp_server_git.git._commit_ops.run_commit_process", return_value=ok
            ) as mock_commit,
            patch(
                "mcp_server_git.git._commit_ops.subprocess.run",
                return_value=rev_parse_result,
            ),
            patch(
                "mcp_server_git.git.security.enforce_secure_git_config",
                return_value="✅ secure",
            ),
        ):
            git_commit(self._make_mock_repo(), **kwargs)
        return mock_commit.call_args[0][0]

    def test_allow_empty_true_adds_flag_to_command(self):
        """allow_empty=True must add --allow-empty before --gpg-sign in cmd."""
        cmd = self._commit_cmd(message="empty commit", allow_empty=True)
        assert "--allow-empty" in cmd

    def test_allow_empty_false_does_not_add_flag(self):
        """allow_empty=False (default) must NOT add --allow-empty to cmd."""
        cmd = self._commit_cmd(message="normal commit", allow_empty=False)
        assert "--allow-empty" not in cmd

    def test_allow_empty_default_does_not_add_flag(self):
        """Calling git_commit without allow_empty must not add --allow-empty."""
        cmd = self._commit_cmd(message="default commit")
        assert "--allow-empty" not in cmd

    def test_allow_empty_flag_position_before_gpg_sign(self):
        """--allow-empty must appear before --gpg-sign= in the command."""
        cmd = self._commit_cmd(message="empty commit", allow_empty=True)
        allow_empty_idx = cmd.index("--allow-empty")
        gpg_idx = next(i for i, arg in enumerate(cmd) if arg.startswith("--gpg-sign="))
        assert allow_empty_idx < gpg_idx

    def test_allow_empty_combined_with_amend(self):
        """allow_empty=True and amend=True should both appear in command."""
        cmd = self._commit_cmd(message="amend empty", amend=True, allow_empty=True)
        assert "--amend" in cmd
        assert "--allow-empty" in cmd
