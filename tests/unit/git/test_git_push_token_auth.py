"""git_push authenticates every GitHub HTTPS push path the same way (#303).

The remote is configured as ``https://github.com/owner/repo.git`` while a
``url.<bare>.insteadOf`` rewrite in the repo config sends git to a local bare
repository, so git really runs. A local transport never consults credential
helpers, so the argv/env handed to git is captured by a spy on
``git.cmd.Git.execute`` that still runs the real command. The credential-fill
tests then prove, with real git, that the per-call override bypasses a broken
global helper.
"""

import os
import subprocess
from pathlib import Path

import git
import git.cmd
import pytest

from mcp_server_git.git import _github_token
from mcp_server_git.git._push_auth import (
    CREDENTIAL_OVERRIDES,
    TOKEN_ENV_VAR,
    TOKEN_HELPER,
    PushAuth,
)
from mcp_server_git.git.operations import git_push

TOKEN = "ghp_testtoken1234567890"
GITHUB_URL = "https://github.com/owner/repo.git"
BROKEN_HELPER = "!/nonexistent/gh auth git-credential"
ENV_NOTE = "\n🔐 Used server GitHub token (GITHUB_TOKEN environment variable)"

Calls = list[tuple[list[str], dict[str, str] | None]]


# Defence in depth: any push that escapes the insteadOf rewrite fails locally
# instead of reaching the network.
NETWORK_BLOCK = (
    '[protocol "https"]\n\tallow = never\n[protocol "http"]\n\tallow = never\n'
)


