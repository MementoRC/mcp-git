"""Characterization tests for the CI/workflow ops (issue #263).

Pins the observable output of github_list_workflow_runs,
github_await_workflow_completion, github_get_failing_jobs and
github_get_pr_checks so the C901 refactor can be proven behaviour-preserving.
Only the ``github_client_context`` boundary is faked.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from mcp_server_git.github.ci_logs import github_await_workflow_completion
from mcp_server_git.github.pr import (
    github_get_failing_jobs,
    github_get_pr_checks,
)
from mcp_server_git.github.workflows import github_list_workflow_runs

WF_CTX = "mcp_server_git.github.workflows.github_client_context"
CI_CTX = "mcp_server_git.github.ci_logs.github_client_context"
PR_CTX = "mcp_server_git.github.pr.github_client_context"
CI_TIME = "mcp_server_git.github.ci_logs.time"
CI_ASYNCIO = "mcp_server_git.github.ci_logs.asyncio"


class FakeResponse:
    def __init__(self, status=200, payload=None, text=""):
        self.status = status
        self._payload = payload
        self._text = text

    async def json(self):
        return self._payload

    async def text(self):
        return self._text


class FakeClient:
    """Routes GETs by endpoint suffix; lists are consumed in order."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    async def get(self, endpoint, **kwargs):
        self.calls.append((endpoint, kwargs))
        for suffix, value in self.routes:
            if endpoint.endswith(suffix):
                if isinstance(value, list):
                    value = value.pop(0) if len(value) > 1 else value[0]
                if isinstance(value, Exception):
                    raise value
                return value
        raise AssertionError(f"unrouted endpoint {endpoint}")


class FakeContext:
    def __init__(self, client=None, exc=None):
        self.client = client
        self.exc = exc

    async def __aenter__(self):
        if self.exc is not None:
            raise self.exc
        return self.client

    async def __aexit__(self, *args):
        return None


def ctx(client=None, exc=None):
    return FakeContext(client, exc)


def ok(payload):
    return FakeResponse(200, payload)


# --------------------------------------------------------------------------
# github_list_workflow_runs
# --------------------------------------------------------------------------


def _run(**overrides) -> dict:
    base = {
        "id": 1,
        "name": "CI",
        "run_number": 7,
        "status": "completed",
        "conclusion": "success",
        "head_branch": "main",
        "head_sha": "abcdef1234567",
        "actor": {"login": "bob"},
        "event": "push",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:05:00Z",
        "html_url": "https://x/1",
    }
    base.update(overrides)
    return base


def _wf_client(status=200, runs=None, total=None, text=""):
    payload = {"workflow_runs": runs if runs is not None else []}
    if total is not None:
        payload["total_count"] = total
    return FakeClient([("/runs", FakeResponse(status, payload, text))])


async def _list(client, **kwargs):
    with patch(WF_CTX, return_value=ctx(client)):
        return await github_list_workflow_runs("o", "r", **kwargs)


COMPLETED_RUN_LINES = [
    "✅ CI #7",
    "   ID: 1",
    "   Status: completed (success)",
    "   Branch: main",
    "   Commit: abcdef12...",
    "   Actor: bob",
    "   Event: push",
    "   Started: 2024-01-01T00:00:00Z",
    "   Updated: 2024-01-01T00:05:00Z",
    "   Duration: 0:05:00",
    "   URL: https://x/1",
    "",
]


class TestListWorkflowRunsStatusPaths:
    @pytest.mark.asyncio
    async def test_list_runs_returns_auth_message_when_status_401(self):
        result = await _list(_wf_client(401, text="bad creds"))
        assert result == (
            "❌ GitHub API authentication failed: Verify your GITHUB_TOKEN "
            "has Actions read permissions"
        )

    @pytest.mark.asyncio
    async def test_list_runs_returns_workflow_not_found_when_404_with_workflow_id(
        self,
    ):
        result = await _list(_wf_client(404), workflow_id="ci.yml")
        assert result == (
            "❌ Workflow 'ci.yml' not found in o/r. Check workflow file name or ID."
        )

    @pytest.mark.asyncio
    async def test_list_runs_returns_repo_not_found_when_404_without_workflow_id(
        self,
    ):
        result = await _list(_wf_client(404))
        assert result == "❌ Repository o/r not found or Actions not enabled"

    @pytest.mark.asyncio
    async def test_list_runs_returns_failure_with_body_when_status_not_200(self):
        result = await _list(_wf_client(500, text="boom"))
        assert result == "❌ Failed to list workflow runs: 500 - boom"


