"""Pydantic models for GitHub API tools"""

import re

from pydantic import BaseModel, field_validator, model_validator

# ============================================================================
# Validation Constants
# ============================================================================

# GitHub merge commit settings
SQUASH_MERGE_COMMIT_TITLES = frozenset({"PR_TITLE", "COMMIT_OR_PR_TITLE"})
SQUASH_MERGE_COMMIT_MESSAGES = frozenset({"PR_BODY", "COMMIT_MESSAGES", "BLANK"})
MERGE_COMMIT_TITLES = frozenset({"PR_TITLE", "MERGE_MESSAGE"})
MERGE_COMMIT_MESSAGES = frozenset({"PR_BODY", "PR_TITLE", "BLANK"})

# Visibility settings
REPO_VISIBILITY_OPTIONS = frozenset({"public", "private", "internal"})

# Branch name validation pattern (based on git-check-ref-format rules)
# Invalid patterns: starts with -, contains .., ~, ^, :, \, @{, ends with .lock
INVALID_BRANCH_PATTERNS = re.compile(
    r"(^-|"  # starts with -
    r"\.\.|"  # contains ..
    r"[\x00-\x1f\x7f]|"  # control characters
    r"~|"  # tilde
    r"\^|"  # caret
    r":|"  # colon
    r"\\|"  # backslash
    r"@\{|"  # @{
    r"^/|"  # starts with /
    r"/$|"  # ends with /
    r"\.lock$)"  # ends with .lock
)


def validate_branch_name(branch: str) -> str:
    """Validate branch name follows git-check-ref-format rules.

    Args:
        branch: The branch name to validate

    Returns:
        The validated branch name

    Raises:
        ValueError: If the branch name is invalid
    """
    if not branch or not branch.strip():
        raise ValueError("branch name cannot be empty")
    if INVALID_BRANCH_PATTERNS.search(branch):
        raise ValueError(
            f"Invalid branch name '{branch}'. Branch names cannot: "
            "start with '-' or '/', contain '..', '~', '^', ':', '\\', '@{{', "
            "control characters, or end with '/' or '.lock'"
        )
    return branch


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


class GitHubGetPRComments(BaseModel):
    """Retrieve top-level conversation comments on a PR."""

    repo_owner: str
    repo_name: str
    pr_number: int


class GitHubGetPRReviews(BaseModel):
    """Retrieve inline code review comments on a PR."""

    repo_owner: str
    repo_name: str
    pr_number: int


class GitHubReplyToPRComment(BaseModel):
    """Reply to a specific review comment thread."""

    repo_owner: str
    repo_name: str
    pr_number: int
    comment_id: int
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
    default_branch: str | None = None
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

    @field_validator("visibility")
    @classmethod
    def validate_visibility(cls, v: str | None) -> str | None:
        """Validate visibility is a valid GitHub option."""
        if v is None:
            return v
        if v not in REPO_VISIBILITY_OPTIONS:
            raise ValueError(
                f"visibility must be one of: {', '.join(sorted(REPO_VISIBILITY_OPTIONS))}"
            )
        return v

    @field_validator("squash_merge_commit_title")
    @classmethod
    def validate_squash_merge_commit_title(cls, v: str | None) -> str | None:
        """Validate squash merge commit title option."""
        if v is None:
            return v
        if v not in SQUASH_MERGE_COMMIT_TITLES:
            raise ValueError(
                f"squash_merge_commit_title must be one of: {', '.join(sorted(SQUASH_MERGE_COMMIT_TITLES))}"
            )
        return v

    @field_validator("squash_merge_commit_message")
    @classmethod
    def validate_squash_merge_commit_message(cls, v: str | None) -> str | None:
        """Validate squash merge commit message option."""
        if v is None:
            return v
        if v not in SQUASH_MERGE_COMMIT_MESSAGES:
            raise ValueError(
                f"squash_merge_commit_message must be one of: {', '.join(sorted(SQUASH_MERGE_COMMIT_MESSAGES))}"
            )
        return v

    @field_validator("merge_commit_title")
    @classmethod
    def validate_merge_commit_title(cls, v: str | None) -> str | None:
        """Validate merge commit title option."""
        if v is None:
            return v
        if v not in MERGE_COMMIT_TITLES:
            raise ValueError(
                f"merge_commit_title must be one of: {', '.join(sorted(MERGE_COMMIT_TITLES))}"
            )
        return v

    @field_validator("merge_commit_message")
    @classmethod
    def validate_merge_commit_message(cls, v: str | None) -> str | None:
        """Validate merge commit message option."""
        if v is None:
            return v
        if v not in MERGE_COMMIT_MESSAGES:
            raise ValueError(
                f"merge_commit_message must be one of: {', '.join(sorted(MERGE_COMMIT_MESSAGES))}"
            )
        return v


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

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, v: str) -> str:
        """Validate branch name is a valid Git reference."""
        return validate_branch_name(v)


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

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, v: str) -> str:
        """Validate branch name is a valid Git reference."""
        return validate_branch_name(v)


