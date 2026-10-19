"""github_dispatch_workflow (issue #311)."""

import pytest

from mcp_server_git.github import workflow_dispatch
from mcp_server_git.github.api import github_dispatch_workflow
from mcp_server_git.lean.interface import GitLeanInterface
from mcp_server_git.utils.tool_failure import ToolFailure

from ._actions_fakes import RUN_PAYLOAD, FakeClient, FakeResponse, call

WF = "/repos/o/r/actions/workflows/ci.yml"
DISPATCH = ("POST", f"{WF}/dispatches")
RUNS = ("GET", f"{WF}/runs?event=workflow_dispatch&branch=main&per_page=5")
REPO = ("GET", "/repos/o/r")
NEW_RUN = {**RUN_PAYLOAD, "created_at": "2999-01-01T00:00:00Z"}
OLD_RUN = {**RUN_PAYLOAD, "id": 1, "created_at": "2000-01-01T00:00:00Z"}


@pytest.fixture(autouse=True)
def _instant_sleep(monkeypatch):
    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(workflow_dispatch, "_sleep", no_sleep)


def _runs(*runs):
    return FakeResponse(200, {"workflow_runs": list(runs)})


async def _dispatch(client, **kwargs):
    args = {"repo_owner": "o", "repo_name": "r", "workflow_id": "ci.yml"} | kwargs
    return await call(github_dispatch_workflow, client, **args)


def _gets(client):
    return [ep for m, ep, _ in client.calls if m == "GET"]


@pytest.mark.asyncio
async def test_dispatch_returns_payload_with_inputs_when_inputs_given():
    client = FakeClient({DISPATCH: FakeResponse(204)})

    await _dispatch(client, ref="main", inputs={"a": "1"}, wait_for_run_s=0)

    assert client.posts() == [
        (f"{WF}/dispatches", {"json": {"ref": "main", "inputs": {"a": "1"}}})
    ]


@pytest.mark.asyncio
async def test_dispatch_returns_payload_without_inputs_when_inputs_none():
    client = FakeClient({DISPATCH: FakeResponse(204)})

    await _dispatch(client, ref="main", wait_for_run_s=0)

    assert client.posts() == [(f"{WF}/dispatches", {"json": {"ref": "main"}})]


@pytest.mark.asyncio
async def test_dispatch_returns_default_branch_dispatch_when_ref_is_none():
    client = FakeClient(
        {
            REPO: FakeResponse(200, {"default_branch": "trunk"}),
            DISPATCH: FakeResponse(204),
        }
    )

    result = await _dispatch(client, wait_for_run_s=0)

    assert client.posts()[0][1] == {"json": {"ref": "trunk"}}
    assert "trunk" in result


@pytest.mark.asyncio
async def test_dispatch_returns_run_details_when_run_discovered():
    client = FakeClient({DISPATCH: FakeResponse(204), RUNS: _runs(NEW_RUN)})

    result = await _dispatch(client, ref="main")

    assert "Run 9" in result
    assert "Attempt: 2" in result
    assert RUN_PAYLOAD["html_url"] in result


@pytest.mark.asyncio
async def test_dispatch_returns_run_when_ref_has_refs_heads_prefix():
    client = FakeClient({DISPATCH: FakeResponse(204), RUNS: _runs(NEW_RUN)})

    result = await _dispatch(client, ref="refs/heads/main")

    assert client.posts()[0][1] == {"json": {"ref": "refs/heads/main"}}
    assert RUNS[1] in _gets(client)
    assert "Run 9" in result


@pytest.mark.asyncio
async def test_dispatch_returns_poll_hint_when_only_older_run_exists():
    client = FakeClient({DISPATCH: FakeResponse(204), RUNS: _runs(OLD_RUN)})

    result = await _dispatch(client, ref="main")

    assert not isinstance(result, ToolFailure)
    assert "run not visible yet" in result
    assert "Run 1" not in result


@pytest.mark.asyncio
async def test_dispatch_returns_poll_hint_when_no_run_within_wait():
    client = FakeClient({DISPATCH: FakeResponse(204), RUNS: _runs()})

    result = await _dispatch(client, ref="main", wait_for_run_s=6)

    assert "github_list_workflow_runs(event='workflow_dispatch')" in result
    assert len(_gets(client)) == 2


@pytest.mark.asyncio
async def test_dispatch_returns_without_discovery_get_when_wait_is_zero():
    client = FakeClient({DISPATCH: FakeResponse(204)})

    result = await _dispatch(client, ref="main", wait_for_run_s=0)

    assert _gets(client) == []
    assert "run not visible yet" in result


@pytest.mark.asyncio
async def test_dispatch_returns_run_summary_when_200_body_has_workflow_run_id():
    client = FakeClient(
        {
            DISPATCH: FakeResponse(200, {"workflow_run_id": 9}),
            ("GET", "/repos/o/r/actions/runs/9"): FakeResponse(200, RUN_PAYLOAD),
        }
    )

    result = await _dispatch(client, ref="main")

    assert "Run 9" in result
    assert RUNS[1] not in _gets(client)


@pytest.mark.asyncio
async def test_dispatch_returns_failure_naming_actions_write_when_403():
    client = FakeClient({DISPATCH: FakeResponse(403, text="nope")})

    result = await _dispatch(client, ref="main")

    assert isinstance(result, ToolFailure)
    assert "actions: write" in result


@pytest.mark.asyncio
async def test_dispatch_returns_trigger_hint_when_422():
    client = FakeClient({DISPATCH: FakeResponse(422, text="no inputs: x")})

    result = await _dispatch(client, ref="main")

    assert isinstance(result, ToolFailure)
    assert "workflow_dispatch" in result and "no inputs: x" in result


@pytest.mark.asyncio
async def test_dispatch_returns_not_found_failure_when_404():
    client = FakeClient({DISPATCH: FakeResponse(404, text="gone")})

    result = await _dispatch(client, ref="main")

    assert isinstance(result, ToolFailure)
    assert "404" in result and "gone" in result


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["../x", "a/b"])
async def test_dispatch_returns_failure_without_http_when_workflow_id_invalid(bad):
    client = FakeClient({})

    result = await _dispatch(client, workflow_id=bad)

    assert isinstance(result, ToolFailure)
    assert client.calls == []


class _Svc:
    def __getattr__(self, name):
        return lambda **kw: {}


def test_tool_registry_contains_dispatch_tool_when_interface_built():
    interface = GitLeanInterface(
        git_service=_Svc(), github_service=_Svc(), azure_service=_Svc()
    )

    tool = interface.tool_registry["github_dispatch_workflow"]

    assert tool.domain == "github" and tool.description.startswith("MUTATING")
