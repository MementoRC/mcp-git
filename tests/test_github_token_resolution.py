"""Regression tests for resolve_github_token env isolation (#340)."""

import os
from pathlib import Path

import git
import pytest

from mcp_server_git.git import _github_token
from mcp_server_git.git._github_token import resolve_github_token

REPO_TOKEN = "repo-token-bbbbbbbbbb"
PROCESS_TOKEN = "env-token-aaaaaaaaaa"


def _make_repo(path: Path, env_text: str | None = None) -> git.Repo:
    path.mkdir()
    repo = git.Repo.init(path)
    if env_text is not None:
        (path / ".env").write_text(env_text)
    return repo


def test_resolve_github_token_returns_dotenv_token_when_repo_has_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    repo = _make_repo(tmp_path / "repo", f"GITHUB_TOKEN={REPO_TOKEN}\n")

    assert resolve_github_token(repo) == (REPO_TOKEN, ".env")


def test_resolve_github_token_leaves_process_env_unchanged_when_repo_has_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GPG_SIGNING_KEY", raising=False)
    repo = _make_repo(
        tmp_path / "repo",
        f"GITHUB_TOKEN={REPO_TOKEN}\nGPG_SIGNING_KEY=ABCDEF1234567890\n",
    )

    resolve_github_token(repo)

    assert "GITHUB_TOKEN" not in os.environ
    assert "GPG_SIGNING_KEY" not in os.environ


def test_resolve_github_token_returns_process_token_when_other_repo_had_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", PROCESS_TOKEN)
    monkeypatch.setattr(_github_token, "_get_github_token_from_cli", lambda: None)
    repo_a = _make_repo(tmp_path / "a", f"GITHUB_TOKEN={REPO_TOKEN}\n")
    repo_b = _make_repo(tmp_path / "b")

    assert resolve_github_token(repo_a) == (REPO_TOKEN, ".env")
    assert resolve_github_token(repo_b) == (PROCESS_TOKEN, "env")