class GitHubDeleteBranchProtection(BaseModel):
    """Model for deleting branch protection rules."""

    repo_owner: str
    repo_name: str
    branch: str

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, v: str) -> str:
        """Validate branch name is a valid Git reference."""
        return validate_branch_name(v)


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


# ============================================================================
# GitHub Release Management Models (Issue #57)
# ============================================================================


class GitHubCreateRelease(BaseModel):
    """Model for creating a new GitHub release.

    Creates a release with optional release notes, draft mode, and prerelease flags.
    Can optionally generate release notes automatically from commit history.
    """

    repo_owner: str
    repo_name: str
    tag_name: str
    target_commitish: str | None = None  # defaults to default branch
    name: str | None = None  # release title, defaults to tag_name
    body: str | None = None  # release notes
    draft: bool = False
    prerelease: bool = False
    generate_release_notes: bool = False


class GitHubGetRelease(BaseModel):
    """Model for fetching a specific release by ID or tag.

    Either release_id or tag must be provided (mutually exclusive).
    Returns full release details including assets, author, and timestamps.
    """

    repo_owner: str
    repo_name: str
    release_id: int | None = None  # mutually exclusive with tag
    tag: str | None = None  # mutually exclusive with release_id

    @model_validator(mode="after")
    def validate_exclusive_params(self) -> "GitHubGetRelease":
        """Ensure either release_id or tag is provided, but not both."""
        if self.release_id is None and self.tag is None:
            raise ValueError("Either release_id or tag must be provided")
        if self.release_id is not None and self.tag is not None:
            raise ValueError("Cannot specify both release_id and tag")
        return self


class GitHubListReleases(BaseModel):
    """Model for listing repository releases.

    Returns a paginated list of releases ordered by creation date (newest first).
    """

    repo_owner: str
    repo_name: str
    per_page: int = 30
    page: int = 1


class GitHubUpdateRelease(BaseModel):
    """Model for updating an existing release.

    All fields except repo_owner, repo_name, and release_id are optional.
    Only provided fields will be updated.
    """

    repo_owner: str
    repo_name: str
    release_id: int
    tag_name: str | None = None
    target_commitish: str | None = None
    name: str | None = None
    body: str | None = None
    draft: bool | None = None
    prerelease: bool | None = None


class GitHubDeleteRelease(BaseModel):
    """Model for deleting a release.

    Note: This does not delete the associated Git tag.
    """

    repo_owner: str
    repo_name: str
    release_id: int


class GitHubUploadReleaseAsset(BaseModel):
    """Model for uploading an asset to a release.

    Uploads a file from the local filesystem to a GitHub release.
    Asset name defaults to the filename if not provided.
    """

    repo_owner: str
    repo_name: str
    release_id: int
    file_path: str  # local path to file
    name: str | None = None  # asset name, defaults to filename
    label: str | None = None  # description


class GitHubListReleaseAssets(BaseModel):
    """Model for listing assets of a release.

    Returns paginated list of release assets with download URLs and metadata.
    """

    repo_owner: str
    repo_name: str
    release_id: int
    per_page: int = 30
    page: int = 1


class GitHubDeleteReleaseAsset(BaseModel):
    """Model for deleting a release asset.

    Removes an asset from a release by asset ID.
    """

    repo_owner: str
    repo_name: str
    asset_id: int


# ============================================================================
# GitHub Actions Job Logs Models (Issue #125)
# ============================================================================


