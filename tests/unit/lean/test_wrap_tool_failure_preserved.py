"""_wrap_tool keeps a ToolFailure an error after limiting or offloading."""

from mcp_server_git.lean._envelope import build_tool_envelope
from mcp_server_git.lean.interface import GitLeanInterface
from mcp_server_git.lean.response_offloader import ResponseOffloader
from mcp_server_git.utils.tool_failure import fail

_BIG = "❌ " + "boom " * 2000


def _make_interface() -> GitLeanInterface:
    iface = GitLeanInterface(git_service=None, github_service=None, azure_service=None)
    iface.token_limiter.default_limit = 50
    return iface


class TestWrapToolPreservesToolFailure:
    def test_wrap_tool_returns_error_envelope_when_failure_exceeds_token_limit(self):
        iface = _make_interface()
        iface.response_offloader = None

        wrapped = iface._wrap_tool(lambda: fail(_BIG), "git_stash_pop")
        envelope = build_tool_envelope("git_stash_pop", wrapped())

        assert envelope["status"] == "error"
        assert _BIG not in str(envelope)

    def test_wrap_tool_returns_error_envelope_when_failure_is_offloaded(self, tmp_path):
        iface = _make_interface()
        iface.response_offloader = ResponseOffloader(
            token_limiter=iface.token_limiter, offload_dir=str(tmp_path)
        )

        wrapped = iface._wrap_tool(lambda: fail(_BIG), "git_stash_pop")
        envelope = build_tool_envelope("git_stash_pop", wrapped())

        assert envelope["status"] == "error"
        assert envelope["result"]["offloaded"] is True
        assert envelope["result"]["full_output_path"]

    def test_wrap_tool_returns_success_when_plain_str_is_offloaded(self, tmp_path):
        iface = _make_interface()
        iface.response_offloader = ResponseOffloader(
            token_limiter=iface.token_limiter, offload_dir=str(tmp_path)
        )

        wrapped = iface._wrap_tool(lambda: _BIG, "git_stash_pop")
        envelope = build_tool_envelope("git_stash_pop", wrapped())

        assert envelope["status"] == "success"
