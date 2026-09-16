"""
Unit tests for the unknown-kwarg error path in execute_tool (issue #227 Part 2).

Bug: when a caller passes a keyword argument that a tool implementation does
not accept (e.g. a deprecated/renamed alias like "path" instead of "files"),
the implementation raises a bare TypeError ("git_log() got an unexpected
keyword argument 'path'") that the generic ``except Exception`` branch in
``execute_tool`` (meta_tools.py) surfaces as an unhelpful string with no hint
about what the caller should have sent instead.

Fix: every registered tool implementation is wrapped by
``GitLeanInterface._wrap_tool`` (in ``register_tool``), which already
catches the TypeError and converts it into an error-shaped dict
(``{"error": ..., "success": False}``) rather than letting it propagate -
so the raw exception never reaches ``execute_tool``'s own try/except. The
single chokepoint shared by every git/github/azure tool is therefore
``_build_envelope``, which now detects "unexpected keyword argument" in
the error message and adds a ``valid_parameters`` list (mirroring the
existing ``ValidationError`` branch) so the caller can self-correct.

Test strategy: end-to-end, via a real ``GitLeanInterface`` (all git tools
registered for real) driven through the actual registered ``execute_tool``
FastMCP tool over ``fastmcp.Client``'s in-memory transport - the same
pattern used in test_execute_tool_error_envelope.py's
``TestExecuteToolEndToEnd``. A real, minimal git repo is used as
``repo_path`` so execution reaches the implementation's own signature check
(param validation via JSON Schema does not reject unknown properties, since
none of these tools set ``additionalProperties: false``).
"""

import pytest
from fastmcp import Client

pytest.importorskip("git")
from git import Repo  # noqa: E402

from mcp_server_git.lean.interface import GitLeanInterface, ToolDefinition  # noqa: E402
from mcp_server_git.lean.meta_tools import _build_envelope  # noqa: E402


class TestBuildEnvelopeUnknownKwarg:
    """Direct unit tests for _build_envelope's valid_parameters enrichment."""

    def test_adds_valid_parameters_when_message_mentions_unexpected_keyword(self):
        """An error result whose message matches the unexpected-keyword
        phrasing gets a 'valid_parameters' list built from the schema."""
        result = {
            "error": "git_log() got an unexpected keyword argument 'path'",
            "tool": "git_log",
            "success": False,
        }
        schema = {"properties": {"repo_path": {}, "files": {}, "grep": {}}}

        envelope = _build_envelope("git_log", result, schema)

        assert envelope["status"] == "error"
        assert envelope["valid_parameters"] == ["repo_path", "files", "grep"]

    def test_omits_valid_parameters_when_schema_not_provided(self):
        """Without a schema argument, no valid_parameters key is added."""
        result = {"error": "boom", "tool": "git_log", "success": False}

        envelope = _build_envelope("git_log", result)

        assert envelope["status"] == "error"
        assert "valid_parameters" not in envelope

    def test_omits_valid_parameters_when_message_does_not_match(self):
        """An unrelated error message does not trigger the enrichment even
        when a schema is provided."""
        result = {"error": "boom", "tool": "git_log", "success": False}
        schema = {"properties": {"repo_path": {}}}

        envelope = _build_envelope("git_log", result, schema)

        assert envelope["status"] == "error"
        assert "valid_parameters" not in envelope


class MockService:
    """Mock service for testing with dynamic method support."""

    def __getattr__(self, name: str):
        return lambda **kwargs: {"result": f"mock_{name}", "params": kwargs}


class TestUnknownKwargError:
    """execute_tool surfaces valid parameter names for an unexpected kwarg."""

    @pytest.mark.asyncio
    async def test_execute_tool_lists_valid_parameters_for_unknown_kwarg(
        self, tmp_path
    ):
        """Passing an unknown kwarg to git_log returns an error listing
        valid parameter names, including 'files' and 'repo_path'.

        Uses a non-path-shaped unknown kwarg name so the failure exercises
        the unexpected-keyword-argument enrichment in ``_build_envelope``
        rather than the unrelated relative-path parameter check, which
        independently rejects any *path*-named parameter before the
        implementation is even called.
        """
        # Arrange
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        repo = Repo.init(repo_path, initial_branch="main")
        with repo.config_writer() as config:
            config.set_value("user", "name", "Test User")
            config.set_value("user", "email", "test@example.com")
        repo.index.commit("initial commit")

        interface = GitLeanInterface(
            git_service=MockService(),
            github_service=MockService(),
            azure_service=MockService(),
        )

        # Act
        async with Client(interface.app) as client:
            call_result = await client.call_tool(
                "execute_tool",
                {
                    "tool_name": "git_log",
                    "parameters": {"repo_path": str(repo_path), "verbose": True},
                },
            )

        envelope = call_result.data

        # Assert
        assert envelope["status"] == "error"
        assert "unexpected keyword argument" in envelope["error"]
        assert "valid_parameters" in envelope
        assert "files" in envelope["valid_parameters"]
        assert "repo_path" in envelope["valid_parameters"]


