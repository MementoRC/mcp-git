"""Pydantic models for git_reflog_expire and git_gc (issue #283)."""

from pydantic import BaseModel, Field

_AGE = (
    "'now', 'never', 'all', an ISO date (YYYY-MM-DD, optionally followed by "
    "' HH:MM[:SS]' or 'THH:MM[:SS]') or '<n>.<unit>.ago' with unit "
    "second|minute|hour|day|week|month|year (plural allowed)"
)


class GitReflogExpire(BaseModel):
    repo_path: str
    expire: str = Field(
        default="now",
        description=f"Expire reflog entries older than this. Allowed: {_AGE}",
    )
    expire_unreachable: str | None = Field(
        default=None,
        description=(
            "Expire entries pointing at commits unreachable from the ref tip "
            f"older than this (--expire-unreachable). Allowed: {_AGE}"
        ),
    )
    include_stash: bool = Field(
        default=False,
        description=(
            "Also expire refs/stash. Default false: the stash stack is shared "
            "across worktrees and sessions, so wiping it destroys other work"
        ),
    )
    dry_run: bool = Field(
        default=True,
        description=(
            "True (default): only report how many entries would be removed. "
            "False: permanently remove them"
        ),
    )


class GitGc(BaseModel):
    repo_path: str
    prune: str = Field(
        default="2.weeks.ago",
        description=(
            "Prune loose unreachable objects older than this (--prune; git's "
            "own default). To finish a scrub pass 'now', only when no other "
            "process or session uses the repository (worktrees share one "
            f"object store). Allowed: {_AGE}"
        ),
    )
    aggressive: bool = Field(
        default=False,
        description="Pass --aggressive (slower, more thorough repack)",
    )
    dry_run: bool = Field(
        default=True,
        description=(
            "True (default): only report object counts and how many loose "
            "objects would be pruned. False: run git gc"
        ),
    )
