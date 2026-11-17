"""Pydantic models for PR review thread tools (#355)."""

from pydantic import BaseModel, Field

_THREAD_ID = "Review thread node id (the thread_id from github_list_review_threads)"


class GitHubListReviewThreads(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int
    unresolved_only: bool = Field(
        default=False, description="Only return threads that are not resolved"
    )


class GitHubReplyReviewThread(BaseModel):
    repo_owner: str
    repo_name: str
    thread_id: str = Field(description=_THREAD_ID)
    body: str = Field(description="Reply text (Markdown); must not be empty")


class GitHubResolveReviewThread(BaseModel):
    repo_owner: str
    repo_name: str
    thread_id: str = Field(description=_THREAD_ID)


class GitHubUnresolveReviewThread(GitHubResolveReviewThread):
    pass
