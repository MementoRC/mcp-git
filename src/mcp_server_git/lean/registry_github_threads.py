"""GitHub PR review thread tool definitions (#355)."""

from ..github.models_threads import (
    GitHubListPRReviews,
    GitHubListReviewThreads,
    GitHubReplyReviewThread,
    GitHubResolveReviewThread,
    GitHubUnresolveReviewThread,
)
from ..github.pr_review_list import github_list_pr_reviews
from ..github.review_threads import (
    github_list_review_threads,
    github_reply_review_thread,
    github_resolve_review_thread,
    github_unresolve_review_thread,
)
from .interface import ToolDefinition

_OWNER_NOTE = (
    " repo_owner/repo_name are not used by the GraphQL call (thread ids are "
    "global); they select the token via the identity mapping."
)

_KEYWORDS = ("thread", "review thread", "review comment", "discussion", "conversation")

_REVIEW_LIST_KEYWORDS = ("review", "reviewer", "bot", "copilot", "sourcery", "commit")

_SPECS = (
    (
        "github_list_review_threads",
        github_list_review_threads,
        "Lists a PR's review threads via GraphQL (paginated): thread_id, "
        "is_resolved, is_outdated, resolved_by, path, line, comment_count and the "
        "first comment (database_id, author, url, body cut to ~200 chars). Use "
        "unresolved_only to see just open threads.",
        GitHubListReviewThreads,
    ),
    (
        "github_list_pr_reviews",
        github_list_pr_reviews,
        "Read-only: lists a PR's reviews (all pages), one compact row each: id, "
        "author, author_type, state, commit_id, submitted_at. No bodies; never "
        "offloaded. Bot logins keep '[bot]' (authors filter is a case-insensitive "
        "substring). Inline comment bodies: github_get_pr_reviews; threads: "
        "github_list_review_threads.",
        GitHubListPRReviews,
    ),
    (
        "github_reply_review_thread",
        github_reply_review_thread,
        "MUTATING: replies to a review thread by thread_id (from "
        "github_list_review_threads). Returns the new comment's url and "
        "database_id." + _OWNER_NOTE + " Equivalent to github_reply_to_pr_comment, "
        "which takes a numeric comment_id plus pr_number instead of a thread node id.",
        GitHubReplyReviewThread,
    ),
    (
        "github_resolve_review_thread",
        github_resolve_review_thread,
        "MUTATING: marks a review thread resolved. Returns thread_id, "
        "is_resolved, resolved_by." + _OWNER_NOTE,
        GitHubResolveReviewThread,
    ),
    (
        "github_unresolve_review_thread",
        github_unresolve_review_thread,
        "MUTATING: reopens a resolved review thread. Returns thread_id, "
        "is_resolved, resolved_by." + _OWNER_NOTE,
        GitHubUnresolveReviewThread,
    ),
)


def thread_tool_definitions() -> list[ToolDefinition]:
    """ToolDefinitions for the PR review thread tools."""
    return [
        ToolDefinition(
            name=name,
            implementation=implementation,
            description=description,
            schema=model.model_json_schema(),
            domain="github",
            complexity="focused",
            keywords=_KEYWORDS
            + (("resolve",) if "resolve" in name else ())
            + _REVIEW_LIST_KEYWORDS * (name == "github_list_pr_reviews"),
        )
        for name, implementation, description, model in _SPECS
    ]
