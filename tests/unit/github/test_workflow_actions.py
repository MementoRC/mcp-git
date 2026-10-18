"""Workflow-run and check-run mutation tools (issues #301, #309)."""

import pytest

from mcp_server_git.github.api import (
    github_cancel_workflow_run,
    github_force_cancel_workflow_run,
    github_rerequest_check_run,
    github_rerun_failed_jobs,
    github_rerun_job,
    github_rerun_workflow_run,
)
from mcp_server_git.lean.interface import GitLeanInterface
from mcp_server_git.utils.tool_failure import ToolFailure

from ._actions_fakes import (
    CHECK,
    JOB,
    RUN,
    RUN_PAYLOAD,
    FakeClient,
    FakeResponse,
    call,
)

TOOL_NAMES = (
    "github_cancel_workflow_run",
    "github_force_cancel_workflow_run",
    "github_rerun_workflow_run",
    "github_rerun_failed_jobs",
    "github_rerun_job",
    "github_rerequest_check_run",
    "github_rerun_failed_pr_checks",
)

RUN_GET = ("GET", f"{RUN}/9")


def _client(post_endpoint, post_response, run=None):
    routes = {
        ("POST", post_endpoint): post_response,
        RUN_GET: run or FakeResponse(200, RUN_PAYLOAD),
    }
    return FakeClient(routes)


# --------------------------------------------------------------------------
# cancel / force-cancel
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_github_cancel_workflow_run_returns_run_state_when_accepted():
    client = _client(f"{RUN}/9/cancel", FakeResponse(202))

    result = await call(github_cancel_workflow_run, client, "o", "r", 9)

    assert not isinstance(result, ToolFailure)
    assert client.posts() == [(f"{RUN}/9/cancel", {})]
    assert "Attempt: 2" in result and "actions/runs/9" in result
    assert "Status: queued" in result and "CI" in result


@pytest.mark.asyncio
async def test_github_force_cancel_workflow_run_posts_force_cancel_when_called():
    client = _client(f"{RUN}/9/force-cancel", FakeResponse(202))

    result = await call(github_force_cancel_workflow_run, client, "o", "r", 9)

    assert not isinstance(result, ToolFailure)
    assert [ep for ep, _ in client.posts()] == [f"{RUN}/9/force-cancel"]


@pytest.mark.asyncio
async def test_github_cancel_workflow_run_returns_failure_when_run_already_completed():
    client = _client(f"{RUN}/9/cancel", FakeResponse(409, text="Cannot cancel"))

    result = await call(github_cancel_workflow_run, client, "o", "r", 9)

    assert isinstance(result, ToolFailure)
    assert "not in a cancellable state" in result and "Cannot cancel" in result


@pytest.mark.asyncio
async def test_github_cancel_workflow_run_names_actions_write_when_forbidden():
    client = _client(f"{RUN}/9/cancel", FakeResponse(403, text="nope"))

    result = await call(github_cancel_workflow_run, client, "o", "r", 9)

    assert isinstance(result, ToolFailure)
    assert "actions: write" in result and "o/r" in result and "nope" in result
    assert "cross-fork" in result


@pytest.mark.asyncio
async def test_github_cancel_workflow_run_returns_not_found_when_run_missing():
    client = _client(f"{RUN}/9/cancel", FakeResponse(404, text="Not Found"))

    result = await call(github_cancel_workflow_run, client, "o", "r", 9)

    assert isinstance(result, ToolFailure)
    assert "not found" in result and "404" in result


@pytest.mark.asyncio
async def test_github_cancel_workflow_run_returns_generic_failure_when_status_unexpected():
    client = _client(f"{RUN}/9/cancel", FakeResponse(500, text="boom"))

    result = await call(github_cancel_workflow_run, client, "o", "r", 9)

    assert isinstance(result, ToolFailure)
    assert "Failed to cancel workflow run 9: 500 - boom" in result


@pytest.mark.asyncio
async def test_github_cancel_workflow_run_reports_success_when_followup_get_fails():
    client = _client(f"{RUN}/9/cancel", FakeResponse(202), run=FakeResponse(500))

    result = await call(github_cancel_workflow_run, client, "o", "r", 9)

    assert not isinstance(result, ToolFailure)
    assert "status could not be fetched" in result


# --------------------------------------------------------------------------
# rerun
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_github_rerun_workflow_run_posts_rerun_without_body_when_defaults():
    client = _client(f"{RUN}/9/rerun", FakeResponse(201))

    result = await call(github_rerun_workflow_run, client, "o", "r", 9)

    assert not isinstance(result, ToolFailure)
    assert client.posts() == [(f"{RUN}/9/rerun", {})]
    assert "Attempt: 2" in result and "actions/runs/9" in result


@pytest.mark.asyncio
async def test_github_rerun_workflow_run_posts_failed_jobs_endpoint_when_failed_only():
    client = _client(f"{RUN}/9/rerun-failed-jobs", FakeResponse(201))

    await call(
        github_rerun_workflow_run,
        client,
        "o",
        "r",
        9,
        failed_only=True,
        enable_debug_logging=True,
    )

    assert client.posts() == [
        (f"{RUN}/9/rerun-failed-jobs", {"json": {"enable_debug_logging": True}})
    ]