class TestListWorkflowRunsEmptyAndParams:
    @pytest.mark.asyncio
    async def test_list_runs_returns_plain_message_when_empty_without_filters(self):
        result = await _list(_wf_client())
        assert result == "No workflow runs found for o/r"

    @pytest.mark.asyncio
    async def test_list_runs_lists_filters_in_message_when_empty_with_filters(self):
        result = await _list(_wf_client(), actor="bob", branch="main", created=">x")
        assert result == (
            "No workflow runs found for o/r "
            "(filtered by: actor=bob, branch=main, created=>x)"
        )

    @pytest.mark.asyncio
    async def test_list_runs_drops_invalid_status_and_conclusion_when_unknown_values(
        self,
    ):
        client = _wf_client()
        result = await _list(client, status="bogus", conclusion="weird")
        assert result == "No workflow runs found for o/r"
        assert client.calls == [
            ("/repos/o/r/actions/runs", {"params": {"per_page": 30, "page": 1}})
        ]

    @pytest.mark.asyncio
    async def test_list_runs_builds_all_params_when_every_filter_given(self):
        client = _wf_client()
        await _list(
            client,
            workflow_id="ci.yml",
            actor="bob",
            branch="main",
            event="push",
            status="completed",
            conclusion="timed_out",
            per_page=10,
            page=3,
            created=">2023-01-01",
            exclude_pull_requests=True,
            check_suite_id=9,
            head_sha="abc",
        )
        endpoint, kwargs = client.calls[0]
        assert endpoint == "/repos/o/r/actions/workflows/ci.yml/runs"
        assert kwargs["params"] == {
            "per_page": 10,
            "page": 3,
            "actor": "bob",
            "branch": "main",
            "event": "push",
            "status": "completed",
            "conclusion": "timed_out",
            "created": ">2023-01-01",
            "exclude_pull_requests": "true",
            "check_suite_id": 9,
            "head_sha": "abc",
        }
        assert list(kwargs["params"]) == [
            "per_page",
            "page",
            "actor",
            "branch",
            "event",
            "status",
            "conclusion",
            "created",
            "exclude_pull_requests",
            "check_suite_id",
            "head_sha",
        ]

    @pytest.mark.asyncio
    async def test_list_runs_clamps_per_page_and_page_when_out_of_range(self):
        high = _wf_client()
        low = _wf_client()
        await _list(high, per_page=500, page=0)
        await _list(low, per_page=0, page=-4)
        assert high.calls[0][1]["params"] == {"per_page": 100, "page": 1}
        assert low.calls[0][1]["params"] == {"per_page": 1, "page": 1}


