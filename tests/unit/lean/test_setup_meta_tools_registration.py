"""Characterization tests for setup_meta_tools registrations (issue #255)."""

import inspect

import pytest

from mcp_server_git.lean.interface import ToolDefinition
from mcp_server_git.lean.meta_tools import setup_meta_tools

_SCHEMA = {
    "type": "object",
    "properties": {"x": {"type": "integer"}, "repo_path": {"type": "string"}},
    "required": ["x"],
}


class _RecordingApp:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(fn):
            self.tools[fn.__name__] = fn
            return fn

        return register


class _Interface:
    def __init__(self, registry):
        self.app = _RecordingApp()
        self.tool_registry = registry
        self._schema_cache = {}

    def _validate_path_parameters(self, parameters, relative_path_params=None):
        if parameters.get("repo_path") == "relative":
            raise ValueError("repo_path must be absolute")


def _def(name, impl, domain="git", complexity="core"):
    return ToolDefinition(
        name, impl, f"{name} description", _SCHEMA, domain=domain, complexity=complexity
    )


async def _async_impl(x, repo_path="."):
    return f"async:{x}"


def _sync_impl(x, repo_path="."):
    return f"sync:{x}"


def _failing_impl(x, repo_path="."):
    raise RuntimeError("kaput")


@pytest.fixture
def tools():
    registry = {
        "git_status": _def("git_status", _sync_impl),
        "github_pr": _def("github_pr", _async_impl, "github", "focused"),
        "azure_logs": _def("azure_logs", _sync_impl, "azure", "advanced"),
        "git_boom": _def("git_boom", _failing_impl),
    }
    interface = _Interface(registry)
    setup_meta_tools(interface)
    return interface.app.tools


def test_setup_meta_tools_registers_four_tools_when_called():
    interface = _Interface({})
    setup_meta_tools(interface)
    assert list(interface.app.tools) == [
        "discover_tools",
        "get_tool_spec",
        "execute_tool",
        "server_info",
    ]


def test_setup_meta_tools_keeps_signatures_and_docstrings_when_registered(tools):
    assert str(inspect.signature(tools["discover_tools"])) == (
        "(pattern: str = '') -> dict[str, typing.Any]"
    )
    assert str(inspect.signature(tools["get_tool_spec"])) == (
        "(tool_name: str) -> dict[str, typing.Any]"
    )
    assert str(inspect.signature(tools["execute_tool"])) == (
        "(tool_name: str, parameters: dict[str, typing.Any]) -> dict[str, typing.Any]"
    )
    assert inspect.iscoroutinefunction(tools["execute_tool"])
    assert (
        tools["discover_tools"]
        .__doc__.strip()
        .startswith("[STEP 1] Discover available Git, GitHub, and Azure DevOps tools.")
    )
    assert (
        tools["get_tool_spec"]
        .__doc__.strip()
        .startswith("[STEP 2] Get detailed schema and parameters for a specific tool.")
    )
    assert (
        tools["execute_tool"]
        .__doc__.strip()
        .startswith("[STEP 3] Execute a Git, GitHub, or Azure DevOps operation.")
    )
    assert (
        tools["server_info"]
        .__doc__.strip()
        .startswith("Returns server metadata for LLM harnesses and clients.")
    )


def test_discover_tools_lists_all_with_domain_counts_when_pattern_empty(tools):
    result = tools["discover_tools"]()
    assert result["available_tools"] == [
        {
            "name": "git_status",
            "description": "git_status description",
            "domain": "git",
            "complexity": "core",
        },
        {
            "name": "github_pr",
            "description": "github_pr description",
            "domain": "github",
            "complexity": "focused",
        },
        {
            "name": "azure_logs",
            "description": "azure_logs description",
            "domain": "azure",
            "complexity": "advanced",
        },
        {
            "name": "git_boom",
            "description": "git_boom description",
            "domain": "git",
            "complexity": "core",
        },
    ]
    assert result["total_tools"] == 4
    assert result["filtered_count"] == 4
    assert result["domains"] == {"git": 2, "github": 1, "azure": 1}
    assert result["context_saving"] == "~2.0K tokens saved vs traditional MCP"
    assert result["issues"] == "https://github.com/MementoRC/mcp-git/issues"


