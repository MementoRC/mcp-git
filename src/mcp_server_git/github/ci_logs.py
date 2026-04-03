"""GitHub Actions CI logs and workflow completion monitoring."""
from __future__ import annotations
import asyncio
import json
import logging
import time
from datetime import datetime
from mcp_server_git.github.client import github_client_context
logger = logging.getLogger(__name__)

# Constants for job logs processing - LLM-friendly defaults
_JOB_LOGS_MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB hard limit (memory protection)
_JOB_LOGS_DEFAULT_TAIL_LINES = 500  # Default lines for LLM context efficiency
_JOB_LOGS_MAX_CHARS_FOR_LLM = 100 * 1024  # 100 KB soft limit (~25k tokens)
_JOB_LOGS_SEPARATOR_LENGTH = 60


async def github_await_workflow_completion(
    repo_owner: str,
    repo_name: str,
    run_id: int | None = None,
    timeout_minutes: int = 15,
    poll_interval_seconds: int = 20,
) -> str:
    """Monitor a GitHub Actions workflow run until completion.

    This tool allows Claude Code to wait for CI runs to complete, enabling
    automated CI response workflows. When a workflow run fails, it automatically
    fetches failure details.

    Args:
        repo_owner: Repository owner/organization
        repo_name: Repository name
        run_id: Specific workflow run ID to monitor. If None, monitors the latest run.
        timeout_minutes: Maximum time to wait in minutes (default: 15)
        poll_interval_seconds: Time between status checks in seconds (default: 20)

    Returns:
        JSON-formatted string with workflow run results including:
        - status: "success", "failure", or "timeout"
        - conclusion: GitHub's conclusion value
        - run_id: The workflow run ID that was monitored
        - run_url: Direct link to the workflow run
        - duration_seconds: How long the run took
        - failed_jobs: List of jobs that failed (if any)
        - logs_note: URL to view detailed logs (for failed runs)
    """
    logger.debug(
        f"Awaiting workflow completion for {repo_owner}/{repo_name}, run_id={run_id}"
    )

    try:
        async with github_client_context() as client:
            # If no run_id provided, get the latest run
            if run_id is None:
                logger.debug("No run_id provided, fetching latest workflow run...")
                response = await client.get(
                    f"/repos/{repo_owner}/{repo_name}/actions/runs",
                    params={"per_page": 1},
                )

                if response.status != 200:
                    error_text = await response.text()
                    return f"Failed to get latest workflow run: {response.status} - {error_text}"

                data = await response.json()
                workflow_runs = data.get("workflow_runs", [])

                if not workflow_runs:
                    return f"No workflow runs found for {repo_owner}/{repo_name}"

                # Safely extract run_id
                run_id = workflow_runs[0].get("id")
                if run_id is None:
                    return "Latest workflow run has no ID"

                logger.info(f"Using latest workflow run ID: {run_id}")

            # Start polling
            start_time = time.time()
            timeout_seconds = timeout_minutes * 60
            poll_count = 0

            logger.info(
                f"Starting to monitor run #{run_id} (timeout: {timeout_minutes}m, poll interval: {poll_interval_seconds}s)"
            )

            while True:
                poll_count += 1
                elapsed_time = time.time() - start_time

                # Check for timeout
                if elapsed_time >= timeout_seconds:
                    # Cleanup any pending operations before timeout
                    logger.info(
                        f"Cleaning up resources after {elapsed_time:.1f}s of monitoring"
                    )
                    logger.warning(
                        f"Timeout reached after {elapsed_time:.1f}s ({poll_count} polls)"
                    )
                    timeout_result = {
                        "status": "timeout",
                        "run_id": run_id,
                        "run_url": f"https://github.com/{repo_owner}/{repo_name}/actions/runs/{run_id}",
                        "elapsed_seconds": elapsed_time,
                        "message": f"Workflow run did not complete within {timeout_minutes} minutes. Consider increasing timeout_minutes for very long-running workflows (max: 350 minutes).",
                        "polls_performed": poll_count,
                    }
                    return json.dumps(timeout_result, indent=2)

                # Get workflow run status
                logger.debug(f"Poll #{poll_count}: Fetching run status...")
                run_response = await client.get(
                    f"/repos/{repo_owner}/{repo_name}/actions/runs/{run_id}"
                )

                if run_response.status != 200:
                    error_text = await run_response.text()
                    return f"Failed to get workflow run #{run_id}: {run_response.status} - {error_text}"

                run_data = await run_response.json()
                run_status = run_data.get("status")
                run_conclusion = run_data.get("conclusion")

                logger.debug(
                    f"Poll #{poll_count}: status={run_status}, conclusion={run_conclusion}"
                )

                # Check if run is complete
                if run_status == "completed":
                    logger.info(
                        f"Workflow run completed with conclusion: {run_conclusion}"
                    )

                    # Calculate duration
                    created_at = run_data.get("created_at")
                    updated_at = run_data.get("updated_at")
                    duration_seconds = 0

                    if created_at and updated_at:
                        try:
                            start_dt = datetime.fromisoformat(
                                created_at.replace("Z", "+00:00")
                            )
                            end_dt = datetime.fromisoformat(
                                updated_at.replace("Z", "+00:00")
                            )
                            duration_seconds = (end_dt - start_dt).total_seconds()
                        except Exception as e:
                            logger.debug(f"Could not calculate duration: {e}")

                    # Prepare basic response
                    result = {
                        "status": "success"
                        if run_conclusion == "success"
                        else "failure",
                        "conclusion": run_conclusion,
                        "run_id": run_id,
                        "run_url": run_data.get("html_url"),
                        "duration_seconds": duration_seconds,
                        "workflow_name": run_data.get("name"),
                        "head_branch": run_data.get("head_branch"),
                        "head_sha": run_data.get("head_sha", "")[:8],
                    }

                    # If run failed, get failed jobs and logs
                    if run_conclusion != "success":
                        logger.debug("Fetching failed jobs...")
                        jobs_response = await client.get(
                            f"/repos/{repo_owner}/{repo_name}/actions/runs/{run_id}/jobs"
                        )

                        if jobs_response.status == 200:
                            jobs_data = await jobs_response.json()
                            failed_jobs = []

                            for job in jobs_data.get("jobs", []):
                                if (
                                    job.get("status") == "completed"
                                    and job.get("conclusion") != "success"
                                ):
                                    failed_job_info = {
                                        "name": job.get("name"),
                                        "conclusion": job.get("conclusion"),
                                        "html_url": job.get("html_url"),
                                    }

                                    # Get failed steps
                                    failed_steps = [
                                        step["name"]
                                        for step in job.get("steps", [])
                                        if step.get("conclusion") == "failure"
                                    ]
                                    if failed_steps:
                                        failed_job_info["failed_steps"] = failed_steps

                                    failed_jobs.append(failed_job_info)

                            result["failed_jobs"] = failed_jobs

                            # Try to get logs summary (truncated)
                            jobs_list = jobs_data.get("jobs", [])
                            if failed_jobs and len(jobs_list) > 0:
                                logger.debug("Fetching failure logs summary...")
                                # Get logs for first job in the list
                                first_job = jobs_list[0]
                                if first_job.get("id"):
                                    try:
                                        # Note: GitHub API doesn't provide direct log text access via REST API
                                        # We'll include a note about where to find logs
                                        result["logs_note"] = (
                                            f"View detailed logs at: {first_job.get('html_url')}"
                                        )
                                    except Exception as log_error:
                                        logger.debug(
                                            f"Could not fetch logs: {log_error}"
                                        )

                    # Return JSON result
                    return json.dumps(result, indent=2)

                # Not complete yet, wait before next poll
                logger.debug(
                    f"Workflow still {run_status}, waiting {poll_interval_seconds}s before next poll..."
                )
                await asyncio.sleep(poll_interval_seconds)

    except ValueError as auth_error:
        logger.error(f"Authentication error awaiting workflow completion: {auth_error}")
        return f"Authentication error: {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error awaiting workflow completion: {conn_error}")
        return f"Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error awaiting workflow completion: {e}", exc_info=True
        )
        return f"Error awaiting workflow completion: {str(e)}"


