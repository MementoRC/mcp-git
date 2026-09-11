"""
Unit tests for execute_tool JSON parameter parsing in meta_tools.py.

Tests the coercion logic that handles parameters arriving as a JSON string
instead of a dict — a pattern some MCP clients use for serialization.

Bug (#151): github_create_issue fails when body contains markdown with backticks,
unescaped newlines, or other special characters that break naive json.loads().

Test strategy: test the _sanitize_json_string helper directly (no I/O, fast),
plus smoke-test the coercion path through a minimal standalone execute_tool
function that mirrors the production logic without the full GitLeanInterface.

Tests cover:
- _sanitize_json_string: newlines, tabs, carriage returns, mixed, already-escaped
- Coercion path: valid JSON string, broken JSON with newlines, backtick markdown,
  tabs, truly invalid string, parameters already a dict
"""

import json

import pytest

from src.mcp_server_git.lean.meta_tools import _sanitize_json_string

# ---------------------------------------------------------------------------
# Tests for _sanitize_json_string helper
# ---------------------------------------------------------------------------


class TestSanitizeJsonString:
    """Direct tests for the _sanitize_json_string escape helper."""

    def test_clean_json_unchanged(self):
        """A valid JSON string with no bare control chars passes through."""
        s = '{"key": "value", "num": 42}'
        assert _sanitize_json_string(s) == s

    def test_properly_escaped_newlines_unchanged(self):
        """Already-escaped \\n sequences are not double-escaped."""
        s = '{"body": "line1\\nline2"}'
        result = _sanitize_json_string(s)
        # Should still be parseable and value preserved
        parsed = json.loads(result)
        assert parsed["body"] == "line1\nline2"

    def test_bare_newline_in_string_value_escaped(self):
        """Bare newline inside a string value is replaced with \\n."""
        body = "line1\nline2"
        broken = f'{{"body": "{body}"}}'
        result = _sanitize_json_string(broken)
        parsed = json.loads(result)
        assert "line1" in parsed["body"]
        assert "line2" in parsed["body"]

    def test_bare_tab_in_string_value_escaped(self):
        """Bare tab inside a string value is replaced with \\t."""
        broken = '{"body": "col1\tcol2"}'
        result = _sanitize_json_string(broken)
        parsed = json.loads(result)
        assert "col1" in parsed["body"]
        assert "col2" in parsed["body"]

    def test_bare_carriage_return_in_string_value_escaped(self):
        """Bare carriage return inside a string value is replaced with \\r."""
        broken = '{"body": "line1\rline2"}'
        result = _sanitize_json_string(broken)
        parsed = json.loads(result)
        assert "line1" in parsed["body"]

    def test_mixed_control_chars_all_escaped(self):
        """Newline, tab, and carriage return all escaped in one pass."""
        broken = '{"body": "a\nb\tc\rd"}'
        result = _sanitize_json_string(broken)
        parsed = json.loads(result)
        body = parsed["body"]
        assert "a" in body
        assert "b" in body
        assert "c" in body
        assert "d" in body

    def test_multiple_string_fields_each_sanitized(self):
        """Each string field in a multi-field object is independently sanitized."""
        broken = '{"title": "My\nTitle", "body": "Line1\nLine2"}'
        result = _sanitize_json_string(broken)
        parsed = json.loads(result)
        assert "My" in parsed["title"]
        assert "Title" in parsed["title"]
        assert "Line1" in parsed["body"]
        assert "Line2" in parsed["body"]

    def test_markdown_code_fence_with_newlines(self):
        """Markdown code fence body with newlines is sanitized correctly."""
        code_body = (
            "## Summary\nUse `code` here.\n\n```python\ndef foo():\n    pass\n```"
        )
        broken = '{"body": "' + code_body + '"}'
        result = _sanitize_json_string(broken)
        # Must now be valid JSON
        parsed = json.loads(result)
        assert "Summary" in parsed["body"]
        assert "foo" in parsed["body"]

    def test_empty_string_value_unchanged(self):
        """Empty string values are handled without error."""
        s = '{"body": ""}'
        result = _sanitize_json_string(s)
        parsed = json.loads(result)
        assert parsed["body"] == ""

    def test_no_string_values_unchanged(self):
        """JSON with only non-string values passes through unchanged."""
        s = '{"count": 42, "flag": true, "ratio": 1.5}'
        result = _sanitize_json_string(s)
        parsed = json.loads(result)
        assert parsed["count"] == 42
        assert parsed["flag"] is True

    def test_null_and_other_c0_controls_escaped(self):
        """Should escape all C0 control characters forbidden by JSON spec."""
        raw = '{"body": "text\x00with\x08null\x0band\x0ccontrols"}'
        result = _sanitize_json_string(raw)
        parsed = json.loads(result)
        assert "text" in parsed["body"]
        assert "\x00" not in result  # literal null must not appear in JSON text


