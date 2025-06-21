"""Pydantic models for Git operations"""

from pydantic import BaseModel
from typing import Optional


class GitStatus(BaseModel):
    repo_path: str
    porcelain: bool = False


class GitDiffUnstaged(BaseModel):
    repo_path: str


class GitDiffStaged(BaseModel):
    repo_path: str


class GitDiff(BaseModel):
    repo_path: str
    target: str


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


class GitRebase(BaseModel):
    repo_path: str
    target_branch: str
    interactive: bool = False


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