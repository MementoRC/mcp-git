"""Per-repo GitHub identities (issue #340): map, slug parsing, push/commit/API."""

import asyncio
import os
import subprocess
import threading
from pathlib import Path

import git
import pytest

from mcp_server_git.git._commit_ops import git_commit
from mcp_server_git.git._commit_runner import run_commit_process
from mcp_server_git.git._gpg import resolve_gpg_key
from mcp_server_git.git._push_auth import resolve_push_auth
from mcp_server_git.git.security import enforce_secure_git_config
from mcp_server_git.github.client import get_github_client
from mcp_server_git.identity import (
    IdentityError,
    RepoIdentity,
    config,
    identity_for_repo,
    identity_for_slug,
    identity_scope,
    slug_from_url,
    use_identity,
)
from mcp_server_git.lean.meta_tools import (
    _execute_registered_tool,
    _validate_and_run,
)

BOT_TOKEN = "ghp_" + "b" * 36
ENV_TOKEN = "ghp_" + "e" * 36


@pytest.fixture
def identity_file(tmp_path, monkeypatch) -> Path:
    env_file = tmp_path / "bot.env"
    env_file.write_text(
        f"GITHUB_TOKEN={BOT_TOKEN}\n"
        "GPG_SIGNING_KEY=BOTKEY123\n"
        "GIT_AUTHOR_NAME=Bot Author\n"
        "GIT_AUTHOR_EMAIL=bot-author@example.com\n"
        "GIT_COMMITTER_NAME=Bot Committer\n"
        "GIT_COMMITTER_EMAIL=bot-committer@example.com\n"
    )
    cfg = tmp_path / "identities.toml"
    cfg.write_text(
        f'[identities.bot]\nenv_file = "{env_file}"\nrepos = ["MementoRC/Roth_Planner"]\n'
    )
    monkeypatch.setenv("MCP_GIT_IDENTITIES", str(cfg))
    return cfg


def _mapped_repo(
    tmp_path: Path, url: str = "git@github.com:mementorc/roth_planner.git"
):
    repo = git.Repo.init(tmp_path / "work")
    repo.create_remote("origin", url)
    return repo


def test_identity_for_slug_returns_identity_when_slug_differs_in_case(identity_file):
    identity = identity_for_slug("mementorc/ROTH_PLANNER")
    assert identity is not None
    assert (identity.name, identity.token, identity.gpg_key) == (
        "bot",
        BOT_TOKEN,
        "BOTKEY123",
    )
    assert identity.author_email == "bot-author@example.com"
    assert identity.committer_name == "Bot Committer"


def test_identity_for_slug_returns_none_when_slug_unmapped(identity_file):
    assert identity_for_slug("other/repo") is None


def test_identity_for_slug_returns_none_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_GIT_IDENTITIES", str(tmp_path / "absent.toml"))
    assert identity_for_slug("a/b") is None


def test_identity_for_slug_raises_when_toml_invalid_and_recovers_when_fixed(
    identity_file,
):
    good = identity_file.read_text()
    identity_file.write_text("[identities.x\nnot toml")
    with pytest.raises(IdentityError, match="is invalid"):
        identity_for_slug("a/b")
    identity_file.write_text(good)
    os.utime(identity_file, ns=(1, identity_file.stat().st_mtime_ns + 10**9))
    assert identity_for_slug("a/b") is None
    assert identity_for_slug("mementorc/roth_planner") is not None


def test_identity_for_slug_raises_when_repos_is_string(tmp_path, monkeypatch):
    cfg = tmp_path / "bad.toml"
    cfg.write_text('[identities.x]\nenv_file = "e.env"\nrepos = "a/b"\n')
    monkeypatch.setenv("MCP_GIT_IDENTITIES", str(cfg))
    with pytest.raises(IdentityError, match="repos must be a list"):
        identity_for_slug("a/b")


def test_identity_for_slug_raises_when_env_file_missing(tmp_path, monkeypatch):
    cfg = tmp_path / "ids.toml"
    cfg.write_text(f'[identities.x]\nenv_file = "{tmp_path}/no.env"\nrepos = ["a/b"]\n')
    monkeypatch.setenv("MCP_GIT_IDENTITIES", str(cfg))
    with pytest.raises(IdentityError, match="missing or unreadable"):
        identity_for_slug("a/b")