@pytest.mark.asyncio
async def test_github_rerun_workflow_run_returns_failure_when_run_in_progress():
    client = _client(f"{RUN}/9/rerun", FakeResponse(409, text="still running"))

    result = await call(github_rerun_workflow_run, client, "o", "r", 9)

    assert isinstance(result, ToolFailure)
    assert "cannot be re-run yet" in result and "still running" in result


@pytest.mark.asyncio
async def test_github_rerun_failed_jobs_delegates_with_failed_only_when_called():
    client = _client(f"{RUN}/9/rerun-failed-jobs", FakeResponse(201))

    result = await call(github_rerun_failed_jobs, client, "o", "r", 9)

    assert not isinstance(result, ToolFailure)
    assert [ep for ep, _ in client.posts()] == [f"{RUN}/9/rerun-failed-jobs"]


@pytest.mark.asyncio
async def test_github_rerun_job_posts_job_rerun_and_reports_parent_run_when_accepted():
    client = FakeClient(
        {
            ("POST", f"{JOB}/5/rerun"): FakeResponse(201),
            ("GET", f"{JOB}/5"): FakeResponse(200, {"run_id": 9}),
            RUN_GET: FakeResponse(200, RUN_PAYLOAD),
        }
    )

    result = await call(
        github_rerun_job, client, "o", "r", 5, enable_debug_logging=True
    )

    assert client.posts() == [
        (f"{JOB}/5/rerun", {"json": {"enable_debug_logging": True}})
    ]
    assert "Attempt: 2" in result and "actions/runs/9" in result


@pytest.mark.asyncio
async def test_github_rerun_job_reports_success_when_job_lookup_fails():
    client = FakeClient(
        {
            ("POST", f"{JOB}/5/rerun"): FakeResponse(201),
            ("GET", f"{JOB}/5"): FakeResponse(500),
        }
    )

    result = await call(github_rerun_job, client, "o", "r", 5)

    assert not isinstance(result, ToolFailure)
    assert "could not be fetched" in result


# --------------------------------------------------------------------------
# rerequest check run
# --------------------------------------------------------------------------

AZURE_CHECK = {
    "name": "Azure build",
    "status": "queued",
    "app": {"slug": "azure-pipelines"},
    "details_url": "https://dev.azure.com/x",
}


@pytest.mark.asyncio
async def test_github_rerequest_check_run_returns_check_state_when_accepted():
    client = FakeClient(
        {
            ("POST", f"{CHECK}/7/rerequest"): FakeResponse(201),
            ("GET", f"{CHECK}/7"): FakeResponse(200, AZURE_CHECK),
        }
    )

    result = await call(github_rerequest_check_run, client, "o", "r", 7)

    assert not isinstance(result, ToolFailure)
    assert "Azure build" in result and "azure-pipelines" in result
    assert "https://dev.azure.com/x" in result and "Status: queued" in result


@pytest.mark.asyncio
async def test_github_rerequest_check_run_names_checks_write_when_forbidden():
    client = FakeClient(
        {
            ("POST", f"{CHECK}/7/rerequest"): FakeResponse(403, text="nope"),
            ("GET", f"{CHECK}/7"): FakeResponse(200, AZURE_CHECK),
        }
    )

    result = await call(github_rerequest_check_run, client, "o", "r", 7)

    assert isinstance(result, ToolFailure)
    assert "checks: write" in result and "actions: write" not in result


@pytest.mark.asyncio
async def test_github_rerequest_check_run_hints_rerun_job_when_check_is_actions():
    actions = {**AZURE_CHECK, "app": {"slug": "github-actions"}}
    client = FakeClient(
        {
            ("POST", f"{CHECK}/7/rerequest"): FakeResponse(422, text="bad"),
            ("GET", f"{CHECK}/7"): FakeResponse(200, actions),
        }
    )

    result = await call(github_rerequest_check_run, client, "o", "r", 7)

    assert isinstance(result, ToolFailure)
    assert "github_rerun_job" in result and "job_id=7" in result


@pytest.mark.asyncio
async def test_github_rerequest_check_run_reports_success_when_followup_get_fails():
    client = FakeClient(
        {
            ("POST", f"{CHECK}/7/rerequest"): FakeResponse(201),
            ("GET", f"{CHECK}/7"): FakeResponse(500),
        }
    )

    result = await call(github_rerequest_check_run, client, "o", "r", 7)

    assert not isinstance(result, ToolFailure)
    assert "status could not be fetched" in result


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------


class _Svc:
    def __getattr__(self, name):
        return lambda **kw: {}


def test_tool_registry_contains_every_workflow_action_tool_when_interface_built():
    interface = GitLeanInterface(
        git_service=_Svc(), github_service=_Svc(), azure_service=_Svc()
    )

    missing = [n for n in TOOL_NAMES if n not in interface.tool_registry]
    wrong_domain = [
        n for n in TOOL_NAMES if interface.tool_registry[n].domain != "github"
    ]
    unmarked = [
        n
        for n in TOOL_NAMES
        if "MUTATING" not in interface.tool_registry[n].description
    ]

    assert missing == [] and wrong_domain == [] and unmarked == []
