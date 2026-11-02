"""Issue-comment tool definitions (#326), kept apart from ``registry_github.py``."""

from ..github.issue_comments import (
    github_add_issue_comment,
    github_list_issue_comments,
)
from ..github.models_issue_comments import (
    GitHubAddIssueComment,
    GitHubListIssueComments,
)
from .interface import ToolDefinition

_SPECS = (
    (
        "github_add_issue_comment",
        github_add_issue_comment,
        "MUTATING: posts a comment via POST /issues/{issue_number}/comments; "
        "issue_number also works for PR conversation comments. Returns the "
        "comment id and URL. Empty bodies are rejected.",
        GitHubAddIssueComment,
    ),
    (
        "github_list_issue_comments",
        github_list_issue_comments,
        "Lists comments via GET /issues/{issue_number}/comments (also PR "
        "conversation comments). Returns id, author, created_at, URL and the FULL "
        "body of each; supports per_page/page. Use for idempotency checks.",
        GitHubListIssueComments,
    ),
)


def issue_comment_tool_definitions() -> list[ToolDefinition]:
    """ToolDefinitions for the issue-comment GitHub tools."""
    return [
        ToolDefinition(
            name=name,
            implementation=implementation,
            description=description,
            schema=model.model_json_schema(),
            domain="github",
            complexity="focused",
        )
        for name, implementation, description, model in _SPECS
    ]
