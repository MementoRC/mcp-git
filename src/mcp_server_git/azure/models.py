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


class AzureGetFailingJobs(BaseModel):
    """Get detailed information about failing jobs in a build"""

    project: str
    build_id: int
    include_logs: bool = True


class AzureListBuilds(BaseModel):
    """List builds for an Azure DevOps project"""

    project: str
    repository_id: str | None = None
    branch_name: str | None = None
    # notStarted, inProgress, completed, cancelling, postponed, all
    status: str | None = None
    # succeeded, partiallySucceeded, failed, canceled
    result: str | None = None
    top: int = 30  # Maximum number of builds to return
    continuation_token: str | None = None  # For pagination