def test_identity_for_slug_raises_when_env_file_has_no_token(identity_file, tmp_path):
    (tmp_path / "bot.env").write_text("GPG_SIGNING_KEY=K\n")
    with pytest.raises(IdentityError, match="no GITHUB_TOKEN"):
        identity_for_slug("mementorc/roth_planner")


def test_load_map_raises_no_keyerror_when_loaded_from_threads(identity_file):
    errors: list[BaseException] = []

    def work(i: int) -> None:
        try:
            for _ in range(50):
                if i == 0:
                    with config._cache_lock:
                        config._cache.clear()
                config._load_map()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []


def test_git_commit_raises_identity_error_when_gpg_key_missing(identity_file, tmp_path):
    env = tmp_path / "bot.env"
    env.write_text(env.read_text().replace("GPG_SIGNING_KEY=BOTKEY123\n", ""))
    repo = _mapped_repo(tmp_path)
    result = git_commit(repo, message="m")
    assert "gpg_key" in str(result) and "BOTKEY123" not in str(result)
    assert "Commit refused" in str(result)


def test_commit_env_defaults_committer_to_author_when_absent():
    identity = RepoIdentity(name="b", author_name="A", author_email="a@x.io")
    env = identity.commit_env()
    assert env["GIT_COMMITTER_NAME"] == "A"
    assert env["GIT_COMMITTER_EMAIL"] == "a@x.io"


def test_resolve_push_auth_skips_identity_token_when_url_unmapped_but_origin_mapped(
    identity_file, tmp_path, monkeypatch
):
    monkeypatch.setenv("GITHUB_TOKEN", ENV_TOKEN)
    auth = resolve_push_auth(_mapped_repo(tmp_path), "https://github.com/fork/repo")
    assert auth is not None
    assert (auth.token, auth.source) == (ENV_TOKEN, "env")


def test_execute_registered_tool_returns_error_result_when_identity_map_invalid(
    identity_file,
):
    identity_file.write_text("[identities.x\nbroken")

    class _Def:
        implementation = staticmethod(lambda **_kw: "ok")
        schema = {"type": "object"}
        relative_path_params: frozenset = frozenset()

    class _Iface:
        _schema_cache: dict = {}
        tool_registry = {"t": _Def()}

        def _validate_path_parameters(self, *_a, **_k):
            return None

    result = asyncio.run(
        _execute_registered_tool(_Iface(), "t", {"repo_owner": "o", "repo_name": "r"})
    )
    assert result["status"] == "error"
    assert "is invalid" in result["error"]


def test_identity_for_slug_reloads_when_mtime_changes(identity_file, tmp_path):
    assert identity_for_slug("new/repo") is None
    identity_file.write_text(identity_file.read_text().replace('"]', '", "New/Repo"]'))
    os.utime(identity_file, ns=(1, identity_file.stat().st_mtime_ns + 10**9))
    found = identity_for_slug("new/repo")
    assert found is not None and found.name == "bot"


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/o/r.git",
        "https://github.com/o/r",
        "git@github.com:o/r.git",
        "git@github.com:o/r",
        "ssh://git@github.com/o/r",
    ],
)
def test_slug_from_url_returns_owner_repo_when_github_url(url):
    assert slug_from_url(url) == "o/r"


def test_slug_from_url_returns_none_when_not_github():
    assert slug_from_url("https://gitlab.com/o/r.git") is None


def test_identity_for_repo_returns_none_when_no_origin(identity_file, tmp_path):
    assert identity_for_repo(git.Repo.init(tmp_path / "bare_work")) is None


def test_identity_for_repo_leaves_environ_unchanged_when_identity_found(
    identity_file, tmp_path
):
    before = dict(os.environ)
    identity = identity_for_repo(_mapped_repo(tmp_path))
    assert identity is not None
    assert dict(os.environ) == before


def test_resolve_push_auth_prefers_identity_token_when_repo_mapped(
    identity_file, tmp_path, monkeypatch
):
    monkeypatch.setenv("GITHUB_TOKEN", ENV_TOKEN)
    url = "https://github.com/MementoRC/Roth_Planner.git"
    auth = resolve_push_auth(_mapped_repo(tmp_path), url)
    assert auth is not None
    assert (auth.token, auth.source) == (BOT_TOKEN, "identity:bot")
    assert "identity: bot" in auth.success_note()


