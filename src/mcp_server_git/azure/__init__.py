"""Azure DevOps integration for MCP Git Server"""

from .api import (
    azure_get_build_logs,
    azure_get_build_status,
    azure_get_failing_jobs,
    azure_list_builds,
)
from .client import AzureClient, get_azure_client
from .models import (
    AzureGetBuildLogs,
    AzureGetBuildStatus,
    AzureGetFailingJobs,
    AzureListBuilds,
)

__all__ = [
    "AzureClient",
    "get_azure_client",
    # Read operations
    "azure_get_build_status",
    "azure_get_build_logs",
    "azure_get_failing_jobs",
    "azure_list_builds",
    # Models
    "AzureGetBuildStatus",
    "AzureGetBuildLogs",
    "AzureGetFailingJobs",
    "AzureListBuilds",
]
