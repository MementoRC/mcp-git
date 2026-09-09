"""Pydantic models for Git operations"""

from typing import Literal

from pydantic import AliasChoices, BaseModel, Field, model_validator


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
    amend: bool = Field(
        default=False,
        description="Amend the most recent commit instead of creating a new one",
    )
    gpg_sign: bool = False
    gpg_key_id: str | None = None
    allow_empty: bool = Field(
        default=False,
        description="Allow creating a commit with no staged changes (--allow-empty)",
    )


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
    show_signature: bool = False  # Include GPG signature status (%G? / %GS)
    since: str | None = None  # Date filter: "2024-01-01", "1 week ago"
    until: str | None = None  # Date filter: "yesterday", "2024-12-31"
    author: str | None = None  # Author filter: email or name
    grep: str | None = None  # Commit message search (regex)
    files: list[str] | None = None  # Commits affecting these files
    branch: str | None = None  # Specific branch (default: current)
    reverse: bool = False  # Reverse chronological order
    merges: bool | None = None  # None=all, True=only merges, False=no merges


class GitReflog(BaseModel):
    repo_path: str
    ref: str = Field(
        default="HEAD", description="Ref to show reflog for (default: HEAD)"
    )
    max_count: int | None = Field(
        default=None, ge=0, description="Maximum number of reflog entries to return"
    )
    all: bool = Field(  # noqa: A003
        default=False,
        description="Show reflog for all refs (git reflog --all)",
    )


class GitCreateBranch(BaseModel):
    repo_path: str
    branch_name: str
    base_branch: str | None = None
    start_point: str | None = None
    checkout: bool = True  # Switch HEAD to the new branch (issue #162)


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


class GitClone(BaseModel):
    repo_url: str
    target_path: str
    branch: str | None = None
    depth: int | None = None
    single_branch: bool = False
    recurse_submodules: bool = False


class GitPush(BaseModel):
    repo_path: str
    remote: str = "origin"
    branch: str | None = None
    set_upstream: bool = False
    force: bool = False
    # Issue #161: safer force-push variants
    force_with_lease: bool = False
    force_with_lease_expect: str | None = None  # "<refname>:<sha>" or "<sha>"
    force_if_includes: bool = False  # git 2.30+, composes with force_with_lease
    # Issue #173: delete remote branch and raw refspec support
    delete: bool = Field(
        False,
        description=(
            "Delete the remote branch (git push <remote> --delete <branch>). "
            "Mutually exclusive with force/refspec."
        ),
    )
    refspec: str | None = Field(
        None,
        description=(
            "Raw push refspec (e.g., 'src:dst' or ':branch' to delete). "
            "Mutually exclusive with branch/delete."
        ),
    )
    dry_run: bool = Field(
        False,
        description=(
            "Show what would be pushed without actually pushing (git push --dry-run). "
            "Compatible with all push modes including delete and refspec."
        ),
    )

    @model_validator(mode="after")
    def _validate_delete_and_refspec(self) -> "GitPush":
        if self.delete:
            if not self.branch:
                raise ValueError("delete=True requires branch to be set")
            if self.force or self.force_with_lease or self.force_if_includes:
                raise ValueError(
                    "delete=True cannot be combined with force/force_with_lease/force_if_includes"
                )
            if self.set_upstream:
                raise ValueError("delete=True cannot be combined with set_upstream")
            if self.refspec is not None:
                raise ValueError("delete=True cannot be combined with refspec")
        if self.refspec is not None:
            if self.branch is not None:
                raise ValueError("refspec cannot be combined with branch")
            if self.delete:
                raise ValueError("refspec cannot be combined with delete")
            if self.set_upstream:
                raise ValueError("refspec cannot be combined with set_upstream")
        return self


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
    onto: str | None = Field(
        default=None, description="Rebase --onto target (new base)"
    )
    fork_point: str | None = Field(
        default=None, description="Fork point / old base for --onto"
    )
    branch: str | None = Field(
        default=None, description="Branch to rebase (default: current HEAD)"
    )


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
    branch_type: Literal["local", "remote", "all"] = Field(
        "local", description="Which branches to list: local, remote, or all"
    )
    pattern: str | None = Field(
        None, description="fnmatch glob filter, e.g. 'feature/*'"
    )
    contains: str | None = Field(
        None, description="commit-ish; only branches containing this commit"
    )
    merged: bool | None = Field(
        None,
        description="True=only merged into HEAD, False=only unmerged, None=no filter",
    )
    sort: str | None = Field(
        None,
        description="Sort key, e.g. '-committerdate' (most-recent first), 'refname', 'authordate'. "
        "Mirrors `git for-each-ref --sort=<key>` semantics. None = no ordering guarantee.",
    )


