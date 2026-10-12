"""GitHub Actions workflow listing and status operations."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime

from mcp_server_git.github.client import github_client_context

from .ci_logs import *  # noqa: F401,F403

logger = logging.getLogger(__name__)

_RUN_STATUSES = ("queued", "in_progress", "completed")
_RUN_CONCLUSIONS = (
    "success",
    "failure",
    "neutral",
    "cancelled",
    "timed_out",
    "action_required",
    "stale",
)


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


def _build_run_params(
    per_page: int,
    page: int,
    actor: str | None,
    branch: str | None,
    event: str | None,
    status: str | None,
    conclusion: str | None,
    created: str | None,
    exclude_pull_requests: bool,
    check_suite_id: int | None,
    head_sha: str | None,
) -> dict[str, str | int | bool]:
    """Build the query parameters, dropping falsy and invalid filters."""
    params: dict[str, str | int | bool] = {
        "per_page": min(max(per_page, 1), 100),  # Enforce GitHub API limits
        "page": max(page, 1),
    }
    candidates: dict[str, str | int | None] = {
        "actor": actor,
        "branch": branch,
        "event": event,
        "status": status if status in _RUN_STATUSES else None,
        "conclusion": conclusion if conclusion in _RUN_CONCLUSIONS else None,
        "created": created,
        "exclude_pull_requests": "true" if exclude_pull_requests else None,
        "check_suite_id": check_suite_id,
        "head_sha": head_sha,
    }
    params.update({key: value for key, value in candidates.items() if value})
    return params


def _runs_endpoint(repo_owner: str, repo_name: str, workflow_id: str | None) -> str:
    """Workflow-specific or repository-wide runs endpoint."""
    if workflow_id:
        logger.debug(f"📡 Fetching workflow-specific runs: {workflow_id}")
        return f"/repos/{repo_owner}/{repo_name}/actions/workflows/{workflow_id}/runs"
    logger.debug("📡 Fetching all repository workflow runs")
    return f"/repos/{repo_owner}/{repo_name}/actions/runs"


async def _check_runs_response(
    response, workflow_id: str | None, repo_owner: str, repo_name: str
) -> str | None:
    """Translate a bad runs-list HTTP response into a user-facing error."""
    if response.status == 401:
        response_text = await response.text()
        logger.error(f"🔒 GitHub API authentication failed (401): {response_text}")
        return "❌ GitHub API authentication failed: Verify your GITHUB_TOKEN has Actions read permissions"
    if response.status == 404:
        if workflow_id:
            return f"❌ Workflow '{workflow_id}' not found in {repo_owner}/{repo_name}. Check workflow file name or ID."
        return (
            f"❌ Repository {repo_owner}/{repo_name} not found or Actions not enabled"
        )
    if response.status != 200:
        response_text = await response.text()
        logger.error(f"❌ GitHub API error {response.status}: {response_text}")
        return f"❌ Failed to list workflow runs: {response.status} - {response_text}"
    return None


def _no_runs_message(repo_owner: str, repo_name: str, params: dict) -> str:
    """Message for an empty result, naming any filters that were applied."""
    filter_desc = (
        f" (filtered by: {', '.join(f'{k}={v}' for k, v in params.items() if k not in ['per_page', 'page'])})"
        if len(params) > 2
        else ""
    )
    return f"No workflow runs found for {repo_owner}/{repo_name}{filter_desc}"


def _runs_header(
    repo_owner: str,
    repo_name: str,
    workflow_id: str | None,
    actor: str | None,
    branch: str | None,
    event: str | None,
    status: str | None,
    conclusion: str | None,
) -> str:
    """Header line naming the repository and the filters the caller passed."""
    labelled = (
        ("workflow", workflow_id),
        ("actor", actor),
        ("branch", branch),
        ("event", event),
        ("status", status),
        ("conclusion", conclusion),
    )
    filter_info = [f"{label}: {value}" for label, value in labelled if value]
    header = f"Workflow Runs for {repo_owner}/{repo_name}"
    if filter_info:
        header += f" ({', '.join(filter_info)})"
    return f"{header}:\n"


def _status_summary_line(runs: list[dict]) -> str | None:
    """Per-status counts, only worth showing when more than one status exists."""
    status_counts = Counter(run.get("status", "unknown") for run in runs)
    if len(status_counts) <= 1:
        return None
    summary = ", ".join(f"{status}: {count}" for status, count in status_counts.items())
    return f"Status summary: {summary}\n"


def _run_duration(run: dict) -> str | None:
    """Duration of a completed run, or None when absent or unparseable."""
    if not (
        run.get("status") == "completed"
        and run.get("created_at")
        and run.get("updated_at")
    ):
        return None
    try:
        start = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00"))
        return str(end - start)
    except Exception:
        return None  # Skip duration calculation if parsing fails


def _format_run(run: dict) -> list[str]:
    """Render one workflow run as output lines, ending with a blank line."""
    status_emoji = {
        "completed": "✅" if run.get("conclusion") == "success" else "❌",
        "in_progress": "🔄",
        "queued": "⏳",
        "requested": "📋",
        "waiting": "⏸️",
    }.get(run.get("status") or "", "❓")

    status_text = run.get("status", "unknown")
    if run.get("conclusion"):
        status_text += f" ({run['conclusion']})"

    lines = [
        f"{status_emoji} {run.get('name', 'Unknown Workflow')} #{run.get('run_number', '?')}",
        f"   ID: {run.get('id', 'N/A')}",
        f"   Status: {status_text}",
        f"   Branch: {run.get('head_branch', 'N/A')}",
        f"   Commit: {run.get('head_sha', 'N/A')[:8]}...",
        f"   Actor: {run.get('actor', {}).get('login', 'N/A')}",
        f"   Event: {run.get('event', 'N/A')}",
    ]

    created_at = run.get("created_at", "N/A")
    updated_at = run.get("updated_at", "N/A")
    if created_at != "N/A":
        lines.append(f"   Started: {created_at}")
    if updated_at != "N/A" and updated_at != created_at:
        lines.append(f"   Updated: {updated_at}")

    duration = _run_duration(run)
    if duration is not None:
        lines.append(f"   Duration: {duration}")
    if run.get("html_url"):
        lines.append(f"   URL: {run['html_url']}")

    lines.append("")
    return lines


def _runs_overview_lines(runs: list[dict], total_count: int, page: int) -> list[str]:
    """Paging notice and status summary shown above the run list."""
    lines = []
    if total_count > len(runs):
        lines.append(f"Showing {len(runs)} of {total_count} total runs (page {page})\n")
    summary = _status_summary_line(runs)
    if summary is not None:
        lines.append(summary)
    return lines


def _pagination_footer(
    runs: list[dict], total_count: int, page: int, per_page: int
) -> list[str]:
    """Footer pointing at further pages; empty when everything is shown.

    Preserved quirk: ``max_page`` uses the raw ``per_page`` argument, not the
    value clamped to 1-100 that was sent to the API.
    """
    if total_count <= len(runs):
        return []
    max_page = (total_count + per_page - 1) // per_page
    return [f"📄 Page {page} of {max_page} (use page parameter to see more)"]


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
            params = _build_run_params(
                per_page,
                page,
                actor,
                branch,
                event,
                status,
                conclusion,
                created,
                exclude_pull_requests,
                check_suite_id,
                head_sha,
            )
            endpoint = _runs_endpoint(repo_owner, repo_name, workflow_id)
            logger.debug(f"📡 Making API call to {endpoint} with params: {params}")

            response = await client.get(endpoint, params=params)
            logger.debug(f"📨 GitHub API response status: {response.status}")

            error = await _check_runs_response(
                response, workflow_id, repo_owner, repo_name
            )
            if error is not None:
                return error

            data = await response.json()
            workflow_runs = data.get("workflow_runs", [])
            if not workflow_runs:
                return _no_runs_message(repo_owner, repo_name, params)

            total_count = data.get("total_count", len(workflow_runs))
            output = [
                _runs_header(
                    repo_owner,
                    repo_name,
                    workflow_id,
                    actor,
                    branch,
                    event,
                    status,
                    conclusion,
                )
            ]
            output.extend(_runs_overview_lines(workflow_runs, total_count, page))
            for run in workflow_runs:
                output.extend(_format_run(run))
            output.extend(
                _pagination_footer(workflow_runs, total_count, page, per_page)
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
