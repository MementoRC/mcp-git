"""GitHub Pull Request operations."""

from __future__ import annotations

import logging

from mcp_server_git.github._payload import login_of, obj_of
from mcp_server_git.github.check_markers import check_marker
from mcp_server_git.github.client import github_client_context
from mcp_server_git.github.patches import PatchMemoryManager

from ..utils.tool_failure import fail
from ._pr_format import (
    annotation_lines,
    failing_run_header,
    format_check_run,
    format_files_section,
    format_pr_summary,
    format_reviews_section,
    merged_line,
    pr_state_marker,
)
from .pr_actions import *  # noqa: F401,F403

logger = logging.getLogger(__name__)


async def _fetch_head_sha(
    client, repo_owner: str, repo_name: str, pr_number: int
) -> tuple[str, None] | tuple[None, str]:
    """Fetch a PR's head SHA; returns (sha, None) or (None, error message)."""
    pr_response = await client.get(f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}")
    if pr_response.status != 200:
        return None, fail(f"❌ Failed to get PR #{pr_number}: {pr_response.status}")
    pr_data = await pr_response.json()
    return pr_data["head"]["sha"], None


async def _fetch_annotation_lines(
    client, repo_owner: str, repo_name: str, run: dict
) -> list[str]:
    """Fetch and render a check run's annotations; failures are non-fatal."""
    try:
        response = await client.get(
            f"/repos/{repo_owner}/{repo_name}/check-runs/{run['id']}/annotations"
        )
        if response.status != 200:
            return []
        return annotation_lines(await response.json())
    except (ConnectionError, ValueError) as annotation_error:
        # Log specific annotation errors but continue processing
        logger.warning(
            f"Failed to get annotations for run {run.get('id')}: {annotation_error}"
        )
    except Exception as annotation_error:
        # Annotations might not be available - log but continue
        logger.debug(
            f"Annotations unavailable for run {run.get('id')}: {annotation_error}"
        )
    return []


async def github_get_pr_checks(
    repo_owner: str,
    repo_name: str,
    pr_number: int,
    status: str | None = None,
    conclusion: str | None = None,
) -> str:
    """Get check runs for a pull request"""
    try:
        async with github_client_context() as client:
            # First get the PR to get the head SHA
            head = await _fetch_head_sha(client, repo_owner, repo_name, pr_number)
            if head[0] is None:
                return head[1]
            head_sha = head[0]

            # Get check runs for the head commit
            params = {}
            if status:
                params["status"] = status

            checks_response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/commits/{head_sha}/check-runs",
                params=params,
            )
            if checks_response.status != 200:
                return fail(f"❌ Failed to get check runs: {checks_response.status}")

            checks_data = await checks_response.json()

            # Filter by conclusion if specified
            check_runs = checks_data.get("check_runs", [])
            if conclusion:
                check_runs = [
                    run for run in check_runs if run.get("conclusion") == conclusion
                ]

            # Format the output
            if not check_runs:
                return f"No check runs found for PR #{pr_number}"

            output = [f"Check runs for PR #{pr_number} (commit {head_sha[:8]}):\n"]

            for run in check_runs:
                output.extend(format_check_run(run))

            return "\n".join(output)

    except ValueError as auth_error:
        # Handle authentication/configuration errors specifically
        logger.error(f"Authentication error getting PR checks: {auth_error}")
        return fail(f"❌ {str(auth_error)}")
    except ConnectionError as conn_error:
        # Handle network connectivity issues
        logger.error(f"Connection error getting PR checks: {conn_error}")
        return fail(f"❌ Network connection failed: {str(conn_error)}")
    except Exception as e:
        # Log unexpected errors with full context for debugging
        logger.error(
            f"Unexpected error getting PR checks for PR #{pr_number}: {e}",
            exc_info=True,
        )
        return fail(f"❌ Error getting PR checks: {str(e)}")


async def github_get_failing_jobs(
    repo_owner: str,
    repo_name: str,
    pr_number: int,
    include_logs: bool = True,
    include_annotations: bool = True,
) -> str:
    """Get detailed information about failing jobs in a PR"""
    try:
        async with github_client_context() as client:
            # Get PR details
            head = await _fetch_head_sha(client, repo_owner, repo_name, pr_number)
            if head[0] is None:
                return head[1]
            head_sha = head[0]

            # Get check runs and filter for failures
            checks_response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/commits/{head_sha}/check-runs"
            )
            if checks_response.status != 200:
                return fail(f"❌ Failed to get check runs: {checks_response.status}")

            checks_data = await checks_response.json()

            failing_runs = [
                run
                for run in checks_data.get("check_runs", [])
                if run["status"] == "completed"
                and run.get("conclusion") in ["failure", "cancelled", "timed_out"]
            ]

            if not failing_runs:
                return f"No failing jobs found for PR #{pr_number}"

            output = [f"Failing jobs for PR #{pr_number}:\n"]

            for run in failing_runs:
                output.extend(failing_run_header(run))

                # Get annotations if requested
                if include_annotations and run.get("id"):
                    output.extend(
                        await _fetch_annotation_lines(
                            client, repo_owner, repo_name, run
                        )
                    )

                # Get logs if requested (simplified)
                if include_logs and run.get("html_url"):
                    output.append(f"   Details: {run['html_url']}")

                output.append("")

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error getting failing jobs: {auth_error}")
        return fail(f"❌ {str(auth_error)}")
    except ConnectionError as conn_error:
        logger.error(f"Connection error getting failing jobs: {conn_error}")
        return fail(f"❌ Network connection failed: {str(conn_error)}")
    except Exception as e:
        logger.error(
            f"Unexpected error getting failing jobs for PR #{pr_number}: {e}",
            exc_info=True,
        )
        return fail(f"❌ Error getting failing jobs: {str(e)}")


