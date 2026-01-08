"""
Null Object Pattern for Azure DevOps Service.

Provides a safe fallback when Azure DevOps client is not available,
returning consistent error responses instead of raising exceptions.
"""

import logging

logger = logging.getLogger(__name__)


class NullAzureService:
    """
    Null object implementation for Azure DevOps service.

    This class implements the same interface as AzureClient but returns
    error responses instead of making actual API calls. Used when Azure
    dependencies are not available.
    """

    def __init__(self):
        """Initialize null Azure service."""
        logger.warning(
            "Azure DevOps client not available - using null object implementation"
        )

    def azure_get_build_status(self, **kwargs) -> dict:
        """Return error for build status request."""
        return {
            "error": "Azure DevOps client not available",
            "message": "Install Azure dependencies to use this feature",
            "requested_operation": "get_build_status",
            "parameters": kwargs,
        }

    def azure_get_build_logs(self, **kwargs) -> dict:
        """Return error for build logs request."""
        return {
            "error": "Azure DevOps client not available",
            "message": "Install Azure dependencies to use this feature",
            "requested_operation": "get_build_logs",
            "parameters": kwargs,
        }

    def azure_get_failing_jobs(self, **kwargs) -> dict:
        """Return error for failing jobs request."""
        return {
            "error": "Azure DevOps client not available",
            "message": "Install Azure dependencies to use this feature",
            "requested_operation": "get_failing_jobs",
            "parameters": kwargs,
        }

    def azure_list_builds(self, **kwargs) -> dict:
        """Return error for list builds request."""
        return {
            "error": "Azure DevOps client not available",
            "message": "Install Azure dependencies to use this feature",
            "requested_operation": "list_builds",
            "parameters": kwargs,
        }
