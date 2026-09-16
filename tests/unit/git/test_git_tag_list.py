"""
Unit tests for git_tag_list operation.

Real-repo fixtures are used for behavioural assertions (see conftest.py);
Mock is used only for error-injection paths.
"""

from pathlib import Path
from unittest.mock import Mock

import pytest

from mcp_server_git.git._tag_ops import git_tag_create, git_tag_list
from mcp_server_git.utils.git_import import GitCommandError


def _commit_file(repo, name: str, content: str) -> str:
    """Add a second commit to `repo` and return its full SHA."""
    path = Path(repo.working_dir) / name
    path.write_text(content)
    repo.index.add([name])
    repo.index.commit(f"add {name}")
    return repo.head.commit.hexsha


class TestGitTagListSuccess:
    """Behavioural tests against a real git repository."""

    def test_git_tag_list_returns_no_tags_found_when_empty(self, real_repo):
        result = git_tag_list(real_repo)

        assert result == "No tags found"

    def test_git_tag_list_returns_created_tags(self, real_repo):
        git_tag_create(real_repo, "v1.0.0")
        git_tag_create(real_repo, "v1.1.0")

        result = git_tag_list(real_repo)

        assert "Tags:" in result
        assert "v1.0.0" in result
        assert "v1.1.0" in result

    def test_git_tag_list_pattern_filters_matching_tags(self, real_repo):
        git_tag_create(real_repo, "v1.0.0")
        git_tag_create(real_repo, "beta-1")

        result = git_tag_list(real_repo, pattern="v*")

        assert "v1.0.0" in result
        assert "beta-1" not in result

    def test_git_tag_list_points_at_filters_by_commit(self, real_repo):
        first_sha = real_repo.head.commit.hexsha
        second_sha = _commit_file(real_repo, "file.txt", "data")
        git_tag_create(real_repo, "at-first", commit_ish=first_sha)
        git_tag_create(real_repo, "at-second", commit_ish=second_sha)

        result = git_tag_list(real_repo, points_at=first_sha)

        assert "at-first" in result
        assert "at-second" not in result


class TestGitTagListInputValidation:
    """Dangerous-character rejection for pattern and points_at."""

    @pytest.mark.parametrize("dangerous_char", [";", "|", "&", "`", "$"])
    def test_git_tag_list_rejects_dangerous_chars_in_pattern(self, dangerous_char):
        mock_repo = Mock()
        malicious = f"v1{dangerous_char}rm -rf /"

        result = git_tag_list(mock_repo, pattern=malicious)

        assert "❌" in result
        assert "Invalid characters detected in pattern" in result
        mock_repo.git.tag.assert_not_called()

    @pytest.mark.parametrize("dangerous_char", [";", "|", "&", "`", "$"])
    def test_git_tag_list_rejects_dangerous_chars_in_points_at(self, dangerous_char):
        mock_repo = Mock()
        malicious = f"HEAD{dangerous_char}rm -rf /"

        result = git_tag_list(mock_repo, points_at=malicious)

        assert "❌" in result
        assert "Invalid characters detected in points_at" in result
        mock_repo.git.tag.assert_not_called()


class TestGitTagListErrorHandling:
    """Error handling via Mock injection."""

    def test_git_tag_list_handles_git_command_error(self):
        mock_repo = Mock()
        mock_repo.git.tag.side_effect = GitCommandError(
            "git tag", 1, b"", b"fatal: not a git repository"
        )

        result = git_tag_list(mock_repo)

        assert "❌" in result
        assert "Tag list failed" in result

    def test_git_tag_list_handles_generic_exception(self):
        mock_repo = Mock()
        mock_repo.git.tag.side_effect = Exception("Unexpected failure")

        result = git_tag_list(mock_repo)

        assert "❌" in result
        assert "Tag list error" in result
        assert "Unexpected failure" in result
