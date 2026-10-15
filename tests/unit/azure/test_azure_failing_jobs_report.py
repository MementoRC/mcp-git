"""Characterization tests for azure_get_failing_jobs report output (issue #255)."""

import logging
from contextlib import asynccontextmanager

import pytest

from mcp_server_git.azure import api
from mcp_server_git.azure.api import azure_get_failing_jobs
from mcp_server_git.github.check_markers import CONCLUSION_MARKERS
from mcp_server_git.utils.tool_failure import ToolFailure

FAILED = CONCLUSION_MARKERS["failure"]
CANCELLED = CONCLUSION_MARKERS["cancelled"]


class FakeResponse:
    def __init__(self, status=200, payload=None, text="", content_type=""):
        self.status = status
        self.headers = {"Content-Type": content_type}
        self._payload = payload
        self._text = text

    async def json(self):
        return self._payload

    async def text(self):
        return self._text


class FakeClient:
    """Routes Azure URLs to canned responses; records requested URLs."""

    def __init__(self, build, timeline, logs=None):
        self.build, self.timeline, self.logs = build, timeline, logs or {}
        self.urls = []

    async def get(self, url, **kwargs):
        self.urls.append(url)
        if "/timeline" in url:
            return self.timeline
        if "/logs/" in url:
            result = self.logs[int(url.split("/logs/")[1].split("?")[0])]
            if isinstance(result, Exception):
                raise result
            return result
        return self.build


@pytest.fixture
def use_client(monkeypatch):
    def _install(client):
        @asynccontextmanager
        async def _ctx():
            yield client

        monkeypatch.setattr(api, "azure_client_context", _ctx)
        return client

    return _install


def _build(result="failed"):
    return FakeResponse(payload={"id": 123, "result": result})


def _timeline(*records):
    return FakeResponse(payload={"records": list(records)})


def _job(**overrides):
    record = {"type": "Job", "name": "Build Job", "result": "failed"}
    record.update(overrides)
    return record


async def _run(**kwargs):
    return await azure_get_failing_jobs("proj", 123, **kwargs)


async def test_azure_get_failing_jobs_returns_full_report_when_json_log_truncated(
    use_client,
):
    issues = [{"type": "error", "message": f"e{i}"} for i in range(6)]
    use_client(
        FakeClient(
            _build(),
            _timeline(
                _job(
                    state="completed",
                    startTime="S",
                    finishTime="F",
                    issues=issues,
                    log={"id": 5},
                )
            ),
            {
                5: FakeResponse(
                    payload={"value": ["l1", "l2", "l3"]},
                    content_type="application/json; charset=utf-8",
                )
            },
        )
    )
    result = await _run(log_tail_lines=2)
    assert result == "\n".join(
        [
            "Failed Jobs for Build #123:\n",
            f"{FAILED} Job: Build Job",
            "   Result: failed",
            "   State: completed",
            "   Started: S",
            "   Finished: F",
            "   Issues:",
            *[f"     [error] e{i}" for i in range(5)],
            "   Log excerpt (showing last 2 of 3 lines):",
            "   ... [truncated 1 lines] ...",
            "   ```",
            "   l2",
            "   l3",
            "   ```",
            "",
        ]
    )


async def test_azure_get_failing_jobs_reports_untruncated_plain_text_log_when_short(
    use_client,
):
    use_client(
        FakeClient(
            _build("partiallySucceeded"),
            _timeline(_job(log={"id": 7})),
            {7: FakeResponse(text="a\nb", content_type="text/plain")},
        )
    )
    result = await _run()
    assert result == "\n".join(
        [
            "Failed Jobs for Build #123:\n",
            f"{FAILED} Job: Build Job",
            "   Result: failed",
            "   State: N/A",
            "   Log excerpt (2 lines):",
            "   ```",
            "   a",
            "   b",
            "   ```",
            "",
        ]
    )


@pytest.mark.parametrize(
    ("payload", "expected_lines"),
    [
        (["x", "y"], ["   x", "   y"]),
        ({"other": 1}, ["   {'other': 1}"]),
    ],
)
async def test_azure_get_failing_jobs_normalises_json_log_shapes_when_not_value_dict(
    use_client, payload, expected_lines
):
    use_client(
        FakeClient(
            _build(),
            _timeline(_job(log={"id": 1})),
            {1: FakeResponse(payload=payload, content_type="application/json")},
        )
    )
    result = await _run()
    assert result.splitlines()[-1 - len(expected_lines) : -1] == expected_lines


