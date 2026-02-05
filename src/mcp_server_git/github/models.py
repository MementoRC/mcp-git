"""Pydantic models for GitHub API tools"""

from pydantic import BaseModel, field_validator


class GitHubGetPRChecks(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int
    status: str | None = None
    conclusion: str | None = None


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


class GitHubListWorkflowRuns(BaseModel):
    repo_owner: str
    repo_name: str
    workflow_id: str | None = None
    actor: str | None = None
    branch: str | None = None
    event: str | None = None
    status: str | None = None
    conclusion: str | None = None
    per_page: int = 30
    page: int = 1
    created: str | None = None
    exclude_pull_requests: bool = False
    check_suite_id: int | None = None
    head_sha: str | None = None


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
    head: str | None = None
    base: str | None = None
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
    body: str | None = None
    base: str | None = None
    head: str | None = None
    draft: bool = False
    web: bool = False


class GitHubCLIEditPR(BaseModel):
    repo_path: str
    pr_number: int
    title: str | None = None
    body: str | None = None
    base: str | None = None
    add_assignee: list[str] | None = None
    remove_assignee: list[str] | None = None
    add_label: list[str] | None = None
    remove_label: list[str] | None = None
    add_reviewer: list[str] | None = None
    remove_reviewer: list[str] | None = None


class GitHubCLIMergePR(BaseModel):
    repo_path: str
    pr_number: int
    merge_method: str = "merge"  # merge, squash, rebase
    delete_branch: bool = False
    auto: bool = False


class GitHubCLIClosePR(BaseModel):
    repo_path: str
    pr_number: int
    comment: str | None = None


class GitHubCLIReopenPR(BaseModel):
    repo_path: str
    pr_number: int
    comment: str | None = None


class GitHubCLIReadyPR(BaseModel):
    repo_path: str
    pr_number: int


# GitHub Issues Models
class GitHubCreateIssue(BaseModel):
    repo_owner: str
    repo_name: str
    title: str
    body: str | None = None
    labels: list[str] | None = None
    assignees: list[str] | None = None
    milestone: int | None = None

    @field_validator("milestone")
    @classmethod
    def validate_milestone(cls, v: int | None) -> int | None:
        """Validate milestone ID is positive (GitHub API expects positive integers)"""
        if v is None:
            return v
        return v if v > 0 else None


class GitHubListIssues(BaseModel):
    """Model for GitHub List Issues API with comprehensive filtering options.

    Complex filtering parameters:
    - since: ISO 8601 timestamp format (e.g., '2023-01-01T00:00:00Z') to filter
      issues updated after this time
    - milestone: Use milestone number as string, '*' for any milestone, 'none'
      for issues without milestone (e.g., '1', '*', 'none')
    - labels: List of label names for AND filtering (e.g., ['bug', 'frontend'])
    """

    repo_owner: str
    repo_name: str
    state: str = "open"  # open, closed, all
    labels: list[str] | None = None
    assignee: str | None = None
    creator: str | None = None
    mentioned: str | None = None
    milestone: str | None = None
    sort: str = "created"  # created, updated, comments
    direction: str = "desc"  # asc, desc
    since: str | None = None
    per_page: int = 30
    page: int = 1


class GitHubGetIssue(BaseModel):
    """Model for fetching a single GitHub issue by number.

    Returns full issue details including title, body, state, labels,
    assignees, milestone, comments count, and timestamps.
    """

    repo_owner: str
    repo_name: str
    issue_number: int


class GitHubUpdateIssue(BaseModel):
    repo_owner: str
    repo_name: str
    issue_number: int
    title: str | None = None
    body: str | None = None
    state: str | None = None  # open, closed
    labels: list[str] | None = None
    assignees: list[str] | None = None
    milestone: int | None = None

    @field_validator("milestone")
    @classmethod
    def validate_milestone(cls, v: int | None) -> int | None:
        """Validate milestone ID is positive (GitHub API expects positive integers)"""
        if v is None:
            return v
        return v if v > 0 else None


class GitHubSearchIssues(BaseModel):
    """Model for GitHub Search Issues API with advanced query capabilities.

    Supports GitHub's search qualifiers like:
    - is:issue is:open author:username
    - label:bug label:"help wanted"
    - created:2023-01-01..2023-12-31
    - updated:>2023-06-01
    - milestone:"v1.0" assignee:username
    """

    repo_owner: str
    repo_name: str
    query: str  # GitHub search query with qualifiers
    sort: str = "created"  # created, updated, comments
    order: str = "desc"  # asc, desc
    per_page: int = 30
    page: int = 1


class GitHubCreateIssueFromTemplate(BaseModel):
    """Model for creating GitHub issues from predefined templates."""

    repo_owner: str
    repo_name: str
    title: str
    template_name: str = "bug_report"  # bug_report, feature_request, question, custom
    template_data: dict | None = None  # Additional data for template customization


class GitHubBulkUpdateIssues(BaseModel):
    """Model for bulk updating multiple GitHub issues with common properties."""

    repo_owner: str
    repo_name: str
    issue_numbers: list[int]  # List of issue numbers to update
    labels: list[str] | None = None
    assignees: list[str] | None = None
    milestone: int | None = None
    state: str | None = None  # open, closed

    @field_validator("milestone")
    @classmethod
    def validate_milestone(cls, v: int | None) -> int | None:
        """Validate milestone ID is positive (GitHub API expects positive integers)"""
        if v is None:
            return v
        return v if v > 0 else None


class GitHubEditPRDescription(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int
    description: str


class GitHubCreatePR(BaseModel):
    repo_owner: str
    repo_name: str
    title: str
    head: str
    base: str
    body: str | None = None
    draft: bool = False


class GitHubMergePR(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int
    commit_title: str | None = None
    commit_message: str | None = None
    merge_method: str = "merge"


class GitHubAddPRComment(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int
    body: str


class GitHubClosePR(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int


class GitHubReopenPR(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int


class GitHubUpdatePR(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int
    title: str | None = None
    body: str | None = None
    state: str | None = None
    base: str | None = None


# ============================================================================
# Repository Settings Management Models (Issue #41)
# ============================================================================


class GitHubGetRepoSettings(BaseModel):
    """Model for fetching repository settings."""

    repo_owner: str
    repo_name: str


class GitHubUpdateRepoSettings(BaseModel):
    """Model for updating repository settings.

    Configurable settings include:
    - Visibility and access settings
    - Feature toggles (issues, wiki, projects, discussions)
    - Merge strategies and options
    - Branch and security settings
    """

    repo_owner: str
    repo_name: str
    # Basic settings
    description: str | None = None
    homepage: str | None = None
    private: bool | None = None
    visibility: str | None = None  # public, private, internal
    # Feature toggles
    has_issues: bool | None = None
    has_projects: bool | None = None
    has_wiki: bool | None = None
    has_discussions: bool | None = None
    # Merge settings
    allow_squash_merge: bool | None = None
    allow_merge_commit: bool | None = None
    allow_rebase_merge: bool | None = None
    allow_auto_merge: bool | None = None
    delete_branch_on_merge: bool | None = None
    allow_update_branch: bool | None = None
    # Squash merge settings
    squash_merge_commit_title: str | None = None  # PR_TITLE, COMMIT_OR_PR_TITLE
    squash_merge_commit_message: str | None = None  # PR_BODY, COMMIT_MESSAGES, BLANK
    # Merge commit settings
    merge_commit_title: str | None = None  # PR_TITLE, MERGE_MESSAGE
    merge_commit_message: str | None = None  # PR_BODY, PR_TITLE, BLANK
    # Security settings
    archived: bool | None = None
    web_commit_signoff_required: bool | None = None


# ============================================================================
# GitHub Actions Configuration Models (Issue #41)
# ============================================================================


class GitHubGetActionsPermissions(BaseModel):
    """Model for fetching GitHub Actions permissions for a repository."""

    repo_owner: str
    repo_name: str


class GitHubUpdateActionsPermissions(BaseModel):
    """Model for updating GitHub Actions permissions.

    Settings include:
    - enabled: Whether GitHub Actions is enabled
    - allowed_actions: Which actions can be used (all, local_only, selected)
    """

    repo_owner: str
    repo_name: str
    enabled: bool | None = None
    allowed_actions: str | None = None  # all, local_only, selected


class GitHubGetAllowedActions(BaseModel):
    """Model for fetching allowed actions for a repository."""

    repo_owner: str
    repo_name: str


class GitHubUpdateAllowedActions(BaseModel):
    """Model for updating allowed actions.

    Specifies which actions and reusable workflows are allowed.
    """

    repo_owner: str
    repo_name: str
    github_owned_allowed: bool | None = None
    verified_allowed: bool | None = None
    patterns_allowed: list[str] | None = None  # e.g., ["actions/checkout@*"]


class GitHubGetWorkflowPermissions(BaseModel):
    """Model for fetching default workflow permissions."""

    repo_owner: str
    repo_name: str


class GitHubUpdateWorkflowPermissions(BaseModel):
    """Model for updating default workflow permissions.

    Controls the default permissions granted to the GITHUB_TOKEN.
    """

    repo_owner: str
    repo_name: str
    default_workflow_permissions: str | None = None  # read, write
    can_approve_pull_request_reviews: bool | None = None


# ============================================================================
# Branch Protection Rules Models (Issue #41)
# ============================================================================


class GitHubGetBranchProtection(BaseModel):
    """Model for fetching branch protection rules."""

    repo_owner: str
    repo_name: str
    branch: str


class GitHubUpdateBranchProtection(BaseModel):
    """Model for creating/updating branch protection rules.

    Comprehensive branch protection settings including:
    - Required status checks
    - Required pull request reviews
    - Enforce admins
    - Restrictions on who can push
    """

    repo_owner: str
    repo_name: str
    branch: str
    # Required status checks
    required_status_checks_strict: bool | None = None
    required_status_checks_contexts: list[str] | None = None
    # Required pull request reviews
    require_pull_request_reviews: bool | None = None
    dismiss_stale_reviews: bool | None = None
    require_code_owner_reviews: bool | None = None
    required_approving_review_count: int | None = None
    require_last_push_approval: bool | None = None
    # Restrictions
    enforce_admins: bool | None = None
    restrict_pushes: bool | None = None
    push_allowances_users: list[str] | None = None
    push_allowances_teams: list[str] | None = None
    # Other settings
    required_linear_history: bool | None = None
    allow_force_pushes: bool | None = None
    allow_deletions: bool | None = None
    block_creations: bool | None = None
    required_conversation_resolution: bool | None = None
    lock_branch: bool | None = None
    allow_fork_syncing: bool | None = None


class GitHubDeleteBranchProtection(BaseModel):
    """Model for deleting branch protection rules."""

    repo_owner: str
    repo_name: str
    branch: str


# ============================================================================
# Security & Compliance Models (Issue #41)
# ============================================================================


class GitHubGetVulnerabilityAlerts(BaseModel):
    """Model for checking if vulnerability alerts are enabled."""

    repo_owner: str
    repo_name: str


class GitHubEnableVulnerabilityAlerts(BaseModel):
    """Model for enabling vulnerability alerts (Dependabot alerts)."""

    repo_owner: str
    repo_name: str


class GitHubDisableVulnerabilityAlerts(BaseModel):
    """Model for disabling vulnerability alerts."""

    repo_owner: str
    repo_name: str


class GitHubGetAutomatedSecurityFixes(BaseModel):
    """Model for checking if automated security fixes are enabled."""

    repo_owner: str
    repo_name: str


class GitHubEnableAutomatedSecurityFixes(BaseModel):
    """Model for enabling automated security fixes (Dependabot security updates)."""

    repo_owner: str
    repo_name: str


class GitHubDisableAutomatedSecurityFixes(BaseModel):
    """Model for disabling automated security fixes."""

    repo_owner: str
    repo_name: str


class GitHubGetSecretScanning(BaseModel):
    """Model for getting secret scanning status."""

    repo_owner: str
    repo_name: str


class GitHubGetSecurityAnalysis(BaseModel):
    """Model for getting comprehensive security analysis status.

    Returns status of:
    - Vulnerability alerts (Dependabot alerts)
    - Automated security fixes (Dependabot security updates)
    - Secret scanning
    - Code scanning (if available)
    """

    repo_owner: str
    repo_name: str