class TestListWorkflowRunsFormatting:
    @pytest.mark.asyncio
    async def test_list_runs_formats_completed_run_when_single_run(self):
        result = await _list(_wf_client(runs=[_run()]))
        assert result.split("\n") == [
            "Workflow Runs for o/r:",
            "",
            *COMPLETED_RUN_LINES,
        ]

    @pytest.mark.asyncio
    async def test_list_runs_header_lists_raw_filters_when_filters_given(self):
        result = await _list(
            _wf_client(runs=[_run()]),
            workflow_id="ci.yml",
            actor="bob",
            branch="main",
            event="push",
            status="bogus",
            conclusion="weird",
        )
        assert result.split("\n")[0] == (
            "Workflow Runs for o/r (workflow: ci.yml, actor: bob, "
            "branch: main, event: push, status: bogus, conclusion: weird):"
        )

    @pytest.mark.asyncio
    async def test_list_runs_adds_status_summary_when_multiple_statuses(self):
        runs = [
            _run(),
            _run(id=2, status="in_progress", conclusion=None),
            _run(id=3),
        ]
        lines = (await _list(_wf_client(runs=runs))).split("\n")
        assert lines[:5] == [
            "Workflow Runs for o/r:",
            "",
            "Status summary: completed: 2, in_progress: 1",
            "",
            "✅ CI #7",
        ]

    @pytest.mark.asyncio
    async def test_list_runs_omits_status_summary_when_single_status(self):
        result = await _list(_wf_client(runs=[_run(), _run(id=2)]))
        assert "Status summary" not in result

    @pytest.mark.asyncio
    async def test_list_runs_omits_updated_and_duration_when_in_progress_unchanged(
        self,
    ):
        run = _run(
            status="in_progress",
            conclusion=None,
            updated_at="2024-01-01T00:00:00Z",
            html_url=None,
        )
        lines = (await _list(_wf_client(runs=[run]))).split("\n")
        assert lines[2:] == [
            "🔄 CI #7",
            "   ID: 1",
            "   Status: in_progress",
            "   Branch: main",
            "   Commit: abcdef12...",
            "   Actor: bob",
            "   Event: push",
            "   Started: 2024-01-01T00:00:00Z",
            "",
        ]

    @pytest.mark.asyncio
    async def test_list_runs_skips_duration_when_timestamps_unparseable(self):
        run = _run(created_at="garbage", updated_at="trash")
        lines = (await _list(_wf_client(runs=[run]))).split("\n")
        assert "   Started: garbage" in lines
        assert "   Updated: trash" in lines
        assert not any(line.startswith("   Duration") for line in lines)
        assert lines[-2:] == ["   URL: https://x/1", ""]

    @pytest.mark.asyncio
    async def test_list_runs_uses_defaults_when_run_fields_missing(self):
        lines = (await _list(_wf_client(runs=[{}]))).split("\n")
        assert lines[2:] == [
            "❓ Unknown Workflow #?",
            "   ID: N/A",
            "   Status: unknown",
            "   Branch: N/A",
            "   Commit: N/A...",
            "   Actor: N/A",
            "   Event: N/A",
            "",
        ]

    @pytest.mark.asyncio
    async def test_list_runs_uses_cross_emoji_when_completed_not_success(self):
        run = _run(conclusion="failure")
        lines = (await _list(_wf_client(runs=[run]))).split("\n")
        assert lines[2:5] == [
            "❌ CI #7",
            "   ID: 1",
            "   Status: completed (failure)",
        ]

    @pytest.mark.asyncio
    async def test_list_runs_adds_pagination_when_total_exceeds_page(self):
        result = await _list(
            _wf_client(runs=[_run(), _run(id=2)], total=65), per_page=30, page=2
        )
        lines = result.split("\n")
        assert lines[2:4] == ["Showing 2 of 65 total runs (page 2)", ""]
        assert lines[-1] == "📄 Page 2 of 3 (use page parameter to see more)"

    @pytest.mark.asyncio
    async def test_list_runs_computes_max_page_from_raw_per_page_when_clamped(self):
        # Quirk preserved: max_page uses the raw per_page (500), not the
        # clamped value (100) sent to the API.
        result = await _list(_wf_client(runs=[_run()], total=250), per_page=500)
        assert result.split("\n")[-1] == (
            "📄 Page 1 of 1 (use page parameter to see more)"
        )

    @pytest.mark.asyncio
    async def test_list_runs_omits_pagination_when_total_fits(self):
        result = await _list(_wf_client(runs=[_run()], total=1))
        assert "Showing" not in result
        assert "📄" not in result


class TestListWorkflowRunsErrors:
    @pytest.mark.asyncio
    async def test_list_runs_returns_message_when_value_error(self):
        with patch(WF_CTX, return_value=ctx(exc=ValueError("no token"))):
            result = await github_list_workflow_runs("o", "r")
        assert result == "❌ no token"

    @pytest.mark.asyncio
    async def test_list_runs_returns_network_message_when_connection_error(self):
        with patch(WF_CTX, return_value=ctx(exc=ConnectionError("down"))):
            result = await github_list_workflow_runs("o", "r")
        assert result == "❌ Network connection failed: down"

    @pytest.mark.asyncio
    async def test_list_runs_returns_generic_message_when_unexpected_error(self):
        with patch(WF_CTX, return_value=ctx(exc=RuntimeError("kaboom"))):
            result = await github_list_workflow_runs("o", "r")
        assert result == "❌ Error listing workflow runs: kaboom"


