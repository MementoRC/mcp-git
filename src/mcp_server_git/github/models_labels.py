"""Pydantic models for label tools (#327)."""

from pydantic import BaseModel, Field

_OWNER = "Repository owner/organization"
_NAME = "Repository name"
_COLOR = "6-digit hex color, with or without leading '#' (e.g. 'fbca04')"


class GitHubListLabels(BaseModel):
    repo_owner: str = Field(description=_OWNER)
    repo_name: str = Field(description=_NAME)
    per_page: int = Field(default=100, description="Labels per page (max 100)")
    page: int = Field(default=1, description="Page number")


class GitHubCreateLabel(BaseModel):
    repo_owner: str = Field(description=_OWNER)
    repo_name: str = Field(description=_NAME)
    name: str = Field(description="Label name")
    color: str = Field(description=_COLOR)
    description: str | None = Field(default=None, description="Label description")


class GitHubUpdateLabel(BaseModel):
    repo_owner: str = Field(description=_OWNER)
    repo_name: str = Field(description=_NAME)
    name: str = Field(description="Current label name")
    new_name: str | None = Field(default=None, description="New label name")
    color: str | None = Field(default=None, description=_COLOR)
    description: str | None = Field(default=None, description="New description")


class GitHubAddIssueLabels(BaseModel):
    repo_owner: str = Field(description=_OWNER)
    repo_name: str = Field(description=_NAME)
    issue_number: int = Field(description="Issue or pull request number")
    labels: list[str] = Field(description="Label names to add (non-empty)")


class GitHubRemoveIssueLabel(BaseModel):
    repo_owner: str = Field(description=_OWNER)
    repo_name: str = Field(description=_NAME)
    issue_number: int = Field(description="Issue or pull request number")
    label: str = Field(description="Label name to remove")
