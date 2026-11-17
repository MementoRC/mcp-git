"""Read-only GitHub GraphQL fallback tool definition (#355)."""

from ..github.graphql_query import GitHubGraphQLQuery, github_graphql_query
from .interface import ToolDefinition

_SPECS = (
    (
        "github_graphql_query",
        github_graphql_query,
        "Read-only GraphQL fallback for data the REST tools do not expose. "
        "Queries only: mutations and subscriptions are rejected locally before "
        "any network call. Returns compact JSON of `data`, truncated beyond "
        "~20k characters. repo_owner/repo_name select the identity/token.",
        GitHubGraphQLQuery,
        ("graphql", "query", "fallback"),
    ),
)


def graphql_tool_definitions() -> list[ToolDefinition]:
    """ToolDefinitions for the read-only GraphQL fallback."""
    return [
        ToolDefinition(
            name=name,
            implementation=implementation,
            description=description,
            schema=model.model_json_schema(),
            domain="github",
            complexity="focused",
            keywords=keywords,
        )
        for name, implementation, description, model, keywords in _SPECS
    ]