# ---------------------------------------------------------------------------
# Tests for the coercion path (string→dict) in execute_tool
#
# We test the logic directly via a standalone async function that mirrors
# exactly the coercion block at meta_tools.py:302-320, without spinning up
# a full GitLeanInterface (which is expensive and causes timeouts).
# ---------------------------------------------------------------------------


async def _coerce_parameters(parameters):
    """
    Mirror of the coercion block in execute_tool.

    Returns (parsed_dict, error_dict_or_None).
    """
    if isinstance(parameters, str):
        try:
            return json.loads(parameters), None
        except json.JSONDecodeError:
            try:
                sanitized = _sanitize_json_string(parameters)
                return json.loads(sanitized), None
            except (json.JSONDecodeError, Exception):
                return None, {
                    "status": "error",
                    "error": f"Parameters must be a JSON object, got unparseable string: {parameters[:100]}",
                }
    return parameters, None


class TestCoercionPath:
    """Tests for the string→dict coercion logic."""

    @pytest.mark.asyncio
    async def test_dict_parameters_pass_through(self):
        """Dict parameters are returned unchanged."""
        params = {"repo_owner": "owner", "repo_name": "repo", "title": "T"}
        result, err = await _coerce_parameters(params)
        assert err is None
        assert result == params

    @pytest.mark.asyncio
    async def test_valid_json_string_parsed(self):
        """A properly-escaped JSON string is parsed on the first attempt."""
        params = {"repo_owner": "owner", "repo_name": "repo", "title": "T"}
        result, err = await _coerce_parameters(json.dumps(params))
        assert err is None
        assert result == params

    @pytest.mark.asyncio
    async def test_json_string_with_bare_newlines_in_body(self):
        """
        Bug reproduction: body with literal newlines fails json.loads but
        succeeds after sanitization.
        """
        body = "## Summary\nLine one.\nLine two.\n\nParagraph."
        broken_json = (
            '{"repo_owner": "owner", "repo_name": "repo", '
            '"title": "Bug", "body": "' + body + '"}'
        )
        # Confirm input is broken JSON
        with pytest.raises(json.JSONDecodeError):
            json.loads(broken_json)

        result, err = await _coerce_parameters(broken_json)
        assert err is None, f"Expected success but got error: {err}"
        assert result["repo_owner"] == "owner"
        assert "Summary" in result["body"]

    @pytest.mark.asyncio
    async def test_json_string_with_markdown_backticks_and_newlines(self):
        """Body with markdown code fences is sanitized and parsed."""
        body = "Use `code` inline.\n\n```python\ndef foo():\n    return 1\n```"
        broken_json = (
            '{"repo_owner": "owner", "repo_name": "repo", '
            '"title": "Code example", "body": "' + body + '"}'
        )
        with pytest.raises(json.JSONDecodeError):
            json.loads(broken_json)

        result, err = await _coerce_parameters(broken_json)
        assert err is None, f"Expected success but got error: {err}"
        assert "foo" in result["body"]

    @pytest.mark.asyncio
    async def test_json_string_with_tabs_in_body(self):
        """Body with literal tab characters is sanitized and parsed."""
        body = "Step 1:\tdo this\nStep 2:\tdo that"
        broken_json = (
            '{"repo_owner": "owner", "repo_name": "repo", '
            '"title": "Steps", "body": "' + body + '"}'
        )
        with pytest.raises(json.JSONDecodeError):
            json.loads(broken_json)

        result, err = await _coerce_parameters(broken_json)
        assert err is None, f"Expected success but got error: {err}"
        assert "Step 1" in result["body"]

    @pytest.mark.asyncio
    async def test_truly_invalid_string_returns_error(self):
        """A completely non-JSON string returns an error dict, not an exception."""
        result, err = await _coerce_parameters("this is plain text, not JSON")
        assert result is None
        assert err is not None
        assert err["status"] == "error"
        assert (
            "unparseable" in err["error"].lower()
            or "parameters" in err["error"].lower()
        )

    @pytest.mark.asyncio
    async def test_error_message_truncates_long_input(self):
        """Error message truncates the input string to 100 chars for readability."""
        very_long_invalid = "x" * 500
        result, err = await _coerce_parameters(very_long_invalid)
        assert err is not None
        # The error should reference only the first 100 chars
        assert len(err["error"]) < 300