async def _fetch_section(
    client, pulls: str, label: str, pr_number: int, formatter
) -> list[str]:
    """Fetch ``{pulls}/{label}`` for an optional section; failures become a notice."""
    try:
        response = await client.get(f"{pulls}/{label}")
        if response.status != 200:
            return []
        return formatter(await response.json())
    except (ConnectionError, ValueError) as section_error:
        logger.warning(f"Failed to get {label} for PR #{pr_number}: {section_error}")
        return [f"\n⚠️ Could not retrieve {label} information"]


async def github_get_pr_details(
    repo_owner: str,
    repo_name: str,
    pr_number: int,
    include_files: bool = False,
    include_reviews: bool = False,
) -> str:
    """Get comprehensive PR details"""
    try:
        async with github_client_context() as client:
            # Get PR details
            pr_response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}"
            )
            if pr_response.status != 200:
                return fail(f"❌ Failed to get PR #{pr_number}: {pr_response.status}")

            pr_data = await pr_response.json()

            output = format_pr_summary(pr_number, pr_data)
            pulls = f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}"
            for wanted, label, formatter in (
                (include_files, "files", format_files_section),
                (include_reviews, "reviews", format_reviews_section),
            ):
                if wanted:
                    output.extend(
                        await _fetch_section(client, pulls, label, pr_number, formatter)
                    )

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error getting PR details: {auth_error}")
        return fail(f"❌ {str(auth_error)}")
    except ConnectionError as conn_error:
        logger.error(f"Connection error getting PR details: {conn_error}")
        return fail(f"❌ Network connection failed: {str(conn_error)}")
    except Exception as e:
        logger.error(
            f"Unexpected error getting PR details for PR #{pr_number}: {e}",
            exc_info=True,
        )
        return fail(f"❌ Error getting PR details: {str(e)}")


async def github_list_pull_requests(
    repo_owner: str,
    repo_name: str,
    state: str = "open",
    head: str | None = None,
    base: str | None = None,
    sort: str = "created",
    direction: str = "desc",
    per_page: int = 30,
    page: int = 1,
) -> str:
    """List pull requests for a repository"""
    logger.debug(f"🔍 Starting github_list_pull_requests for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            logger.debug("✅ GitHub client obtained successfully")
            logger.debug(
                f"🔗 Token prefix: {client.token[:8]}..."
                if client.token
                else "No token"
            )

            params = {
                "state": state,
                "sort": sort,
                "direction": direction,
                "per_page": per_page,
                "page": page,
            }

            if head:
                params["head"] = head
            if base:
                params["base"] = base

            logger.debug(
                f"📡 Making API call to /repos/{repo_owner}/{repo_name}/pulls with params: {params}"
            )

            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/pulls", params=params
            )

            logger.debug(f"📨 GitHub API response status: {response.status}")

            if response.status == 401:
                response_text = await response.text()
                logger.error(
                    f"🔒 GitHub API authentication failed (401): {response_text}"
                )
                return fail(f"❌ GitHub API error 401: {response_text}")
            elif response.status != 200:
                response_text = await response.text()
                logger.error(f"❌ GitHub API error {response.status}: {response_text}")
                return fail(
                    f"❌ Failed to list pull requests: {response.status} - {response_text}"
                )

            prs = await response.json()

            if not prs:
                return f"No {state} pull requests found"

            output = [f"{state.title()} Pull Requests for {repo_owner}/{repo_name}:\n"]

            for pr in prs:
                state_emoji = pr_state_marker(pr)
                output.append(f"{state_emoji} #{pr['number']}: {pr['title']}")
                output.append(f"   Author: {login_of(pr)}")
                base_ref = obj_of(pr, "base").get("ref", "N/A")
                head_ref = obj_of(pr, "head").get("ref", "N/A")
                output.append(f"   Base: {base_ref} ← Head: {head_ref}")
                output.append(f"   Created: {pr.get('created_at', 'N/A')}")
                output.append("")

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error listing pull requests: {auth_error}")
        return fail(f"❌ {str(auth_error)}")
    except ConnectionError as conn_error:
        logger.error(f"Connection error listing pull requests: {conn_error}")
        return fail(f"❌ Network connection failed: {str(conn_error)}")
    except Exception as e:
        logger.error(
            f"Unexpected error listing pull requests for {repo_owner}/{repo_name}: {e}",
            exc_info=True,
        )
        return fail(f"❌ Error listing pull requests: {str(e)}")


