"""
Unit tests for the bad-repo_path error message defect.

Bug: any ``git_*`` lean tool called with a ``repo_path`` that does not exist,
or that exists but is not a git repository, returns an error envelope whose
``error`` text is ONLY the path (e.g.
``{"status": "error", "error": "/x/does-not-exist"}``), with no hint about
what went wrong. Cause: ``wrap_repo_op.wrapper`` in
``mcp_server_git.lean.registry_git`` does ``repo = Repo(repo_path)``;
GitPython's ``NoSuchPathError`` and ``InvalidGitRepositoryError`` stringify
to just the path, and ``GitLeanInterface._wrap_tool`` propagates
``str(e)`` verbatim as the ``error`` field.

Fix: ``wrapper`` now catches those two GitPython exceptions and re-raises a
``ValueError`` with an explicit, descriptive message. It RE-RAISES (rather
than returning a "❌ ..." string) on purpose: a raise is what ``_wrap_tool``
turns into an error-shaped result, so the envelope reports
``status: "error"`` on both transports (#232); returning a string would
silently downgrade it to ``status: "success"``.

Test strategy: end-to-end, via a real ``GitLeanInterface`` (all git tools
registered for real) driven through both the MCP ``execute_tool`` tool (via
fastmcp.Client's in-memory transport) and the HTTP ``execute_tool_direct``
path -- the same pattern used in ``test_meta_tools_errors.py``. Real
filesystem fixtures (``tmp_path``) are used throughout; no mocks.
"""

import pytest
from fastmcp import Client

pytest.importorskip("git")
from git import Repo  # noqa: E402

from mcp_server_git.lean.interface import GitLeanInterface  # noqa: E402


class MockService:
    """Mock service for testing with dynamic method support."""

    def __getattr__(self, name: str):
        return lambda **kwargs: {"result": f"mock_{name}", "params": kwargs}


def _make_interface() -> GitLeanInterface:
    return GitLeanInterface(
        git_service=MockService(),
        github_service=MockService(),
        azure_service=MockService(),
    )


class TestMCPPathBadRepoPathErrors:
    """MCP transport (``execute_tool``) surfaces a descriptive error for a
    bad ``repo_path``."""

    @pytest.mark.asyncio
    async def test_execute_tool_returns_descriptive_error_when_repo_path_does_not_exist(
        self, tmp_path
    ):
        missing_path = tmp_path / "missing"
        interface = _make_interface()

        async with Client(interface.app) as client:
            call_result = await client.call_tool(
                "execute_tool",
                {
                    "tool_name": "git_status",
                    "parameters": {"repo_path": str(missing_path)},
                },
            )
        envelope = call_result.data

        assert envelope["status"] == "error"
        assert envelope["error"] == f"repo_path does not exist: {missing_path}"

    @pytest.mark.asyncio
    async def test_execute_tool_returns_descriptive_error_when_repo_path_is_not_a_git_repository(
        self, tmp_path
    ):
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()
        interface = _make_interface()

        async with Client(interface.app) as client:
            call_result = await client.call_tool(
                "execute_tool",
                {
                    "tool_name": "git_status",
                    "parameters": {"repo_path": str(plain_dir)},
                },
            )
        envelope = call_result.data

        assert envelope["status"] == "error"
        assert envelope["error"] == f"repo_path is not a git repository: {plain_dir}"


class TestHTTPPathBadRepoPathErrors:
    """HTTP transport (``execute_tool_direct``) surfaces the same
    descriptive error text as the MCP path."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("subdir", "expected_template", "create_dir"),
        [
            ("missing", "repo_path does not exist: {path}", False),
            ("plain", "repo_path is not a git repository: {path}", True),
        ],
    )
    async def test_execute_tool_direct_returns_descriptive_error_when_repo_path_is_bad(
        self, tmp_path, subdir, expected_template, create_dir
    ):
        path = tmp_path / subdir
        if create_dir:
            path.mkdir()
        interface = _make_interface()

        result = await interface.execute_tool_direct(
            "git_status", {"repo_path": str(path)}
        )

        assert result["status"] == "error"
        assert result["error"] == expected_template.format(path=path)


class TestBadRepoPathErrorControl:
    """Control case: a real, initialized repo still succeeds, guarding
    against the try/except swallowing the good path."""

    @pytest.mark.asyncio
    async def test_execute_tool_returns_success_when_repo_path_is_a_real_repository(
        self, tmp_path
    ):
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        repo = Repo.init(repo_path, initial_branch="main")
        with repo.config_writer() as config:
            config.set_value("user", "name", "Test User")
            config.set_value("user", "email", "test@example.com")
        repo.index.commit("initial commit")

        interface = _make_interface()

        async with Client(interface.app) as client:
            call_result = await client.call_tool(
                "execute_tool",
                {
                    "tool_name": "git_status",
                    "parameters": {"repo_path": str(repo_path)},
                },
            )
        envelope = call_result.data

        assert envelope["status"] == "success"
