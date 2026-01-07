"""
Main entry point for mcp-git-lean server.

Initializes the lean MCP interface with 3 meta-tools for 95% context reduction.
"""

import logging

from dotenv import load_dotenv

# Import services from the main server
from ..services.git_service import GitService
from ..services.github_service import GitHubService

# Import Azure service when available
try:
    from ..azure.client import AzureClient

    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False

from .interface import create_git_lean_interface

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point for mcp-git-lean server."""
    # Load environment variables
    load_dotenv()

    logger.info("Initializing mcp-git-lean server...")

    # Initialize services
    # Note: These need to be properly initialized with repository paths
    # For now, we'll create placeholder services
    git_service = GitService()
    github_service = GitHubService()

    if AZURE_AVAILABLE:
        azure_service = AzureClient()
    else:
        # Create a placeholder service
        azure_service = type(
            "AzureService",
            (),
            {
                "azure_get_build_status": lambda **kwargs: {
                    "error": "Azure not available"
                },
                "azure_get_build_logs": lambda **kwargs: {
                    "error": "Azure not available"
                },
                "azure_get_failing_jobs": lambda **kwargs: {
                    "error": "Azure not available"
                },
                "azure_list_builds": lambda **kwargs: {"error": "Azure not available"},
            },
        )()

    # Create lean interface
    app = create_git_lean_interface(
        git_service=git_service,
        github_service=github_service,
        azure_service=azure_service,
    )

    logger.info("mcp-git-lean server initialized successfully")
    logger.info("3 meta-tools exposed: discover_tools, get_tool_spec, execute_tool")
    logger.info("57 tools registered across git, github, and azure domains")

    # Run the FastMCP server
    app.run()


if __name__ == "__main__":
    main()