def test_resolve_push_auth_uses_env_token_when_repo_unmapped(
    identity_file, tmp_path, monkeypatch
):
    monkeypatch.setenv("GITHUB_TOKEN", ENV_TOKEN)
    repo = _mapped_repo(tmp_path, "git@github.com:other/repo.git")
    auth = resolve_push_auth(repo, "https://github.com/other/repo")
    assert auth is not None
    assert (auth.token, auth.source) == (ENV_TOKEN, "env")


def test_resolve_gpg_key_returns_identity_key_when_no_explicit_key(
    identity_file, tmp_path, monkeypatch
):
    monkeypatch.setenv("GPG_SIGNING_KEY", "ENVKEY")
    repo = _mapped_repo(tmp_path)
    assert resolve_gpg_key(repo, None, "BOTKEY123") == ("BOTKEY123", None)
    assert resolve_gpg_key(repo, "EXPLICIT", "BOTKEY123") == ("EXPLICIT", None)
    assert resolve_gpg_key(repo, None, None) == ("ENVKEY", None)


def test_enforce_secure_git_config_skips_key_when_identity_active(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("GPG_SIGNING_KEY", "ENVKEY")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Env Name")
    repo = git.Repo.init(tmp_path / "w")
    enforce_secure_git_config(repo, strict_mode=True, identity_active=True)
    reader = repo.config_reader("repository")
    assert not reader.has_option("user", "signingkey")
    assert not reader.has_option("user", "name")


def test_run_commit_process_uses_identity_author_when_extra_env_given(
    identity_file, tmp_path
):
    repo = _mapped_repo(tmp_path)
    work = Path(repo.working_dir)
    (work / "f.txt").write_text("x")
    repo.index.add(["f.txt"])
    identity = identity_for_repo(repo)
    assert identity is not None
    cmd = ["git", "-c", "commit.gpgsign=false", "commit", "-m", "m"]
    result = run_commit_process(cmd, str(work), identity.commit_env())
    assert result.returncode == 0, result.stderr
    out = subprocess.run(
        ["git", "log", "-1", "--format=%an|%ae|%cn|%ce"],
        cwd=work,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert out == (
        "Bot Author|bot-author@example.com|Bot Committer|bot-committer@example.com"
    )
    assert os.environ.get("GIT_AUTHOR_NAME") != "Bot Author"


@pytest.mark.asyncio
async def test_get_github_client_uses_context_token_when_identity_set(
    identity_file, monkeypatch
):
    monkeypatch.setenv("GITHUB_TOKEN", ENV_TOKEN)
    identity = identity_for_slug("mementorc/roth_planner")
    with use_identity(identity):
        client = get_github_client()
    assert client is not None
    assert client.token == BOT_TOKEN
    await client.session.close()
    client = get_github_client()
    assert client is not None
    assert client.token == ENV_TOKEN
    await client.session.close()


def test_validate_and_run_sets_identity_when_repo_params_mapped(identity_file):
    seen: list[str | None] = []

    def impl(repo_owner: str, repo_name: str) -> str:
        from mcp_server_git.identity import current_identity

        current = current_identity.get()
        seen.append(current.name if current else None)
        return "ok"

    class _Def:
        implementation = staticmethod(impl)
        schema = {"type": "object"}
        relative_path_params: frozenset = frozenset()

    class _Iface:
        _schema_cache: dict = {}

        def _validate_path_parameters(self, *_a, **_k):
            return None

    for owner, name in (("MementoRC", "roth_planner"), ("o", "r")):
        asyncio.run(
            _validate_and_run(
                _Iface(), "t", _Def(), {"repo_owner": owner, "repo_name": name}
            )
        )
    assert seen == ["bot", None]


def test_identity_scope_restores_none_when_block_exits(identity_file):
    from mcp_server_git.identity import current_identity

    with identity_scope({"repo_owner": "MementoRC", "repo_name": "roth_planner"}):
        assert current_identity.get() is not None
    assert current_identity.get() is None