# --------------------------------------------------------------------------
# github_await_workflow_completion
# --------------------------------------------------------------------------

RUN_URL = "https://github.com/o/r/actions/runs/5"


def _done(**overrides) -> dict:
    base = {
        "status": "completed",
        "conclusion": "success",
        "name": "CI",
        "head_branch": "main",
        "head_sha": "abcdef1234567",
        "html_url": RUN_URL,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:05:00Z",
    }
    base.update(overrides)
    return base


async def _await(client, times=(0, 1, 2, 3), sleeper=None, **kwargs):
    ticks = iter(times)
    fake_time = SimpleNamespace(time=lambda: next(ticks))
    fake_asyncio = SimpleNamespace(sleep=sleeper or AsyncMock())
    kwargs.setdefault("run_id", 5)
    with (
        patch(CI_CTX, return_value=ctx(client)),
        patch(CI_TIME, fake_time),
        patch(CI_ASYNCIO, fake_asyncio),
    ):
        return await github_await_workflow_completion("o", "r", **kwargs)


class TestAwaitLatestRunResolution:
    @pytest.mark.asyncio
    async def test_await_returns_failure_when_latest_run_lookup_not_200(self):
        client = FakeClient([("/actions/runs", FakeResponse(500, text="err"))])
        result = await _await(client, run_id=None)
        assert result == "Failed to get latest workflow run: 500 - err"
        assert client.calls == [
            ("/repos/o/r/actions/runs", {"params": {"per_page": 1}})
        ]

    @pytest.mark.asyncio
    async def test_await_returns_message_when_no_runs_exist(self):
        client = FakeClient([("/actions/runs", ok({"workflow_runs": []}))])
        assert await _await(client, run_id=None) == "No workflow runs found for o/r"

    @pytest.mark.asyncio
    async def test_await_returns_message_when_latest_run_has_no_id(self):
        client = FakeClient([("/actions/runs", ok({"workflow_runs": [{}]}))])
        assert await _await(client, run_id=None) == "Latest workflow run has no ID"

    @pytest.mark.asyncio
    async def test_await_monitors_latest_run_when_run_id_omitted(self):
        client = FakeClient(
            [
                ("/actions/runs", ok({"workflow_runs": [{"id": 5}]})),
                ("/actions/runs/5", ok(_done())),
            ]
        )
        result = json.loads(await _await(client, run_id=None))
        assert result["run_id"] == 5
        assert [c[0] for c in client.calls] == [
            "/repos/o/r/actions/runs",
            "/repos/o/r/actions/runs/5",
        ]


class TestAwaitPolling:
    @pytest.mark.asyncio
    async def test_await_returns_failure_when_run_status_not_200(self):
        client = FakeClient([("/actions/runs/5", FakeResponse(404, text="nope"))])
        result = await _await(client)
        assert result == "Failed to get workflow run #5: 404 - nope"

    @pytest.mark.asyncio
    async def test_await_returns_timeout_json_when_elapsed_exceeds_timeout(self):
        client = FakeClient([("/actions/runs/5", ok(_done()))])
        result = await _await(client, times=(0, 60), timeout_minutes=1)
        expected = {
            "status": "timeout",
            "run_id": 5,
            "run_url": RUN_URL,
            "elapsed_seconds": 60,
            "message": (
                "Workflow run did not complete within 1 minutes. Consider "
                "increasing timeout_minutes for very long-running workflows "
                "(max: 350 minutes)."
            ),
            "polls_performed": 1,
        }
        assert result == json.dumps(expected, indent=2)
        assert client.calls == []

    @pytest.mark.asyncio
    async def test_await_sleeps_and_repolls_when_run_in_progress(self):
        sleeper = AsyncMock()
        client = FakeClient(
            [
                (
                    "/actions/runs/5",
                    [ok({"status": "in_progress"}), ok(_done())],
                )
            ]
        )
        result = json.loads(
            await _await(client, sleeper=sleeper, poll_interval_seconds=7)
        )
        assert result["status"] == "success"
        sleeper.assert_awaited_once_with(7)
        assert len(client.calls) == 2


