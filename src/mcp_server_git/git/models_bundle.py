"""Pydantic models for git bundle tools (issue #283)."""

from pydantic import BaseModel, Field


class GitBundleCreate(BaseModel):
    repo_path: str
    output_path: str = Field(description="Absolute path of the bundle file to write")
    refs: list[str] = Field(
        default=["--all"],
        description=(
            "Refs or rev-list ranges to include (default ['--all']; also "
            "--branches, --tags, --remotes, 'main', '^base..main')"
        ),
    )
    overwrite: bool = Field(
        default=False,
        description="Replace output_path if it already exists (refused by default)",
    )


class GitBundleVerify(BaseModel):
    repo_path: str
    bundle_path: str = Field(description="Absolute path of the bundle file to verify")
