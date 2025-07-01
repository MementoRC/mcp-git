"""
Simplified MCP Git Server - Testing minimal setup to resolve connection issues.

This is a minimal implementation following the working aider pattern to diagnose
MCP handshake/connection problems with the main server.
"""

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Any, Dict, List

from git import Repo, InvalidGitRepositoryError
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# Import core functionality from main server
from .core.tools import ToolRegistry
from .core.handlers import CallToolHandler
from .logging_config import configure_logging
from .server import load_environment_variables

# Global instances
_tool_handler = None
_tool_registry = None


async def main_simple(repository: Path | None, test_mode: bool = False) -> None:
    """
    Simplified MCP Git Server main function following aider pattern.
    
    This version removes all complex initialization that might interfere 
    with MCP handshake: no heartbeat managers, no session restoration,
    no stream wrapping, no async component startup before MCP connection.
    """
    # Basic logging setup
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
    logger = logging.getLogger(__name__)
    
    logger.info("🚀 Starting Simplified MCP Git Server")
    logger.info(f"Repository: {repository or '.'}")

    # Load environment variables
    load_environment_variables(repository)

    # Validate repository if provided
    if repository is not None:
        try:
            Repo(repository)
            logger.info(f"✅ Using repository at {repository}")
        except InvalidGitRepositoryError:
            logger.error(f"{repository} is not a valid Git repository")
            return

    # Create MCP server with minimal setup - exactly like aider
    server = Server("mcp-git-simple")

    @server.list_tools()
    async def list_tools() -> List[Tool]:
        """Return available git tools"""
        global _tool_registry
        if _tool_registry is None:
            _tool_registry = ToolRegistry()
            _tool_registry.initialize_default_tools()
        return _tool_registry.list_tools()

    @server.call_tool()
    async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        """Handle tool calls with minimal wrapper"""
        logger.info(f"Tool call: {name}")
        
        try:
            # Initialize handler if needed
            global _tool_handler
            if _tool_handler is None:
                _tool_handler = CallToolHandler()
            
            # Route the tool call
            result = await _tool_handler.router.route_tool_call(name, arguments)
            return result
        except Exception as e:
            logger.exception(f"Error in tool {name}: {e}")
            error_result = f"❌ Error: {str(e)}"
            return [TextContent(type="text", text=error_result)]

    # Test mode for CI
    if test_mode:
        logger.info("🧪 Running in test mode - staying alive for CI testing")
        await asyncio.sleep(10)
        logger.info("🧪 Test mode completed successfully")
        return

    # SIMPLE stdio server setup - exactly like aider
    try:
        options = server.create_initialization_options()
        logger.info("Initializing stdio server connection...")
        
        async with stdio_server() as (read_stream, write_stream):
            logger.info("Server running. Waiting for requests...")
            # Use raise_exceptions=True like aider to see handshake failures
            await server.run(read_stream, write_stream, options, raise_exceptions=True)
            
    except Exception as e:
        logger.exception(f"Critical Error: Server stopped due to unhandled exception: {e}")
        sys.exit(1)
    finally:
        logger.info("Simplified MCP Git Server shutting down.")


def main_cli() -> None:
    """Entry point for console script"""
    import click
    
    @click.command()
    @click.option("--repository", "-r", type=Path, help="Git repository path")
    @click.option("-v", "--verbose", count=True, help="Increase verbosity")
    @click.option("--enable-file-logging", is_flag=True, help="Enable file logging")
    @click.option("--test-mode", is_flag=True, help="Run in test mode for CI")
    def cli(repository: Path | None, verbose: int, enable_file_logging: bool, test_mode: bool) -> None:
        """Simplified MCP Git Server CLI"""
        # Set logging level based on verbosity
        if verbose == 1:
            os.environ["LOG_LEVEL"] = "INFO"
        elif verbose >= 2:
            os.environ["LOG_LEVEL"] = "DEBUG"
        
        asyncio.run(main_simple(repository, test_mode))
    
    cli()


if __name__ == "__main__":
    main_cli()