class TestAwaitCompletion:
    @pytest.mark.asyncio
    async def test_await_returns_success_json_when_run_succeeded(self):
        client = FakeClient([("/actions/runs/5", ok(_done()))])
        result = await _await(client)
        expected = {
            "status": "success",
            "conclusion": "success",
            "run_id": 5,
            "run_url": RUN_URL,
            "duration_seconds": 300.0,
            "workflow_name": "CI",
            "head_branch": "main",
            "head_sha": "abcdef12",
        }
        assert result == json.dumps(expected, indent=2)
        assert len(client.calls) == 1

    @pytest.mark.asyncio
    async def test_await_reports_zero_duration_when_timestamps_bad_or_missing(self):
        bad = FakeClient([("/actions/runs/5", ok(_done(created_at="x")))])
        assert json.loads(await _await(bad))["duration_seconds"] == 0
        missing = FakeClient(
            [("/actions/runs/5", ok({"status": "completed", "conclusion": "success"}))]
        )
        result = json.loads(await _await(missing))
        assert result == {
            "status": "success",
            "conclusion": "success",
            "run_id": 5,
            "run_url": None,
            "duration_seconds": 0,
            "workflow_name": None,
            "head_branch": None,
            "head_sha": "",
        }

    @pytest.mark.asyncio
    async def test_await_returns_failure_json_with_failed_jobs_when_run_failed(self):
        jobs = {
            "jobs": [
                {
                    "id": 1,
                    "name": "Test",
                    "status": "completed",
                    "conclusion": "failure",
                    "html_url": "https://j/1",
                    "steps": [
                        {"name": "Setup", "conclusion": "success"},
                        {"name": "Run", "conclusion": "failure"},
                    ],
                },
                {
                    "id": 2,
                    "name": "Lint",
                    "status": "completed",
                    "conclusion": "cancelled",
                    "html_url": "https://j/2",
                    "steps": [{"name": "Setup", "conclusion": "success"}],
                },
                {"id": 3, "name": "Ok", "status": "completed", "conclusion": "success"},
                {"id": 4, "name": "Run", "status": "in_progress"},
            ]
        }
        client = FakeClient(
            [
                ("/jobs", ok(jobs)),
                ("/actions/runs/5", ok(_done(conclusion="failure"))),
            ]
        )
        result = await _await(client)
        expected = {
            "status": "failure",
            "conclusion": "failure",
            "run_id": 5,
            "run_url": RUN_URL,
            "duration_seconds": 300.0,
            "workflow_name": "CI",
            "head_branch": "main",
            "head_sha": "abcdef12",
            "failed_jobs": [
                {
                    "name": "Test",
                    "conclusion": "failure",
                    "html_url": "https://j/1",
                    "failed_steps": ["Run"],
                },
                {
                    "name": "Lint",
                    "conclusion": "cancelled",
                    "html_url": "https://j/2",
                },
            ],
            "logs_note": "View detailed logs at: https://j/1",
        }
        assert result == json.dumps(expected, indent=2)

    @pytest.mark.asyncio
    async def test_await_omits_logs_note_when_no_failed_jobs(self):
        jobs = {"jobs": [{"id": 3, "status": "completed", "conclusion": "success"}]}
        client = FakeClient(
            [
                ("/jobs", ok(jobs)),
                ("/actions/runs/5", ok(_done(conclusion="failure"))),
            ]
        )
        result = json.loads(await _await(client))
        assert result["failed_jobs"] == []
        assert "logs_note" not in result

    @pytest.mark.asyncio
    async def test_await_omits_logs_note_when_first_job_has_no_id(self):
        jobs = {
            "jobs": [
                {"name": "T", "status": "completed", "conclusion": "failure"},
            ]
        }
        client = FakeClient(
            [
                ("/jobs", ok(jobs)),
                ("/actions/runs/5", ok(_done(conclusion="failure"))),
            ]
        )
        result = json.loads(await _await(client))
        assert result["failed_jobs"] == [
            {"name": "T", "conclusion": "failure", "html_url": None}
        ]
        assert "logs_note" not in result

    @pytest.mark.asyncio
    async def test_await_omits_failed_jobs_when_jobs_fetch_not_200(self):
        client = FakeClient(
            [
                ("/jobs", FakeResponse(500, text="x")),
                ("/actions/runs/5", ok(_done(conclusion="failure"))),
            ]
        )
        result = json.loads(await _await(client))
        assert result["status"] == "failure"
        assert "failed_jobs" not in result
        assert "logs_note" not in result