class GitHubGetJobLogs(BaseModel):
    """Model for fetching GitHub Actions job logs.

    Fetches the actual log content for a specific job, enabling CI failure
    diagnosis without navigating to the GitHub UI.

    IMPORTANT - LLM Context Efficiency:
        By default, logs are truncated to the last 500 lines and 100KB to prevent
        overwhelming the LLM context window. This is intentional for MCP server usage.

    The job_id can be obtained from:
    - github_get_failing_jobs: Returns failing job IDs for a PR
    - github_get_workflow_run: Returns job IDs for a workflow run
    - github_get_pr_checks: Returns check run IDs (which are job IDs)

    Example usage:
        # Get failing jobs first
        failing = github_get_failing_jobs(owner, repo, pr_number)
        # Extract job_id from output, then fetch logs (default: last 500 lines)
        logs = github_get_job_logs(owner, repo, job_id=12345)
        # For more context, increase tail_lines
        logs = github_get_job_logs(owner, repo, job_id=12345, tail_lines=1000)
        # For complete logs (still capped at 100KB for LLM safety)
        logs = github_get_job_logs(owner, repo, job_id=12345, full_log=True)

    Note:
        - Default: last 500 lines (LLM-friendly)
        - Hard limit: 100KB character limit for LLM context protection
        - Memory limit: 10MB for very large logs
        - Logs may not be available for old jobs (GitHub retention policy)
        - Rate limiting (429) may occur with frequent requests
    """

    repo_owner: str  # GitHub repository owner or organization name
    repo_name: str  # GitHub repository name
    job_id: int  # Job ID from GitHub Actions (from check runs or workflow jobs)
    tail_lines: int | None = None  # Return only last N lines; None uses default (500)
    full_log: bool = False  # If True, skip line limit (still has 100KB char limit)


# ============================================================================
# GitHub Repository Creation Model (Issue #127)
# ============================================================================


class GitHubCreateRepo(BaseModel):
    """Model for creating a new GitHub repository.

    Creates a new repository for the authenticated user or an organization.
    If org is provided, creates an organization repository (requires org admin rights).

    Example usage:
        # Create personal public repo
        github_create_repo(name="my-project", private=False)

        # Create org private repo with settings
        github_create_repo(
            name="internal-tool",
            org="my-org",
            private=True,
            description="Internal tooling",
            auto_init=True,
            gitignore_template="Python",
            license_template="mit"
        )

    Common gitignore_template values: Python, Node, Go, Java, Rust, C++, etc.
    Common license_template values: mit, apache-2.0, gpl-3.0, bsd-3-clause, etc.
    """

    name: str  # Repository name (required)
    org: str | None = None  # Organization name (None = personal repo)
    description: str | None = None  # Repository description
    private: bool = False  # True for private, False for public
    auto_init: bool = False  # Initialize with README
    gitignore_template: str | None = None  # e.g., "Python", "Node"
    license_template: str | None = None  # e.g., "mit", "apache-2.0"
    has_issues: bool = True  # Enable issues
    has_projects: bool = True  # Enable projects
    has_wiki: bool = True  # Enable wiki

    @field_validator("name")
    @classmethod
    def validate_repo_name(cls, v: str) -> str:
        """Validate repository name follows GitHub naming rules."""
        if not v:
            raise ValueError("Repository name cannot be empty")
        if len(v) > 100:
            raise ValueError("Repository name too long (max 100 characters)")
        if v.startswith("."):
            raise ValueError("Repository name cannot start with a period")
        if not re.match(r"^[a-zA-Z0-9._-]+$", v):
            raise ValueError(
                "Repository name can only contain alphanumeric characters, "
                "periods, hyphens, and underscores"
            )
        return v

    @field_validator("org")
    @classmethod
    def validate_org_name(cls, v: str | None) -> str | None:
        """Validate organization name if provided."""
        if v is None:
            return v
        if not v:
            raise ValueError("Organization name cannot be empty string")
        if len(v) > 39:
            raise ValueError("Organization name too long (max 39 characters)")
        if not re.match(r"^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?$", v):
            raise ValueError(
                "Organization name must start/end with alphanumeric and "
                "can only contain alphanumeric characters and hyphens"
            )
        return v