class TestExecuteToolDirectUnknownKwarg:
    """HTTP-transport ``execute_tool_direct`` surfaces the same
    ``valid_parameters`` hint as the MCP ``execute_tool`` path.

    Regression for the gap identified while verifying issue #227 Part 2:
    the reporter's environment was "mcp-git 0.6.3, HTTP (SSE) transport",
    which drives ``GitLeanInterface.execute_tool_direct`` (interface.py),
    not the FastMCP-registered ``execute_tool`` meta-tool exercised by
    ``TestUnknownKwargError`` above. ``execute_tool_direct`` built its own
    response and its ``except Exception`` branch never even sees the
    unknown-kwarg ``TypeError``, because ``_wrap_tool`` (see
    ``register_tool``) already caught it and returned an error-shaped dict
    -- so the enrichment has to be applied to that returned result, not
    just to a caught exception.
    """

    @staticmethod
    def _make_interface() -> GitLeanInterface:
        return GitLeanInterface(
            git_service=MockService(),
            github_service=MockService(),
            azure_service=MockService(),
        )

    @staticmethod
    def _init_repo(tmp_path):
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        repo = Repo.init(repo_path, initial_branch="main")
        with repo.config_writer() as config:
            config.set_value("user", "name", "Test User")
            config.set_value("user", "email", "test@example.com")
        repo.index.commit("initial commit")
        return repo_path

    @pytest.mark.asyncio
    async def test_execute_tool_direct_lists_valid_parameters_for_unknown_kwarg(
        self, tmp_path
    ):
        """execute_tool_direct("git_log", ...) with an unknown kwarg
        returns status "error", a message mentioning the unexpected
        keyword, and a valid_parameters list including "files" and
        "repo_path"."""
        repo_path = self._init_repo(tmp_path)
        interface = self._make_interface()

        # Act
        result = await interface.execute_tool_direct(
            "git_log",
            {"repo_path": str(repo_path), "verbose": True},
        )

        # Assert
        assert result["status"] == "error"
        assert "unexpected keyword argument" in result["error"]
        assert "valid_parameters" in result
        assert "files" in result["valid_parameters"]
        assert "repo_path" in result["valid_parameters"]

    @pytest.mark.asyncio
    async def test_execute_tool_direct_matches_mcp_path_valid_parameters(
        self, tmp_path
    ):
        """The HTTP direct path and the MCP execute_tool path return the
        identical valid_parameters list for the same unknown-kwarg error,
        locking the two transports to the same enrichment behaviour."""
        repo_path = self._init_repo(tmp_path)
        interface = self._make_interface()
        params = {"repo_path": str(repo_path), "verbose": True}

        # Act
        direct_result = await interface.execute_tool_direct("git_log", params)
        async with Client(interface.app) as client:
            mcp_call = await client.call_tool(
                "execute_tool",
                {"tool_name": "git_log", "parameters": params},
            )
        mcp_result = mcp_call.data

        # Assert
        assert direct_result["status"] == mcp_result["status"] == "error"
        assert direct_result["valid_parameters"] == mcp_result["valid_parameters"]


def _generic_error_result() -> dict:
    """A ``_wrap_tool``-shaped error result that is NOT an unexpected-kwarg
    failure -- the core issue #232 regression case (every other
    error-shaped result used to be misreported as "status": "success" by
    ``execute_tool_direct``)."""
    return {
        "error": "Repository not found",
        "tool": "fake_generic_error_tool",
        "success": False,
    }


