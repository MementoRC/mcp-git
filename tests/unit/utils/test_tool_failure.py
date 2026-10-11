"""Unit tests for the explicit ToolFailure type."""

from mcp_server_git.utils.tool_failure import ToolFailure, fail


class TestToolFailure:
    def test_tool_failure_is_str_when_constructed(self):
        assert isinstance(ToolFailure("❌ x"), str)

    def test_tool_failure_equals_text_when_compared_to_plain_str(self):
        assert ToolFailure("❌ x") == "❌ x"

    def test_fail_returns_tool_failure_when_given_message(self):
        failure = fail("❌ boom")

        assert type(failure) is ToolFailure
        assert failure == "❌ boom"
