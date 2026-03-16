"""Pydantic models for Git operations"""

from pydantic import AliasChoices, BaseModel, Field


class GitStatus(BaseModel):
    repo_path: str
    porcelain: bool = False


class GitDiffUnstaged(BaseModel):
    repo_path: str
    stat_only: bool | None = False
    max_lines: int | None = None
    name_only: bool | None = False
    paths: list[str] | None = None


class GitDiffStaged(BaseModel):
    repo_path: str
    stat_only: bool | None = False
    max_lines: int | None = None
    name_only: bool | None = False
    paths: list[str] | None = None


class GitDiff(BaseModel):
    repo_path: str
    target: str | None = None  # Made optional for commit range scenarios
    stat_only: bool | None = False
    max_lines: int | None = None
    name_only: bool | None = False
    commit_range: str | None = None
    base_commit: str | None = None
    target_commit: str | None = None
    paths: list[str] | None = None


class GitCommit(BaseModel):
    repo_path: str
    message: str
    amend: bool = Field(default=False, description="Amend the most recent commit instead of creating a new one")
    gpg_sign: bool = False
    gpg_key_id: str | None = None


class GitAdd(BaseModel):
    repo_path: str
    files: list[str]


class GitReset(BaseModel):
    repo_path: str
    mode: str | None = None  # --soft, --mixed, --hard
    target: str | None = None  # commit hash, branch, tag
    files: list[str] | None = None  # specific files to reset


class GitLog(BaseModel):
    repo_path: str
    max_count: int = 10
    oneline: bool = False
    graph: bool = False
    format: str | None = None
    since: str | None = None  # Date filter: "2024-01-01", "1 week ago"
    until: str | None = None  # Date filter: "yesterday", "2024-12-31"
    author: str | None = None  # Author filter: email or name
    grep: str | None = None  # Commit message search (regex)
    files: list[str] | None = None  # Commits affecting these files
    branch: str | None = None  # Specific branch (default: current)
    reverse: bool = False  # Reverse chronological order
    merges: bool | None = None  # None=all, True=only merges, False=no merges


class GitCreateBranch(BaseModel):
    repo_path: str
    branch_name: str
    base_branch: str | None = None


class GitCheckout(BaseModel):
    repo_path: str
    branch_name: str


class GitShow(BaseModel):
    repo_path: str
    revision: str
    stat_only: bool | None = False
    max_lines: int | None = None


class GitInit(BaseModel):
    repo_path: str


class GitPush(BaseModel):
    repo_path: str
    remote: str = "origin"
    branch: str | None = None
    set_upstream: bool = False
    force: bool = False


class GitPull(BaseModel):
    repo_path: str
    remote: str = "origin"
    branch: str | None = None


class GitDiffBranches(BaseModel):
    """Compare two branches.

    Accepts both 'base_branch'/'compare_branch' and 'branch1'/'branch2' naming.
    """

    repo_path: str
    base_branch: str = Field(validation_alias=AliasChoices("base_branch", "branch1"))
    compare_branch: str = Field(
        validation_alias=AliasChoices("compare_branch", "branch2")
    )
    stat_only: bool | None = False
    max_lines: int | None = None


class GitRebase(BaseModel):
    repo_path: str
    target_branch: str


class GitMerge(BaseModel):
    repo_path: str
    source_branch: str
    strategy: str = "merge"
    message: str | None = None


class GitCherryPick(BaseModel):
    repo_path: str
    commit_hash: str
    no_commit: bool = False


class GitAbort(BaseModel):
    repo_path: str
    operation: str


class GitContinue(BaseModel):
    repo_path: str
    operation: str


class GitSecurityValidate(BaseModel):
    repo_path: str


class GitSecurityEnforce(BaseModel):
    repo_path: str
    strict_mode: bool = True


class GitBranchList(BaseModel):
    repo_path: str
    remote: bool = False
    all: bool = False
    pattern: str | None = None


class GitMergeBase(BaseModel):
    repo_path: str
    ref1: str
    ref2: str
