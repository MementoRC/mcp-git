"""
Unit tests for git_tag_delete operation.

Real-repo fixtures are used for behavioural assertions (see conftest.py);
Mock is used only for error-injection paths.
"""

from unittest.mock import Mock

import pytest

from mcp_server_git.git._tag_ops import git_tag_create, git_tag_delete
from mcp_server_git.utils.git_import import GitCommandError


class TestGitTagDeleteSuccess:
    """Behavioural tests against a real git repository."""

    def test_git_tag_delete_removes_existing_tag(self, real_repo):
        git_tag_create(real_repo, "v1.0.0")

        result = git_tag_delete(real_repo, "v1.0.0")

        assert "✅" in result
        assert "v1.0.0" in result
        assert "v1.0.0" not in [t.name for t in real_repo.tags]


class TestGitTagDeleteInputValidation:
    """Dangerous-character rejection for tag_name."""

    @pytest.mark.parametrize("dangerous_char", [";", "|", "&", "`", "$"])
    def test_git_tag_delete_rejects_dangerous_chars_in_tag_name(self, dangerous_char):
        mock_repo = Mock()
        malicious = f"v1{dangerous_char}rm -rf /"

        result = git_tag_delete(mock_repo, malicious)

        assert "❌" in result
        assert "Invalid characters detected in tag_name" in result
        mock_repo.git.tag.assert_not_called()


class TestGitTagDeleteErrorHandling:
    """Error handling: one real-repo natural failure, rest via Mock injection."""

    def test_git_tag_delete_returns_error_when_tag_not_found(self, real_repo):
        result = git_tag_delete(real_repo, "nonexistent")

        assert "❌" in result
        assert "Tag delete failed" in result

    def test_git_tag_delete_handles_git_command_error(self):
        mock_repo = Mock()
        mock_repo.git.tag.side_effect = GitCommandError(
            "git tag", 1, b"", b"error: tag 'v1.0.0' not found."
        )

        result = git_tag_delete(mock_repo, "v1.0.0")

        assert "❌" in result
        assert "Tag delete failed" in result

    def test_git_tag_delete_handles_generic_exception(self):
        mock_repo = Mock()
        mock_repo.git.tag.side_effect = Exception("Unexpected failure")

        result = git_tag_delete(mock_repo, "v1.0.0")

        assert "❌" in result
        assert "Tag delete error" in result
        assert "Unexpected failure" in result
