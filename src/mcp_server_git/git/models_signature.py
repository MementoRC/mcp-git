"""Pydantic model for git_verify_commit (issue #321)."""

from pydantic import BaseModel, Field


class GitVerifyCommit(BaseModel):
    repo_path: str
    commit: str = Field(
        default="HEAD", description="Commit-ish to verify (default: HEAD)"
    )
