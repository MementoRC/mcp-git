"""GitHub PR review thread tool definitions (#355)."""

from ..github.models_threads import (
    GitHubListReviewThreads,
    GitHubReplyReviewThread,
    GitHubResolveReviewThread,
    GitHubUnresolveReviewThread,
)
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
        "github_reply_review_thread",
        github_reply_review_thread,
        "MUTATING: replies to a review thread by thread_id (from "
        "github_list_review_threads). Returns the new comment's url and "
        "database_id." + _OWNER_NOTE,
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
            keywords=_KEYWORDS + (("resolve",) if "resolve" in name else ()),
        )
        for name, implementation, description, model in _SPECS
    ]