async def github_get_job_logs(
    repo_owner: str,
    repo_name: str,
    job_id: int,
    tail_lines: int | None = None,
    full_log: bool = False,
) -> str:
    """Get logs for a specific GitHub Actions job.

    Fetches the actual log content for a job, enabling CI failure diagnosis
    without navigating to the GitHub UI. The job_id can be obtained from
    github_get_failing_jobs or github_get_workflow_run output.

    IMPORTANT: By default, logs are truncated to the last 500 lines to be
    LLM-context-friendly. Use tail_lines to adjust or full_log=True for complete logs.

    Args:
        repo_owner: Repository owner/organization
        repo_name: Repository name
        job_id: The job ID (from check runs or workflow jobs)
        tail_lines: Return only last N lines (default: 500 for LLM efficiency)
        full_log: If True, return complete log without line limit (still has 100KB char limit)

    Returns:
        Formatted string with job information and log content.
        Logs are automatically truncated to be LLM-context-friendly.
    """
    logger.debug(f"🔍 Fetching logs for job {job_id} in {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            # First get job details for context
            job_response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/actions/jobs/{job_id}"
            )
            if job_response.status == 404:
                return f"❌ Job #{job_id} not found in {repo_owner}/{repo_name}"
            if job_response.status == 403:
                return f"❌ Access denied for job #{job_id}. Check repository permissions or API rate limits."
            if job_response.status == 429:
                return "❌ GitHub API rate limit exceeded. Please wait and try again."
            if job_response.status != 200:
                return f"❌ Failed to get job #{job_id}: HTTP {job_response.status}"

            job_data = await job_response.json()

            # Build job info header
            output = [f"Job #{job_id} - {job_data.get('name', 'N/A')}:\n"]
            output.append(f"Status: {job_data.get('status', 'N/A')}")
            if job_data.get("conclusion"):
                output.append(f"Conclusion: {job_data['conclusion']}")
            if job_data.get("started_at"):
                output.append(f"Started: {job_data['started_at']}")
            if job_data.get("completed_at"):
                output.append(f"Completed: {job_data['completed_at']}")
            if job_data.get("html_url"):
                output.append(f"URL: {job_data['html_url']}")

            # Fetch the actual logs
            # Note: GitHub API returns logs as plain text, not JSON
            # and may redirect to a download URL
            logs_response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/actions/jobs/{job_id}/logs",
                allow_redirects=True,
            )

            if logs_response.status == 404:
                output.append("\n⚠️ Logs not available (may have been deleted)")
                return "\n".join(output)
            if logs_response.status == 403:
                output.append(
                    "\n❌ Access denied for logs. Check repository permissions."
                )
                return "\n".join(output)
            if logs_response.status == 429:
                output.append("\n❌ GitHub API rate limit exceeded for logs.")
                return "\n".join(output)
            if logs_response.status != 200:
                output.append(f"\n❌ Failed to fetch logs: HTTP {logs_response.status}")
                return "\n".join(output)

            # Get logs as text
            logs_text = await logs_response.text()

            if not logs_text.strip():
                output.append("\n📭 Log content is empty")
                return "\n".join(output)

            # Check for oversized logs and truncate if necessary (memory protection)
            original_size = len(logs_text)
            was_size_truncated = False
            if original_size > _JOB_LOGS_MAX_SIZE_BYTES:
                logs_text = logs_text[-_JOB_LOGS_MAX_SIZE_BYTES:]
                was_size_truncated = True
                logger.warning(
                    f"Job logs truncated from {original_size} to {_JOB_LOGS_MAX_SIZE_BYTES} bytes"
                )

            # Split lines once for efficient processing
            lines = logs_text.splitlines()
            total_lines = len(lines)

            # Apply LLM-friendly truncation
            # Priority: explicit tail_lines > full_log flag > default limit
            effective_tail_lines = tail_lines
            was_line_truncated = False

            if tail_lines is None and not full_log:
                # Apply default LLM-friendly limit
                effective_tail_lines = _JOB_LOGS_DEFAULT_TAIL_LINES

            if (
                effective_tail_lines is not None
                and effective_tail_lines > 0
                and total_lines > effective_tail_lines
            ):
                lines = lines[-effective_tail_lines:]
                was_line_truncated = True
                output.append(
                    f"\n📋 Logs (last {effective_tail_lines} of {total_lines} lines):"
                )
            else:
                output.append(f"\n📋 Logs ({total_lines} lines):")

            # Apply character limit for LLM context efficiency
            logs_output = "\n".join(lines)
            was_char_truncated = False
            if len(logs_output) > _JOB_LOGS_MAX_CHARS_FOR_LLM:
                logs_output = logs_output[-_JOB_LOGS_MAX_CHARS_FOR_LLM:]
                # Find first complete line after truncation
                first_newline = logs_output.find("\n")
                if first_newline > 0:
                    logs_output = logs_output[first_newline + 1 :]
                was_char_truncated = True
                logger.info(
                    f"Job logs char-truncated to {_JOB_LOGS_MAX_CHARS_FOR_LLM} chars for LLM context"
                )

            # Add truncation warnings
            truncation_notes = []
            if was_size_truncated:
                truncation_notes.append(f"size: {original_size:,} bytes")
            if was_line_truncated:
                truncation_notes.append(f"lines: {total_lines} total")
            if was_char_truncated:
                truncation_notes.append("chars: exceeded 100KB limit")

            if truncation_notes:
                output.append(
                    f"⚠️ Truncated for LLM context ({', '.join(truncation_notes)})"
                )

            separator = "-" * _JOB_LOGS_SEPARATOR_LENGTH
            output.append(separator)
            output.append(logs_output)
            output.append(separator)

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error getting job logs: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error getting job logs: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error getting job logs: {e}", exc_info=True)
        return f"❌ Error getting job logs: {str(e)}"