def test_discover_tools_filters_case_insensitively_when_pattern_given(tools):
    result = tools["discover_tools"]("GITHUB")
    assert [t["name"] for t in result["available_tools"]] == ["github_pr"]
    assert result["filtered_count"] == 1
    assert result["total_tools"] == 4


def test_discover_tools_ignores_blank_pattern_when_only_whitespace(tools):
    assert tools["discover_tools"]("   ")["filtered_count"] == 4


def test_get_tool_spec_returns_definition_when_tool_registered(tools):
    assert tools["get_tool_spec"]("github_pr") == {
        "name": "github_pr",
        "description": "github_pr description",
        "domain": "github",
        "complexity": "focused",
        "schema": _SCHEMA,
        "examples": [],
        "usage_note": "Execute with: execute_tool('github_pr', parameters)",
    }


def test_get_tool_spec_returns_error_when_tool_unknown(tools):
    assert tools["get_tool_spec"]("nope") == {
        "error": "Tool 'nope' not found",
        "available_tools": ["git_status", "github_pr", "azure_logs", "git_boom"],
        "suggestion": "Use discover_tools() to find available tools",
    }


async def test_execute_tool_returns_error_when_tool_unknown(tools):
    result = await tools["execute_tool"]("nope", {})
    assert result["error"] == "Tool 'nope' not found"
    assert result["suggestion"] == "Use discover_tools() to find available tools"


async def test_execute_tool_returns_envelope_when_sync_impl(tools):
    result = await tools["execute_tool"]("git_status", {"x": 1})
    assert result == {
        "tool": "git_status",
        "status": "success",
        "result": "sync:1",
        "execution_mode": "lean_mcp_dynamic",
    }


async def test_execute_tool_awaits_impl_when_async_impl(tools):
    result = await tools["execute_tool"]("github_pr", {"x": 2})
    assert result["result"] == "async:2"


async def test_execute_tool_parses_parameters_when_json_string(tools):
    result = await tools["execute_tool"]("git_status", '{"x": 3}')
    assert result["result"] == "sync:3"


async def test_execute_tool_sanitizes_parameters_when_raw_newline_in_string(tools):
    result = await tools["execute_tool"]("git_status", '{"x": 4, "repo_path": "a\nb"}')
    assert result["status"] == "success"


async def test_execute_tool_returns_error_when_string_unparseable(tools):
    result = await tools["execute_tool"]("git_status", "x" * 150)
    assert result == {
        "tool": "git_status",
        "status": "error",
        "error": "Parameters must be a JSON object, got unparseable string: "
        + "x" * 100,
    }


async def test_execute_tool_returns_validation_error_when_required_missing(tools):
    result = await tools["execute_tool"]("git_status", {})
    assert result == {
        "tool": "git_status",
        "status": "error",
        "error": "Parameter validation failed: 'x' is a required property",
        "validation_path": [],
        "schema_path": ["required"],
        "valid_parameters": ["x", "repo_path"],
    }


async def test_execute_tool_returns_validation_paths_when_type_wrong(tools):
    result = await tools["execute_tool"]("git_status", {"x": "s"})
    assert (
        result["error"] == "Parameter validation failed: 's' is not of type 'integer'"
    )
    assert result["validation_path"] == ["x"]
    assert result["schema_path"] == ["properties", "x", "type"]


async def test_execute_tool_returns_path_error_when_path_validation_fails(tools):
    result = await tools["execute_tool"](
        "git_status", {"x": 1, "repo_path": "relative"}
    )
    assert result == {
        "tool": "git_status",
        "status": "error",
        "error": "repo_path must be absolute",
        "execution_mode": "lean_mcp_dynamic",
    }


async def test_execute_tool_returns_error_when_impl_raises(tools):
    result = await tools["execute_tool"]("git_boom", {"x": 1})
    assert result == {
        "tool": "git_boom",
        "status": "error",
        "error": "kaput",
        "execution_mode": "lean_mcp_dynamic",
    }


def test_server_info_returns_metadata_when_called(tools):
    info = tools["server_info"]()
    assert info["total_tools"] == 4
    assert info["transport"] == "HTTP (SSE)"
