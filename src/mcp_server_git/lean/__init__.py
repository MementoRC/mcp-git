"""
Lean MCP Interface for mcp-git server.

Provides 95%+ context reduction through the 3-meta-tool pattern:
- discover_tools(): List available tools with filtering
- get_tool_spec(): Get tool schema on-demand
- execute_tool(): Execute any registered tool

Reduces token consumption from ~30k to ~2k while maintaining 100% functionality.
"""

from .interface import GitLeanInterface, create_git_lean_interface
from .token_limiter import MCPTokenLimiter

__all__ = ["GitLeanInterface", "create_git_lean_interface", "MCPTokenLimiter", "main"]


def main():
    """Entry point for mcp-git-lean command."""
    from .__main__ import main as _main

    _main()
