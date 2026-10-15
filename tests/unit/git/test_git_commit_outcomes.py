"""Characterization tests pinning git_commit's outcome messages (issue #255)."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from mcp_server_git.git._commit_ops import git_commit
from mcp_server_git.git._commit_runner import CommitProcessResult, CommitTimeoutError
from mcp_server_git.utils.git_import import GitCommandError
from mcp_server_git.utils.tool_failure import ToolFailure

_RUN = "mcp_server_git.git._commit_ops.run_commit_process"
_SUBPROCESS = "mcp_server_git.git._commit_ops.subprocess.run"
_SECURITY = "mcp_server_git.git.security.enforce_secure_git_config"


def _repo() -> MagicMock:
    repo = MagicMock()
    repo.working_dir = "/tmp/test_repo"
    return repo


def _rev_parse(returncode: int = 0, stdout: str = "0123456789abcdef\n") -> MagicMock:
    return MagicMock(
        spec=subprocess.CompletedProcess, returncode=returncode, stdout=stdout
    )


def _commit(security: str = "✅ secure", run=None, rev=None, **kwargs):
    run = run if run is not None else {"return_value": CommitProcessResult(0, "", "")}
    rev = rev if rev is not None else _rev_parse()
    with (
        patch(_RUN, **run),
        patch(_SUBPROCESS, return_value=rev),
        patch(_SECURITY, return_value=security),
    ):
        return git_commit(
            _repo(), "msg", gpg_key_id=kwargs.pop("key", "KEY1"), **kwargs
        )


def test_git_commit_returns_created_message_when_security_enforced():
    result = _commit()
    assert result == (
        "✅ Commit 01234567 created with VERIFIED GPG signature"
        "\n🔒 Security configuration enforced"
        "\n🔒 Enforced GPG signing with key KEY1"
        "\n⚠️  MCP Git Server used - no fallback to system git commands"
    )
    assert not isinstance(result, ToolFailure)


def test_git_commit_returns_amended_message_when_amend_requested():
    result = _commit(amend=True)
    assert result.startswith("✅ Commit 01234567 amended with VERIFIED GPG signature")


def test_git_commit_omits_security_line_when_enforcement_reports_no_check_mark():
    result = _commit(security="nothing")
    assert result == (
        "✅ Commit 01234567 created with VERIFIED GPG signature"
        "\n🔒 Enforced GPG signing with key KEY1"
        "\n⚠️  MCP Git Server used - no fallback to system git commands"
    )


def test_git_commit_reports_unknown_hash_when_rev_parse_fails():
    result = _commit(rev=_rev_parse(returncode=1, stdout=""))
    assert result.startswith("✅ Commit unknown created")


def test_git_commit_returns_failure_when_commit_process_exits_nonzero():
    result = _commit(run={"return_value": CommitProcessResult(1, "", "hook said no")})
    assert result == (
        "❌ Commit failed: hook said no\n🔒 GPG signing was enforced but failed"
    )
    assert isinstance(result, ToolFailure)


def test_git_commit_returns_failure_when_commit_process_times_out():
    result = _commit(run={"side_effect": CommitTimeoutError(5)})
    assert result == (
        "❌ Commit failed: git commit timed out after 5s\n"
        "🔒 The commit process group was terminated "
        "(a GPG pinentry or hook may be blocking)"
    )
    assert isinstance(result, ToolFailure)


def test_git_commit_returns_gpg_error_when_no_key_resolves(monkeypatch):
    monkeypatch.delenv("GPG_SIGNING_KEY", raising=False)
    repo = _repo()
    repo.config_reader.side_effect = KeyError("signingkey")
    with patch(_SECURITY, return_value="✅ secure"):
        result = git_commit(repo, "msg")
    assert result == (
        "❌ Could not determine GPG signing key. "
        "Please configure GPG_SIGNING_KEY env var"
    )
    assert isinstance(result, ToolFailure)


def test_git_commit_returns_security_violation_when_force_gpg_disabled():
    run = MagicMock()
    with patch("mcp_server_git.git._commit_ops._FORCE_GPG", False):
        result = _commit(run={"new": run})
    assert result == (
        "❌ SECURITY VIOLATION: Unsigned commits are not allowed by MCP Git Server"
    )
    assert isinstance(result, ToolFailure)
    run.assert_not_called()


def test_git_commit_returns_failure_when_git_command_error_raised():
    err = GitCommandError("git commit", 1, stderr="boom")
    with patch(_SECURITY, side_effect=err):
        result = git_commit(_repo(), "msg", gpg_key_id="KEY1")
    assert result.startswith("❌ Commit failed: ")
    assert result.endswith(
        "\n🔒 Security enforcement may have prevented insecure operation"
    )
    assert isinstance(result, ToolFailure)


def test_git_commit_returns_failure_when_unexpected_error_raised():
    with patch(_SECURITY, side_effect=RuntimeError("kaput")):
        result = git_commit(_repo(), "msg", gpg_key_id="KEY1")
    assert result == (
        "❌ Commit error: kaput\n🔒 Verify repository security configuration"
    )
    assert isinstance(result, ToolFailure)


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, ["git", "commit", "--gpg-sign=KEY1", "-m", "msg"]),
        (
            {"amend": True, "allow_empty": True},
            [
                "git",
                "commit",
                "--amend",
                "--allow-empty",
                "--gpg-sign=KEY1",
                "-m",
                "msg",
            ],
        ),
    ],
)
def test_git_commit_builds_expected_argv_when_flags_vary(kwargs, expected):
    with (
        patch(_RUN, return_value=CommitProcessResult(0, "", "")) as run,
        patch(_SUBPROCESS, return_value=_rev_parse()),
        patch(_SECURITY, return_value="✅ secure"),
    ):
        git_commit(_repo(), "msg", gpg_key_id="KEY1", **kwargs)
    assert run.call_args[0] == (expected, "/tmp/test_repo")
