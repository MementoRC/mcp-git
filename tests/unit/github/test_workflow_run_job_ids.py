"""Job ids in workflow runs, name-based job log lookup, include_logs (issue #279).

Only the ``github_client_context`` boundary is faked.
"""

from unittest.mock import patch

import pytest

from mcp_server_git.github.api import github_get_job_logs, github_get_workflow_run
from mcp_server_git.lean.interface import GitLeanInterface
from mcp_server_git.utils.tool_failure import ToolFailure

WF_CTX = "mcp_server_git.github.workflows.github_client_context"
CI_CTX = "mcp_server_git.github.ci_logs.github_client_context"

RUN = {
    "name": "CI",
    "status": "completed",
    "conclusion": "failure",
    "head_branch": "main",
    "head_sha": "abcdef1234567",
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:05:00Z",
    "html_url": "https://github.com/o/r/actions/runs/9",
}


def _job(job_id: int, name: str, conclusion: str = "success") -> dict:
    return {
        "id": job_id,
        "name": name,
        "status": "completed",
        "conclusion": conclusion,
        "html_url": f"https://github.com/o/r/actions/runs/9/job/{job_id}",
    }


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
    """Routes GETs by exact endpoint; records every call."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    async def get(self, endpoint, **kwargs):
        self.calls.append((endpoint, kwargs))
        value = self.routes[endpoint]
        if isinstance(value, list):
            value = value.pop(0)
        return value


RUN_URL = "/repos/o/r/actions/runs/9"
JOBS_URL = f"{RUN_URL}/jobs"


def _jobs_page(jobs):
    return FakeResponse(200, {"jobs": jobs})


def _routes(jobs, **extra):
    routes = {RUN_URL: FakeResponse(200, RUN), JOBS_URL: _jobs_page(jobs)}
    routes.update(extra)
    return routes


async def _call(op, client, *args, **kwargs):
    with patch(WF_CTX) as wf, patch(CI_CTX) as ci:
        wf.return_value.__aenter__.return_value = client
        ci.return_value.__aenter__.return_value = client
        return await op(*args, **kwargs)


def _job_and_logs(job_id, name, log_text, conclusion="failure"):
    return {
        f"/repos/o/r/actions/jobs/{job_id}": FakeResponse(
            200, _job(job_id, name, conclusion)
        ),
        f"/repos/o/r/actions/jobs/{job_id}/logs": FakeResponse(200, text=log_text),
    }


# --------------------------------------------------------------------------
# github_get_workflow_run: job id and url
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_github_get_workflow_run_returns_job_id_and_url_when_run_has_jobs():
    client = FakeClient(_routes([_job(111, "build"), _job(222, "test", "failure")]))

    result = await _call(github_get_workflow_run, client, "o", "r", 9)

    assert "build" in result
    assert "ID: 111" in result
    assert "ID: 222" in result
    assert "https://github.com/o/r/actions/runs/9/job/222" in result
    assert "Conclusion: failure" in result


@pytest.mark.asyncio
async def test_github_get_workflow_run_returns_all_jobs_when_jobs_span_pages():
    page1 = [_job(i, f"job{i}") for i in range(1, 101)]
    page2 = [_job(101, "job101")]
    client = FakeClient(
        _routes([], **{JOBS_URL: [_jobs_page(page1), _jobs_page(page2)]})
    )

    result = await _call(github_get_workflow_run, client, "o", "r", 9)

    assert "ID: 101" in result
    jobs_calls = [kw for ep, kw in client.calls if ep == JOBS_URL]
    assert [c["params"] for c in jobs_calls] == [
        {"per_page": 100, "page": 1},
        {"per_page": 100, "page": 2},
    ]


# --------------------------------------------------------------------------
# github_get_job_logs: run_id + job_name
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_github_get_job_logs_returns_logs_when_job_name_matches_exactly():
    routes = _routes(
        [_job(111, "build"), _job(222, "test", "failure")],
        **_job_and_logs(222, "test", "boom\nline2"),
    )
    client = FakeClient(routes)

    result = await _call(
        github_get_job_logs, client, "o", "r", run_id=9, job_name="test"
    )

    assert not isinstance(result, ToolFailure)
    assert "Job #222 - test" in result
    assert "boom" in result


@pytest.mark.asyncio
async def test_github_get_job_logs_returns_tool_failure_when_no_selector_given():
    client = FakeClient({})

    result = await _call(github_get_job_logs, client, "o", "r")

    assert isinstance(result, ToolFailure)
    assert "job_id" in result and "run_id" in result and "job_name" in result


@pytest.mark.asyncio
async def test_github_get_job_logs_returns_tool_failure_when_only_run_id_given():
    client = FakeClient({})

    result = await _call(github_get_job_logs, client, "o", "r", run_id=9)

    assert isinstance(result, ToolFailure)
    assert client.calls == []


@pytest.mark.asyncio
async def test_github_get_job_logs_returns_tool_failure_when_job_id_and_name_both_given():
    client = FakeClient({})

    result = await _call(
        github_get_job_logs, client, "o", "r", job_id=5, run_id=9, job_name="test"
    )

    assert isinstance(result, ToolFailure)
    assert "not both" in result
    assert client.calls == []


@pytest.mark.asyncio
async def test_github_get_job_logs_returns_tool_failure_when_job_name_not_found():
    client = FakeClient(_routes([_job(111, "build"), _job(222, "test")]))

    result = await _call(
        github_get_job_logs, client, "o", "r", run_id=9, job_name="lint"
    )

    assert isinstance(result, ToolFailure)
    assert "'lint'" in result
    assert "build" in result and "test" in result


@pytest.mark.asyncio
async def test_github_get_job_logs_returns_tool_failure_when_job_name_is_ambiguous():
    client = FakeClient(_routes([_job(111, "test"), _job(222, "test")]))

    result = await _call(
        github_get_job_logs, client, "o", "r", run_id=9, job_name="test"
    )

    assert isinstance(result, ToolFailure)
    assert "111" in result and "222" in result


@pytest.mark.asyncio
async def test_github_get_job_logs_returns_tool_failure_when_jobs_listing_fails():
    routes = {JOBS_URL: FakeResponse(404, text="Not Found")}
    client = FakeClient(routes)

    result = await _call(
        github_get_job_logs, client, "o", "r", run_id=9, job_name="test"
    )

    assert isinstance(result, ToolFailure)
    assert "404" in result


@pytest.mark.asyncio
async def test_execute_tool_direct_returns_error_when_no_job_selector_given():
    class _Svc:
        def __getattr__(self, name):
            return lambda **kw: {}

    interface = GitLeanInterface(
        git_service=_Svc(), github_service=_Svc(), azure_service=_Svc()
    )

    envelope = await interface.execute_tool_direct(
        "github_get_job_logs", {"repo_owner": "o", "repo_name": "r"}
    )

    assert envelope["status"] == "error"


def test_github_get_job_logs_schema_lists_run_id_and_job_name_when_inspected():
    from mcp_server_git.github.models import GitHubGetJobLogs

    schema = GitHubGetJobLogs.model_json_schema()

    assert "run_id" in schema["properties"]
    assert "job_name" in schema["properties"]
    assert "job_id" not in schema.get("required", [])


# --------------------------------------------------------------------------
# github_get_workflow_run: include_logs
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_github_get_workflow_run_returns_failed_job_log_tail_when_include_logs():
    log = "\n".join(f"line{i}" for i in range(300))
    routes = _routes(
        [_job(111, "build"), _job(222, "test", "failure")],
        **_job_and_logs(222, "test", log),
    )
    client = FakeClient(routes)

    result = await _call(
        github_get_workflow_run, client, "o", "r", 9, include_logs=True
    )

    assert "line299" in result
    assert "line200" in result
    assert "line199\n" not in result
    assert not isinstance(result, ToolFailure)


@pytest.mark.asyncio
async def test_github_get_workflow_run_keeps_other_logs_when_one_log_fetch_fails():
    routes = _routes(
        [_job(222, "test", "failure"), _job(333, "lint", "failure")],
        **_job_and_logs(333, "lint", "lint-output"),
    )
    routes["/repos/o/r/actions/jobs/222"] = FakeResponse(404)
    client = FakeClient(routes)

    result = await _call(
        github_get_workflow_run, client, "o", "r", 9, include_logs=True
    )

    assert not isinstance(result, ToolFailure)
    assert "lint-output" in result
    assert "test" in result and "could not fetch" in result


@pytest.mark.asyncio
async def test_github_get_workflow_run_says_no_failed_jobs_when_include_logs_and_all_pass():
    client = FakeClient(_routes([_job(111, "build")]))

    result = await _call(
        github_get_workflow_run, client, "o", "r", 9, include_logs=True
    )

    assert "no failed jobs" in result.lower()


@pytest.mark.asyncio
async def test_github_get_workflow_run_omits_logs_when_include_logs_is_false():
    client = FakeClient(_routes([_job(222, "test", "failure")]))

    result = await _call(github_get_workflow_run, client, "o", "r", 9)

    assert "no failed jobs" not in result.lower()
    assert [ep for ep, _ in client.calls] == [RUN_URL, JOBS_URL]


@pytest.mark.asyncio
async def test_github_get_workflow_run_caps_total_log_output_when_logs_are_huge():
    big = "\n".join("x" * 200 for _ in range(100))
    jobs = [_job(i, f"job{i}", "failure") for i in range(1, 9)]
    extra = {}
    for i in range(1, 9):
        extra.update(_job_and_logs(i, f"job{i}", big))
    client = FakeClient(_routes(jobs, **extra))

    result = await _call(
        github_get_workflow_run, client, "o", "r", 9, include_logs=True
    )

    assert len(result) < 100_000
    assert "omitted" in result