async def github_get_pr_status(repo_owner: str, repo_name: str, pr_number: int) -> str:
    """Get the status and check runs for a pull request"""
    try:
        async with github_client_context() as client:
            # Get PR details
            pr_response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}"
            )
            if pr_response.status != 200:
                return fail(f"❌ Failed to get PR #{pr_number}: {pr_response.status}")

            pr_data = await pr_response.json()
            head_sha = pr_data["head"]["sha"]

            output = [f"Status for PR #{pr_number}:\n"]
            output.append(f"State: {pr_data.get('state', 'N/A')}")
            merged = merged_line(pr_data)
            if merged:
                # Closed: report whether it merged. "Mergeable"/"Merge State"
                # answer "can this merge now", which is noise once closed.
                output.append(merged)
            else:
                output.append(f"Mergeable: {pr_data.get('mergeable', 'N/A')}")
                output.append(f"Merge State: {pr_data.get('mergeable_state', 'N/A')}")
            output.append("")

            # Get check runs
            checks_response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/commits/{head_sha}/check-runs"
            )
            if checks_response.status == 200:
                checks_data = await checks_response.json()
                check_runs = checks_data.get("check_runs", [])

                if check_runs:
                    output.append("Check Runs:")
                    for run in check_runs:
                        status_emoji = check_marker(run)

                        output.append(
                            f"  {status_emoji} {run['name']}: {run['status']}"
                        )
                        if run.get("conclusion"):
                            output.append(f"    Conclusion: {run['conclusion']}")

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error getting PR status: {auth_error}")
        return fail(f"❌ {str(auth_error)}")
    except ConnectionError as conn_error:
        logger.error(f"Connection error getting PR status: {conn_error}")
        return fail(f"❌ Network connection failed: {str(conn_error)}")
    except Exception as e:
        logger.error(
            f"Unexpected error getting PR status for PR #{pr_number}: {e}",
            exc_info=True,
        )
        return fail(f"❌ Error getting PR status: {str(e)}")


async def github_get_pr_files(
    repo_owner: str,
    repo_name: str,
    pr_number: int,
    per_page: int = 30,
    page: int = 1,
    include_patch: bool = False,
) -> str:
    """Get files changed in a pull request with memory-aware patch handling"""
    try:
        async with github_client_context() as client:
            params = {"per_page": per_page, "page": page}

            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}/files",
                params=params,
            )
            if response.status != 200:
                return fail(f"❌ Failed to get PR files: {response.status}")

            files = await response.json()

            if not files:
                return f"No files found for PR #{pr_number}"

            output = [f"Files changed in PR #{pr_number}:\n"]

            total_additions = 0
            total_deletions = 0

            # Initialize memory manager for patch processing
            patch_manager = PatchMemoryManager(
                max_patch_size=1000, max_total_memory=50000
            )

            for file in files:
                status_emoji = {
                    "added": "➕",
                    "modified": "📝",
                    "removed": "➖",
                    "renamed": "📝",
                }.get(file.get("status"), "❓")

                additions = file.get("additions", 0)
                deletions = file.get("deletions", 0)
                total_additions += additions
                total_deletions += deletions

                output.append(
                    f"{status_emoji} {file['filename']} (+{additions}, -{deletions})"
                )

                if include_patch and file.get("patch"):
                    # Use memory manager to safely process patch content
                    processed_patch, was_truncated = patch_manager.process_patch(
                        file["patch"]
                    )
                    output.append(processed_patch)

                    if was_truncated:
                        logger.info(
                            f"Patch for {file['filename']} was truncated or skipped for memory management"
                        )

                output.append("")

            output.append(f"Total: +{total_additions}, -{total_deletions}")

            # Add memory usage summary if patches were included
            if include_patch:
                output.append(
                    f"\nMemory usage: {patch_manager.current_memory_usage}/{patch_manager.max_total_memory} bytes"
                )
                output.append(f"Patches processed: {patch_manager.patches_processed}")

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error getting PR files: {auth_error}")
        return fail(f"❌ {str(auth_error)}")
    except ConnectionError as conn_error:
        logger.error(f"Connection error getting PR files: {conn_error}")
        return fail(f"❌ Network connection failed: {str(conn_error)}")
    except Exception as e:
        logger.error(
            f"Unexpected error getting PR files for PR #{pr_number}: {e}", exc_info=True
        )
        return fail(f"❌ Error getting PR files: {str(e)}")
