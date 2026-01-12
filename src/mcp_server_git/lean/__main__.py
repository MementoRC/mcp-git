"""
Main entry point for mcp-git-lean server.

Initializes the lean MCP interface with 3 meta-tools for 95% context reduction.
"""

import logging
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

# Import services from the main server
from ..services.git_service import GitService
from ..services.github_service import GitHubService

from .interface import create_git_lean_interface

logger = logging.getLogger(__name__)


@click.command()
@click.option("--repository", "-r", type=Path, help="Git repository path")
@click.option("-v", "--verbose", count=True)
def main(repository: Path | None, verbose: int) -> None:
    """MCP Git Lean Server - Git functionality with 95% context reduction."""
    # Set up logging level
    logging_level = logging.WARN
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

    # Load environment variables from repository if it exists
    if repository:
        env_file = repository / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            logger.info(f"Loaded environment variables from {env_file}")
    else:
        load_dotenv()

    logger.info("Initializing mcp-git-lean server...")

    # Initialize services
    git_service = GitService()
    github_service = GitHubService()

    # Always use NullAzureService for lean interface
    # Azure support requires token, organization, and session configuration
    # which is not set up by default
    from .null_azure_service import NullAzureService

    azure_service = NullAzureService()

    # Create lean interface
    app = create_git_lean_interface(
        git_service=git_service,
        github_service=github_service,
        azure_service=azure_service,
    )

    logger.info("mcp-git-lean server initialized successfully")
    logger.info("3 meta-tools exposed: discover_tools, get_tool_spec, execute_tool")
    logger.info("51 tools registered across git, github, and azure domains")

    # Run the FastMCP server
    app.run()


if __name__ == "__main__":
    main()
