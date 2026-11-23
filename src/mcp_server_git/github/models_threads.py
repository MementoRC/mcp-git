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


class GitHubListPRReviews(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int
    authors: list[str] | None = Field(
        default=None,
        description="Case-insensitive login substrings (e.g. 'copilot' matches "
        "'copilot-pull-request-reviewer[bot]')",
    )
    commit_id: str | None = Field(
        default=None,
        description="Keep reviews on this commit; full SHA or prefix (min 7 chars)",
    )
    include_inline_counts: bool = Field(
        default=False,
        description="Add inline_comment_count per review (one extra paginated call)",
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
