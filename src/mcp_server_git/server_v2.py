"""
MCP Git Server v2 - Clean modular architecture
Uses tool registry and routing system for better maintainability
"""

import logging
import time
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server

# Import configuration handling from original server
from .server import load_environment_variables

# Import the new modular components
from .core.handlers import CallToolHandler

logger = logging.getLogger(__name__)


async def serve_v2(repository: Path | None = None):
    """Serve the MCP Git Server v2 with clean modular architecture"""
    
    start_time = time.time()
    logger.info("🚀 Starting MCP Git Server v2 (Modular Architecture)...")
    
    # Load environment variables
    load_environment_variables(repository)
    
    # Create server
    server = Server("mcp-git")
    
    # Initialize the centralized tool handler
    tool_handler = CallToolHandler()
    
    @server.list_tools()
    async def list_tools():
        """List all available tools using the tool registry"""
        return tool_handler.registry.list_tools()
    
    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        """Route tool calls through the centralized handler"""
        return await tool_handler.call_tool(name, arguments)
    
    # Server initialization
    logger.info("🎯 MCP Git Server v2 initialized with modular architecture")
    initialization_time = time.time() - start_time
    logger.info(f"📡 Server listening (startup took {initialization_time:.2f}s)")
    
    # Start server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, raise_exceptions=False)