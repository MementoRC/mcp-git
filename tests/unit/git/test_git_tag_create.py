"""
Unit tests for git_tag_create operation.

Real-repo fixtures are used for behavioural assertions (see conftest.py);
Mock is used only for error-injection and for asserting the exact argv
passed to `repo.git.tag` in the GPG-signing case (no real GPG signatures
are created in tests).
"""

from pathlib import Path
from unittest.mock import Mock

import pytest

from mcp_server_git.git._tag_ops import git_tag_create
from mcp_server_git.utils.git_import import GitCommandError


def _commit_file(repo, name: str, content: str) -> str:
    """Add a second commit to `repo` and return its full SHA."""
    path = Path(repo.working_dir) / name
    path.write_text(content)
    repo.index.add([name])
    repo.index.commit(f"add {name}")
    return repo.head.commit.hexsha


class TestGitTagCreateSuccess:
    """Behavioural tests against a real git repository."""

    def test_git_tag_create_lightweight_tag_has_no_annotation(self, real_repo):
        result = git_tag_create(real_repo, "v1.0.0")

        assert "✅" in result
        assert "v1.0.0" in result
        assert "v1.0.0" in [t.name for t in real_repo.tags]
        assert real_repo.tags["v1.0.0"].tag is None

    def test_git_tag_create_with_message_creates_annotated_tag(self, real_repo):
        result = git_tag_create(real_repo, "v1.1.0", message="Release 1.1.0")

        assert "✅" in result
        assert real_repo.tags["v1.1.0"].tag is not None
        assert real_repo.tags["v1.1.0"].tag.message == "Release 1.1.0"

    def test_git_tag_create_annotate_without_message_defaults_to_tag_name(
        self, real_repo
    ):
        result = git_tag_create(real_repo, "v1.2.0", annotate=True)

        assert "✅" in result
        assert real_repo.tags["v1.2.0"].tag is not None
        assert real_repo.tags["v1.2.0"].tag.message == "v1.2.0"

    def test_git_tag_create_commit_ish_targets_specified_commit(self, real_repo):
        first_sha = real_repo.head.commit.hexsha
        _commit_file(real_repo, "file.txt", "data")

        result = git_tag_create(real_repo, "v-old", commit_ish=first_sha)

        assert "✅" in result
        assert first_sha in result
        assert real_repo.tags["v-old"].commit.hexsha == first_sha

    def test_git_tag_create_deprecated_commit_alias_still_works(self, real_repo):
        first_sha = real_repo.head.commit.hexsha
        _commit_file(real_repo, "file.txt", "data")

        result = git_tag_create(real_repo, "v-alias", commit=first_sha)

        assert "✅" in result
        assert real_repo.tags["v-alias"].commit.hexsha == first_sha

    def test_git_tag_create_commit_ish_wins_over_deprecated_commit_alias(
        self, real_repo
    ):
        first_sha = real_repo.head.commit.hexsha
        second_sha = _commit_file(real_repo, "file.txt", "data")

        result = git_tag_create(
            real_repo, "v-both", commit_ish=second_sha, commit=first_sha
        )

        assert "✅" in result
        assert real_repo.tags["v-both"].commit.hexsha == second_sha

    def test_git_tag_create_force_replaces_existing_tag(self, real_repo):
        git_tag_create(real_repo, "v-force")
        second_sha = _commit_file(real_repo, "file.txt", "data")

        result = git_tag_create(real_repo, "v-force", commit_ish=second_sha, force=True)

        assert "✅" in result
        assert real_repo.tags["v-force"].commit.hexsha == second_sha


class TestGitTagCreateInputValidation:
    """Dangerous-character rejection for tag_name and commit_ish."""

    @pytest.mark.parametrize("dangerous_char", [";", "|", "&", "`", "$"])
    def test_git_tag_create_rejects_dangerous_chars_in_tag_name(self, dangerous_char):
        mock_repo = Mock()
        malicious = f"v1{dangerous_char}rm -rf /"

        result = git_tag_create(mock_repo, malicious)

        assert "❌" in result
        assert "Invalid characters detected in tag_name" in result
        mock_repo.git.tag.assert_not_called()

    @pytest.mark.parametrize("dangerous_char", [";", "|", "&", "`", "$"])
    def test_git_tag_create_rejects_dangerous_chars_in_commit_ish(self, dangerous_char):
        mock_repo = Mock()
        malicious = f"HEAD{dangerous_char}rm -rf /"

        result = git_tag_create(mock_repo, "v1.0.0", commit_ish=malicious)

        assert "❌" in result
        assert "Invalid characters detected in commit_ish" in result
        mock_repo.git.tag.assert_not_called()


class TestGitTagCreateSigning:
    """GPG-signing argv assertions via Mock — no real signatures are created."""

    def test_git_tag_create_sign_with_gpg_key_id_passes_dash_u_and_key(self):
        mock_repo = Mock()

        result = git_tag_create(mock_repo, "v1.0.0", sign=True, gpg_key_id="ABC123")

        assert "✅" in result
        mock_repo.git.tag.assert_called_once_with(
            "-u", "ABC123", "-m", "v1.0.0", "v1.0.0"
        )

    def test_git_tag_create_sign_without_resolvable_key_returns_error(
        self, monkeypatch
    ):
        monkeypatch.delenv("GPG_SIGNING_KEY", raising=False)
        mock_repo = Mock()
        mock_repo.config_reader.return_value.get_value.side_effect = Exception(
            "no signingkey configured"
        )

        result = git_tag_create(mock_repo, "v1.0.0", sign=True)

        assert "❌" in result
        assert "Could not determine GPG signing key" in result
        mock_repo.git.tag.assert_not_called()


class TestGitTagCreateErrorHandling:
    """Error handling: one real-repo natural failure, rest via Mock injection."""

    def test_git_tag_create_returns_error_when_tag_already_exists(self, real_repo):
        git_tag_create(real_repo, "v1.0.0")

        result = git_tag_create(real_repo, "v1.0.0")

        assert "❌" in result
        assert "Tag create failed" in result

    def test_git_tag_create_handles_git_command_error(self):
        mock_repo = Mock()
        mock_repo.git.tag.side_effect = GitCommandError(
            "git tag", 1, b"", b"fatal: tag already exists"
        )

        result = git_tag_create(mock_repo, "v1.0.0")

        assert "❌" in result
        assert "Tag create failed" in result

    def test_git_tag_create_handles_generic_exception(self):
        mock_repo = Mock()
        mock_repo.git.tag.side_effect = Exception("Unexpected failure")

        result = git_tag_create(mock_repo, "v1.0.0")

        assert "❌" in result
        assert "Tag create error" in result
        assert "Unexpected failure" in result
