"""Azure DevOps API operations for MCP Git Server

azure_get_logs_for_check_run lives in check_run_logs.py (kept separate to
stay under the file-size policy); shared log fetch/render helpers used by
both modules live in log_rendering.py.
"""

import logging
from contextlib import asynccontextmanager

from .client import get_azure_client
from .log_rendering import (
    FAILURE_RESULTS,
    fetch_and_render_log,
    fetch_timeline,
    render_log_index,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def azure_client_context():
    """Async context manager for Azure DevOps client with guaranteed
    resource cleanup.

    The client works in anonymous mode when AZURE_DEVOPS_TOKEN is unset,
    allowing read-only access to public projects (e.g. conda-forge).
    get_azure_client() returns None only if the org cannot be determined,
    which is now extremely unlikely given the conda-forge default.
    """
    client = None
    try:
        client = get_azure_client()
        if client is None:
            # This should only happen if _DEFAULT_ORG is somehow falsy.
            raise ValueError(
                "Azure DevOps client could not be created. "
                "Set AZURE_DEVOPS_ORG environment variable."
            )
        yield client
    finally:
        if client and client.session:
            try:
                await client.session.close()
            except Exception as cleanup_error:
                logger.warning(f"Error during Azure client cleanup: {cleanup_error}")


async def azure_get_build_status(project: str, build_id: int) -> str:
    """Get status of an Azure DevOps build/pipeline run

    Args:
        project: The project name or ID
        build_id: The build ID

    Returns:
        Formatted string with build status information
    """
    try:
        async with azure_client_context() as client:
            # Get build details
            # API: GET https://dev.azure.com/{organization}/{project}/_apis/build/builds/{buildId}?api-version=7.1
            response = await client.get(
                f"{project}/_apis/build/builds/{build_id}?api-version=7.1"
            )

            if response.status != 200:
                error_text = await response.text()
                return (
                    f"❌ Failed to get build #{build_id}: "
                    f"{response.status} - {error_text}"
                )

            build_data = await response.json()

            # Format the output
            output = [f"Azure DevOps Build #{build_id} ({project}):\n"]
            definition_name = build_data.get("definition", {}).get("name", "N/A")
            output.append(f"Definition: {definition_name}")
            output.append(f"Status: {build_data.get('status', 'N/A')}")
            output.append(f"Result: {build_data.get('result', 'N/A')}")
            source_branch = build_data.get("sourceBranch", "N/A")
            output.append(f"Source Branch: {source_branch}")
            source_version = build_data.get("sourceVersion", "N/A")[:8]
            output.append(f"Source Version: {source_version}")

            if build_data.get("queueTime"):
                output.append(f"Queued: {build_data['queueTime']}")
            if build_data.get("startTime"):
                output.append(f"Started: {build_data['startTime']}")
            if build_data.get("finishTime"):
                output.append(f"Finished: {build_data['finishTime']}")

            if build_data.get("requestedFor"):
                requester = build_data["requestedFor"]
                output.append(f"Requested By: {requester.get('displayName', 'N/A')}")

            if build_data.get("_links", {}).get("web", {}).get("href"):
                output.append(f"\nURL: {build_data['_links']['web']['href']}")

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error getting build status: {auth_error}")
        return f"❌ {str(auth_error)}"
    except Exception as e:
        logger.error(
            f"Error getting build status for build #{build_id}: {e}", exc_info=True
        )
        return f"❌ Error getting build status: {str(e)}"


async def azure_get_build_logs(
    project: str,
    build_id: int,
    log_id: int | None = None,
    tail_lines: int | None = None,
    full_log: bool = False,
    head_lines: int | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
    grep: str | None = None,
    context_lines: int = 0,
    ignore_case: bool = False,
    output_path: str | None = None,
) -> str:
    """Get logs from an Azure DevOps build

    If log_id is None, lists all logs for the build with joined
    "<Job name> / <Task name>" labels. Otherwise fetches that log's content,
    with the same selection/output knobs as github_get_job_logs: by default
    the last 500 lines are returned; head_lines, start_line/end_line, grep,
    context_lines, ignore_case, full_log, and output_path all work exactly
    as they do there (only one of head_lines/tail_lines/start_line+end_line
    may be given; grep composes with any of them and searches the whole log
    by default).

    Args:
        project: The project name or ID
        build_id: The build ID
        log_id: Optional specific log ID to retrieve. If None, lists all logs.
        tail_lines: Return only last N lines (default: 500 for LLM efficiency)
        full_log: If True, return complete log without line limit (still has
            100KB char limit unless output_path is given)
        head_lines: Return only first N lines, reaching the start of the log
        start_line: 1-indexed inclusive start of an explicit window
        end_line: 1-indexed inclusive end of an explicit window
        grep: Regex; return only matching lines. Searches the whole log by
            default, not just the last 500 lines
        context_lines: Lines of context to keep either side of a grep match
        ignore_case: Case-insensitive grep
        output_path: Absolute path to write the complete log to disk instead
            of returning it inline; the response then carries only metadata

    Returns:
        Formatted string with log information or content
    """
    try:
        async with azure_client_context() as client:
            if log_id is None:
                # List all logs for the build
                # API: GET https://dev.azure.com/{organization}/{project}/_apis/build/builds/{buildId}/logs?api-version=7.1
                response = await client.get(
                    f"{project}/_apis/build/builds/{build_id}/logs?api-version=7.1"
                )

                if response.status != 200:
                    error_text = await response.text()
                    return (
                        f"❌ Failed to get build logs: {response.status} - {error_text}"
                    )

                logs_data = await response.json()
                logs = logs_data.get("value", [])

                if not logs:
                    return f"No logs found for build #{build_id}"

                # Join in job/task names from the timeline (best effort: a
                # timeline fetch failure degrades to plain "Container" labels
                # rather than failing the whole listing).
                records, _timeline_error = await fetch_timeline(
                    client, project, build_id
                )
                return render_log_index(build_id, logs, records)

            # Get specific log content.
            # API: GET https://dev.azure.com/{organization}/{project}/_apis/build/builds/{buildId}/logs/{logId}?api-version=7.1
            return await fetch_and_render_log(
                client,
                project,
                build_id,
                log_id,
                [f"Log #{log_id} for Build #{build_id}:\n"],
                tail_lines=tail_lines,
                full_log=full_log,
                head_lines=head_lines,
                start_line=start_line,
                end_line=end_line,
                grep=grep,
                context_lines=context_lines,
                ignore_case=ignore_case,
                output_path=output_path,
            )

    except ValueError as auth_error:
        logger.error(f"Authentication error getting build logs: {auth_error}")
        return f"❌ {str(auth_error)}"
    except Exception as e:
        logger.error(
            f"Error getting build logs for build #{build_id}: {e}", exc_info=True
        )
        return f"❌ Error getting build logs: {str(e)}"


async def azure_get_failing_jobs(
    project: str, build_id: int, include_logs: bool = True, log_tail_lines: int = 500
) -> str:
    """Get detailed information about failing jobs in a build

    Args:
        project: The project name or ID
        build_id: The build ID
        include_logs: Whether to include log excerpts from failing jobs
        log_tail_lines: Number of lines to include from each log (default: 500)

    Returns:
        Formatted string with failing job information
    """
    try:
        async with azure_client_context() as client:
            # First get build status to check if it failed
            build_response = await client.get(
                f"{project}/_apis/build/builds/{build_id}?api-version=7.1"
            )

            if build_response.status != 200:
                error_text = await build_response.text()
                return (
                    f"❌ Failed to get build #{build_id}: "
                    f"{build_response.status} - {error_text}"
                )

            build_data = await build_response.json()

            result = build_data.get("result", "N/A")
            if result not in ["failed", "partiallySucceeded", "canceled"]:
                return (
                    f"Build #{build_id} has result '{result}' - no failures to report"
                )

            # Get timeline data which contains job information
            records, timeline_error = await fetch_timeline(client, project, build_id)
            if timeline_error is not None:
                return timeline_error

            # Filter for failed jobs/tasks
            failed_records = [
                record
                for record in records
                if record.get("result") in FAILURE_RESULTS
                and record.get("type") in ["Job", "Task", "Phase"]
            ]

            if not failed_records:
                return f"No failed jobs found for build #{build_id}"

            output = [f"Failed Jobs for Build #{build_id}:\n"]

            for record in failed_records:
                record_type = record.get("type", "Unknown")
                status_emoji = {"failed": "❌", "canceled": "🚫", "abandoned": "⚠️"}.get(
                    record.get("result", ""), "❓"
                )

                record_name = record.get("name", "N/A")
                output.append(f"{status_emoji} {record_type}: {record_name}")
                output.append(f"   Result: {record.get('result', 'N/A')}")
                output.append(f"   State: {record.get('state', 'N/A')}")

                if record.get("startTime"):
                    output.append(f"   Started: {record['startTime']}")
                if record.get("finishTime"):
                    output.append(f"   Finished: {record['finishTime']}")

                # Get error messages from issues
                if record.get("issues"):
                    output.append("   Issues:")
                    for issue in record["issues"][:5]:  # Limit to 5 issues
                        issue_type = issue.get("type", "unknown")
                        message = issue.get("message", "No message")
                        output.append(f"     [{issue_type}] {message}")

                # Include log excerpt if requested.
                # Use `record.get("log") or {}`: the log key may be present but
                # explicitly null, in which case `.get("log", {})` returns None
                # and `.get("id")` would raise 'NoneType' object has no attribute 'get'.
                if include_logs and (record.get("log") or {}).get("id"):
                    log_id = record["log"]["id"]
                    try:
                        log_response = await client.get(
                            f"{project}/_apis/build/builds/{build_id}/logs/{log_id}?api-version=7.1",
                            accept="text/plain",
                        )
                        if log_response.status == 200:
                            # Azure DevOps returns log content as JSON with a "value" array
                            content_type = log_response.headers.get("Content-Type", "")
                            if "application/json" in content_type:
                                log_data = await log_response.json()
                                if isinstance(log_data, dict) and "value" in log_data:
                                    log_lines = log_data["value"]
                                elif isinstance(log_data, list):
                                    log_lines = log_data
                                else:
                                    log_lines = [str(log_data)]
                            else:
                                # Plain text response
                                log_text = await log_response.text()
                                log_lines = log_text.split("\n")

                            # Get last N lines
                            original_line_count = len(log_lines)
                            if len(log_lines) > log_tail_lines:
                                truncated_count = original_line_count - log_tail_lines
                                excerpt_lines = log_lines[-log_tail_lines:]
                                output.append(
                                    f"   Log excerpt (showing last {log_tail_lines} of {original_line_count} lines):"
                                )
                                output.append(
                                    f"   ... [truncated {truncated_count} lines] ..."
                                )
                            else:
                                excerpt_lines = log_lines
                                output.append(
                                    f"   Log excerpt ({original_line_count} lines):"
                                )
                            output.append("   ```")
                            # Indent each line
                            for line in excerpt_lines:
                                output.append(f"   {line}")
                            output.append("   ```")
                    except Exception as log_error:
                        logger.warning(f"Failed to get log {log_id}: {log_error}")

                output.append("")  # Empty line between records

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error getting failing jobs: {auth_error}")
        return f"❌ {str(auth_error)}"
    except Exception as e:
        logger.error(
            f"Error getting failing jobs for build #{build_id}: {e}", exc_info=True
        )
        return f"❌ Error getting failing jobs: {str(e)}"
