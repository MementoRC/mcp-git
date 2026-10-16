"""Real-git tests for config scope handling (no mocks of git itself)."""

import os
from pathlib import Path

import pytest

from mcp_server_git.git import _config_ops
from mcp_server_git.utils.git_import import Repo


@pytest.fixture
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect global config and HOME to temp locations; yield (repo, global_file)."""
    home = tmp_path / "home"
    home.mkdir()
    global_file = tmp_path / "global.gitconfig"
    global_file.write_text("[scopetest]\n\tmarker = from-global\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_file))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    assert os.environ["GIT_CONFIG_GLOBAL"] == str(global_file)
    assert os.environ["HOME"] == str(home)
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    repo = Repo.init(repo_dir)
    return repo, global_file


def test_git_config_list_returns_global_entries_when_scope_global(isolated_config):
    repo, _ = isolated_config
    out = _config_ops.git_config_list(repo, scope="global")
    assert "scopetest.marker=from-global" in out


def test_git_config_list_excludes_global_entries_when_scope_local(isolated_config):
    repo, _ = isolated_config
    out = _config_ops.git_config_list(repo, scope="local")
    assert "scopetest.marker" not in out


def test_git_config_get_returns_value_when_scope_global(isolated_config):
    repo, _ = isolated_config
    out = _config_ops.git_config_get(repo, "scopetest.marker", scope="global")
    assert out == "scopetest.marker = from-global"


def test_git_config_get_fails_when_scope_local_and_key_only_global(isolated_config):
    repo, _ = isolated_config
    out = _config_ops.git_config_get(repo, "scopetest.marker", scope="local")
    assert "from-global" not in out


@pytest.mark.parametrize("bad_scope", ["-x", "foo", "--global", "global --list"])
def test_build_config_scope_flags_raises_on_invalid_scope_when_unknown(bad_scope):
    with pytest.raises(ValueError, match="Invalid scope"):
        _config_ops._build_config_scope_flags(bad_scope)


@pytest.mark.parametrize("scope", ["global", "system", "local", "worktree"])
def test_build_config_scope_flags_returns_double_dash_flag_when_valid(scope):
    assert _config_ops._build_config_scope_flags(scope) == [f"--{scope}"]


def test_build_config_scope_flags_returns_empty_when_scope_none():
    assert _config_ops._build_config_scope_flags(None) == []


@pytest.mark.parametrize("bad_scope", ["-x", "foo"])
def test_git_config_tools_return_error_when_scope_invalid(isolated_config, bad_scope):
    repo, global_file = isolated_config
    before = global_file.read_text()
    outs = [
        _config_ops.git_config_list(repo, scope=bad_scope),
        _config_ops.git_config_get(repo, "scopetest.marker", scope=bad_scope),
        _config_ops.git_config_set(repo, "scopetest.x", "1", scope=bad_scope),
    ]
    for out in outs:
        assert "Invalid scope" in out
    assert global_file.read_text() == before


def test_git_config_set_writes_global_file_only_when_scope_global(isolated_config):
    repo, global_file = isolated_config
    out = _config_ops.git_config_set(repo, "scopetest.written", "yes", scope="global")
    assert "✅" in out
    assert "written = yes" in global_file.read_text()
    local_cfg = Path(repo.git_dir) / "config"
    assert "scopetest" not in local_cfg.read_text()
    assert not (Path(os.environ["HOME"]) / ".gitconfig").exists()


def test_git_config_list_rejects_absolute_file_outside_repo_when_scope_global(
    isolated_config,
):
    repo, global_file = isolated_config
    out = _config_ops.git_config_list(repo, file=str(global_file), scope="global")
    assert "absolute path must be within the repository" in out
