"""Azure DevOps integration for MCP Git Server"""

from .api import (
    azure_get_build_logs,
    azure_get_build_status,
    azure_get_failing_jobs,
)
from .check_run_logs import azure_get_logs_for_check_run
from .client import AzureClient, get_azure_client
from .models import (
    AzureGetBuildLogs,
    AzureGetBuildStatus,
    AzureGetFailingJobs,
    AzureGetLogsForCheckRun,
)

__all__ = [
    "AzureClient",
    "get_azure_client",
    # Read operations
    "azure_get_build_status",
    "azure_get_build_logs",
    "azure_get_failing_jobs",
    "azure_get_logs_for_check_run",
    # Models
    "AzureGetBuildStatus",
    "AzureGetBuildLogs",
    "AzureGetFailingJobs",
    "AzureGetLogsForCheckRun",
]
