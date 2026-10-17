"""Credential-helper inspection: push hint and health flag (#303).

Helpers are read by real ``git config`` from an isolated global config file.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from git.exc import GitCommandError

from mcp_server_git.git import _github_token
from mcp_server_git.git.operations import git_push
from mcp_server_git.lean.interface import GitLeanInterface
from mcp_server_git.server_metadata import build_server_info
from mcp_server_git.utils.credential_helpers import (
    credential_helper_health,
    credential_hint,
    list_credential_helpers,
    missing_executable,
)
from mcp_server_git.utils.tool_failure import ToolFailure

MISSING = "/nonexistent/gh"
BROKEN_HELPER = f"!{MISSING} auth git-credential"
URL = "https://github.com/owner/repo.git"


def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> Path:
    gitconfig = tmp_path / "global.gitconfig"
    # Network block + no token fallthrough: nothing here may reach GitHub.
    gitconfig.write_text(
        body
        + '[protocol "https"]\n\tallow = never\n[protocol "http"]\n\tallow = never\n'
    )
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_fake_credential_test_token")
    monkeypatch.setattr(_github_token, "_get_github_token_from_cli", lambda: None)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.chdir(tmp_path)
    return gitconfig


@pytest.fixture()
def broken_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return _isolate(
        tmp_path,
        monkeypatch,
        f'[credential "https://github.com"]\n\thelper = {BROKEN_HELPER}\n'
        '[credential "https://gitlab.com"]\n\thelper = !/nonexistent/glab\n',
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (BROKEN_HELPER, MISSING),
        ("/nonexistent/helper --flag", "/nonexistent/helper"),
        (f"!{sys.executable} -c pass", None),
        (sys.executable, None),
        ("store", None),
        ("cache --timeout=60", None),
        ("!f() { echo username=x; }; f", None),
        ("", None),
    ],
)
def test_missing_executable_returns_expected_when_helper_value_given(
    value: str, expected: str | None
) -> None:
    assert missing_executable(value) == expected


def test_list_credential_helpers_returns_origin_key_value_when_global_has_helpers(
    broken_config: Path,
) -> None:
    entries = list_credential_helpers()

    assert [(e.origin, e.key, e.value) for e in entries] == [
        (
            f"file:{broken_config}",
            "credential.https://github.com.helper",
            BROKEN_HELPER,
        ),
        (
            f"file:{broken_config}",
            "credential.https://gitlab.com.helper",
            "!/nonexistent/glab",
        ),
    ]


@pytest.mark.parametrize(
    "stderr",
    [
        "fatal: could not read Username for 'https://github.com': No such device",
        "fatal: could not read Password: terminal prompts disabled",
        f"{MISSING} auth git-credential get: 1: {MISSING}: not found",
        "git: 'credential-manager' not found",
    ],
)
def test_credential_hint_names_missing_executable_and_origin_when_stderr_matches(
    broken_config: Path, stderr: str
) -> None:
    hint = credential_hint(stderr, URL)

    assert f"file:{broken_config}: credential.https://github.com.helper" in hint
    assert f"missing executable: {MISSING}" in hint
    assert "gh auth setup-git" in hint
    assert "GITHUB_TOKEN" in hint
    assert "glab" not in hint


def test_credential_hint_returns_empty_when_stderr_is_unrelated(
    broken_config: Path,
) -> None:
    assert credential_hint("error: src refspec x does not match any", URL) == ""


def test_credential_hint_strips_userinfo_when_url_embeds_credentials(
    broken_config: Path,
) -> None:
    hint = credential_hint(
        "could not read Username", "https://user:secret@github.com/owner/repo.git"
    )

    assert "secret" not in hint
    assert "https://github.com/owner/repo.git" in hint


def test_git_push_appends_helper_hint_when_push_cannot_read_username(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gitconfig = _isolate(
        tmp_path, monkeypatch, f"[credential]\n\thelper = {BROKEN_HELPER}\n"
    )
    repo = MagicMock()
    repo.working_dir = str(tmp_path)
    repo.active_branch.name = "main"
    repo.remote.return_value.url = "https://gitlab.com/owner/repo.git"
    repo.git.push.side_effect = GitCommandError(
        "push",
        128,
        stderr="fatal: could not read Username for 'https://gitlab.com': "
        "terminal prompts disabled",
    )

    result = git_push(repo)

    assert isinstance(result, ToolFailure)
    assert result.startswith(
        "❌ Push failed (exit 128): fatal: could not read Username"
    )
    assert f"file:{gitconfig}: credential.helper = {BROKEN_HELPER}" in result
    assert f"missing executable: {MISSING}" in result


def test_credential_helper_health_flags_missing_executable_when_helper_absent(
    broken_config: Path,
) -> None:
    health = credential_helper_health()

    assert health["status"] == "warning"
    assert health["helpers_checked"] == 2
    assert health["missing_executables"][0] == {
        "origin": f"file:{broken_config}",
        "key": "credential.https://github.com.helper",
        "executable": MISSING,
    }


def test_credential_helper_health_returns_ok_when_helper_executable_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(tmp_path, monkeypatch, f"[credential]\n\thelper = !{sys.executable}\n")

    health = credential_helper_health()

    assert health == {"status": "ok", "helpers_checked": 1, "missing_executables": []}


def test_credential_helper_health_returns_unknown_when_git_cannot_run(
    broken_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(broken_config.parent / "no-bin"))

    health = credential_helper_health()

    assert health["status"] == "unknown"
    assert health["missing_executables"] == []


def test_health_check_reports_missing_helper_when_global_helper_absent(
    broken_config: Path,
) -> None:
    interface = GitLeanInterface(
        git_service=MagicMock(), github_service=MagicMock(), azure_service=MagicMock()
    )

    health = interface.health_check()

    assert health["credential_helpers"]["status"] == "warning"
    assert health["credential_helpers"]["missing_executables"][0]["executable"] == (
        MISSING
    )


def test_build_server_info_reports_helper_status_when_global_helper_absent(
    broken_config: Path,
) -> None:
    assert build_server_info({}, "test")["credential_helper_status"] == "warning"
