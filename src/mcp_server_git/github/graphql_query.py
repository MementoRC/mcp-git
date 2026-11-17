"""Read-only GitHub GraphQL fallback tool (#355)."""

import json
from typing import Any

from pydantic import BaseModel, Field

from ..utils.tool_failure import fail
from .client import GraphQLError
from .graphql_readonly import read_only_violation
from .workflow_actions import run_guarded

MAX_CHARS = 20_000


class GitHubGraphQLQuery(BaseModel):
    repo_owner: str = Field(description="Repository owner (selects the identity/token)")
    repo_name: str = Field(description="Repository name (selects the identity/token)")
    query: str = Field(description="GraphQL query document; mutations are rejected")
    variables: dict[str, Any] | None = Field(
        default=None, description="Optional GraphQL variables"
    )


def _compact(data: Any) -> str:
    text = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    if len(text) <= MAX_CHARS:
        return text
    return (
        f"{text[:MAX_CHARS]}\n... [truncated: showing first {MAX_CHARS} "
        f"of {len(text)} characters; narrow the query or paginate]"
    )


async def github_graphql_query(
    repo_owner: str,
    repo_name: str,
    query: str,
    variables: dict[str, Any] | None = None,
) -> str:
    """Run a read-only GraphQL query; ``repo_owner``/``repo_name`` pick the token."""
    violation = read_only_violation(query)
    if violation:
        return fail(f"❌ Rejected GraphQL document: {violation}")

    async def op(client: Any) -> str:
        try:
            return _compact(await client.graphql(query, variables))
        except GraphQLError as exc:
            return fail(f"❌ {exc}")

    return await run_guarded(op)
