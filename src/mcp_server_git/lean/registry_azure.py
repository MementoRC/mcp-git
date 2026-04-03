"""Azure DevOps domain tool registration for lean MCP interface."""

import logging
from typing import Any

from ..azure import api as azure_ops
from ..azure.models import (
    AzureGetBuildLogs,
    AzureGetBuildStatus,
    AzureGetFailingJobs,
    AzureListBuilds,
)
from .interface import ToolDefinition

logger = logging.getLogger(__name__)


def _register_azure_tools(interface: Any, azure_service: Any):
    """Register all Azure DevOps domain tools."""

    azure_tools = [
        ToolDefinition(
            name="azure_get_build_status",
            implementation=azure_ops.azure_get_build_status,
            description="Get the status of an Azure DevOps build/pipeline run",
            schema=AzureGetBuildStatus.model_json_schema(),
            domain="azure",
            complexity="focused",
        ),
        ToolDefinition(
            name="azure_get_build_logs",
            implementation=azure_ops.azure_get_build_logs,
            description="Get logs from an Azure DevOps build",
            schema=AzureGetBuildLogs.model_json_schema(),
            domain="azure",
            complexity="focused",
        ),
        ToolDefinition(
            name="azure_get_failing_jobs",
            implementation=azure_ops.azure_get_failing_jobs,
            description="Get detailed information about failing jobs in an Azure DevOps build",
            schema=AzureGetFailingJobs.model_json_schema(),
            domain="azure",
            complexity="focused",
        ),
        ToolDefinition(
            name="azure_list_builds",
            implementation=azure_ops.azure_list_builds,
            description="List Azure DevOps builds with filtering options",
            schema=AzureListBuilds.model_json_schema(),
            domain="azure",
            complexity="focused",
        ),
    ]

    for tool in azure_tools:
        interface.register_tool(tool)

    logger.info(f"Registered {len(azure_tools)} Azure tools")
