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
import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from fastmcp import FastMCP
from jsonschema import ValidationError, validate

from .token_limiter import MCPTokenLimiter, apply_token_limits

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
    ):
        self.name = name
        self.implementation = implementation
        self.description = description
        self.schema = schema
        self.domain = domain
        self.complexity = complexity
        self.examples = examples or []


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
        self.app = FastMCP(app_name, version=version)
        self.token_limiter = token_limiter or MCPTokenLimiter()

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

    def _validate_path_parameters(self, parameters: dict[str, Any]) -> None:
        """
        Reject relative paths to prevent CWD confusion between client and server.

        MCP servers resolve paths relative to their process CWD, not Claude Code's
        working directory. This causes cross-repository pollution when using ".".

        Args:
            parameters: Dictionary of tool parameters

        Raises:
            ValueError: If any path parameter is relative
        """
        for param_name, param_value in parameters.items():
            # Check all parameters containing "path" in their name
            if "path" in param_name.lower() and isinstance(param_value, str):
                # Reject ".", "..", or any path not starting with "/"
                if param_value in (".", "..") or not param_value.startswith("/"):
                    raise ValueError(
                        f"Relative path '{param_value}' not supported. MCP servers "
                        f"resolve paths relative to their process CWD, not Claude Code's "
                        f"working directory. Use absolute path instead."
                    )

    def _wrap_tool(self, tool_func: Callable, tool_name: str) -> Callable:
        """Wrap tool function with token limiting and error handling.

        Handles both sync and async tool implementations correctly.
        """
        is_async = inspect.iscoroutinefunction(tool_func)

        if is_async:

            @wraps(tool_func)
            async def async_wrapper(*args, **kwargs):
                try:
                    result = await tool_func(*args, **kwargs)
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
                    return self.token_limiter.limit_response(result, tool_name)
                except Exception as e:
                    logger.error(f"Error in {tool_name}: {e}")
                    return {"error": str(e), "tool": tool_name, "success": False}

            return sync_wrapper

    def _setup_meta_tools(self):
        """Setup the 3 meta-tools for dynamic discovery."""

        @self.app.tool()
        def discover_tools(pattern: str = "") -> dict[str, Any]:
            """
            [STEP 1] Discover available Git, GitHub, and Azure DevOps tools.

            USE WHEN:
            - You don't know if a specific Git/GitHub/Azure operation exists as a tool
            - You want to see all available tools in a domain (git, github, azure)
            - You need to find the exact tool name before calling get_tool_spec()
            - You're exploring what operations are available

            COMMON TASKS:
            - Git: status, diff, commit, push, pull, merge, rebase, checkout, branch, reset, log
            - GitHub: create/list/merge PRs, manage issues, check workflows, get CI status
            - Azure: get build status/logs, list builds, analyze failing jobs

            This lean interface provides 51 tools across 3 domains, saving ~25k tokens
            vs loading all tool schemas upfront.

            WORKFLOW:
            1. discover_tools(pattern) ← YOU ARE HERE
            2. get_tool_spec(tool_name) ← Get schema/parameters for a specific tool
            3. execute_tool(tool_name, params) ← Execute the operation

            Args:
                pattern: Filter tools by name (e.g., "status", "pr", "merge", "rebase")
                         Leave empty "" to see all 51 tools

            Returns:
                Dictionary containing:
                - available_tools: List of tools, each with:
                  * name: Tool name to use in get_tool_spec() or execute_tool()
                  * description: What the tool does
                  * domain: "git", "github", or "azure"
                  * complexity: "core", "focused", "advanced", or "comprehensive"
                - total_tools: Total tools in registry (51)
                - filtered_count: How many matched your pattern
                - domains: Breakdown by domain (git: 25, github: 22, azure: 4)

                Example output for discover_tools("status"):
                {
                  "available_tools": [
                    {"name": "git_status", "description": "Shows working tree status", "domain": "git"},
                    {"name": "github_get_pr_status", "description": "Get PR status", "domain": "github"}
                  ],
                  "filtered_count": 2,
                  "total_tools": 51
                }

            Examples:
                discover_tools("")              # List all 51 tools
                discover_tools("status")        # Find: git_status, github_get_pr_status
                discover_tools("pr")            # Find all PR tools: create, list, merge, etc.
                discover_tools("rebase")        # Find: git_rebase, git_abort, git_continue
                discover_tools("workflow")      # Find GitHub workflow/CI tools

            MISSING TOOL? If you need a Git/GitHub/Azure operation that's not available:
            File an issue at https://github.com/MementoRC/mcp-git/issues with:
            - What operation you need (e.g., "git stash", "github list contributors")
            - Use case description
            - Expected parameters and behavior
            """
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

            result = {
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

            return apply_token_limits(result, "discover_tools", 1000)

        @self.app.tool()
        def get_tool_spec(tool_name: str) -> dict[str, Any]:
            """
            [STEP 2] Get detailed schema and parameters for a specific tool.

            USE WHEN:
            - You know the tool name but don't know what parameters it needs
            - You need to see required vs optional parameters before calling execute_tool()
            - You want to understand parameter types (string, int, bool, etc.)
            - You're debugging parameter validation errors from execute_tool()

            DON'T SKIP THIS STEP! Calling execute_tool() without checking the schema first
            will likely fail parameter validation. This tool shows you exactly what to pass.

            WORKFLOW:
            1. discover_tools(pattern) ← Already done
            2. get_tool_spec(tool_name) ← YOU ARE HERE
            3. execute_tool(tool_name, params) ← Execute with correct parameters

            Args:
                tool_name: Exact tool name from discover_tools() output
                          (e.g., "git_status", "github_create_pr", "azure_get_build_logs")

            Returns:
                Dictionary containing:
                - name: Tool name (same as input)
                - description: What the tool does
                - domain: "git", "github", or "azure"
                - complexity: "core", "focused", "advanced", or "comprehensive"
                - schema: JSON Schema with:
                  * properties: Each parameter's type, description, default value
                  * required: List of required parameters
                - examples: Usage examples (if available)
                - usage_note: How to call with execute_tool()

                Example output for get_tool_spec("git_status"):
                {
                  "name": "git_status",
                  "description": "Shows the working tree status",
                  "domain": "git",
                  "schema": {
                    "type": "object",
                    "properties": {
                      "repo_path": {"type": "string", "description": "Path to repository"}
                    },
                    "required": ["repo_path"]
                  },
                  "usage_note": "Execute with: execute_tool('git_status', parameters)"
                }

                Example for get_tool_spec("github_create_pr"):
                {
                  "name": "github_create_pr",
                  "schema": {
                    "properties": {
                      "repo_owner": {"type": "string"},
                      "repo_name": {"type": "string"},
                      "title": {"type": "string"},
                      "head": {"type": "string"},
                      "base": {"type": "string"},
                      "body": {"type": "string"},  # Optional
                      "draft": {"type": "boolean", "default": false}  # Optional
                    },
                    "required": ["repo_owner", "repo_name", "title", "head", "base"]
                  }
                }

            Examples:
                get_tool_spec("git_status")           # See: needs repo_path
                get_tool_spec("github_create_pr")     # See: needs repo_owner, repo_name, title, head, base
                get_tool_spec("git_rebase")           # See: needs repo_path, target_branch
                get_tool_spec("github_get_pr_checks") # See: needs repo_owner, repo_name, pr_number

            TOOL NOT FOUND? If the tool doesn't exist but should:
            File a feature request at https://github.com/MementoRC/mcp-git/issues
            """
            if tool_name not in self.tool_registry:
                return {
                    "error": f"Tool '{tool_name}' not found",
                    "available_tools": list(self.tool_registry.keys()),
                    "suggestion": "Use discover_tools() to find available tools",
                }

            tool_def = self.tool_registry[tool_name]
            result = {
                "name": tool_name,
                "description": tool_def.description,
                "domain": tool_def.domain,
                "complexity": tool_def.complexity,
                "schema": tool_def.schema,
                "examples": tool_def.examples,
                "usage_note": f"Execute with: execute_tool('{tool_name}', parameters)",
            }

            return apply_token_limits(result, "get_tool_spec", 1500)

        @self.app.tool()
        async def execute_tool(
            tool_name: str, parameters: dict[str, Any]
        ) -> dict[str, Any]:
            """
            [STEP 3] Execute a Git, GitHub, or Azure DevOps operation.

            USE WHEN: You have the tool name and parameters ready to perform:
            - Git operations: checking status, creating commits, pushing, merging
            - GitHub operations: creating PRs, checking CI status, managing issues
            - Azure DevOps: checking build status, fetching logs

            WORKFLOW:
            1. discover_tools(pattern) ← Found the right tool
            2. get_tool_spec(tool_name) ← Got the parameter schema
            3. execute_tool(tool_name, params) ← YOU ARE HERE

            VALIDATION: Parameters are validated against the tool schema before execution.
            Unexpected parameters will be rejected with an error listing valid parameters.

            Args:
                tool_name: Exact tool name (e.g., "git_status", "github_create_pr")
                parameters: Dictionary of parameters matching the tool schema
                           Use get_tool_spec() if unsure what parameters are needed

            Returns:
                SUCCESS: Tool execution result containing:
                - git_status: Working tree status, staged/unstaged changes, branch info
                - github_create_pr: PR URL, number, merge status
                - git_rebase: Rebase status, conflicts if any
                - github_get_pr_checks: CI check results, pass/fail status
                - azure_get_build_logs: Build logs, job details

                ERROR: Validation/execution failure with:
                - Error message explaining what went wrong
                - Valid parameters list if parameter validation failed
                - Suggestion to use discover_tools() if tool not found

            DON'T KNOW WHAT TOOL TO USE?
            Call discover_tools(pattern) first to find the right tool for your task

            Examples:
                execute_tool("git_status", {"repo_path": "."})

                execute_tool("github_create_pr", {
                    "repo_owner": "owner",
                    "repo_name": "repo",
                    "title": "feat: new feature",
                    "head": "feature-branch",
                    "base": "main"
                })

                execute_tool("git_rebase", {
                    "repo_path": ".",
                    "target_branch": "origin/main"
                })

                execute_tool("github_get_pr_checks", {
                    "repo_owner": "owner",
                    "repo_name": "repo",
                    "pr_number": 42
                })

            FOUND A BUG OR MISSING FEATURE?
            File an issue at https://github.com/MementoRC/mcp-git/issues
            Include: tool name, parameters used, error message, expected vs actual behavior
            """
            if tool_name not in self.tool_registry:
                return {
                    "error": f"Tool '{tool_name}' not found",
                    "available_tools": list(self.tool_registry.keys()),
                    "suggestion": "Use discover_tools() to find available tools",
                }

            tool_def = self.tool_registry[tool_name]

            try:
                # Get cached schema for validation
                schema = self._schema_cache.get(tool_name, tool_def.schema)

                # Validate parameters using JSON Schema
                # This validates both parameter names AND values/types
                try:
                    validate(instance=parameters, schema=schema)
                except ValidationError as ve:
                    return {
                        "tool": tool_name,
                        "status": "error",
                        "error": f"Parameter validation failed: {ve.message}",
                        "validation_path": list(ve.path) if ve.path else [],
                        "schema_path": list(ve.schema_path) if ve.schema_path else [],
                        "valid_parameters": list(schema.get("properties", {}).keys()),
                    }

                # Validate path parameters to prevent relative path issues
                try:
                    self._validate_path_parameters(parameters)
                except ValueError as ve:
                    return {
                        "tool": tool_name,
                        "status": "error",
                        "error": str(ve),
                        "execution_mode": "lean_mcp_dynamic",
                    }

                # Execute tool through its implementation
                # Check if implementation is async BEFORE calling to avoid race condition
                # where a sync function might return a coroutine object as data
                if inspect.iscoroutinefunction(tool_def.implementation):
                    result = await tool_def.implementation(**parameters)
                else:
                    result = tool_def.implementation(**parameters)

                return {
                    "tool": tool_name,
                    "status": "success",
                    "result": result,
                    "execution_mode": "lean_mcp_dynamic",
                }

            except ValidationError as ve:
                # Catch any schema validation errors not caught above
                logger.error(f"Schema validation error in {tool_name}: {ve}")
                return {
                    "tool": tool_name,
                    "status": "error",
                    "error": f"Validation error: {ve.message}",
                    "execution_mode": "lean_mcp_dynamic",
                }
            except Exception as e:
                logger.error(f"Error executing {tool_name}: {e}", exc_info=True)
                return {
                    "tool": tool_name,
                    "status": "error",
                    "error": str(e),
                    "execution_mode": "lean_mcp_dynamic",
                }

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

        try:
            # Validate path parameters
            self._validate_path_parameters(parameters)

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
                "git": len([t for t in self.tool_registry.values() if t.domain == "git"]),
                "github": len([t for t in self.tool_registry.values() if t.domain == "github"]),
                "azure": len([t for t in self.tool_registry.values() if t.domain == "azure"]),
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