class TestAwaitErrors:
    @pytest.mark.asyncio
    async def test_await_returns_auth_message_when_value_error(self):
        with patch(CI_CTX, return_value=ctx(exc=ValueError("no token"))):
            result = await github_await_workflow_completion("o", "r", run_id=5)
        assert result == "Authentication error: no token"

    @pytest.mark.asyncio
    async def test_await_returns_network_message_when_connection_error(self):
        with patch(CI_CTX, return_value=ctx(exc=ConnectionError("down"))):
            result = await github_await_workflow_completion("o", "r", run_id=5)
        assert result == "Network connection failed: down"

    @pytest.mark.asyncio
    async def test_await_returns_generic_message_when_unexpected_error(self):
        with patch(CI_CTX, return_value=ctx(exc=RuntimeError("kaboom"))):
            result = await github_await_workflow_completion("o", "r", run_id=5)
        assert result == "Error awaiting workflow completion: kaboom"


# --------------------------------------------------------------------------
# github_get_pr_checks
# --------------------------------------------------------------------------


def _pr() -> FakeResponse:
    return ok({"head": {"sha": "abcdef1234567"}})


def _check(**overrides) -> dict:
    base = {
        "id": 9,
        "name": "build",
        "status": "completed",
        "conclusion": "success",
        "started_at": "2024-01-01T00:00:00Z",
        "completed_at": "2024-01-01T00:05:00Z",
        "html_url": "https://c/9",
    }
    base.update(overrides)
    return base


def _pr_client(checks, checks_status=200, extra=()):
    return FakeClient(
        [
            *extra,
            ("/check-runs", FakeResponse(checks_status, {"check_runs": checks})),
            ("/pulls/5", _pr()),
        ]
    )


async def _checks(client, **kwargs):
    with patch(PR_CTX, return_value=ctx(client)):
        return await github_get_pr_checks("o", "r", 5, **kwargs)


