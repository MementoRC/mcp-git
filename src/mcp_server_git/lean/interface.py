"""
Git Lean MCP Interface - 95% Context Reduction Implementation.

This module provides the lean MCP interface for the mcp-git server, reducing
context consumption from ~30k tokens to ~2k tokens through the 3-meta-tool pattern.

Architecture:
- Registers all 51 tools from git, github, and azure domains
- Exposes only 3 meta-tools: discover_tools, get_tool_spec, execute_tool
- Routes tool execution to appropriate handlers
- Applies intelligent token limiting to responses
"""

import inspect
import json
import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from fastmcp import FastMCP

from .response_offloader import ResponseOffloader
from .token_limiter import MCPTokenLimiter

logger = logging.getLogger(__name__)


class ToolDefinition:
    """Tool definition with metadata for lean MCP registry."""

    def __init__(
        self,
        name: str,
        implementation: Callable,
        description: str,
        schema: dict[str, Any],
        domain: str = "general",
        complexity: str = "focused",
        examples: list[dict[str, Any]] | None = None,
        relative_path_params: set[str] | None = None,
    ):
        """Initialize a ToolDefinition.

        Args:
            name: Tool name (used as registry key).
            implementation: Callable that executes the tool.
            description: Human-readable description.
            schema: JSON Schema for parameters.
            domain: "git", "github", "azure", or "general".
            complexity: "core", "focused", "advanced", or "comprehensive".
            examples: Optional usage examples.
            relative_path_params: Set of parameter names whose path-shaped
                values are intentionally allowed to be relative. Used by
                _validate_path_parameters to exempt parameters that are
                semantically repo-relative by git convention (e.g. the
                "path" parameter on git_submodule_add per gitmodules(5);
                issue #168). Defaults to None (no exemptions).
        """
        self.name = name
        self.implementation = implementation
        self.description = description
        self.schema = schema
        self.domain = domain
        self.complexity = complexity
        self.examples = examples or []
        self.relative_path_params = relative_path_params or set()


