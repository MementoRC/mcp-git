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

from mcp_server_git.lean.interface import GitLeanInterface  # noqa: E402
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