def _make_interface_with_generic_error_tool() -> GitLeanInterface:
    """A real GitLeanInterface with one extra tool registered whose
    implementation always returns a generic error-shaped dict, so both
    transports can be driven through the same, controlled failure."""
    interface = GitLeanInterface(
        git_service=MockService(),
        github_service=MockService(),
        azure_service=MockService(),
    )
    interface.register_tool(
        ToolDefinition(
            name="fake_generic_error_tool",
            implementation=lambda **kwargs: _generic_error_result(),
            description="Test double returning a generic (non-kwarg) error-shaped result.",
            schema={"type": "object", "properties": {}},
            domain="git",
        )
    )
    return interface


class TestExecuteToolDirectGenericErrorResult:
    """Core regression for issue #232: ``execute_tool_direct`` must promote
    ANY ``_wrap_tool``-shaped error result to "status": "error", not just
    the unexpected-kwarg case handled by issue #227 Part 2."""

    @pytest.mark.asyncio
    async def test_execute_tool_direct_returns_error_status_for_generic_error_result(
        self,
    ):
        interface = _make_interface_with_generic_error_tool()

        result = await interface.execute_tool_direct("fake_generic_error_tool", {})

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_execute_tool_direct_surfaces_error_message_and_original_result(
        self,
    ):
        """The error message is surfaced at the top level, and the
        original error-shaped result dict is still present under
        "result"."""
        interface = _make_interface_with_generic_error_tool()

        result = await interface.execute_tool_direct("fake_generic_error_tool", {})

        assert result["error"] == "Repository not found"
        assert result["result"] == _generic_error_result()


class TestErrorDetectionStaysStrictForExecuteToolDirect:
    """The issue #232 fix must not loosen ``_is_error_result``: a dict that
    merely carries an "error" key as *data* (not the ``_wrap_tool`` failure
    shape) still yields "status": "success", avoiding false positives on
    payloads describing someone else's error."""

    @staticmethod
    def _make_interface(name: str, payload: dict) -> GitLeanInterface:
        interface = GitLeanInterface(
            git_service=MockService(),
            github_service=MockService(),
            azure_service=MockService(),
        )
        interface.register_tool(
            ToolDefinition(
                name=name,
                implementation=lambda **kwargs: payload,
                description="Test double carrying an 'error' key as data.",
                schema={"type": "object", "properties": {}},
                domain="git",
            )
        )
        return interface

    @pytest.mark.asyncio
    async def test_execute_tool_direct_success_when_error_key_present_and_success_true(
        self,
    ):
        interface = self._make_interface(
            "fake_data_error_success_true",
            {"error": "someone else's error, as data", "success": True},
        )

        result = await interface.execute_tool_direct("fake_data_error_success_true", {})

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_execute_tool_direct_success_when_error_key_present_no_success_key(
        self,
    ):
        interface = self._make_interface(
            "fake_data_error_no_success_key",
            {"error": "a log line mentions an error"},
        )

        result = await interface.execute_tool_direct(
            "fake_data_error_no_success_key", {}
        )

        assert result["status"] == "success"


class TestMCPAndHTTPAgreeOnGenericErrorEnvelope:
    """Lock the two transports to the same status/execution_mode behaviour
    for a generic error-shaped result, mirroring
    TestExecuteToolDirectUnknownKwarg's cross-transport lock above."""

    @pytest.mark.asyncio
    async def test_mcp_and_http_paths_agree_on_status_for_generic_error_result(self):
        interface = _make_interface_with_generic_error_tool()

        direct_result = await interface.execute_tool_direct(
            "fake_generic_error_tool", {}
        )
        async with Client(interface.app) as client:
            mcp_call = await client.call_tool(
                "execute_tool",
                {"tool_name": "fake_generic_error_tool", "parameters": {}},
            )
        mcp_result = mcp_call.data

        assert direct_result["status"] == mcp_result["status"] == "error"
        assert direct_result["error"] == mcp_result["error"]

    @pytest.mark.asyncio
    async def test_mcp_envelope_has_execution_mode_http_envelope_does_not(self):
        interface = _make_interface_with_generic_error_tool()

        direct_result = await interface.execute_tool_direct(
            "fake_generic_error_tool", {}
        )
        async with Client(interface.app) as client:
            mcp_call = await client.call_tool(
                "execute_tool",
                {"tool_name": "fake_generic_error_tool", "parameters": {}},
            )
        mcp_result = mcp_call.data

        assert mcp_result["execution_mode"] == "lean_mcp_dynamic"
        assert "execution_mode" not in direct_result


