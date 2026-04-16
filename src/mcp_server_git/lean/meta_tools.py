"""
Meta-tool definitions for the lean MCP interface.

Provides the 3-meta-tool pattern implementations:
- discover_tools: Dynamic tool discovery with filtering
- get_tool_spec: On-demand schema retrieval
- execute_tool: Unified tool execution with validation
"""

import inspect
import json
import logging
import re
from typing import Any

from jsonschema import ValidationError, validate

from .token_limiter import apply_token_limits

logger = logging.getLogger(__name__)


def _sanitize_json_string(s: str) -> str:
    """
    Escape bare control characters inside JSON string values.

    Some MCP clients produce JSON where string values contain literal
    newlines, carriage returns, or tabs rather than the escaped forms
    required by the JSON specification (\\n, \\r, \\t).  This causes
    json.loads() to raise JSONDecodeError even though the overall
    structure is otherwise valid JSON.

    Strategy: use a regex that matches the interior of JSON string
    literals (content between un-escaped double-quotes) and replace
    any bare control characters found there with their escape sequences.

    Args:
        s: A JSON-like string that may contain bare control characters.

    Returns:
        The string with bare control characters inside string values
        replaced by their JSON escape sequences.
    """

    def _escape_controls(m: re.Match) -> str:
        content = m.group(1)
        content = content.replace("\n", "\\n")
        content = content.replace("\r", "\\r")
        content = content.replace("\t", "\\t")
        # Cover remaining C0 controls that JSON forbids
        content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]',
                         lambda c: f'\\u{ord(c.group()):04x}', content)
        return f'"{content}"'

    # Match JSON string literals: opening quote, captured body, closing quote.
    # The body allows escaped sequences (\\.) or any char that is not a bare
    # quote or backslash.  We use a non-greedy match so we don't span across
    # multiple string values.
    return re.sub(r'"((?:[^"\\]|\\.)*?)"', _escape_controls, s, flags=re.DOTALL)


def setup_meta_tools(interface) -> None:
    """
    Register the 3 meta-tools on the interface's FastMCP app.

    Args:
        interface: GitLeanInterface instance providing app, tool_registry,
                   _schema_cache, and _validate_path_parameters.
    """
    app = interface.app

    @app.tool()
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

        for name, tool_def in interface.tool_registry.items():
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
            "total_tools": len(interface.tool_registry),
            "filtered_count": len(tools),
            "domains": {
                "git": len(
                    [t for t in interface.tool_registry.values() if t.domain == "git"]
                ),
                "github": len(
                    [t for t in interface.tool_registry.values() if t.domain == "github"]
                ),
                "azure": len(
                    [t for t in interface.tool_registry.values() if t.domain == "azure"]
                ),
            },
            "context_saving": f"~{len(interface.tool_registry) * 0.5}K tokens saved vs traditional MCP",
            "issues": "https://github.com/MementoRC/mcp-git/issues",
        }

        return apply_token_limits(result, "discover_tools", 1000)

    @app.tool()
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
        if tool_name not in interface.tool_registry:
            return {
                "error": f"Tool '{tool_name}' not found",
                "available_tools": list(interface.tool_registry.keys()),
                "suggestion": "Use discover_tools() to find available tools",
            }

        tool_def = interface.tool_registry[tool_name]
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

    @app.tool()
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
        if tool_name not in interface.tool_registry:
            return {
                "error": f"Tool '{tool_name}' not found",
                "available_tools": list(interface.tool_registry.keys()),
                "suggestion": "Use discover_tools() to find available tools",
            }

        tool_def = interface.tool_registry[tool_name]

        # Coerce string parameters to dict (clients may send JSON string)
        if isinstance(parameters, str):
            try:
                parameters = json.loads(parameters)
            except json.JSONDecodeError:
                # Some MCP clients serialize parameters with literal control
                # characters inside string values (raw newlines, tabs) instead
                # of the escaped forms (\n, \t) required by the JSON spec.
                # This is common when the body contains multi-line markdown.
                # Attempt to sanitize by replacing bare control characters
                # inside what appear to be JSON string values, then retry.
                try:
                    sanitized = _sanitize_json_string(parameters)
                    parameters = json.loads(sanitized)
                except json.JSONDecodeError:
                    return {
                        "tool": tool_name,
                        "status": "error",
                        "error": f"Parameters must be a JSON object, got unparseable string: {parameters[:100]}",
                    }

        try:
            # Get cached schema for validation
            schema = interface._schema_cache.get(tool_name, tool_def.schema)

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
                interface._validate_path_parameters(parameters)
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

    @app.tool()
    def server_info() -> dict[str, Any]:
        """
        Returns server metadata for LLM harnesses and clients.

        USE WHEN:
        - You need to identify this server's version or capabilities
        - You want to know where to file bugs or feature requests
        - You need documentation or support URLs

        Returns:
            Dictionary containing:
            - name: Server identifier
            - version: Server version string
            - description: Human-readable description
            - repository: Source code repository URL
            - issues: URL to file bug reports or feature requests
            - documentation: README / docs URL
            - support: Specific URLs for bug reports and feature requests
            - domains: Supported operation domains with descriptions
            - transport: MCP transport type
            - protocol_version: MCP protocol version

        Examples:
            server_info()  # Get server metadata and support URLs
        """
        try:
            from importlib.metadata import version

            pkg_version = version("mcp-server-git")
        except Exception:
            pkg_version = "unknown"
        return {
            "name": "mcp-git",
            "version": pkg_version,
            "description": "MCP server for Git, GitHub, and Azure DevOps operations",
            "repository": "https://github.com/MementoRC/mcp-git",
            "issues": "https://github.com/MementoRC/mcp-git/issues",
            "documentation": "https://github.com/MementoRC/mcp-git#readme",
            "support": {
                "bug_reports": "https://github.com/MementoRC/mcp-git/issues/new?template=bug_report.md",
                "feature_requests": "https://github.com/MementoRC/mcp-git/issues/new?template=feature_request.md",
            },
            "domains": {
                "git": "Local git operations",
                "github": "GitHub API",
                "azure": "Azure DevOps",
            },
            "transport": "HTTP (SSE)",
            "protocol_version": "2024-11-05",
        }
