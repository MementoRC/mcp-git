"""Pydantic models for GitHub Actions / check-run mutation tools (#301, #309)."""

from pydantic import BaseModel, Field

_OWNER = "Repository owner/organization"
_NAME = "Repository name"
_DEBUG = "Re-run with runner diagnostic and step debug logging enabled"


class GitHubCancelWorkflowRun(BaseModel):
    repo_owner: str = Field(description=_OWNER)
    repo_name: str = Field(description=_NAME)
    run_id: int = Field(description="Workflow run ID to cancel")


class GitHubForceCancelWorkflowRun(BaseModel):
    repo_owner: str = Field(description=_OWNER)
    repo_name: str = Field(description=_NAME)
    run_id: int = Field(description="Workflow run ID that ignores a normal cancel")


class GitHubRerunWorkflowRun(BaseModel):
    repo_owner: str = Field(description=_OWNER)
    repo_name: str = Field(description=_NAME)
    run_id: int = Field(description="Workflow run ID to re-run")
    failed_only: bool = Field(
        default=False, description="Re-run only the failed jobs (and their dependents)"
    )
    enable_debug_logging: bool = Field(default=False, description=_DEBUG)


class GitHubRerunFailedJobs(BaseModel):
    repo_owner: str = Field(description=_OWNER)
    repo_name: str = Field(description=_NAME)
    run_id: int = Field(description="Workflow run ID whose failed jobs to re-run")
    enable_debug_logging: bool = Field(default=False, description=_DEBUG)


class GitHubRerunJob(BaseModel):
    repo_owner: str = Field(description=_OWNER)
    repo_name: str = Field(description=_NAME)
    job_id: int = Field(description="Actions job ID (same as its check-run ID)")
    enable_debug_logging: bool = Field(default=False, description=_DEBUG)


class GitHubRerequestCheckRun(BaseModel):
    repo_owner: str = Field(description=_OWNER)
    repo_name: str = Field(description=_NAME)
    check_run_id: int = Field(
        description="Check run ID created by a GitHub App such as Azure Pipelines"
    )


class GitHubRerunFailedPRChecks(BaseModel):
    repo_owner: str = Field(description=_OWNER)
    repo_name: str = Field(description=_NAME)
    pr_number: int = Field(description="Pull request number")
    dry_run: bool = Field(
        default=False, description="List what would be re-run without changing anything"
    )
