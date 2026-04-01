"""GitHub Actions workflow operations."""
from __future__ import annotations
import asyncio
import json
import logging
import time
from datetime import datetime
from mcp_server_git.github.client import github_client_context
logger = logging.getLogger(__name__)


async def github_get_workflow_run(
    repo_owner: str, repo_name: str, run_id: int, include_logs: bool = False
) -> str:
    """Get detailed workflow run information"""
    try:
        async with github_client_context() as client:
            # Get workflow run details
            run_response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/actions/runs/{run_id}"
            )
            if run_response.status != 200:
                return f"❌ Failed to get workflow run #{run_id}: {run_response.status}"

            run_data = await run_response.json()

            output = [f"Workflow Run #{run_id}:\n"]
            output.append(f"Name: {run_data.get('name', 'N/A')}")
            output.append(f"Status: {run_data.get('status', 'N/A')}")
            output.append(f"Conclusion: {run_data.get('conclusion', 'N/A')}")
            output.append(f"Branch: {run_data.get('head_branch', 'N/A')}")
            output.append(f"Commit: {run_data.get('head_sha', 'N/A')[:8]}")
            output.append(f"Started: {run_data.get('created_at', 'N/A')}")
            output.append(f"Updated: {run_data.get('updated_at', 'N/A')}")

            if run_data.get("html_url"):
                output.append(f"URL: {run_data['html_url']}")

            # Get jobs if available
            jobs_response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/actions/runs/{run_id}/jobs"
            )
            if jobs_response.status == 200:
                jobs_data = await jobs_response.json()
                jobs = jobs_data.get("jobs", [])

                if jobs:
                    output.append("\nJobs:")
                    for job in jobs:
                        status_emoji = {
                            "completed": "✅"
                            if job.get("conclusion") == "success"
                            else "❌",
                            "in_progress": "🔄",
                            "queued": "⏳",
                        }.get(job["status"], "❓")

                        output.append(f"  {status_emoji} {job['name']}")
                        output.append(f"    Status: {job['status']}")
                        if job.get("conclusion"):
                            output.append(f"    Conclusion: {job['conclusion']}")

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error getting workflow run: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error getting workflow run: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error getting workflow run #{run_id}: {e}", exc_info=True
        )
        return f"❌ Error getting workflow run: {str(e)}"


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


