"""Pydantic models for GitHub API tools"""

from pydantic import BaseModel
from typing import Optional


class GitHubGetPRChecks(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int
    status: Optional[str] = None
    conclusion: Optional[str] = None


class GitHubGetFailingJobs(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int
    include_logs: bool = True
    include_annotations: bool = True


class GitHubGetWorkflowRun(BaseModel):
    repo_owner: str
    repo_name: str
    run_id: int
    include_logs: bool = False


class GitHubGetPRDetails(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int
    include_files: bool = False
    include_reviews: bool = False


class GitHubListPullRequests(BaseModel):
    repo_owner: str
    repo_name: str
    state: str = "open"
    head: Optional[str] = None
    base: Optional[str] = None
    sort: str = "created"
    direction: str = "desc"
    per_page: int = 30
    page: int = 1


class GitHubGetPRStatus(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int


class GitHubGetPRFiles(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int
    per_page: int = 30
    page: int = 1
    include_patch: bool = False
