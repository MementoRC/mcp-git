"""Pydantic models for issue-comment tools (#326)."""

from pydantic import BaseModel, Field

_OWNER = "Repository owner/organization"
_NAME = "Repository name"
_NUMBER = "Issue or pull request number (PR conversation comments use this too)"


class GitHubAddIssueComment(BaseModel):
    repo_owner: str = Field(description=_OWNER)
    repo_name: str = Field(description=_NAME)
    issue_number: int = Field(description=_NUMBER)
    body: str = Field(description="Comment text (markdown); must not be empty")


class GitHubListIssueComments(BaseModel):
    repo_owner: str = Field(description=_OWNER)
    repo_name: str = Field(description=_NAME)
    issue_number: int = Field(description=_NUMBER)
    per_page: int = Field(default=30, description="Comments per page (max 100)")
    page: int = Field(default=1, description="Page number, starting at 1")
