"""Pydantic models for Git operations"""

from pydantic import BaseModel
from typing import Optional


class GitStatus(BaseModel):
    repo_path: str
    porcelain: bool = False
    status_filter: Optional[str] = (
        None  # Filter by status (staged, unstaged, untracked, ignored)
    )
    path_filter: Optional[str] = None  # Filter by file path pattern
    include_ignored: bool = False  # Include ignored files
    include_untracked: bool = True  # Include untracked files


class GitDiffUnstaged(BaseModel):
    repo_path: str
    stat_only: Optional[bool] = False
    max_lines: Optional[int] = None


class GitDiffStaged(BaseModel):
    repo_path: str
    stat_only: Optional[bool] = False
    max_lines: Optional[int] = None


class GitDiff(BaseModel):
    repo_path: str
    target: str
    stat_only: Optional[bool] = False
    max_lines: Optional[int] = None


class GitCommit(BaseModel):
    repo_path: str
    message: str
    gpg_sign: bool = False
    gpg_key_id: Optional[str] = None


class GitAdd(BaseModel):
    repo_path: str
    files: list[str]


class GitReset(BaseModel):
    repo_path: str
    mode: Optional[str] = None  # --soft, --mixed, --hard
    target: Optional[str] = None  # commit hash, branch, tag
    files: Optional[list[str]] = None  # specific files to reset


class GitLog(BaseModel):
    repo_path: str
    max_count: int = 10
    oneline: bool = False
    graph: bool = False
    format: Optional[str] = None


class GitCreateBranch(BaseModel):
    repo_path: str
    branch_name: str
    base_branch: Optional[str] = None


class GitCheckout(BaseModel):
    repo_path: str
    branch_name: str


class GitShow(BaseModel):
    repo_path: str
    revision: str
    stat_only: Optional[bool] = False
    max_lines: Optional[int] = None


class GitInit(BaseModel):
    repo_path: str


class GitPush(BaseModel):
    repo_path: str
    remote: str = "origin"
    branch: Optional[str] = None
    set_upstream: bool = False
    force: bool = False


class GitPull(BaseModel):
    repo_path: str
    remote: str = "origin"
    branch: Optional[str] = None


class GitDiffBranches(BaseModel):
    repo_path: str
    base_branch: str
    compare_branch: str
    stat_only: Optional[bool] = False
    max_lines: Optional[int] = None


class GitRebase(BaseModel):
    repo_path: str
    target_branch: str


class GitMerge(BaseModel):
    repo_path: str
    source_branch: str
    strategy: str = "merge"
    message: Optional[str] = None


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


class GitRemoteList(BaseModel):
    repo_path: str
    verbose: bool = False


class GitRemoteAdd(BaseModel):
    repo_path: str
    name: str
    url: str


class GitRemoteRemove(BaseModel):
    repo_path: str
    name: str


class GitRemoteRename(BaseModel):
    repo_path: str
    old_name: str
    new_name: str


class GitRemoteSetUrl(BaseModel):
    repo_path: str
    name: str
    url: str


class GitRemoteGetUrl(BaseModel):
    repo_path: str
    name: str


class GitFetch(BaseModel):
    repo_path: str
    remote: str = "origin"
    branch: Optional[str] = None
    prune: bool = False


class GitStashList(BaseModel):
    repo_path: str


class GitStashPush(BaseModel):
    repo_path: str
    message: Optional[str] = None
    include_untracked: bool = False


class GitStashPop(BaseModel):
    repo_path: str
    stash_id: Optional[str] = None


class GitStashDrop(BaseModel):
    repo_path: str
    stash_id: Optional[str] = None


class GitClean(BaseModel):
    repo_path: str
    dry_run: bool = True  # Safety first - default to dry run
    force: bool = False  # Force removal (required for directories like __pycache__)
    directories: bool = False  # Remove untracked directories
    ignored: bool = False  # Remove ignored files (e.g., files in .gitignore)
    exclude_pattern: Optional[str] = None  # Pattern to exclude from cleaning
    include_pattern: Optional[str] = None  # Pattern to include in cleaning (e.g., "__pycache__")