def _error_emoji_string_result() -> str:
    """A plain string result matching the ~250 real git/github/azure tool
    call sites that report failure by RETURNING "❌ ..." instead of
    raising -- the highest-risk unguarded shape in the envelope module."""
    return "❌ Repository not found"


class TestBuildEnvelopeDoesNotSniffNonDictResults:
    """Pin the `isinstance(result, dict)` early return in `_is_error_result`
    (issue #232): no non-dict result -- string or otherwise -- may ever be
    treated as error-shaped, regardless of its content. Mutation testing
    found that loosening this check for "❌"-prefixed strings killed
    zero tests; these two pin that gap directly against `_build_envelope`."""

    def test_error_emoji_string_result_is_not_treated_as_error_shaped(self):
        """A plain string result starting with the "❌" glyph used by
        ~250 string-returning tool call sites must stay "status": "success",
        with the string carried untouched under "result". If
        `_is_error_result` were ever loosened to sniff string content for
        this marker, every one of those ~250 tools would start reporting
        "status": "error" -- including tools that legitimately return a
        string payload containing "❌" as DATA (e.g. a CI-log excerpt
        describing someone else's failure), not as a failure signal of
        their own. Do not "fix" this test to expect "error"."""
        result = _error_emoji_string_result()

        envelope = _build_envelope("fake_string_error_tool", result)

        assert envelope["status"] == "success"
        assert envelope["result"] == result
        assert "error" not in envelope

    def test_non_dict_non_string_result_is_not_treated_as_error_shaped(self):
        """A non-dict, non-string result (list, None) is never error-shaped,
        guarding the `isinstance(result, dict)` early return in
        `_is_error_result` generally -- not just for the "❌"-string
        case above."""
        list_envelope = _build_envelope("fake_list_result_tool", ["error", False])
        none_envelope = _build_envelope("fake_none_result_tool", None)

        assert list_envelope["status"] == "success"
        assert list_envelope["result"] == ["error", False]
        assert none_envelope["status"] == "success"
        assert none_envelope["result"] is None


def _make_interface_with_error_emoji_string_tool() -> GitLeanInterface:
    """A real GitLeanInterface with one extra tool registered whose
    implementation always returns a "❌"-prefixed string result,
    matching the ~250 real git/github/azure tools that report failure this
    way instead of raising."""
    interface = GitLeanInterface(
        git_service=MockService(),
        github_service=MockService(),
        azure_service=MockService(),
    )
    interface.register_tool(
        ToolDefinition(
            name="fake_error_emoji_string_tool",
            implementation=lambda **kwargs: _error_emoji_string_result(),
            description="Test double returning a ❌-prefixed string result.",
            schema={"type": "object", "properties": {}},
            domain="git",
        )
    )
    return interface


class TestMCPAndHTTPAgreeOnErrorEmojiStringResult:
    """Lock the two transports to the same "status": "success" behaviour
    for a "❌"-prefixed string result, mirroring
    TestMCPAndHTTPAgreeOnGenericErrorEnvelope above but for the
    string-returning-tool case rather than the dict-error case. Roughly
    250 tool call sites across git/github/azure report failure by
    returning such a string; if `_is_error_result` is ever loosened to
    sniff string content, both transports must break together, not just
    one."""

    @pytest.mark.asyncio
    async def test_error_emoji_string_result_is_not_treated_as_error_shaped_on_both_transports(
        self,
    ):
        """Neither `execute_tool_direct` (HTTP) nor `execute_tool` (MCP)
        may promote a "❌"-prefixed string result to "status": "error";
        both must agree on "success" with the string untouched under
        "result". Do not "fix" this test to expect "error" -- see
        `_is_error_result`'s docstring for the deliberate design rationale."""
        interface = _make_interface_with_error_emoji_string_tool()

        direct_result = await interface.execute_tool_direct(
            "fake_error_emoji_string_tool", {}
        )
        async with Client(interface.app) as client:
            mcp_call = await client.call_tool(
                "execute_tool",
                {"tool_name": "fake_error_emoji_string_tool", "parameters": {}},
            )
        mcp_result = mcp_call.data

        expected = _error_emoji_string_result()
        assert direct_result["status"] == mcp_result["status"] == "success"
        assert direct_result["result"] == mcp_result["result"] == expected
