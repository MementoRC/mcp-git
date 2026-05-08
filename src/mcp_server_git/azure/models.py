"""Pydantic models for Azure DevOps API tools"""

from pydantic import BaseModel


class AzureGetBuildStatus(BaseModel):
    """Get status of an Azure DevOps build/pipeline run"""

    project: str
    build_id: int


class AzureGetBuildLogs(BaseModel):
    """Get logs from an Azure DevOps build"""

    project: str
    build_id: int
    log_id: int | None = None  # If None, get all logs
    tail_lines: int = 500  # Number of lines to return from the end (default: 500)


class AzureGetFailingJobs(BaseModel):
    """Get detailed information about failing jobs in a build"""

    project: str
    build_id: int
    include_logs: bool = True
    log_tail_lines: int = 500  # Number of lines to include from each log (default: 500)
