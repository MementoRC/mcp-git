"""
Unit tests for the execute_tool error envelope fix (issue #196 defect 2).

Bug: interface.py::_wrap_tool catches exceptions raised by tool
implementations and returns an error-shaped dict
``{"error": str(e), "tool": tool_name, "success": False}`` instead of
raising. meta_tools.py::execute_tool then unconditionally wrapped *any*
returned value in ``{"status": "success", "result": ...}``, so a genuine
failure was reported as a contradictory
``{"status": "success", "result": {"error": ..., "success": False}}``
envelope.

Fix: execute_tool now inspects the result via the ``_is_error_result``
helper and reports ``status: "error"`` (with the message surfaced at the
top level) when the result matches the ``_wrap_tool`` error shape.

Test strategy: unit-test ``_is_error_result`` directly, then exercise the
real ``_build_envelope`` helper extracted from ``execute_tool`` in
meta_tools.py (not a test-local copy) so a regression that removes the
``if _is_error_result(result):`` branch from production code fails these
tests. An integration-style test drives a real
``GitLeanInterface._wrap_tool`` (which is NOT modified by this fix) to
confirm a raised exception still ends up correctly classified as an error
by the envelope logic. Finally, an end-to-end test drives the actual
registered ``execute_tool`` FastMCP tool (via ``fastmcp.Client`` in-memory
transport) to reproduce the exact issue #196 scenario.
"""

import pytest
from fastmcp import Client

from mcp_server_git.lean.interface import GitLeanInterface, ToolDefinition
from mcp_server_git.lean.meta_tools import _build_envelope, _is_error_result


class MockService:
    """Mock service for testing with dynamic method support."""

    def __getattr__(self, name: str):
        return lambda **kwargs: {"result": f"mock_{name}", "params": kwargs}


class TestIsErrorResult:
    """Direct unit tests for the _is_error_result helper."""

    def test_is_error_result_returns_true_when_wrap_tool_error_shape(self):
        """A dict with success is False and an error key is error-shaped."""
        result = {"error": "boom", "tool": "x", "success": False}
        assert _is_error_result(result) is True

    def test_is_error_result_returns_false_when_success_true_and_error_present(self):
        """A dict carrying 'error' as data with success True is not an error."""
        result = {"error": "log line from CI", "success": True}
        assert _is_error_result(result) is False

    def test_is_error_result_returns_false_when_error_present_without_success_key(self):
        """A dict with an 'error' key but no 'success' key is not an error."""
        result = {"error": "some data field"}
        assert _is_error_result(result) is False

    def test_is_error_result_returns_false_when_success_is_zero_not_false(self):
        """success: 0 is falsy but not identical to False; must not trigger."""
        result = {"error": "boom", "success": 0}
        assert _is_error_result(result) is False

    def test_is_error_result_returns_false_when_no_error_key(self):
        """A dict with success False but no 'error' key is not error-shaped."""
        result = {"success": False, "message": "no error field here"}
        assert _is_error_result(result) is False

    def test_is_error_result_returns_false_when_result_is_not_dict(self):
        """Non-dict results (str, list, None) are never error-shaped."""
        assert _is_error_result("plain string") is False
        assert _is_error_result(["error", False]) is False
        assert _is_error_result(None) is False


class TestExecuteToolEnvelope:
    """Tests for the envelope status derived from a tool's raw result."""

    def test_build_envelope_returns_error_status_when_wrap_tool_error_shape(self):
        """execute_tool reports status 'error' for a _wrap_tool-style failure."""
        result = {"error": "boom", "tool": "git_status", "success": False}
        envelope = _build_envelope("git_status", result)

        assert envelope["status"] == "error"
        assert envelope["error"] == "boom"
        assert envelope["result"] == result
        assert envelope["execution_mode"] == "lean_mcp_dynamic"

    def test_build_envelope_returns_success_status_for_dict_result(self):
        """A normal successful dict result still yields status 'success'."""
        result = {"branch": "main", "clean": True}
        envelope = _build_envelope("git_status", result)

        assert envelope["status"] == "success"
        assert envelope["result"] == result
        assert "error" not in envelope

    def test_build_envelope_returns_success_status_for_string_result(self):
        """A normal successful string result still yields status 'success'."""
        result = "operation completed"
        envelope = _build_envelope("git_status", result)

        assert envelope["status"] == "success"
        assert envelope["result"] == result

    def test_build_envelope_returns_success_when_error_key_present_but_success_true(self):
        """No false positive: 'error' as legitimate data must stay 'success'."""
        result = {"error": "some CI job reported an error", "success": True, "log": "..."}
        envelope = _build_envelope("azure_get_build_logs", result)

        assert envelope["status"] == "success"
        assert envelope["result"] == result

    def test_build_envelope_returns_success_when_error_key_present_no_success_key(self):
        """No false positive: 'error' data without a 'success' key stays 'success'."""
        result = {"error": "no such branch in log output"}
        envelope = _build_envelope("azure_get_build_logs", result)

        assert envelope["status"] == "success"
        assert envelope["result"] == result