async def github_list_workflow_runs(
    repo_owner: str,
    repo_name: str,
    workflow_id: str | None = None,
    actor: str | None = None,
    branch: str | None = None,
    event: str | None = None,
    status: str | None = None,
    conclusion: str | None = None,
    per_page: int = 30,
    page: int = 1,
    created: str | None = None,
    exclude_pull_requests: bool = False,
    check_suite_id: int | None = None,
    head_sha: str | None = None,
) -> str:
    """List workflow runs for a repository with comprehensive filtering options.

    This provides essential CI/CD monitoring capabilities for GitHub Actions workflows.

    Args:
        repo_owner: Repository owner/organization
        repo_name: Repository name
        workflow_id: Filter by specific workflow ID or filename (e.g., "ci.yml")
        actor: Filter by GitHub username who triggered the run
        branch: Filter by branch name
        event: Filter by event type (push, pull_request, schedule, etc.)
        status: Filter by run status (queued, in_progress, completed)
        conclusion: Filter by conclusion (success, failure, neutral, cancelled, timed_out, action_required, stale)
        per_page: Number of results per page (1-100, default: 30)
        page: Page number to retrieve (default: 1)
        created: Filter by creation date (ISO 8601 format or relative like >2023-01-01)
        exclude_pull_requests: If true, exclude workflow runs triggered by pull requests
        check_suite_id: Filter by specific check suite ID
        head_sha: Filter by specific commit SHA

    Returns:
        Formatted string with workflow run information including status, conclusion,
        timing, and links for CI/CD monitoring and debugging.
    """
    logger.debug(f"🔍 Listing workflow runs for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            # Build query parameters with validation
            params: dict[str, str | int | bool] = {
                "per_page": min(max(per_page, 1), 100),  # Enforce GitHub API limits
                "page": max(page, 1),
            }

            # Add optional filters
            if actor:
                params["actor"] = actor
            if branch:
                params["branch"] = branch
            if event:
                params["event"] = event
            if status and status in ["queued", "in_progress", "completed"]:
                params["status"] = status
            if conclusion and conclusion in [
                "success",
                "failure",
                "neutral",
                "cancelled",
                "timed_out",
                "action_required",
                "stale",
            ]:
                params["conclusion"] = conclusion
            if created:
                params["created"] = created
            if exclude_pull_requests:
                params["exclude_pull_requests"] = "true"
            if check_suite_id:
                params["check_suite_id"] = check_suite_id
            if head_sha:
                params["head_sha"] = head_sha

            # Determine API endpoint - workflow-specific or repository-wide
            if workflow_id:
                # Get runs for specific workflow
                endpoint = f"/repos/{repo_owner}/{repo_name}/actions/workflows/{workflow_id}/runs"
                logger.debug(f"📡 Fetching workflow-specific runs: {workflow_id}")
            else:
                # Get all workflow runs for repository
                endpoint = f"/repos/{repo_owner}/{repo_name}/actions/runs"
                logger.debug("📡 Fetching all repository workflow runs")

            logger.debug(f"📡 Making API call to {endpoint} with params: {params}")

            response = await client.get(endpoint, params=params)

            logger.debug(f"📨 GitHub API response status: {response.status}")

            if response.status == 401:
                response_text = await response.text()
                logger.error(
                    f"🔒 GitHub API authentication failed (401): {response_text}"
                )
                return "❌ GitHub API authentication failed: Verify your GITHUB_TOKEN has Actions read permissions"
            elif response.status == 404:
                if workflow_id:
                    return f"❌ Workflow '{workflow_id}' not found in {repo_owner}/{repo_name}. Check workflow file name or ID."
                else:
                    return f"❌ Repository {repo_owner}/{repo_name} not found or Actions not enabled"
            elif response.status != 200:
                response_text = await response.text()
                logger.error(f"❌ GitHub API error {response.status}: {response_text}")
                return f"❌ Failed to list workflow runs: {response.status} - {response_text}"

            data = await response.json()
            workflow_runs = data.get("workflow_runs", [])

            if not workflow_runs:
                filter_desc = (
                    f" (filtered by: {', '.join(f'{k}={v}' for k, v in params.items() if k not in ['per_page', 'page'])})"
                    if len(params) > 2
                    else ""
                )
                return (
                    f"No workflow runs found for {repo_owner}/{repo_name}{filter_desc}"
                )

            # Build formatted output
            filter_info = []
            if workflow_id:
                filter_info.append(f"workflow: {workflow_id}")
            if actor:
                filter_info.append(f"actor: {actor}")
            if branch:
                filter_info.append(f"branch: {branch}")
            if event:
                filter_info.append(f"event: {event}")
            if status:
                filter_info.append(f"status: {status}")
            if conclusion:
                filter_info.append(f"conclusion: {conclusion}")

            header = f"Workflow Runs for {repo_owner}/{repo_name}"
            if filter_info:
                header += f" ({', '.join(filter_info)})"

            output = [f"{header}:\n"]

            # Add summary statistics
            total_count = data.get("total_count", len(workflow_runs))
            if total_count > len(workflow_runs):
                output.append(
                    f"Showing {len(workflow_runs)} of {total_count} total runs (page {page})\n"
                )

            # Group runs by status for quick overview
            status_counts = {}
            for run in workflow_runs:
                run_status = run.get("status", "unknown")
                status_counts[run_status] = status_counts.get(run_status, 0) + 1

            if len(status_counts) > 1:
                status_summary = ", ".join(
                    [f"{status}: {count}" for status, count in status_counts.items()]
                )
                output.append(f"Status summary: {status_summary}\n")

            # Format individual workflow runs
            for run in workflow_runs:
                # Status and conclusion emojis
                status_emoji = {
                    "completed": "✅" if run.get("conclusion") == "success" else "❌",
                    "in_progress": "🔄",
                    "queued": "⏳",
                    "requested": "📋",
                    "waiting": "⏸️",
                }.get(run.get("status"), "❓")

                # Enhanced status display
                status_text = run.get("status", "unknown")
                if run.get("conclusion"):
                    status_text += f" ({run['conclusion']})"

                # Workflow name and run number
                workflow_name = run.get("name", "Unknown Workflow")
                run_number = run.get("run_number", "?")

                output.append(f"{status_emoji} {workflow_name} #{run_number}")
                output.append(f"   ID: {run.get('id', 'N/A')}")
                output.append(f"   Status: {status_text}")
                output.append(f"   Branch: {run.get('head_branch', 'N/A')}")
                output.append(f"   Commit: {run.get('head_sha', 'N/A')[:8]}...")
                output.append(f"   Actor: {run.get('actor', {}).get('login', 'N/A')}")
                output.append(f"   Event: {run.get('event', 'N/A')}")

                # Timing information
                created_at = run.get("created_at", "N/A")
                updated_at = run.get("updated_at", "N/A")
                if created_at != "N/A":
                    output.append(f"   Started: {created_at}")
                if updated_at != "N/A" and updated_at != created_at:
                    output.append(f"   Updated: {updated_at}")

                # Duration calculation for completed runs
                if (
                    run.get("status") == "completed"
                    and run.get("created_at")
                    and run.get("updated_at")
                ):
                    try:
                        from datetime import datetime

                        start = datetime.fromisoformat(
                            run["created_at"].replace("Z", "+00:00")
                        )
                        end = datetime.fromisoformat(
                            run["updated_at"].replace("Z", "+00:00")
                        )
                        duration = end - start
                        output.append(f"   Duration: {duration}")
                    except Exception:
                        pass  # Skip duration calculation if parsing fails

                # Links for further investigation
                if run.get("html_url"):
                    output.append(f"   URL: {run['html_url']}")

                output.append("")

            # Add pagination info if applicable
            if total_count > len(workflow_runs):
                max_page = (total_count + per_page - 1) // per_page
                output.append(
                    f"📄 Page {page} of {max_page} (use page parameter to see more)"
                )

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error listing workflow runs: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error listing workflow runs: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error listing workflow runs: {e}", exc_info=True)
        return f"❌ Error listing workflow runs: {str(e)}"


# Constants for job logs processing - LLM-friendly defaults
_JOB_LOGS_MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB hard limit (memory protection)
_JOB_LOGS_DEFAULT_TAIL_LINES = 500  # Default lines for LLM context efficiency
_JOB_LOGS_MAX_CHARS_FOR_LLM = 100 * 1024  # 100 KB soft limit (~25k tokens)
_JOB_LOGS_SEPARATOR_LENGTH = 60


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
