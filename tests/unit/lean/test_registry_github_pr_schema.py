"""Regression tests for stale hand-written PR schemas (GitHub issue #238).

github_update_pr and github_create_pr advertised hand-written inline
schemas that had drifted from their handlers' real parameters —
github_create_pr's schema omitted ``head`` and ``base``, two required
positional params. Both are now generated from their pydantic models via
``model_json_schema()``, which keeps the advertised schema and the
handler signature from drifting apart.

Follows the contract-test style of
tests/unit/lean/test_registry_git_param_map.py
(TestGitLogSchemaImplementationContract).
"""

from typing import Any

from src.mcp_server_git.lean.registry_github import _register_github_tools


class _StubInterface:
    """Minimal stand-in for GitLeanInterface.register_tool."""

    def __init__(self) -> None:
        self.tool_registry: dict[str, Any] = {}

    def register_tool(self, tool_def: Any) -> None:
        self.tool_registry[tool_def.name] = tool_def


def _build_github_registry() -> dict[str, Any]:
    interface = _StubInterface()
    _register_github_tools(interface, github_service=object())
    return interface.tool_registry


class TestGitHubUpdatePrSchemaImplementationContract:
    def test_update_pr_schema_exposes_title_body_state_base(self) -> None:
        registry = _build_github_registry()
        properties = registry["github_update_pr"].schema["properties"]

        assert "title" in properties
        assert "body" in properties
        assert "state" in properties
        assert "base" in properties


class TestGitHubCreatePrSchemaImplementationContract:
    def test_create_pr_schema_exposes_head_and_base(self) -> None:
        """head and base are required positional params on the handler;
        the old hand-written schema silently omitted both."""
        registry = _build_github_registry()
        properties = registry["github_create_pr"].schema["properties"]

        assert "head" in properties
        assert "base" in properties