class GitMergeBase(BaseModel):
    repo_path: str
    ref1: str
    ref2: str


class GitSubmoduleStatus(BaseModel):
    repo_path: str


class GitSubmoduleAdd(BaseModel):
    repo_path: str
    url: str
    path: str
    branch: str | None = None


class GitSubmoduleUpdate(BaseModel):
    repo_path: str
    init: bool = True
    recursive: bool = False
    remote: bool = False
    paths: list[str] | None = None


class GitSubmoduleSync(BaseModel):
    repo_path: str
    recursive: bool = False


class GitConfigGet(BaseModel):
    repo_path: str
    key: str
    file: str | None = None
    scope: str | None = None


class GitConfigSet(BaseModel):
    repo_path: str
    key: str
    value: str
    file: str | None = None
    scope: str | None = None


class GitConfigList(BaseModel):
    repo_path: str
    file: str | None = None
    scope: str | None = None


class GitRestore(BaseModel):
    repo_path: str
    files: list[str] = Field(description="Files to restore")
    staged: bool = Field(
        default=False, description="Unstage files (git restore --staged)"
    )
    source: str | None = Field(
        default=None,
        description="Restore from specific commit/ref (git restore --source)",
    )


class GitBranchUpdate(BaseModel):
    repo_path: str
    branch_name: str = Field(description="Branch to update or delete")
    target: str | None = Field(
        default=None,
        description="Target ref for force-update (git branch -f <name> <target>)",
    )
    delete: bool = Field(default=False, description="Delete the branch")
    force: bool = Field(
        default=False, description="Force delete even if not merged (git branch -D)"
    )


class GitBranchDelete(BaseModel):
    repo_path: str
    branch_name: str = Field(description="Branch to delete")
    force: bool = Field(default=False, description="Force delete unmerged branch (-D)")


class GitWorktreeList(BaseModel):
    repo_path: str


class GitWorktreeRemove(BaseModel):
    repo_path: str
    worktree_path: str = Field(description="Path of worktree to remove")
    force: bool = Field(
        default=False, description="Force removal even with modifications"
    )


class GitWorktreeAdd(BaseModel):
    """Inputs for git_worktree_add — create a new linked worktree."""

    repo_path: str = Field(..., description="Path to the existing git repository.")
    worktree_path: str = Field(
        ..., description="Filesystem path where the new worktree should be created."
    )
    branch: str | None = Field(
        default=None,
        description=(
            "Existing branch to check out in the new worktree. When new_branch "
            "is also set, this is instead used as the START POINT that the new "
            "branch is created from (legacy form; prefer commit_ish)."
        ),
    )
    new_branch: str | None = Field(
        default=None,
        description="Name of a NEW branch to create and check out (uses -b, or -B with force).",
    )
    commit_ish: str | None = Field(
        default=None,
        description=(
            "Start point for new_branch: the trailing <commit-ish> of "
            "`git worktree add` (branch, tag, or SHA). Without new_branch this "
            "creates a detached worktree at that commit. Takes precedence over "
            "branch when both are supplied alongside new_branch."
        ),
    )
    force: bool = Field(
        default=False,
        description="Pass --force to git worktree add. When combined with new_branch, uses -B (force-create) instead of -b.",
    )


class GitMergeTree(BaseModel):
    """Dry-run three-way merge; returns the merged tree's OID on success."""

    repo_path: str
    branch1: str = Field(description="First branch (typically current)")
    branch2: str = Field(
        description="Second branch (typically incoming); accepts a raw SHA"
    )


class GitMergeFile(BaseModel):
    """Three-way merge of a single file across three arbitrary revisions.

    The natural unit of work when hand-resolving a transplant: one file at a
    time, with conflict markers, without merging every other conflicting
    path. Neither the working tree nor the index is modified.
    """

    repo_path: str
    path: str = Field(description="File path as it appears in each revision")
    base_rev: str = Field(description="Merge base revision")
    ours_rev: str = Field(description="Our side revision (accepts a raw SHA)")
    theirs_rev: str = Field(description="Their side revision (accepts a raw SHA)")
    labels: list[str] | None = Field(
        default=None,
        description="Three conflict-marker labels: ours, base, theirs",
    )
    output_path: str | None = Field(
        default=None,
        description="Absolute path; write the complete merged result there instead of returning it inline",
    )


class GitRm(BaseModel):
    repo_path: str
    file: str = Field(
        description="Single file path to remove (no wildcards, no directories)"
    )
    cached: bool = Field(
        default=False,
        description="Remove from index only, keep working tree file (--cached)",
    )
    dry_run: bool = Field(
        default=False,
        description="Show what would be removed without doing it (--dry-run)",
    )
