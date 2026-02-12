"""
CLI entry point for HTTP Lean Server.

Provides a command-line interface to start the HTTP transport layer for the
MCP Git lean interface, exposing the 3 meta-tools (discover_tools, get_tool_spec,
execute_tool) over HTTP with session management and security features.

Key features:
- JSON-RPC 2.0 tool execution over HTTP
- Session management with repository isolation
- Optional API key authentication
- Configurable session timeout
- Verbosity-based logging control
"""

import logging
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

from .services.git_service import GitService
from .services.github_service import GitHubService
from .transport.http_server import HTTPGitServer
from .lean.null_azure_service import NullAzureService
from .lean.interface import create_git_lean_interface

logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--host",
    default="127.0.0.1",
    help="Host address to bind to (default: 127.0.0.1)",
)
@click.option(
    "--port",
    type=int,
    default=4100,
    help="Port to listen on (default: 4100)",
)
@click.option(
    "--api-key",
    default=None,
    help="Optional API key for authentication",
)
@click.option(
    "--session-timeout",
    type=int,
    default=3600,
    help="Session timeout in seconds (default: 3600 = 1 hour)",
)
@click.option(
    "--default-repo",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    default=None,
    help="Default repository for auto-session mode (enables MCP client compatibility)",
)
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="Increase verbosity (-v for INFO, -vv for DEBUG)",
)
def main(
    host: str,
    port: int,
    api_key: str | None,
    session_timeout: int,
    default_repo: str | None,
    verbose: int,
) -> None:
    """
    HTTP Lean Server - MCP Git functionality over HTTP with lean interface.

    Starts an HTTP server that exposes the 3 meta-tools (discover_tools,
    get_tool_spec, execute_tool) for 95% context reduction, with session
    management and optional API key security.
    """
    # Set up logging level based on verbosity
    logging_level = logging.WARNING
    if verbose == 1:
        logging_level = logging.INFO
    elif verbose >= 2:
        logging_level = logging.DEBUG

    # Configure logging
    logging.basicConfig(
        level=logging_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )

    # Load environment variables
    load_dotenv()

    logger.info("Initializing HTTP Lean Server...")

    # Initialize services
    git_service = GitService()
    github_service = GitHubService()
    azure_service = NullAzureService()

    # Create lean interface (this prepares the interface but we use it
    # to validate that all services are properly initialized)
    _app = create_git_lean_interface(
        git_service=git_service,
        github_service=github_service,
        azure_service=azure_service,
    )

    logger.info("Lean interface initialized successfully")
    logger.info("3 meta-tools available: discover_tools, get_tool_spec, execute_tool")
    logger.info("51 tools registered across git, github, and azure domains")

    # Create and configure HTTP server
    server = HTTPGitServer(
        host=host,
        port=port,
        api_key=api_key,
        session_timeout=float(session_timeout),
        default_repo=Path(default_repo) if default_repo else None,
    )

    logger.info(f"HTTP Server configured: {host}:{port}")
    if api_key:
        logger.info("API key authentication enabled")
    else:
        logger.info("API key authentication disabled")
    logger.info(f"Session timeout: {session_timeout} seconds")
    if default_repo:
        logger.info(f"Default repository: {default_repo} (auto-session mode enabled)")

    logger.info("Starting HTTP Lean Server...")

    # Run the HTTP server
    server.run()


if __name__ == "__main__":
    main()
