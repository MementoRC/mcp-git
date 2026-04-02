"""Tool Registry coordinator for Git Lean MCP Interface.

Registers all tools across git, github, and azure domains.

Tool Distribution:
- Git tools (26): Core git operations
- GitHub tools (47): PR, issues, workflows, repo settings, actions, branch protection, security, releases
- Azure tools (4): Build logs and status
"""

import logging
from typing import Any

from .registry_azure import _register_azure_tools
from .registry_git import _register_git_tools
from .registry_github import _register_github_tools

logger = logging.getLogger(__name__)


def register_all_tools(
    interface: Any,
    git_service: Any,
    github_service: Any,
    azure_service: Any,
):
    """Register all tools from git, github, and azure domains.

    Args:
        interface: GitLeanInterface instance
        git_service: Git operations service
        github_service: GitHub API service
        azure_service: Azure DevOps service
    """
    _register_git_tools(interface, git_service)
    _register_github_tools(interface, github_service)
    _register_azure_tools(interface, azure_service)
    logger.info(f"Registered {len(interface.tool_registry)} tools total")
