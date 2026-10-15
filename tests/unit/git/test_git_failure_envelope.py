"""Failing git ops report status "error" through the lean path (issue #271).

Real temporary repositories, no mocks: git_add blocked by a fresh
index.lock and git_checkout of a missing branch must come back as a
ToolFailure so the execute_tool envelope is not "success".
"""

import pytest

pytest.importorskip("git")
from git import Repo  # noqa: E402

from mcp_server_git.git.operations import git_add, git_checkout  # noqa: E402
from mcp_server_git.lean.interface import GitLeanInterface  # noqa: E402
from mcp_server_git.utils.tool_failure import ToolFailure  # noqa: E402


class _MockService:
    def __getattr__(self, name: str):
        return lambda **kwargs: {"result": f"mock_{name}", "params": kwargs}


@pytest.fixture
def repo(tmp_path):
    r = Repo.init(tmp_path)
    with r.config_writer() as cw:
        cw.set_value("user", "name", "T")
        cw.set_value("user", "email", "t@example.com")
    (tmp_path / "tracked.txt").write_text("v1\n")
    r.git.add("tracked.txt")
    r.git.commit("-m", "init")
    return r


@pytest.fixture
def interface():
    return GitLeanInterface(
        git_service=_MockService(),
        github_service=_MockService(),
        azure_service=_MockService(),
    )


@pytest.fixture
def locked_repo(repo, tmp_path, monkeypatch):
    """Repo with a fresh index.lock that is neither waited out nor reaped.

    Holder detection is "unknown", so a young lock is left alone (a dead
    holder would be waited out and healed, see #292).
    """
    for module in ("lock_holders", "lock_reaper"):
        monkeypatch.setattr(
            f"mcp_server_git.lean.{module}.has_live_lock_holder", lambda _: None
        )
    (tmp_path / "new.txt").write_text("x\n")
    (tmp_path / ".git" / "index.lock").write_bytes(b"")
    return repo


def test_git_add_returns_tool_failure_when_index_lock_exists(locked_repo):
    result = git_add(locked_repo, files=["new.txt"])

    assert isinstance(result, ToolFailure)
    assert result.startswith("❌ Git add failed")


@pytest.mark.asyncio
async def test_execute_tool_direct_returns_error_when_git_add_hits_index_lock(
    locked_repo, interface, tmp_path
):
    envelope = await interface.execute_tool_direct(
        "git_add", {"repo_path": str(tmp_path), "files": ["new.txt"]}
    )

    assert envelope["status"] == "error"
    assert envelope["error"].startswith("❌ Git add failed")


def test_git_checkout_returns_tool_failure_when_branch_does_not_exist(repo):
    result = git_checkout(repo, "no-such-branch")

    assert isinstance(result, ToolFailure)
    assert result.startswith("❌ ")


@pytest.mark.asyncio
async def test_execute_tool_direct_returns_error_when_checkout_branch_missing(
    repo, interface, tmp_path
):
    envelope = await interface.execute_tool_direct(
        "git_checkout", {"repo_path": str(tmp_path), "branch_name": "no-such-branch"}
    )

    assert envelope["status"] == "error"
    assert envelope["error"].startswith("❌ ")
