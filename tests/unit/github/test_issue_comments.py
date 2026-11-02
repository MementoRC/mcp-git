"""github_add_issue_comment / github_list_issue_comments (issue #326)."""

import pytest

from mcp_server_git.github.api import (
    github_add_issue_comment,
    github_list_issue_comments,
)
from mcp_server_git.lean.interface import GitLeanInterface
from mcp_server_git.utils.tool_failure import ToolFailure

from ._actions_fakes import FakeClient, FakeResponse, call

PATH = "/repos/o/r/issues/7/comments"
POST = ("POST", PATH)
GET = ("GET", PATH)
LONG_BODY = "line one\n" + "x" * 5000 + "\n<!-- marker:abc -->"


def _comment(cid, body="hi", login="alice"):
    return {
        "id": cid,
        "user": {"login": login},
        "created_at": "2026-01-02T03:04:05Z",
        "html_url": f"https://github.com/o/r/issues/7#issuecomment-{cid}",
        "body": body,
    }


async def _add(client, **kwargs):
    args = {"repo_owner": "o", "repo_name": "r", "issue_number": 7, "body": "hi"}
    return await call(github_add_issue_comment, client, **(args | kwargs))


async def _list(client, **kwargs):
    args = {"repo_owner": "o", "repo_name": "r", "issue_number": 7}
    return await call(github_list_issue_comments, client, **(args | kwargs))


@pytest.mark.asyncio
async def test_add_returns_id_and_url_when_created():
    client = FakeClient({POST: FakeResponse(201, _comment(55))})

    result = await _add(client)

    assert client.posts() == [(PATH, {"json": {"body": "hi"}})]
    assert "55" in result and "issuecomment-55" in result


@pytest.mark.asyncio
@pytest.mark.parametrize("body", ["", "   ", "\n\t"])
async def test_add_rejects_body_without_http_call_when_blank(body):
    client = FakeClient({})

    result = await _add(client, body=body)

    assert isinstance(result, ToolFailure) and "empty" in result
    assert client.calls == []


@pytest.mark.asyncio
async def test_add_returns_not_found_when_issue_missing():
    client = FakeClient({POST: FakeResponse(404, text='{"message":"Not Found"}')})

    result = await _add(client)

    assert isinstance(result, ToolFailure) and "Issue not found" in result


@pytest.mark.asyncio
async def test_add_returns_status_and_message_when_api_rejects():
    client = FakeClient({POST: FakeResponse(422, text="Validation Failed")})

    result = await _add(client)

    assert isinstance(result, ToolFailure)
    assert "422" in result and "Validation Failed" in result


@pytest.mark.asyncio
async def test_list_returns_full_bodies_when_multiple_comments():
    payload = [_comment(1, LONG_BODY), _comment(2, "short", "bob")]
    client = FakeClient({GET: FakeResponse(200, payload)})

    result = await _list(client)

    assert LONG_BODY in result and "short" in result
    assert "bob" in result and "2026-01-02T03:04:05Z" in result
    assert "issuecomment-1" in result and "Comment 2" in result


@pytest.mark.asyncio
async def test_list_returns_empty_notice_when_no_comments():
    client = FakeClient({GET: FakeResponse(200, [])})

    result = await _list(client)

    assert "No comments" in result


@pytest.mark.asyncio
async def test_list_forwards_pagination_params_when_given():
    client = FakeClient({GET: FakeResponse(200, [])})

    await _list(client, per_page=100, page=3)

    assert client.calls == [("GET", PATH, {"params": {"per_page": 100, "page": 3}})]


@pytest.mark.asyncio
async def test_list_returns_default_pagination_when_unspecified():
    client = FakeClient({GET: FakeResponse(200, [])})

    await _list(client)

    assert client.calls[0][2] == {"params": {"per_page": 30, "page": 1}}


@pytest.mark.asyncio
async def test_list_returns_not_found_when_issue_missing():
    client = FakeClient({GET: FakeResponse(404, text="Not Found")})

    result = await _list(client)

    assert isinstance(result, ToolFailure) and "Issue not found" in result


@pytest.mark.asyncio
async def test_list_returns_status_and_message_when_server_error():
    client = FakeClient({GET: FakeResponse(500, text="boom")})

    result = await _list(client)

    assert isinstance(result, ToolFailure)
    assert "500" in result and "boom" in result


class _Svc:
    def __getattr__(self, name):
        return lambda **kw: {}


@pytest.mark.parametrize(
    "name", ["github_add_issue_comment", "github_list_issue_comments"]
)
def test_tool_registry_contains_comment_tool_when_interface_built(name):
    interface = GitLeanInterface(
        git_service=_Svc(), github_service=_Svc(), azure_service=_Svc()
    )

    tool = interface.tool_registry[name]

    assert tool.domain == "github" and "issue_number" in tool.description
