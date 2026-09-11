"""GitHub Actions workflow listing and status operations."""

from __future__ import annotations

import logging

from mcp_server_git.github.client import github_client_context

from .ci_logs import *  # noqa: F401,F403

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
