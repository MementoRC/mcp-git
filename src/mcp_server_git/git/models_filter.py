"""Pydantic model for the git_filter_paths tool (issue #283)."""

from pydantic import BaseModel, Field


class GitFilterPaths(BaseModel):
    repo_path: str
    paths: list[str] = Field(
        description=(
            "Repo-relative files or directories, taken literally (no globs). "
            "Leading '-', absolute paths and '..' are rejected"
        ),
    )
    invert: bool = Field(
        default=False,
        description=(
            "False: remove the listed paths from history. True: keep ONLY the "
            "listed paths and remove everything else"
        ),
    )
    all_refs: bool = Field(
        default=False,
        description=(
            "Rewrite all local branches and tags (--branches --tags; tags via "
            "--tag-name-filter cat, annotated signed tags lose their "
            "signatures). refs/remotes/* and refs/stash are never rewritten. "
            "Default: only `branch`"
        ),
    )
    branch: str | None = Field(
        default=None,
        description="Branch to rewrite when all_refs is false (default: current)",
    )
    prune_empty: bool = Field(
        default=True, description="Drop commits left empty by the filter"
    )
    dry_run: bool = Field(
        default=False,
        description="Only report the commits, files and refs affected; change nothing",
    )
    allow_with_remote: bool = Field(
        default=False,
        description=(
            "Proceed although remotes are configured (the remote keeps the old, "
            "now divergent history; this tool never pushes)"
        ),
    )
    gpg_sign: bool = Field(
        default=False,
        description="Sign rewritten commits; always applied while the server "
        "enforces signing (the default configuration)",
    )
    backup_path: str | None = Field(
        default=None,
        description=(
            "Absolute path for the verified bundle backup written before the "
            "rewrite (default: <repo>/../<name>-pre-filter-<UTC>.bundle); "
            "an existing file is never overwritten"
        ),
    )