class TestPrChecks:
    @pytest.mark.asyncio
    async def test_pr_checks_returns_failure_when_pr_lookup_not_200(self):
        client = FakeClient([("/pulls/5", FakeResponse(404))])
        assert await _checks(client) == "❌ Failed to get PR #5: 404"

    @pytest.mark.asyncio
    async def test_pr_checks_returns_failure_when_check_runs_not_200(self):
        result = await _checks(_pr_client([], checks_status=500))
        assert result == "❌ Failed to get check runs: 500"

    @pytest.mark.asyncio
    async def test_pr_checks_returns_message_when_no_check_runs(self):
        assert await _checks(_pr_client([])) == "No check runs found for PR #5"

    @pytest.mark.asyncio
    async def test_pr_checks_passes_status_param_when_status_given(self):
        client = _pr_client([_check()])
        await _checks(client, status="completed")
        assert client.calls[1] == (
            "/repos/o/r/commits/abcdef1234567/check-runs",
            {"params": {"status": "completed"}},
        )

    @pytest.mark.asyncio
    async def test_pr_checks_sends_empty_params_when_no_status(self):
        client = _pr_client([_check()])
        await _checks(client)
        assert client.calls[1][1] == {"params": {}}

    @pytest.mark.asyncio
    async def test_pr_checks_filters_by_conclusion_when_conclusion_given(self):
        checks = [_check(), _check(name="lint", conclusion="failure")]
        result = await _checks(_pr_client(checks), conclusion="failure")
        assert result.split("\n")[2:4] == ["❌ lint", "   Status: completed"]
        assert "build" not in result

    @pytest.mark.asyncio
    async def test_pr_checks_returns_message_when_conclusion_filters_all_out(self):
        result = await _checks(_pr_client([_check()]), conclusion="failure")
        assert result == "No check runs found for PR #5"

    @pytest.mark.asyncio
    async def test_pr_checks_formats_full_run_when_all_fields_present(self):
        result = await _checks(_pr_client([_check()]))
        assert result.split("\n") == [
            "Check runs for PR #5 (commit abcdef12):",
            "",
            "✅ build",
            "   Status: completed",
            "   Conclusion: success",
            "   Started: 2024-01-01T00:00:00Z",
            "   Completed: 2024-01-01T00:05:00Z",
            "   URL: https://c/9",
            "",
        ]

    @pytest.mark.asyncio
    async def test_pr_checks_omits_optional_lines_when_fields_missing(self):
        run = {"name": "build", "status": "queued"}
        result = await _checks(_pr_client([run]))
        lines = result.split("\n")
        assert lines[3:] == ["   Status: queued", "   Started: N/A", ""]

    @pytest.mark.asyncio
    async def test_pr_checks_returns_message_when_value_error(self):
        with patch(PR_CTX, return_value=ctx(exc=ValueError("no token"))):
            assert await github_get_pr_checks("o", "r", 5) == "❌ no token"

    @pytest.mark.asyncio
    async def test_pr_checks_returns_network_message_when_connection_error(self):
        with patch(PR_CTX, return_value=ctx(exc=ConnectionError("down"))):
            result = await github_get_pr_checks("o", "r", 5)
        assert result == "❌ Network connection failed: down"

    @pytest.mark.asyncio
    async def test_pr_checks_returns_generic_message_when_unexpected_error(self):
        with patch(PR_CTX, return_value=ctx(exc=RuntimeError("kaboom"))):
            result = await github_get_pr_checks("o", "r", 5)
        assert result == "❌ Error getting PR checks: kaboom"


# --------------------------------------------------------------------------
# github_get_failing_jobs
# --------------------------------------------------------------------------


async def _failing(client, **kwargs):
    with patch(PR_CTX, return_value=ctx(client)):
        return await github_get_failing_jobs("o", "r", 5, **kwargs)


def _failing_run(**overrides):
    return _check(conclusion="failure", **overrides)


def _annotations(payload, status=200):
    return ("/annotations", FakeResponse(status, payload))