class TestWrapToolIntegrationWithEnvelope:
    """Integration: a real _wrap_tool error dict flows through to status 'error'."""

    def setup_method(self):
        self.interface = GitLeanInterface(
            git_service=MockService(),
            github_service=MockService(),
            azure_service=MockService(),
        )

    def test_build_envelope_returns_error_status_when_implementation_raises_typeerror(self):
        """
        Original issue reproduction: a TypeError raised by a tool implementation
        is converted by the real (unmodified) _wrap_tool into an error dict, and
        the envelope logic correctly classifies it as status 'error'.
        """

        def failing_impl(**kwargs):
            raise TypeError("unexpected keyword argument 'foo'")

        wrapped = self.interface._wrap_tool(failing_impl, "failing_tool")
        raw_result = wrapped()

        assert raw_result == {
            "error": "unexpected keyword argument 'foo'",
            "tool": "failing_tool",
            "success": False,
        }

        envelope = _build_envelope("failing_tool", raw_result)

        assert envelope["status"] == "error"
        assert envelope["error"] == "unexpected keyword argument 'foo'"
        assert envelope["result"] == raw_result

    @pytest.mark.asyncio
    async def test_build_envelope_returns_error_status_when_async_implementation_raises(self):
        """Async variant: raised exception in an async implementation is also caught."""

        async def failing_async_impl(**kwargs):
            raise ValueError("async failure")

        wrapped = self.interface._wrap_tool(failing_async_impl, "failing_async_tool")
        raw_result = await wrapped()

        envelope = _build_envelope("failing_async_tool", raw_result)

        assert envelope["status"] == "error"
        assert envelope["error"] == "async failure"


class TestExecuteToolEndToEnd:
    """
    End-to-end reproduction of issue #196: drives the actual registered
    ``execute_tool`` FastMCP tool (not a helper mirror) via ``fastmcp.Client``
    using FastMCP's in-memory transport (passing the ``FastMCP`` app instance
    directly to ``Client`` connects without any network/process boundary).

    This closes the gap where deleting the
    ``if _is_error_result(result):`` branch from the real ``execute_tool``
    closure would not be caught by any test.
    """

    @pytest.mark.asyncio
    async def test_execute_tool_returns_error_status_when_implementation_raises_typeerror(
        self,
    ):
        """
        Original issue #196 reproduction: a tool implementation raises
        TypeError("git_log() got an unexpected keyword argument 'format'").
        The registered execute_tool must report status 'error' (not
        'success') and preserve the original error text in the result.
        """
        interface = GitLeanInterface(
            git_service=MockService(),
            github_service=MockService(),
            azure_service=MockService(),
        )

        def failing_git_log(**kwargs):
            raise TypeError(
                "git_log() got an unexpected keyword argument 'format'"
            )

        interface.register_tool(
            ToolDefinition(
                name="git_log_broken",
                implementation=failing_git_log,
                description="Reproduces issue #196 for end-to-end coverage",
                schema={"type": "object", "properties": {}},
                domain="test",
                complexity="focused",
            )
        )

        async with Client(interface.app) as client:
            call_result = await client.call_tool(
                "execute_tool",
                {"tool_name": "git_log_broken", "parameters": {}},
            )

        envelope = call_result.data

        assert envelope["status"] == "error"
        assert (
            "git_log() got an unexpected keyword argument 'format'"
            in envelope["error"]
        )
        assert envelope["result"]["success"] is False
        assert (
            "git_log() got an unexpected keyword argument 'format'"
            in envelope["result"]["error"]
        )
