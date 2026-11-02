"""git_commit no_verify on a real, signing-capable repo with failing hooks (#330)."""

import os

import pytest

from mcp_server_git.git._commit_ops import _build_commit_cmd, git_commit
from mcp_server_git.git.models import GitCommit
from mcp_server_git.utils.tool_failure import ToolFailure

ENV = "MCP_GIT_NO_VERIFY_BRANCHES"


@pytest.fixture
def hooked_repo(signing_repo):
    signing_repo.index.commit("base")
    hooks = signing_repo.git_dir + "/hooks"
    for name in ("pre-commit", "commit-msg"):
        path = f"{hooks}/{name}"
        with open(path, "w") as handle:
            handle.write("#!/bin/sh\nexit 1\n")
        os.chmod(path, 0o755)
    with open(f"{signing_repo.working_dir}/f.txt", "w") as handle:
        handle.write("x\n")
    signing_repo.index.add(["f.txt"])
    return signing_repo


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)


def test_git_commit_creates_signed_commit_when_no_verify_and_hooks_fail(hooked_repo):
    before = hooked_repo.head.commit.hexsha

    result = git_commit(hooked_repo, "skip hooks", no_verify=True)

    assert result.startswith("✅"), result
    assert "no_verify=true" in result
    assert hooked_repo.head.commit.hexsha != before
    assert "gpgsig" in hooked_repo.git.cat_file("-p", "HEAD")


def test_git_commit_fails_when_hook_rejects_and_no_verify_omitted(hooked_repo):
    before = hooked_repo.head.commit.hexsha

    result = git_commit(hooked_repo, "hooks run")

    assert isinstance(result, ToolFailure)
    assert hooked_repo.head.commit.hexsha == before


def test_git_commit_succeeds_when_branch_matches_no_verify_allowlist(
    hooked_repo, monkeypatch
):
    monkeypatch.setenv(ENV, "_for_overlay/*")
    hooked_repo.git.checkout("-b", "_for_overlay/x")

    result = git_commit(hooked_repo, "overlay", no_verify=True)

    assert result.startswith("✅"), result


def test_git_commit_refuses_when_branch_not_in_no_verify_allowlist(
    hooked_repo, monkeypatch
):
    monkeypatch.setenv(ENV, "_for_overlay/*")
    hooked_repo.git.checkout("-b", "feature/y")
    before = hooked_repo.head.commit.hexsha

    result = git_commit(hooked_repo, "nope", no_verify=True)

    assert isinstance(result, ToolFailure)
    assert "no_verify refused on branch 'feature/y'" in result
    assert hooked_repo.head.commit.hexsha == before


def test_git_commit_refuses_when_head_detached_and_allowlist_set(
    hooked_repo, monkeypatch
):
    monkeypatch.setenv(ENV, "_for_overlay/*")
    hooked_repo.git.checkout("--detach")
    before = hooked_repo.head.commit.hexsha

    result = git_commit(hooked_repo, "nope", no_verify=True)

    assert isinstance(result, ToolFailure)
    assert "no_verify refused" in result
    assert hooked_repo.head.commit.hexsha == before


def test_git_commit_ignores_allowlist_when_no_verify_false(hooked_repo, monkeypatch):
    monkeypatch.setenv(ENV, "_for_overlay/*")
    hooked_repo.git.checkout("-b", "feature/y")

    result = git_commit(hooked_repo, "hooks run")

    assert "no_verify refused" not in result


def test_build_commit_cmd_includes_no_verify_and_gpg_sign_when_enabled():
    cmd = _build_commit_cmd(["-m", "m"], False, False, "KEY", True)

    assert "--no-verify" in cmd
    assert "--gpg-sign=KEY" in cmd


def test_build_commit_cmd_omits_no_verify_when_default():
    assert "--no-verify" not in _build_commit_cmd(["-m", "m"], False, False, "KEY")


def test_git_commit_schema_describes_no_verify_when_generated():
    prop = GitCommit.model_json_schema()["properties"]["no_verify"]

    assert prop["description"]
    assert prop["default"] is False