class GitLeanInterface:
    """
    Lean MCP interface for mcp-git server providing 95%+ context reduction.

    Implements the 3-meta-tool pattern:
    - discover_tools(): Dynamic tool discovery with filtering
    - get_tool_spec(): On-demand schema retrieval
    - execute_tool(): Unified tool execution

    Registers all 51 tools across git, github, and azure domains.
    """

    def __init__(
        self,
        git_service: Any,
        github_service: Any,
        azure_service: Any,
        app_name: str = "mcp-git-lean",
        version: str = "0.1.0",
        token_limiter: MCPTokenLimiter | None = None,
    ):
        """
        Initialize lean MCP interface.

        Args:
            git_service: Git operations service
            github_service: GitHub API service
            azure_service: Azure DevOps service
            app_name: FastMCP application name
            version: Application version
            token_limiter: Token limiting configuration
        """
        self.git_service = git_service
        self.github_service = github_service
        self.azure_service = azure_service
        self.app_name = app_name
        self.app = FastMCP(
            app_name,
            version=version,
            instructions=(
                "MCP server for Git, GitHub, and Azure DevOps operations. "
                "Issues: https://github.com/MementoRC/mcp-git/issues"
            ),
        )
        self.token_limiter = token_limiter or MCPTokenLimiter()
        self.response_offloader = ResponseOffloader(token_limiter=self.token_limiter)

        # Tool registry
        self.tool_registry: dict[str, ToolDefinition] = {}

        # Schema cache for performance optimization
        self._schema_cache: dict[str, dict[str, Any]] = {}

        # Build tool registry
        self._build_tool_registry()

        # Setup the 3 meta-tools
        self._setup_meta_tools()

        logger.info(
            f"Git Lean MCP interface initialized: {len(self.tool_registry)} tools registered"
        )

    def _build_tool_registry(self):
        """Build tool registry with all git, github, and azure tools."""
        # Import registration function
        from .tool_registry import register_all_tools

        # Register all tools
        register_all_tools(
            self, self.git_service, self.github_service, self.azure_service
        )

    def register_tool(self, tool_def: ToolDefinition):
        """Register a tool in the registry."""
        # Wrap implementation with token limiting
        wrapped_impl = self._wrap_tool(tool_def.implementation, tool_def.name)
        tool_def.implementation = wrapped_impl

        self.tool_registry[tool_def.name] = tool_def

        # Cache the schema for performance
        self._schema_cache[tool_def.name] = tool_def.schema

        logger.debug(
            f"Registered tool: {tool_def.name} ({tool_def.domain}/{tool_def.complexity})"
        )

    def _validate_path_parameters(
        self,
        parameters: dict[str, Any],
        relative_path_params: set[str] | None = None,
    ) -> None:
        """
        Reject relative paths to prevent CWD confusion between client and server.

        MCP servers resolve paths relative to their process CWD, not Claude Code's
        working directory. This causes cross-repository pollution when using ".".

        Parameters explicitly marked in ``relative_path_params`` are exempt from
        the absolute-path requirement (e.g. submodule "path" which is repo-relative
        by git convention per gitmodules(5); issue #168). Exempted parameters are
        STILL rejected when they are empty or contain ".." path-traversal segments.

        Args:
            parameters: Dictionary of tool parameters.
            relative_path_params: Set of parameter names whose values are
                semantically repo-relative by git convention and should NOT
                be rejected for being relative. Defaults to no exemptions.

        Raises:
            ValueError: If any non-exempt path parameter is relative, or if an
                exempt parameter is empty or contains a ".." traversal segment.
        """
        exemptions = relative_path_params or set()
        for param_name, param_value in parameters.items():
            # Only inspect string-valued parameters whose name contains "path".
            if not isinstance(param_value, str):
                continue
            if "path" not in param_name.lower():
                continue

            if param_name in exemptions:
                # Exempted: relative paths are allowed, but reject empty values
                # and any ".." segment to prevent path-traversal escapes.
                if param_value == "":
                    raise ValueError(
                        f"Path parameter '{param_name}' must not be empty."
                    )
                segments = param_value.replace("\\", "/").split("/")
                if ".." in segments:
                    raise ValueError(
                        f"Path traversal ('..') not allowed in '{param_name}': "
                        f"'{param_value}'."
                    )
                continue

            # Non-exempt path params must be absolute.
            if param_value in (".", "..") or not param_value.startswith("/"):
                raise ValueError(
                    f"Relative path '{param_value}' not supported. MCP servers "
                    f"resolve paths relative to their process CWD, not Claude Code's "
                    f"working directory. Use absolute path instead."
                )

    def _wrap_tool(self, tool_func: Callable, tool_name: str) -> Callable:
        """Wrap tool function with response offloading, token limiting, and error handling."""
        is_async = inspect.iscoroutinefunction(tool_func)

        if is_async:

            @wraps(tool_func)
            async def async_wrapper(*args, **kwargs):
                try:
                    result = await tool_func(*args, **kwargs)
                    if (
                        self.response_offloader
                        and self.response_offloader.should_offload(result, tool_name)
                    ):
                        try:
                            return self.response_offloader.offload(result, tool_name)
                        except Exception:
                            logger.warning(
                                f"Offload failed for {tool_name}, falling back to truncation"
                            )
                    return self.token_limiter.limit_response(result, tool_name)
                except Exception as e:
                    logger.error(f"Error in {tool_name}: {e}")
                    return {"error": str(e), "tool": tool_name, "success": False}

            return async_wrapper
        else:

            @wraps(tool_func)
            def sync_wrapper(*args, **kwargs):
                try:
                    result = tool_func(*args, **kwargs)
                    if (
                        self.response_offloader
                        and self.response_offloader.should_offload(result, tool_name)
                    ):
                        try:
                            return self.response_offloader.offload(result, tool_name)
                        except Exception:
                            logger.warning(
                                f"Offload failed for {tool_name}, falling back to truncation"
                            )
                    return self.token_limiter.limit_response(result, tool_name)
                except Exception as e:
                    logger.error(f"Error in {tool_name}: {e}")
                    return {"error": str(e), "tool": tool_name, "success": False}

            return sync_wrapper

    def _setup_meta_tools(self):
        """Setup the 3 meta-tools for dynamic discovery."""
        from .meta_tools import setup_meta_tools

        setup_meta_tools(self)

    def get_app(self) -> FastMCP:
        """Get the FastMCP application instance."""
        return self.app

    async def execute_tool_direct(
        self, tool_name: str, parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a tool directly without going through FastMCP protocol.

        Used by HTTP transport for direct programmatic tool invocation.

        Args:
            tool_name: Name of the tool to execute
            parameters: Tool parameters

        Returns:
            Dictionary containing:
            - tool: Tool name
            - status: "success" or "error"
            - result: Tool execution result (on success)
            - error: Error message (on failure)
        """
        if tool_name not in self.tool_registry:
            return {
                "error": f"Tool '{tool_name}' not found",
                "available_tools": list(self.tool_registry.keys()),
            }

        tool_def = self.tool_registry[tool_name]

        # Coerce string parameters to dict (clients may send JSON string)
        if isinstance(parameters, str):
            try:
                parameters = json.loads(parameters)
            except json.JSONDecodeError:
                return {
                    "tool": tool_name,
                    "status": "error",
                    "error": f"Parameters must be a JSON object, got unparseable string: {parameters[:100]}",
                }

        try:
            # Validate path parameters (honoring per-tool exemptions, e.g.
            # submodule "path" which is intentionally repo-relative).
            self._validate_path_parameters(
                parameters, tool_def.relative_path_params
            )

            # Execute tool
            if inspect.iscoroutinefunction(tool_def.implementation):
                result = await tool_def.implementation(**parameters)
            else:
                result = tool_def.implementation(**parameters)

            return {
                "tool": tool_name,
                "status": "success",
                "result": result,
            }
        except Exception as e:
            return {
                "tool": tool_name,
                "status": "error",
                "error": str(e),
            }

    def discover_tools(self, pattern: str = "") -> dict[str, Any]:
        """Discover available tools (direct method for HTTP transport)."""
        tools = []

        for name, tool_def in self.tool_registry.items():
            if pattern and pattern.strip() and pattern.lower() not in name.lower():
                continue

            tools.append(
                {
                    "name": name,
                    "description": tool_def.description,
                    "domain": tool_def.domain,
                    "complexity": tool_def.complexity,
                }
            )

        return {
            "available_tools": tools,
            "total_tools": len(self.tool_registry),
            "filtered_count": len(tools),
            "domains": {
                "git": len(
                    [t for t in self.tool_registry.values() if t.domain == "git"]
                ),
                "github": len(
                    [t for t in self.tool_registry.values() if t.domain == "github"]
                ),
                "azure": len(
                    [t for t in self.tool_registry.values() if t.domain == "azure"]
                ),
            },
            "context_saving": f"~{len(self.tool_registry) * 0.5}K tokens saved vs traditional MCP",
        }

    def get_tool_spec(self, tool_name: str) -> dict[str, Any]:
        """Get tool specification (direct method for HTTP transport)."""
        if tool_name not in self.tool_registry:
            return {
                "error": f"Tool '{tool_name}' not found",
                "available_tools": list(self.tool_registry.keys()),
            }

        tool_def = self.tool_registry[tool_name]
        return {
            "name": tool_name,
            "description": tool_def.description,
            "domain": tool_def.domain,
            "complexity": tool_def.complexity,
            "schema": tool_def.schema,
            "examples": tool_def.examples,
            "usage_note": f"Execute with: execute_tool('{tool_name}', parameters)",
        }

    def health_check(self) -> dict[str, Any]:
        """Perform health check on the lean MCP interface."""
        return {
            "interface_type": "lean_mcp",
            "tools_registered": len(self.tool_registry),
            "meta_tools": ["discover_tools", "get_tool_spec", "execute_tool"],
            "context_efficiency": "95%+ reduction vs traditional MCP",
            "token_limiter_enabled": self.token_limiter is not None,
            "domains": {
                "git": len(
                    [t for t in self.tool_registry.values() if t.domain == "git"]
                ),
                "github": len(
                    [t for t in self.tool_registry.values() if t.domain == "github"]
                ),
                "azure": len(
                    [t for t in self.tool_registry.values() if t.domain == "azure"]
                ),
            },
        }


def create_git_lean_interface(
    git_service: Any, github_service: Any, azure_service: Any, **kwargs
) -> FastMCP:
    """
    Factory function to create Git lean MCP interface.

    Args:
        git_service: Git operations service
        github_service: GitHub API service
        azure_service: Azure DevOps service
        **kwargs: Additional arguments for interface

    Returns:
        FastMCP application instance
    """
    interface = GitLeanInterface(git_service, github_service, azure_service, **kwargs)
    return interface.get_app()
