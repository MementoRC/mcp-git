"""Realistic review-thread GraphQL payloads and a GraphQL-boundary fake (#355)."""


def comment(database_id, body="Please fix", author="rev"):
    return {
        "databaseId": database_id,
        "url": f"https://github.com/o/r/pull/7#discussion_r{database_id}",
        "body": body,
        "author": {"login": author},
    }


def thread(thread_id, comments, resolved=False, **overrides):
    node = {
        "id": thread_id,
        "isResolved": resolved,
        "isOutdated": False,
        "path": "src/a.py",
        "line": 10,
        "originalLine": 8,
        "resolvedBy": {"login": "alice"} if resolved else None,
        "comments": {
            "totalCount": len(comments),
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": comments,
        },
    }
    return node | overrides


def threads_response(nodes, cursor=None):
    return {
        "repository": {
            "pullRequest": {
                "reviewThreads": {
                    "pageInfo": {
                        "hasNextPage": cursor is not None,
                        "endCursor": cursor,
                    },
                    "nodes": nodes,
                }
            }
        }
    }


class FakeGraphQL:
    """Routes a query by marker substring; list values are consumed in order."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    async def graphql(self, query, variables=None):
        self.calls.append((query, variables))
        for marker, value in self.routes.items():
            if marker in query:
                result = value.pop(0) if isinstance(value, list) else value
                if isinstance(result, Exception):
                    raise result
                return result
        raise AssertionError(f"unrouted query: {query[:60]}")
