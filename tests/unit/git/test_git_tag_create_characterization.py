"""Characterization tests pinning every branch of git_tag_create (issue #255).

Real temporary repositories check the exact message strings; a mock repo is
used only to pin the argv order and to reach the unexpected-exception branch.
"""

from unittest.mock import MagicMock

import pytest

from mcp_server_git.git._tag_ops import git_tag_create
from mcp_server_git.utils.tool_failure import ToolFailure

pytest.importorskip("git")
from git import Repo  # noqa: E402


@pytest.fixture
def repo(tmp_path):
    r = Repo.init(tmp_path)
    with r.config_writer() as cw:
        cw.set_value("user", "name", "T")
        cw.set_value("user", "email", "t@example.com")
        cw.set_value("commit", "gpgsign", "false")
    (tmp_path / "m.txt").write_text("v1\n")
    r.git.add("m.txt")
    r.git.commit("-m", "init")
    return r


@pytest.fixture(autouse=True)
def _no_env_key(monkeypatch):
    monkeypatch.delenv("GPG_SIGNING_KEY", raising=False)


def test_git_tag_create_returns_invalid_chars_when_tag_name_dangerous(repo):
    result = git_tag_create(repo, "v1;rm")
    assert result == "❌ Invalid characters detected in tag_name: 'v1;rm'"
    assert isinstance(result, ToolFailure)


def test_git_tag_create_returns_invalid_chars_when_commit_ish_dangerous(repo):
    result = git_tag_create(repo, "v1", commit_ish="HEAD|x")
    assert result == "❌ Invalid characters detected in commit_ish: 'HEAD|x'"
    assert isinstance(result, ToolFailure)


def test_git_tag_create_returns_invalid_chars_when_legacy_commit_dangerous(repo):
    result = git_tag_create(repo, "v1", commit="HEAD&x")
    assert result == "❌ Invalid characters detected in commit_ish: 'HEAD&x'"
    assert isinstance(result, ToolFailure)


def test_git_tag_create_returns_success_when_lightweight_tag(repo):
    result = git_tag_create(repo, "v1")
    assert result == "✅ Successfully created tag 'v1'"
    assert not isinstance(result, ToolFailure)
    assert repo.git.cat_file("-t", "v1") == "commit"


def test_git_tag_create_returns_success_with_target_when_commit_ish_given(repo):
    result = git_tag_create(repo, "v1", commit_ish="HEAD")
    assert result == "✅ Successfully created tag 'v1' on HEAD"
    assert not isinstance(result, ToolFailure)


def test_git_tag_create_returns_success_with_target_when_legacy_commit_given(repo):
    result = git_tag_create(repo, "v1", commit="HEAD")
    assert result == "✅ Successfully created tag 'v1' on HEAD"


def test_git_tag_create_prefers_commit_ish_when_both_target_args_given(repo):
    result = git_tag_create(repo, "v1", commit_ish="HEAD", commit="nope")
    assert result == "✅ Successfully created tag 'v1' on HEAD"


def test_git_tag_create_creates_annotated_tag_when_annotate_true(repo):
    result = git_tag_create(repo, "v1", annotate=True)
    assert result == "✅ Successfully created tag 'v1'"
    assert repo.git.cat_file("-t", "v1") == "tag"
    assert repo.git.tag("-n1", "v1").split(None, 1)[1] == "v1"


def test_git_tag_create_creates_annotated_tag_when_message_given(repo):
    result = git_tag_create(repo, "v1", message="release notes")
    assert result == "✅ Successfully created tag 'v1'"
    assert repo.git.cat_file("-t", "v1") == "tag"
    assert repo.git.tag("-n1", "v1").split(None, 1)[1] == "release notes"


def test_git_tag_create_returns_failure_when_tag_exists_without_force(repo):
    git_tag_create(repo, "v1")
    result = git_tag_create(repo, "v1")
    assert result.startswith("❌ Tag create failed: ")
    assert "already exists" in result
    assert isinstance(result, ToolFailure)


def test_git_tag_create_replaces_tag_when_force_true(repo):
    git_tag_create(repo, "v1")
    result = git_tag_create(repo, "v1", force=True)
    assert result == "✅ Successfully created tag 'v1'"
    assert not isinstance(result, ToolFailure)


def test_git_tag_create_returns_key_error_when_sign_without_any_key():
    # A mock repo keeps the host's global user.signingkey out of the picture.
    repo = MagicMock()
    repo.config_reader.return_value.get_value.side_effect = KeyError("signingkey")
    result = git_tag_create(repo, "v1", sign=True)
    assert result == (
        "❌ Could not determine GPG signing key. "
        "Please configure GPG_SIGNING_KEY env var"
    )
    assert isinstance(result, ToolFailure)


def test_git_tag_create_returns_failure_when_signing_key_unusable(repo):
    result = git_tag_create(repo, "v1", sign=True, gpg_key_id="NOSUCHKEY")
    assert result.startswith("❌ Tag create failed: ")
    assert isinstance(result, ToolFailure)


def test_git_tag_create_passes_lightweight_argv_when_no_message_or_flags():
    repo = MagicMock()
    git_tag_create(repo, "v1")
    repo.git.tag.assert_called_once_with("v1")


def test_git_tag_create_passes_force_annotate_message_target_in_order():
    repo = MagicMock()
    git_tag_create(repo, "v1", commit_ish="HEAD", message="m", force=True)
    repo.git.tag.assert_called_once_with("-f", "-a", "-m", "m", "v1", "HEAD")


def test_git_tag_create_defaults_message_to_tag_name_when_annotate_without_message():
    repo = MagicMock()
    git_tag_create(repo, "v1", annotate=True)
    repo.git.tag.assert_called_once_with("-a", "-m", "v1", "v1")


def test_git_tag_create_uses_explicit_key_when_sign_with_gpg_key_id():
    repo = MagicMock()
    git_tag_create(repo, "v1", sign=True, gpg_key_id="KEY", force=True)
    repo.git.tag.assert_called_once_with("-f", "-u", "KEY", "-m", "v1", "v1")


def test_git_tag_create_uses_env_key_when_sign_without_explicit_key(monkeypatch):
    monkeypatch.setenv("GPG_SIGNING_KEY", "ENVKEY")
    repo = MagicMock()
    git_tag_create(repo, "v1", sign=True, message="m")
    repo.git.tag.assert_called_once_with("-u", "ENVKEY", "-m", "m", "v1")


def test_git_tag_create_uses_config_key_when_sign_without_env_key():
    repo = MagicMock()
    repo.config_reader.return_value.get_value.return_value = "CFGKEY"
    git_tag_create(repo, "v1", sign=True, message="m")
    repo.git.tag.assert_called_once_with("-u", "CFGKEY", "-m", "m", "v1")


def test_git_tag_create_returns_error_when_unexpected_exception_raised():
    repo = MagicMock()
    repo.git.tag.side_effect = RuntimeError("boom")
    result = git_tag_create(repo, "v1")
    assert result == "❌ Tag create error: boom"
    assert isinstance(result, ToolFailure)