@pytest.fixture(autouse=True)
def isolated_git_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Global config whose github helper points at a missing executable.

    The token is injected explicitly (fake env value; gh stubbed to None) so
    resolution can never fall through to the machine's real token.
    """
    home = tmp_path / "home"
    home.mkdir()
    gitconfig = home / ".gitconfig"
    gitconfig.write_text(
        f'[credential "https://github.com"]\n\thelper = {BROKEN_HELPER}\n'
        + NETWORK_BLOCK
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GITHUB_TOKEN", TOKEN)
    monkeypatch.setattr(_github_token, "_get_github_token_from_cli", lambda: None)
    return gitconfig


@pytest.fixture()
def bare_remote(tmp_path: Path) -> Path:
    path = tmp_path / "remote.git"
    git.Repo.init(path, bare=True)
    return path


def _make_repo(path: Path, url: str, bare_remote: Path | None) -> git.Repo:
    repo = git.Repo.init(path, initial_branch="main")
    with repo.config_writer() as cfg:
        cfg.set_value("user", "name", "Test")
        cfg.set_value("user", "email", "test@example.com")
        cfg.set_value('protocol "https"', "allow", "never")
        cfg.set_value('protocol "http"', "allow", "never")
        if bare_remote is not None:
            cfg.set_value(f'url "{bare_remote}"', "insteadOf", url)
    (path / "a.txt").write_text("a")
    repo.index.add(["a.txt"])
    repo.index.commit("add a")
    repo.create_remote("origin", url)
    return repo


@pytest.fixture()
def work_repo(tmp_path: Path, bare_remote: Path) -> git.Repo:
    return _make_repo(tmp_path / "work", GITHUB_URL, bare_remote)


@pytest.fixture()
def git_calls(monkeypatch: pytest.MonkeyPatch) -> Calls:
    calls: Calls = []
    original = git.cmd.Git.execute

    def spy(self, command, *args, **kwargs):
        argv = list(command) if isinstance(command, list | tuple) else [command]
        calls.append((argv, kwargs.get("env")))
        return original(self, command, *args, **kwargs)

    monkeypatch.setattr(git.cmd.Git, "execute", spy)
    return calls


def _push_call(calls: Calls) -> tuple[list[str], dict[str, str] | None]:
    return next((argv, env) for argv, env in calls if "push" in argv)


def _config_text(repo: git.Repo) -> str:
    return (Path(repo.git_dir) / "config").read_text()


_MODES = {
    "branch": {"branch": "main"},
    "refspec": {"refspec": "main:refs/heads/copy"},
    "delete": {"branch": "feature", "delete": True},
}


@pytest.mark.parametrize("mode", list(_MODES))
def test_git_push_passes_token_in_env_only_when_github_https_push_uses_path(
    work_repo: git.Repo, git_calls: Calls, mode: str
) -> None:
    work_repo.git.push("origin", "main:feature")
    git_calls.clear()

    result = git_push(work_repo, **_MODES[mode])

    assert result.startswith("✅"), result
    assert result.endswith(ENV_NOTE)
    argv, env = _push_call(git_calls)
    assert argv[1 : argv.index("push")] == [
        "-c",
        "credential.helper=",
        "-c",
        TOKEN_HELPER,
    ]
    assert all(TOKEN not in arg for arg in argv)
    assert env == {TOKEN_ENV_VAR: TOKEN, "GIT_TERMINAL_PROMPT": "0"}
    assert TOKEN not in result


def test_git_push_returns_env_source_note_when_token_from_environment(
    work_repo: git.Repo, bare_remote: Path
) -> None:
    result = git_push(work_repo)

    assert result == "✅ Successfully pushed main to origin" + ENV_NOTE
    assert [h.name for h in git.Repo(bare_remote).heads] == ["main"]


def test_git_push_returns_dotenv_source_note_when_token_in_repo_dotenv(
    work_repo: git.Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN")
    (Path(work_repo.working_dir) / ".env").write_text(f"GITHUB_TOKEN={TOKEN}\n")

    result = git_push(work_repo)

    assert result.endswith("\n🔐 Used server GitHub token (repo .env GITHUB_TOKEN)")


def test_git_push_returns_cli_source_note_when_only_gh_has_token(
    work_repo: git.Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN")
    monkeypatch.setattr(_github_token, "_get_github_token_from_cli", lambda: TOKEN)

    result = git_push(work_repo, refspec="main:refs/heads/copy")

    assert result.endswith("\n🔐 Used server GitHub token (GitHub CLI gh auth token)")


def test_git_push_leaves_token_out_of_git_config_when_push_succeeds(
    work_repo: git.Repo,
) -> None:
    git_push(work_repo)

    assert TOKEN not in _config_text(work_repo)
    assert work_repo.remote("origin").url == GITHUB_URL


def test_git_push_leaves_token_out_of_config_and_output_when_push_fails(
    work_repo: git.Repo,
) -> None:
    result = git_push(work_repo, branch="no-such-branch")

    assert result.startswith("❌ Push failed (exit 1): ")
    assert TOKEN not in result
    assert TOKEN not in _config_text(work_repo)


@pytest.mark.parametrize(
    "url",
    [
        "git@github.com:owner/repo.git",
        "ssh://git@github.com/owner/repo.git",
        "https://gitlab.com/owner/repo.git",
    ],
)
def test_git_push_omits_helper_override_when_remote_is_not_github_https(
    tmp_path: Path, bare_remote: Path, git_calls: Calls, url: str
) -> None:
    repo = _make_repo(tmp_path / "other", url, bare_remote)

    result = git_push(repo)

    assert result == "✅ Successfully pushed main to origin"
    argv, env = _push_call(git_calls)
    assert not any(arg.startswith("credential.helper") for arg in argv)
    assert env is None


def test_git_push_applies_override_when_only_pushurl_is_github_https(
    work_repo: git.Repo, bare_remote: Path, git_calls: Calls
) -> None:
    work_repo.git.config("remote.origin.url", str(bare_remote))
    work_repo.git.config("remote.origin.pushurl", GITHUB_URL)

    result = git_push(work_repo)

    assert result.endswith(ENV_NOTE)
    assert "credential.helper=" in _push_call(git_calls)[0]
    assert [h.name for h in git.Repo(bare_remote).heads] == ["main"]


def test_git_push_omits_override_when_pushurl_is_not_github_https(
    work_repo: git.Repo, bare_remote: Path, git_calls: Calls
) -> None:
    work_repo.git.config("remote.origin.pushurl", str(bare_remote))

    result = git_push(work_repo)

    assert result == "✅ Successfully pushed main to origin"
    assert _push_call(git_calls)[1] is None


def test_git_push_applies_override_when_remote_argument_is_github_url(
    work_repo: git.Repo, git_calls: Calls
) -> None:
    result = git_push(work_repo, remote=GITHUB_URL, branch="main")

    assert result == f"✅ Successfully pushed main to {GITHUB_URL}" + ENV_NOTE
    assert _push_call(git_calls)[1] == {
        TOKEN_ENV_VAR: TOKEN,
        "GIT_TERMINAL_PROMPT": "0",
    }


def test_git_push_fails_locally_when_github_url_is_not_rewritten(
    tmp_path: Path, git_calls: Calls
) -> None:
    """Guard for the guard: an un-rewritten github push never leaves the box."""
    repo = _make_repo(tmp_path / "unrewritten", GITHUB_URL, None)

    result = git_push(repo)

    assert result.startswith("❌ Push failed (exit 128): "), result
    assert "transport 'https' not allowed" in result
    assert TOKEN not in result
    assert "credential.helper=" in _push_call(git_calls)[0]


def _credential_fill(options: list[str], cwd: Path) -> subprocess.CompletedProcess:
    argv = ["git"]
    for option in options:
        argv += ["-c", option]
    auth = PushAuth(token=TOKEN, source="env")
    return subprocess.run(
        [*argv, "credential", "fill"],
        input="protocol=https\nhost=github.com\npath=owner/repo.git\n\n",
        capture_output=True,
        text=True,
        env={**os.environ, **auth.env()},
        cwd=cwd,
        timeout=30,
        check=False,
    )


def test_credential_fill_returns_server_token_when_global_helper_is_missing(
    tmp_path: Path,
) -> None:
    result = _credential_fill(list(CREDENTIAL_OVERRIDES), tmp_path)

    assert result.returncode == 0, result.stderr
    assert "username=x-access-token\n" in result.stdout
    assert f"password={TOKEN}\n" in result.stdout
    assert "nonexistent" not in result.stderr


def test_credential_fill_runs_broken_global_helper_when_reset_is_absent(
    tmp_path: Path,
) -> None:
    """Control: without the reset the stale global helper is consulted."""
    result = _credential_fill([TOKEN_HELPER], tmp_path)

    assert "/nonexistent/gh" in result.stderr
