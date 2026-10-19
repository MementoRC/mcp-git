"""github_rerun_failed_pr_checks: grouping, pagination, dry run (issue #309)."""

import pytest

from mcp_server_git.github.api import github_rerun_failed_pr_checks
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

PULL = ("GET", "/repos/o/r/pulls/4")
CHECKS = ("GET", "/repos/o/r/commits/abcdef123456/check-runs")


def _actions_check(check_id, name="job", conclusion="failure", run_id=9, url=True):
    details = f"https://github.com/o/r/actions/runs/{run_id}/job/{check_id}"
    return {
        "id": check_id,
        "name": name,
        "conclusion": conclusion,
        "app": {"slug": "github-actions"},
        "details_url": details if url else None,
    }


def _azure_check(check_id, conclusion="failure"):
    return {
        "id": check_id,
        "name": "Azure",
        "conclusion": conclusion,
        "app": {"slug": "azure-pipelines"},
        "details_url": "https://dev.azure.com/x",
    }


def _client(check_runs, extra=None):
    routes = {
        PULL: FakeResponse(200, {"head": {"sha": "abcdef123456"}}),
        CHECKS: FakeResponse(
            200, {"total_count": len(check_runs), "check_runs": check_runs}
        ),
        ("GET", f"{RUN}/9"): FakeResponse(200, RUN_PAYLOAD),
        ("POST", f"{RUN}/9/rerun-failed-jobs"): FakeResponse(201),
        ("POST", f"{CHECK}/20/rerequest"): FakeResponse(201),
        ("GET", f"{CHECK}/20"): FakeResponse(200, _azure_check(20)),
    }
    routes.update(extra or {})
    return FakeClient(routes)


@pytest.mark.asyncio
async def test_github_rerun_failed_pr_checks_reruns_run_once_when_two_jobs_share_it():
    client = _client([_actions_check(10), _actions_check(11, "other", "timed_out")])

    result = await call(github_rerun_failed_pr_checks, client, "o", "r", 4)

    assert not isinstance(result, ToolFailure)
    assert client.posts() == [(f"{RUN}/9/rerun-failed-jobs", {"json": {}})]
    assert "1 of 1 actions succeeded" in result


@pytest.mark.asyncio
async def test_github_rerun_failed_pr_checks_rerequests_check_when_app_is_not_actions():
    client = _client([_azure_check(20), _actions_check(10, conclusion="success")])

    result = await call(github_rerun_failed_pr_checks, client, "o", "r", 4)

    assert client.posts() == [(f"{CHECK}/20/rerequest", {"json": {}})]
    assert "Azure" in result and "1 of 1 actions succeeded" in result


@pytest.mark.asyncio
async def test_github_rerun_failed_pr_checks_sends_dict_json_body_when_posting():
    client = _client([_actions_check(10), _azure_check(20)])

    await call(github_rerun_failed_pr_checks, client, "o", "r", 4)

    posts = client.posts()
    assert len(posts) == 2
    assert all(isinstance(kw.get("json"), dict) for _, kw in posts)


@pytest.mark.asyncio
async def test_github_rerun_failed_pr_checks_returns_no_failures_when_all_checks_pass():
    client = _client(
        [_actions_check(10, conclusion="success"), _azure_check(20, "skipped")]
    )

    result = await call(github_rerun_failed_pr_checks, client, "o", "r", 4)

    assert result == "✅ No failed checks on PR #4"
    assert client.posts() == []


@pytest.mark.asyncio
async def test_github_rerun_failed_pr_checks_resolves_run_via_job_when_url_unparsable():
    client = _client(
        [_actions_check(10, url=False)],
        {("GET", f"{JOB}/10"): FakeResponse(200, {"run_id": 9})},
    )

    await call(github_rerun_failed_pr_checks, client, "o", "r", 4)

    assert client.posts() == [(f"{RUN}/9/rerun-failed-jobs", {"json": {}})]


@pytest.mark.asyncio
async def test_github_rerun_failed_pr_checks_follows_pagination_when_more_pages_exist():
    page1 = [_actions_check(i, conclusion="success") for i in range(100)]
    page2 = [_azure_check(20)]
    client = _client(
        [],
        {
            CHECKS: [
                FakeResponse(200, {"total_count": 101, "check_runs": page1}),
                FakeResponse(200, {"total_count": 101, "check_runs": page2}),
            ]
        },
    )

    await call(github_rerun_failed_pr_checks, client, "o", "r", 4)

    pages = [kw["params"]["page"] for m, ep, kw in client.calls if (m, ep) == CHECKS]
    assert pages == [1, 2]
    assert client.posts() == [(f"{CHECK}/20/rerequest", {"json": {}})]


@pytest.mark.asyncio
async def test_github_rerun_failed_pr_checks_lists_plan_without_posting_when_dry_run():
    client = _client([_actions_check(10), _azure_check(20)])

    result = await call(
        github_rerun_failed_pr_checks, client, "o", "r", 4, dry_run=True
    )

    assert client.posts() == []
    assert "Would rerun failed jobs of run 9 (job)" in result
    assert "Would rerequest check run 20" in result


@pytest.mark.asyncio
async def test_github_rerun_failed_pr_checks_returns_failure_when_every_action_fails():
    client = _client(
        [_actions_check(10)],
        {("POST", f"{RUN}/9/rerun-failed-jobs"): FakeResponse(403, text="no")},
    )

    result = await call(github_rerun_failed_pr_checks, client, "o", "r", 4)

    assert isinstance(result, ToolFailure)
    assert "actions: write" in result and "0 of 1 actions succeeded" in result


@pytest.mark.asyncio
async def test_github_rerun_failed_pr_checks_returns_text_when_some_actions_fail():
    client = _client(
        [_actions_check(10), _azure_check(20)],
        {("POST", f"{CHECK}/20/rerequest"): FakeResponse(403, text="no")},
    )

    result = await call(github_rerun_failed_pr_checks, client, "o", "r", 4)

    assert not isinstance(result, ToolFailure)
    assert "1 of 2 actions succeeded, 1 failed" in result


@pytest.mark.asyncio
async def test_github_rerun_failed_pr_checks_returns_failure_when_pr_not_found():
    client = _client([], {PULL: FakeResponse(404, text="Not Found")})

    result = await call(github_rerun_failed_pr_checks, client, "o", "r", 4)

    assert isinstance(result, ToolFailure)
    assert "404" in result
