"""Azure ops report their own failures as ToolFailure (issue #271, part 5).

A build that RAN and FAILED is a successful query: it stays a plain str.
"""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_server_git.azure.api import (
    azure_get_build_logs,
    azure_get_build_status,
    azure_get_failing_jobs,
)
from mcp_server_git.lean.interface import GitLeanInterface
from mcp_server_git.utils.tool_failure import ToolFailure


def _response(status: int, payload: dict | None = None, text: str = "") -> MagicMock:
    response = MagicMock()
    response.status = status
    response.json = AsyncMock(return_value=payload)
    response.text = AsyncMock(return_value=text)
    return response


@contextmanager
def _azure_client(*responses: MagicMock):
    client = MagicMock()
    client.get = AsyncMock(side_effect=list(responses))
    with patch("mcp_server_git.azure.api.azure_client_context") as context:
        context.return_value.__aenter__.return_value = client
        yield client


_FAILED_BUILD = {"result": "failed", "definition": {"name": "CI"}, "sourceVersion": "x"}
_FAILED_TASK = {
    "type": "Task",
    "name": "Compile",
    "result": "failed",
    "state": "completed",
}


@pytest.mark.asyncio
async def test_build_status_returns_tool_failure_when_build_not_found():
    with _azure_client(_response(404, text="no such build")):
        result = await azure_get_build_status("proj", 7)

    assert isinstance(result, ToolFailure)
    assert result == "❌ Failed to get build #7: 404 - no such build"


@pytest.mark.asyncio
async def test_build_logs_returns_tool_failure_when_unauthorized():
    with _azure_client(_response(401, text="denied")):
        result = await azure_get_build_logs("proj", 7)

    assert isinstance(result, ToolFailure)
    assert result == "❌ Failed to get build logs: 401 - denied"


@pytest.mark.asyncio
async def test_build_logs_returns_tool_failure_when_single_log_missing():
    with _azure_client(_response(404, text="gone")):
        result = await azure_get_build_logs("proj", 7, log_id=3)

    assert isinstance(result, ToolFailure)
    assert result == "❌ Failed to get log #3: 404 - gone"


@pytest.mark.asyncio
async def test_failing_jobs_returns_tool_failure_when_timeline_fetch_fails():
    with _azure_client(_response(200, _FAILED_BUILD), _response(500, text="boom")):
        result = await azure_get_failing_jobs("proj", 7, include_logs=False)

    assert isinstance(result, ToolFailure)
    assert result == "❌ Failed to get build timeline: 500 - boom"


@pytest.mark.asyncio
async def test_build_status_returns_tool_failure_when_client_raises():
    with patch("mcp_server_git.azure.api.azure_client_context") as context:
        context.return_value.__aenter__.side_effect = RuntimeError("down")
        result = await azure_get_build_status("proj", 7)

    assert isinstance(result, ToolFailure)
    assert result == "❌ Error getting build status: down"


@pytest.mark.asyncio
async def test_build_status_returns_plain_str_when_build_failed():
    with _azure_client(_response(200, _FAILED_BUILD)):
        result = await azure_get_build_status("proj", 7)

    assert not isinstance(result, ToolFailure)
    assert "Result: failed" in result


@pytest.mark.asyncio
async def test_failing_jobs_returns_plain_str_with_marker_when_build_failed():
    records = {"records": [_FAILED_TASK]}
    with _azure_client(_response(200, _FAILED_BUILD), _response(200, records)):
        result = await azure_get_failing_jobs("proj", 7, include_logs=False)

    assert not isinstance(result, ToolFailure)
    assert "❌ Task: Compile" in result


def _interface() -> GitLeanInterface:
    service = MagicMock()
    return GitLeanInterface(
        git_service=service, github_service=service, azure_service=service
    )


@pytest.mark.asyncio
async def test_execute_tool_direct_returns_error_when_azure_http_fails():
    with _azure_client(_response(404, text="no such build")):
        envelope = await _interface().execute_tool_direct(
            "azure_get_build_status", {"project": "proj", "build_id": 7}
        )

    assert envelope["status"] == "error"
    assert envelope["error"] == "❌ Failed to get build #7: 404 - no such build"


@pytest.mark.asyncio
async def test_execute_tool_direct_returns_success_when_build_failed():
    with _azure_client(_response(200, _FAILED_BUILD)):
        envelope = await _interface().execute_tool_direct(
            "azure_get_build_status", {"project": "proj", "build_id": 7}
        )

    assert envelope["status"] == "success"
    assert "Result: failed" in envelope["result"]
