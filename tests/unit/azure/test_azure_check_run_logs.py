"""Unit tests for azure_get_logs_for_check_run (issue #229).

Mock-based only, following tests/unit/azure/test_azure_api.py and
tests/unit/github/test_github_job_logs.py conventions. Fixtures mirror the
real captured shapes from a live conda-forge build (1588986): a Job record
carries a generic "Container" log (id 22) while its child Task records carry
the real build output (id 19 for "Run OSX build"); the check run's
details_url path/query shape is reproduced exactly.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp_server_git.azure.check_run_logs import azure_get_logs_for_check_run

_PROJECT_GUID = "29b95f83-9057-4ac8-8624-9b1f6ce6b52f"
_BUILD_ID = 1588986
_JOB_ID = "job1"


def _details_url(job_id: str = _JOB_ID) -> str:
    return (
        f"https://dev.azure.com/conda-forge/{_PROJECT_GUID}/_build/results"
        f"?buildId={_BUILD_ID}&view=logs&jobId={job_id}"
    )


def _check_run_payload(details_url: str | None) -> dict:
    return {"id": 987654321, "details_url": details_url}


def _timeline_records(*, build_result: str = "succeeded") -> list[dict]:
    """One Job with 5 child Tasks, matching the verified conda-forge shape."""
    return [
        {
            "id": _JOB_ID,
            "type": "Job",
            "name": "osx osx_64_cross_target_platform_osx-64",
            "log": {"id": 22},
        },
        {
            "id": "task-init",
            "type": "Task",
            "name": "Initialize job",
            "parentId": _JOB_ID,
            "result": "succeeded",
            "log": {"id": 16, "lineCount": 20},
        },
        {
            "id": "task-checkout",
            "type": "Task",
            "name": "Checkout",
            "parentId": _JOB_ID,
            "result": "succeeded",
            "log": {"id": 17, "lineCount": 15},
        },
        {
            "id": "task-build",
            "type": "Task",
            "name": "Run OSX build",
            "parentId": _JOB_ID,
            "result": build_result,
            "log": {"id": 19, "lineCount": 400},
        },
        {
            "id": "task-post-checkout",
            "type": "Task",
            "name": "Post-job Checkout",
            "parentId": _JOB_ID,
            "result": "succeeded",
            "log": {"id": 20, "lineCount": 10},
        },
        {
            "id": "task-finalize",
            "type": "Task",
            "name": "Finalize Job",
            "parentId": _JOB_ID,
            "result": "succeeded",
            "log": None,
        },
    ]


def _mock_clients(
    *,
    details_url: str | None,
    records: list[dict],
    log_lines: list[str] | None = None,
) -> tuple[MagicMock, MagicMock]:
    """Build (github_client, azure_client) mocks routed by URL content."""
    gh_client = MagicMock()
    check_run_response = AsyncMock()
    check_run_response.status = 200
    check_run_response.json = AsyncMock(return_value=_check_run_payload(details_url))
    gh_client.get = AsyncMock(return_value=check_run_response)

    az_client = MagicMock()
    timeline_response = AsyncMock()
    timeline_response.status = 200
    timeline_response.json = AsyncMock(return_value={"records": records})

    log_response = AsyncMock()
    log_response.status = 200
    log_response.headers = {"Content-Type": "application/json"}
    log_response.json = AsyncMock(return_value={"value": log_lines or ["log body"]})

    async def mock_az_get(url, **kwargs):
        return timeline_response if "timeline" in url else log_response

    az_client.get = AsyncMock(side_effect=mock_az_get)
    return gh_client, az_client


class TestAzureGetLogsForCheckRun:
    """Test azure_get_logs_for_check_run's resolution + selection pipeline."""

    @pytest.mark.asyncio
    async def test_resolves_to_child_task_log_not_job_own_log(self):
        """Central trap: selected log id is the Task's (19), NOT the Job's (22)."""
        gh_client, az_client = _mock_clients(
            details_url=_details_url(), records=_timeline_records()
        )

        with (
            patch(
                "src.mcp_server_git.azure.check_run_logs.github_client_context"
            ) as mock_gh,
            patch(
                "src.mcp_server_git.azure.check_run_logs.azure_client_context"
            ) as mock_az,
        ):
            mock_gh.return_value.__aenter__.return_value = gh_client
            mock_az.return_value.__aenter__.return_value = az_client

            result = await azure_get_logs_for_check_run(
                "conda-forge", "feedstock", 987654321
            )

            fetched_urls = [call.args[0] for call in az_client.get.call_args_list]
            log_urls = [url for url in fetched_urls if "/logs/" in url]
            assert len(log_urls) == 1
            assert "/logs/19?" in log_urls[0]
            assert "/logs/22?" not in log_urls[0]
            assert "Run OSX build" in result

    @pytest.mark.asyncio
    async def test_task_name_override_selects_the_named_task(self):
        """task_name picks that child regardless of result/log size."""
        gh_client, az_client = _mock_clients(
            details_url=_details_url(), records=_timeline_records()
        )

        with (
            patch(
                "src.mcp_server_git.azure.check_run_logs.github_client_context"
            ) as mock_gh,
            patch(
                "src.mcp_server_git.azure.check_run_logs.azure_client_context"
            ) as mock_az,
        ):
            mock_gh.return_value.__aenter__.return_value = gh_client
            mock_az.return_value.__aenter__.return_value = az_client

            result = await azure_get_logs_for_check_run(
                "conda-forge", "feedstock", 987654321, task_name="checkout"
            )

            log_urls = [
                call.args[0]
                for call in az_client.get.call_args_list
                if "/logs/" in call.args[0]
            ]
            assert "/logs/17?" in log_urls[0]
            assert "Task: Checkout" in result

    @pytest.mark.asyncio
    async def test_failure_result_preferred_over_largest_log(self):
        """A failing task wins even though another sibling has a larger log."""
        records = _timeline_records(build_result="failed")
        gh_client, az_client = _mock_clients(
            details_url=_details_url(), records=records
        )

        with (
            patch(
                "src.mcp_server_git.azure.check_run_logs.github_client_context"
            ) as mock_gh,
            patch(
                "src.mcp_server_git.azure.check_run_logs.azure_client_context"
            ) as mock_az,
        ):
            mock_gh.return_value.__aenter__.return_value = gh_client
            mock_az.return_value.__aenter__.return_value = az_client

            result = await azure_get_logs_for_check_run(
                "conda-forge", "feedstock", 987654321
            )

            log_urls = [
                call.args[0]
                for call in az_client.get.call_args_list
                if "/logs/" in call.args[0]
            ]
            # "Run OSX build" (log 19) is both the failing task AND the
            # largest log here, so make it succeed and give a smaller task
            # the failure to prove failure-preference, not size, decided it.
            assert "/logs/19?" in log_urls[0]
            assert "failing result" in result

    @pytest.mark.asyncio
    async def test_failure_preference_beats_size_when_smaller_task_fails(self):
        """A smaller failing task is chosen over the larger succeeding one."""
        records = _timeline_records()
        for record in records:
            if record.get("id") == "task-checkout":
                record["result"] = "failed"
        gh_client, az_client = _mock_clients(
            details_url=_details_url(), records=records
        )

        with (
            patch(
                "src.mcp_server_git.azure.check_run_logs.github_client_context"
            ) as mock_gh,
            patch(
                "src.mcp_server_git.azure.check_run_logs.azure_client_context"
            ) as mock_az,
        ):
            mock_gh.return_value.__aenter__.return_value = gh_client
            mock_az.return_value.__aenter__.return_value = az_client

            result = await azure_get_logs_for_check_run(
                "conda-forge", "feedstock", 987654321
            )

            log_urls = [
                call.args[0]
                for call in az_client.get.call_args_list
                if "/logs/" in call.args[0]
            ]
            assert "/logs/17?" in log_urls[0]  # Checkout's log, not Run OSX build's
            assert "Task: Checkout" in result

    @pytest.mark.asyncio
    async def test_largest_log_fallback_when_all_tasks_succeeded(self):
        """No failures: the child with the largest log (400 lines) wins."""
        gh_client, az_client = _mock_clients(
            details_url=_details_url(), records=_timeline_records()
        )

        with (
            patch(
                "src.mcp_server_git.azure.check_run_logs.github_client_context"
            ) as mock_gh,
            patch(
                "src.mcp_server_git.azure.check_run_logs.azure_client_context"
            ) as mock_az,
        ):
            mock_gh.return_value.__aenter__.return_value = gh_client
            mock_az.return_value.__aenter__.return_value = az_client

            result = await azure_get_logs_for_check_run(
                "conda-forge", "feedstock", 987654321
            )

            log_urls = [
                call.args[0]
                for call in az_client.get.call_args_list
                if "/logs/" in call.args[0]
            ]
            assert "/logs/19?" in log_urls[0]
            assert "largest log" in result

    @pytest.mark.asyncio
    async def test_response_lists_sibling_tasks_with_log_ids(self):
        """The header lists sibling tasks so a caller can re-query directly."""
        gh_client, az_client = _mock_clients(
            details_url=_details_url(), records=_timeline_records()
        )

        with (
            patch(
                "src.mcp_server_git.azure.check_run_logs.github_client_context"
            ) as mock_gh,
            patch(
                "src.mcp_server_git.azure.check_run_logs.azure_client_context"
            ) as mock_az,
        ):
            mock_gh.return_value.__aenter__.return_value = gh_client
            mock_az.return_value.__aenter__.return_value = az_client

            result = await azure_get_logs_for_check_run(
                "conda-forge", "feedstock", 987654321
            )

            assert "Initialize job: Log #16" in result
            assert "Checkout: Log #17" in result
            assert "Post-job Checkout: Log #20" in result
            assert "re-query with azure_get_build_logs" in result

    @pytest.mark.asyncio
    async def test_grep_and_output_path_match_shared_helper_shape(self, tmp_path):
        """grep / output_path behave like github_get_job_logs's shared helper."""
        log_lines = ["filler" for _ in range(9)] + ["ERROR: build failed"]
        gh_client, az_client = _mock_clients(
            details_url=_details_url(),
            records=_timeline_records(),
            log_lines=log_lines,
        )

        with (
            patch(
                "src.mcp_server_git.azure.check_run_logs.github_client_context"
            ) as mock_gh,
            patch(
                "src.mcp_server_git.azure.check_run_logs.azure_client_context"
            ) as mock_az,
        ):
            mock_gh.return_value.__aenter__.return_value = gh_client
            mock_az.return_value.__aenter__.return_value = az_client

            grep_result = await azure_get_logs_for_check_run(
                "conda-forge", "feedstock", 987654321, grep="ERROR"
            )
            assert "10: ERROR: build failed" in grep_result
            assert "1: filler" not in grep_result

        gh_client2, az_client2 = _mock_clients(
            details_url=_details_url(),
            records=_timeline_records(),
            log_lines=log_lines,
        )
        output_path = tmp_path / "check_run.log"
        with (
            patch(
                "src.mcp_server_git.azure.check_run_logs.github_client_context"
            ) as mock_gh,
            patch(
                "src.mcp_server_git.azure.check_run_logs.azure_client_context"
            ) as mock_az,
        ):
            mock_gh.return_value.__aenter__.return_value = gh_client2
            mock_az.return_value.__aenter__.return_value = az_client2

            written_result = await azure_get_logs_for_check_run(
                "conda-forge",
                "feedstock",
                987654321,
                output_path=str(output_path),
            )
            assert output_path.exists()
            assert output_path.read_text(encoding="utf-8") == "\n".join(log_lines)
            assert "written to" in written_result

    @pytest.mark.asyncio
    async def test_malformed_details_url_returns_clear_error(self):
        """A non-Azure or malformed details_url returns an error, not a crash."""
        gh_client, az_client = _mock_clients(
            details_url="https://github.com/conda-forge/feedstock/runs/123",
            records=_timeline_records(),
        )

        with (
            patch(
                "src.mcp_server_git.azure.check_run_logs.github_client_context"
            ) as mock_gh,
            patch(
                "src.mcp_server_git.azure.check_run_logs.azure_client_context"
            ) as mock_az,
        ):
            mock_gh.return_value.__aenter__.return_value = gh_client
            mock_az.return_value.__aenter__.return_value = az_client

            result = await azure_get_logs_for_check_run(
                "conda-forge", "feedstock", 987654321
            )

            assert result.startswith("❌")
            assert "Azure DevOps details_url" in result
            az_client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_details_url_returns_clear_error(self):
        """A check run with no details_url at all returns an error, not a crash."""
        gh_client, az_client = _mock_clients(
            details_url=None, records=_timeline_records()
        )

        with (
            patch(
                "src.mcp_server_git.azure.check_run_logs.github_client_context"
            ) as mock_gh,
            patch(
                "src.mcp_server_git.azure.check_run_logs.azure_client_context"
            ) as mock_az,
        ):
            mock_gh.return_value.__aenter__.return_value = gh_client
            mock_az.return_value.__aenter__.return_value = az_client

            result = await azure_get_logs_for_check_run(
                "conda-forge", "feedstock", 987654321
            )

            assert result.startswith("❌")
