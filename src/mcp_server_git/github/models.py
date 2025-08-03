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


# GitHub CLI Models
class GitHubCLICreatePR(BaseModel):
    repo_path: str
    title: str
    body: Optional[str] = None
    base: Optional[str] = None
    head: Optional[str] = None
    draft: bool = False
    web: bool = False


class GitHubCLIEditPR(BaseModel):
    repo_path: str
    pr_number: int
    title: Optional[str] = None
    body: Optional[str] = None
    base: Optional[str] = None
    add_assignee: Optional[list[str]] = None
    remove_assignee: Optional[list[str]] = None
    add_label: Optional[list[str]] = None
    remove_label: Optional[list[str]] = None
    add_reviewer: Optional[list[str]] = None
    remove_reviewer: Optional[list[str]] = None


class GitHubCLIMergePR(BaseModel):
    repo_path: str
    pr_number: int
    merge_method: str = "merge"  # merge, squash, rebase
    delete_branch: bool = False
    auto: bool = False


class GitHubCLIClosePR(BaseModel):
    repo_path: str
    pr_number: int
    comment: Optional[str] = None


class GitHubCLIReopenPR(BaseModel):
    repo_path: str
    pr_number: int
    comment: Optional[str] = None


class GitHubCLIReadyPR(BaseModel):
    repo_path: str
    pr_number: int


class GitHubCreateIssue(BaseModel):
    repo_owner: str
    repo_name: str
    title: str
    body: Optional[str] = None
    labels: Optional[list[str]] = None
    assignees: Optional[list[str]] = None


class GitHubEditPRDescription(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int
    description: str


class GitHubListIssues(BaseModel):
    repo_owner: str
    repo_name: str
    state: str = "open"
    labels: Optional[str] = None
    assignee: Optional[str] = None
    sort: str = "created"
    direction: str = "desc"
    per_page: int = 30
    page: int = 1


class GitHubUpdateIssue(BaseModel):
    repo_owner: str
    repo_name: str
    issue_number: int
    state: Optional[str] = None
    labels: Optional[list[str]] = None
    assignees: Optional[list[str]] = None
    title: Optional[str] = None
    body: Optional[str] = None


# GitHub Repository Settings Management Models

class GitHubRepoSettings(BaseModel):
    """Update repository settings like merge options, wikis, etc."""
    repo_owner: str
    repo_name: str
    has_issues: Optional[bool] = None
    has_projects: Optional[bool] = None
    has_wiki: Optional[bool] = None
    allow_squash_merge: Optional[bool] = None
    allow_merge_commit: Optional[bool] = None
    allow_rebase_merge: Optional[bool] = None
    delete_branch_on_merge: Optional[bool] = None
    allow_auto_merge: Optional[bool] = None
    allow_update_branch: Optional[bool] = None
    use_squash_pr_title_as_default: Optional[bool] = None
    squash_merge_commit_title: Optional[str] = None  # "PR_TITLE" or "COMMIT_OR_PR_TITLE"
    squash_merge_commit_message: Optional[str] = None  # "PR_BODY", "COMMIT_MESSAGES", or "BLANK"
    merge_commit_title: Optional[str] = None  # "PR_TITLE" or "MERGE_MESSAGE"
    merge_commit_message: Optional[str] = None  # "PR_TITLE", "PR_BODY", or "BLANK"


class GitHubActionsSettings(BaseModel):
    """Configure GitHub Actions permissions and settings."""
    repo_owner: str
    repo_name: str
    enabled: Optional[bool] = None
    allowed_actions: Optional[str] = None  # "all", "disabled", "selected", "local_only"
    github_owned_allowed: Optional[bool] = None
    verified_allowed: Optional[bool] = None
    patterns_allowed: Optional[list[str]] = None


class GitHubWorkflowPermissions(BaseModel):
    """Configure default workflow permissions."""
    repo_owner: str
    repo_name: str
    default_workflow_permissions: Optional[str] = None  # "read" or "write"
    can_approve_pull_request_reviews: Optional[bool] = None


class GitHubBranchProtection(BaseModel):
    """Configure branch protection rules."""
    repo_owner: str
    repo_name: str
    branch: str
    required_status_checks: Optional[dict] = None
    enforce_admins: Optional[bool] = None
    required_pull_request_reviews: Optional[dict] = None
    restrictions: Optional[dict] = None
    allow_force_pushes: Optional[bool] = None
    allow_deletions: Optional[bool] = None
    block_creations: Optional[bool] = None
    required_linear_history: Optional[bool] = None
    allow_fork_syncing: Optional[bool] = None
    lock_branch: Optional[bool] = None
    required_conversation_resolution: Optional[bool] = None


class GitHubSecuritySettings(BaseModel):
    """Configure repository security settings."""
    repo_owner: str
    repo_name: str
    security_and_analysis: Optional[dict] = None
    vulnerability_alerts: Optional[bool] = None
    automated_security_fixes: Optional[bool] = None
