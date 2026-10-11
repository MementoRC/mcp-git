"""ToolFailure is the explicit opt-in for status "error" (extends #232 pin).

Plain strings, even "❌"-prefixed ones, stay "success"; only ToolFailure
(via ``fail``) is reported as an error. Includes an end-to-end check
through the real stash operation on a temp repo.
"""

import pytest
from fastmcp import Client

pytest.importorskip("git")
from git import Repo  # noqa: E402

from mcp_server_git.lean._envelope import build_tool_envelope  # noqa: E402
from mcp_server_git.lean.interface import GitLeanInterface  # noqa: E402
from mcp_server_git.lean.meta_tools import _build_envelope  # noqa: E402
from mcp_server_git.utils.tool_failure import fail  # noqa: E402


class MockService:
    def __getattr__(self, name: str):
        return lambda **kwargs: {"result": f"mock_{name}", "params": kwargs}


def _make_interface() -> GitLeanInterface:
    return GitLeanInterface(
        git_service=MockService(),
        github_service=MockService(),
        azure_service=MockService(),
    )


class TestBuildEnvelopeToolFailure:
    def test_build_tool_envelope_returns_error_when_result_is_tool_failure(self):
        envelope = build_tool_envelope("git_stash_pop", fail("❌ x"))

        assert envelope["status"] == "error"
        assert envelope["error"] == "❌ x"
        assert envelope["result"] == "❌ x"
        assert type(envelope["result"]) is str
        assert "execution_mode" not in envelope

    def test_mcp_build_envelope_returns_error_when_result_is_tool_failure(self):
        envelope = _build_envelope("git_stash_pop", fail("❌ x"))

        assert envelope["status"] == "error"
        assert envelope["error"] == "❌ x"
        assert type(envelope["result"]) is str
        assert envelope["execution_mode"] == "lean_mcp_dynamic"

    def test_build_tool_envelope_returns_success_when_plain_error_emoji_str(self):
        envelope = build_tool_envelope("git_stash_pop", "❌ x")

        assert envelope["status"] == "success"
        assert envelope["result"] == "❌ x"


class TestStashFailureEndToEnd:
    @pytest.mark.asyncio
    async def test_execute_tool_direct_returns_error_when_stash_pop_has_no_stash(
        self, tmp_path
    ):
        Repo.init(tmp_path)

        envelope = await _make_interface().execute_tool_direct(
            "git_stash_pop", {"repo_path": str(tmp_path)}
        )

        assert envelope["status"] == "error"
        assert envelope["error"].startswith("❌ Stash pop failed")

    @pytest.mark.asyncio
    async def test_execute_tool_returns_error_when_stash_pop_has_no_stash(
        self, tmp_path
    ):
        Repo.init(tmp_path)

        async with Client(_make_interface().app) as client:
            call_result = await client.call_tool(
                "execute_tool",
                {
                    "tool_name": "git_stash_pop",
                    "parameters": {"repo_path": str(tmp_path)},
                },
            )

        assert call_result.data["status"] == "error"
        assert call_result.data["error"].startswith("❌ Stash pop failed")
