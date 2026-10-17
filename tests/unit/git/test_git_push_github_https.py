"""
Characterization tests for git_push on GitHub HTTPS remotes (issue #255).

These paths need a credential/network boundary, so the repo is a mock and the
only patched collaborator is ``subprocess.run`` (used for both ``gh auth
token`` and the system-git fallback). The token source is driven through the
``GITHUB_TOKEN`` environment variable. A token push goes through
``repo.git(c=[...]).push(...)`` (the per-call credential helper, #303), which
on the mock is ``repo.git.return_value.push``.
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from git.exc import GitCommandError

from mcp_server_git.git._push_auth import TOKEN_ENV_VAR
from mcp_server_git.git.operations import git_push

URL = "https://github.com/owner/repo.git"
NO_TOKEN_DEBUG = "GITHUB_TOKEN: NOT SET"


@pytest.fixture()
def https_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    repo = MagicMock()
    repo.working_dir = str(tmp_path)
    repo.active_branch.name = "main"
    repo.remote.return_value.url = URL
    repo.git.push.return_value = ""
    return repo


def _run_result(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


def _fallback_run(git_result: MagicMock | Exception):
    """subprocess.run stub: `gh auth token` yields no token, git push -> result."""

    def run(cmd: list[str], **_: object) -> MagicMock:
        if cmd[0] == "gh":
            return _run_result(returncode=1)
        if isinstance(git_result, Exception):
            raise git_result
        return git_result

    return run


def test_git_push_returns_token_auth_success_when_github_token_set(
    https_repo: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "tok1234567890")

    result = git_push(https_repo, set_upstream=True, dry_run=True)

    assert result == (
        "✅ Successfully pushed main to origin (set upstream tracking)"
        " (dry-run; no remote state modified)"
        "\n🔐 Used server GitHub token (GITHUB_TOKEN environment variable)"
    )
    push = https_repo.git.return_value.push
    assert push.call_args.args == ("--set-upstream", "origin", "main", "--dry-run")
    assert push.call_args.kwargs["env"][TOKEN_ENV_VAR] == "tok1234567890"
    https_repo.remote.return_value.set_url.assert_not_called()


def test_git_push_returns_cli_auth_success_when_only_gh_cli_has_token(
    https_repo: MagicMock,
) -> None:
    with patch("subprocess.run", return_value=_run_result(stdout="cli-token-123456\n")):
        result = git_push(https_repo)

    assert result == (
        "✅ Successfully pushed main to origin"
        "\n🔐 Used server GitHub token (GitHub CLI gh auth token)"
    )


def test_git_push_returns_outer_auth_error_without_token_text_when_token_push_fails(
    https_repo: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "tok1234567890")
    https_repo.git.return_value.push.side_effect = GitCommandError(
        "push", 1, stderr="Authentication failed"
    )

    result = git_push(https_repo)

    assert result.startswith(
        "❌ Authentication failed. Configure GITHUB_TOKEN environment variable "
        "or GitHub CLI authentication (gh auth login)\n"
        "🔍 DEBUG [OUTER_EXCEPTION]: GITHUB_TOKEN: SET (length=13), "
    )
    assert result.endswith("🔍 Outer GitPython error: Authentication failed")
    assert "tok1" not in result
    https_repo.remote.return_value.set_url.assert_not_called()


def test_git_push_returns_outer_auth_error_without_env_token_when_cli_token_push_fails(
    https_repo: MagicMock,
) -> None:
    https_repo.git.return_value.push.side_effect = GitCommandError(
        "push", 1, stderr="HTTP 401"
    )

    with patch("subprocess.run", return_value=_run_result(stdout="cli-token-123456\n")):
        result = git_push(https_repo)

    assert "DEBUG [OUTER_EXCEPTION]: GITHUB_TOKEN: NOT SET, " in result
    assert result.endswith("🔍 Outer GitPython error: HTTP 401")


def test_git_push_returns_exit_code_failure_when_ssh_github_push_reports_401(
    https_repo: MagicMock,
) -> None:
    https_repo.remote.return_value.url = "git@github.com:owner/repo.git"
    https_repo.git.push.side_effect = GitCommandError("push", 1, stderr="HTTP 401")

    result = git_push(https_repo)

    assert result == "❌ Push failed (exit 1): HTTP 401"


def test_git_push_returns_permission_denied_when_error_mentions_403(
    https_repo: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "tok1234567890")
    https_repo.git.return_value.push.side_effect = GitCommandError(
        "push", 1, stderr="error 403"
    )

    result = git_push(https_repo)

    assert result == "❌ Permission denied. Check repository access permissions"


def test_git_push_returns_rejected_hint_when_token_push_non_fast_forward(
    https_repo: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "tok1234567890")
    https_repo.git.return_value.push.side_effect = GitCommandError(
        "push", 1, stderr="! [rejected] (non-fast-forward)"
    )

    result = git_push(https_repo, force_with_lease=True)

    assert result.startswith(
        "❌ Push rejected (non-fast-forward) even though force_with_lease=True. "
    )


def test_git_push_returns_exit_code_failure_when_token_push_fails_otherwise(
    https_repo: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "tok1234567890")
    https_repo.git.return_value.push.side_effect = GitCommandError(
        "push", 7, stderr="boom"
    )

    result = git_push(https_repo)

    assert result == "❌ Push failed (exit 7): boom"


def test_git_push_returns_push_error_when_unexpected_exception_raised(
    https_repo: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "tok1234567890")
    https_repo.git.return_value.push.side_effect = RuntimeError("kaboom")

    result = git_push(https_repo)

    assert result == "❌ Push error: kaboom"


def test_git_push_returns_system_git_success_when_no_token_available(
    https_repo: MagicMock,
) -> None:
    with patch("subprocess.run", side_effect=_fallback_run(_run_result())) as run:
        result = git_push(https_repo, set_upstream=True, dry_run=True)

    assert result == (
        "✅ Successfully pushed main to origin (set upstream tracking)"
        " (dry-run; no remote state modified)\n🔐 Used system git authentication"
    )
    assert run.call_args.args[0] == [
        "git",
        "push",
        "--set-upstream",
        "origin",
        "main",
        "--dry-run",
    ]
    https_repo.git.push.assert_not_called()


def test_git_push_returns_auth_failure_debug_when_system_git_reports_401(
    https_repo: MagicMock,
) -> None:
    failed = _run_result(returncode=1, stderr="fatal: Authentication failed\n")

    with patch("subprocess.run", side_effect=_fallback_run(failed)):
        result = git_push(https_repo)

    assert result.startswith(
        "❌ Authentication failed. Configure GITHUB_TOKEN environment variable "
        "or GitHub CLI authentication (gh auth login)\n"
        f"🔍 DEBUG: {NO_TOKEN_DEBUG}, .env exists: False, working_dir: "
    )
    assert result.endswith("\n🔍 System git error: fatal: Authentication failed")


def test_git_push_returns_permission_denied_when_system_git_reports_denied(
    https_repo: MagicMock,
) -> None:
    failed = _run_result(returncode=1, stderr="Permission denied")

    with patch("subprocess.run", side_effect=_fallback_run(failed)):
        result = git_push(https_repo)

    assert result == "❌ Permission denied. Check repository access permissions"


def test_git_push_returns_rejected_hint_when_system_git_non_fast_forward(
    https_repo: MagicMock,
) -> None:
    failed = _run_result(returncode=1, stderr="rejected non-fast-forward")

    with patch("subprocess.run", side_effect=_fallback_run(failed)):
        result = git_push(https_repo, force=True)

    assert result.startswith(
        "❌ Push rejected (non-fast-forward) even though force=True. "
    )


def test_git_push_returns_failure_text_when_system_git_fails_otherwise(
    https_repo: MagicMock,
) -> None:
    failed = _run_result(returncode=1, stderr="  something broke \n")

    with patch("subprocess.run", side_effect=_fallback_run(failed)):
        result = git_push(https_repo)

    assert result == "❌ Push failed: something broke"


def test_git_push_returns_timeout_message_when_system_git_times_out(
    https_repo: MagicMock,
) -> None:
    timeout = subprocess.TimeoutExpired("git", 300)

    with patch("subprocess.run", side_effect=_fallback_run(timeout)):
        result = git_push(https_repo)

    assert result == (
        "❌ Push operation timed out. Check network connection and repository access"
    )


def test_git_push_returns_system_git_error_when_subprocess_raises(
    https_repo: MagicMock,
) -> None:
    with patch("subprocess.run", side_effect=_fallback_run(OSError("no git"))):
        result = git_push(https_repo)

    assert result == "❌ System git push failed: no git"