class TestFailingJobs:
    @pytest.mark.asyncio
    async def test_failing_jobs_returns_failure_when_pr_lookup_not_200(self):
        client = FakeClient([("/pulls/5", FakeResponse(404))])
        assert await _failing(client) == "❌ Failed to get PR #5: 404"

    @pytest.mark.asyncio
    async def test_failing_jobs_returns_failure_when_check_runs_not_200(self):
        result = await _failing(_pr_client([], checks_status=502))
        assert result == "❌ Failed to get check runs: 502"

    @pytest.mark.asyncio
    async def test_failing_jobs_returns_message_when_none_failing(self):
        runs = [
            _check(),
            _check(status="in_progress", conclusion=None),
            _check(conclusion="skipped"),
        ]
        assert await _failing(_pr_client(runs)) == "No failing jobs found for PR #5"

    @pytest.mark.asyncio
    async def test_failing_jobs_formats_run_with_annotations_when_requested(self):
        annotations = [
            {"title": f"T{i}", "message": f"M{i}", "path": f"f{i}.py", "start_line": i}
            for i in range(7)
        ]
        annotations[1] = {}
        client = _pr_client([_failing_run()], extra=[_annotations(annotations)])
        result = await _failing(client)
        assert result.split("\n") == [
            "Failing jobs for PR #5:",
            "",
            "❌ build",
            "   Conclusion: failure",
            "   Started: 2024-01-01T00:00:00Z",
            "   Completed: 2024-01-01T00:05:00Z",
            "   Annotations:",
            "     • T0: M0",
            "       File: f0.py (line 0)",
            "     • Error: No message",
            "     • T2: M2",
            "       File: f2.py (line 2)",
            "     • T3: M3",
            "       File: f3.py (line 3)",
            "     • T4: M4",
            "       File: f4.py (line 4)",
            "   Details: https://c/9",
            "",
        ]
        assert client.calls[2][0] == "/repos/o/r/check-runs/9/annotations"

    @pytest.mark.asyncio
    async def test_failing_jobs_prints_unknown_line_when_start_line_missing(self):
        annotations = [{"title": "T", "message": "M", "path": "a.py"}]
        client = _pr_client([_failing_run()], extra=[_annotations(annotations)])
        result = await _failing(client)
        assert "       File: a.py (line unknown)" in result.split("\n")

    @pytest.mark.asyncio
    async def test_failing_jobs_skips_annotations_when_disabled_and_hides_details(
        self,
    ):
        client = _pr_client([_failing_run()])
        result = await _failing(client, include_annotations=False, include_logs=False)
        assert result.split("\n") == [
            "Failing jobs for PR #5:",
            "",
            "❌ build",
            "   Conclusion: failure",
            "   Started: 2024-01-01T00:00:00Z",
            "   Completed: 2024-01-01T00:05:00Z",
            "",
        ]
        assert len(client.calls) == 2

    @pytest.mark.asyncio
    async def test_failing_jobs_skips_annotations_when_run_has_no_id(self):
        run = {"name": "x", "status": "completed", "conclusion": "cancelled"}
        client = _pr_client([run])
        result = await _failing(client)
        assert result.split("\n") == [
            "Failing jobs for PR #5:",
            "",
            "❌ x",
            "   Conclusion: cancelled",
            "   Started: N/A",
            "   Completed: N/A",
            "",
        ]
        assert len(client.calls) == 2

    @pytest.mark.asyncio
    async def test_failing_jobs_omits_annotations_when_response_not_200_or_empty(
        self,
    ):
        for extra in (_annotations(None, status=500), _annotations([])):
            result = await _failing(_pr_client([_failing_run()], extra=[extra]))
            assert "Annotations" not in result
            assert result.endswith("   Details: https://c/9\n")

    @pytest.mark.asyncio
    async def test_failing_jobs_continues_when_annotation_fetch_raises(self):
        for exc in (ConnectionError("down"), ValueError("bad"), RuntimeError("x")):
            client = _pr_client([_failing_run()], extra=[("/annotations", exc)])
            result = await _failing(client)
            assert result.split("\n")[-2:] == ["   Details: https://c/9", ""]

    @pytest.mark.asyncio
    async def test_failing_jobs_includes_timed_out_runs_when_listing(self):
        runs = [_failing_run(), _check(name="slow", conclusion="timed_out")]
        result = await _failing(_pr_client(runs), include_annotations=False)
        assert "❌ slow" in result.split("\n")
        assert "   Conclusion: timed_out" in result.split("\n")

    @pytest.mark.asyncio
    async def test_failing_jobs_returns_message_when_value_error(self):
        with patch(PR_CTX, return_value=ctx(exc=ValueError("no token"))):
            assert await github_get_failing_jobs("o", "r", 5) == "❌ no token"

    @pytest.mark.asyncio
    async def test_failing_jobs_returns_network_message_when_connection_error(self):
        with patch(PR_CTX, return_value=ctx(exc=ConnectionError("down"))):
            result = await github_get_failing_jobs("o", "r", 5)
        assert result == "❌ Network connection failed: down"

    @pytest.mark.asyncio
    async def test_failing_jobs_returns_generic_message_when_unexpected_error(self):
        with patch(PR_CTX, return_value=ctx(exc=RuntimeError("kaboom"))):
            result = await github_get_failing_jobs("o", "r", 5)
        assert result == "❌ Error getting failing jobs: kaboom"