async def test_azure_get_failing_jobs_skips_log_section_when_log_fetch_not_ok(
    use_client,
):
    use_client(
        FakeClient(
            _build(),
            _timeline(_job(log={"id": 1})),
            {1: FakeResponse(status=404)},
        )
    )
    result = await _run()
    assert result == "\n".join(
        [
            "Failed Jobs for Build #123:\n",
            f"{FAILED} Job: Build Job",
            "   Result: failed",
            "   State: N/A",
            "",
        ]
    )


async def test_azure_get_failing_jobs_warns_and_continues_when_log_fetch_raises(
    use_client, caplog
):
    use_client(
        FakeClient(
            _build(),
            _timeline(_job(log={"id": 1}), _job(name="Second", type="Task")),
            {1: RuntimeError("net down")},
        )
    )
    with caplog.at_level(logging.WARNING, logger=api.logger.name):
        result = await _run()
    assert "Task: Second" in result
    assert [r.getMessage() for r in caplog.records] == ["Failed to get log 1: net down"]


async def test_azure_get_failing_jobs_does_not_fetch_logs_when_include_logs_false(
    use_client,
):
    client = use_client(
        FakeClient(_build(), _timeline(_job(log={"id": 1})), {1: FakeResponse()})
    )
    await _run(include_logs=False)
    assert not any("/logs/" in url for url in client.urls)


async def test_azure_get_failing_jobs_uses_result_specific_marker_and_filters_types(
    use_client,
):
    use_client(
        FakeClient(
            _build("canceled"),
            _timeline(
                _job(result="canceled", name="C"),
                _job(result="abandoned", name="A", type="Phase"),
                _job(result="failed", name="Stage", type="Stage"),
                _job(result="succeeded", name="Ok"),
                {"name": "Untyped", "result": "failed"},
            ),
        )
    )
    result = await _run()
    assert f"{CANCELLED} Job: C" in result
    assert "⚠️ Phase: A" in result
    assert "Stage" not in result
    assert "Ok" not in result
    assert "Untyped" not in result


async def test_azure_get_failing_jobs_returns_message_when_build_not_failed(use_client):
    use_client(FakeClient(_build("succeeded"), _timeline()))
    result = await _run()
    assert result == "Build #123 has result 'succeeded' - no failures to report"
    assert not isinstance(result, ToolFailure)


async def test_azure_get_failing_jobs_returns_message_when_no_failed_records(
    use_client,
):
    use_client(FakeClient(_build(), _timeline(_job(result="succeeded"))))
    assert await _run() == "No failed jobs found for build #123"


async def test_azure_get_failing_jobs_returns_failure_when_build_fetch_not_ok(
    use_client,
):
    use_client(FakeClient(FakeResponse(status=500, text="boom"), _timeline()))
    result = await _run()
    assert result == "❌ Failed to get build #123: 500 - boom"
    assert isinstance(result, ToolFailure)


async def test_azure_get_failing_jobs_returns_timeline_failure_when_timeline_not_ok(
    use_client,
):
    use_client(FakeClient(_build(), FakeResponse(status=503, text="down")))
    result = await _run()
    assert result == "❌ Failed to get build timeline: 503 - down"
    assert isinstance(result, ToolFailure)


async def test_azure_get_failing_jobs_returns_auth_failure_when_value_error_raised(
    monkeypatch,
):
    @asynccontextmanager
    async def _ctx():
        raise ValueError("no org")
        yield

    monkeypatch.setattr(api, "azure_client_context", _ctx)
    result = await _run()
    assert result == "❌ no org"
    assert isinstance(result, ToolFailure)


async def test_azure_get_failing_jobs_returns_generic_failure_when_unexpected_error(
    use_client,
):
    class Boom(FakeClient):
        async def get(self, url, **kwargs):
            raise RuntimeError("kaput")

    use_client(Boom(None, None))
    result = await _run()
    assert result == "❌ Error getting failing jobs: kaput"
    assert isinstance(result, ToolFailure)
