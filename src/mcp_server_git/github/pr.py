"""GitHub Pull Request operations."""

from __future__ import annotations

import logging

from mcp_server_git.github.client import github_client_context
from mcp_server_git.github.patches import PatchMemoryManager
from .pr_actions import *  # noqa: F401,F403

logger = logging.getLogger(__name__)


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
            pr_response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}"
            )
            if pr_response.status != 200:
                return f"❌ Failed to get PR #{pr_number}: {pr_response.status}"

            pr_data = await pr_response.json()
            head_sha = pr_data["head"]["sha"]

            # Get check runs for the head commit
            params = {}
            if status:
                params["status"] = status

            checks_response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/commits/{head_sha}/check-runs",
                params=params,
            )
            if checks_response.status != 200:
                return f"❌ Failed to get check runs: {checks_response.status}"

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
                status_emoji = {
                    "completed": "✅" if run.get("conclusion") == "success" else "❌",
                    "in_progress": "🔄",
                    "queued": "⏳",
                }.get(run["status"], "❓")

                output.append(f"{status_emoji} {run['name']}")
                output.append(f"   Status: {run['status']}")
                if run.get("conclusion"):
                    output.append(f"   Conclusion: {run['conclusion']}")
                output.append(f"   Started: {run.get('started_at', 'N/A')}")
                if run.get("completed_at"):
                    output.append(f"   Completed: {run['completed_at']}")
                if run.get("html_url"):
                    output.append(f"   URL: {run['html_url']}")
                output.append("")

            return "\n".join(output)

    except ValueError as auth_error:
        # Handle authentication/configuration errors specifically
        logger.error(f"Authentication error getting PR checks: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        # Handle network connectivity issues
        logger.error(f"Connection error getting PR checks: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        # Log unexpected errors with full context for debugging
        logger.error(
            f"Unexpected error getting PR checks for PR #{pr_number}: {e}",
            exc_info=True,
        )
        return f"❌ Error getting PR checks: {str(e)}"


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
            pr_response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}"
            )
            if pr_response.status != 200:
                return f"❌ Failed to get PR #{pr_number}: {pr_response.status}"

            pr_data = await pr_response.json()
            head_sha = pr_data["head"]["sha"]

            # Get check runs and filter for failures
            checks_response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/commits/{head_sha}/check-runs"
            )
            if checks_response.status != 200:
                return f"❌ Failed to get check runs: {checks_response.status}"

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
                output.append(f"❌ {run['name']}")
                output.append(f"   Conclusion: {run['conclusion']}")
                output.append(f"   Started: {run.get('started_at', 'N/A')}")
                output.append(f"   Completed: {run.get('completed_at', 'N/A')}")

                # Get annotations if requested
                if include_annotations and run.get("id"):
                    try:
                        annotations_response = await client.get(
                            f"/repos/{repo_owner}/{repo_name}/check-runs/{run['id']}/annotations"
                        )
                        if annotations_response.status == 200:
                            annotations_data = await annotations_response.json()
                            if annotations_data:
                                output.append("   Annotations:")
                                for annotation in annotations_data[
                                    :5
                                ]:  # Limit to first 5
                                    output.append(
                                        f"     • {annotation.get('title', 'Error')}: {annotation.get('message', 'No message')}"
                                    )
                                    if annotation.get("path"):
                                        output.append(
                                            f"       File: {annotation['path']} (line {annotation.get('start_line', 'unknown')})"
                                        )
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

                # Get logs if requested (simplified)
                if include_logs and run.get("html_url"):
                    output.append(f"   Details: {run['html_url']}")

                output.append("")

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error getting failing jobs: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error getting failing jobs: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error getting failing jobs for PR #{pr_number}: {e}",
            exc_info=True,
        )
        return f"❌ Error getting failing jobs: {str(e)}"


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
                return f"❌ Failed to get PR #{pr_number}: {pr_response.status}"

            pr_data = await pr_response.json()

            output = [f"Pull Request #{pr_number}:\n"]
            output.append(f"Title: {pr_data.get('title', 'N/A')}")
            output.append(f"State: {pr_data.get('state', 'N/A')}")
            output.append(f"Author: {pr_data.get('user', {}).get('login', 'N/A')}")
            output.append(f"Base: {pr_data.get('base', {}).get('ref', 'N/A')}")
            output.append(f"Head: {pr_data.get('head', {}).get('ref', 'N/A')}")
            output.append(f"Created: {pr_data.get('created_at', 'N/A')}")
            output.append(f"Updated: {pr_data.get('updated_at', 'N/A')}")

            if pr_data.get("body"):
                output.append(
                    f"\nDescription:\n{pr_data['body'][:500]}{'...' if len(pr_data['body']) > 500 else ''}"
                )

            if pr_data.get("html_url"):
                output.append(f"\nURL: {pr_data['html_url']}")

            # Get files if requested
            if include_files:
                try:
                    files_response = await client.get(
                        f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}/files"
                    )
                    if files_response.status == 200:
                        files_data = await files_response.json()
                        if files_data:
                            output.append(f"\nFiles ({len(files_data)}):")
                            for file in files_data[:10]:  # Limit to first 10
                                output.append(
                                    f"  {file['status'][0].upper()} {file['filename']} (+{file['additions']}, -{file['deletions']})"
                                )
                            if len(files_data) > 10:
                                output.append(
                                    f"  ... and {len(files_data) - 10} more files"
                                )
                except (ConnectionError, ValueError) as files_error:
                    logger.warning(
                        f"Failed to get files for PR #{pr_number}: {files_error}"
                    )
                    output.append("\n⚠️ Could not retrieve files information")

            # Get reviews if requested
            if include_reviews:
                try:
                    reviews_response = await client.get(
                        f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}/reviews"
                    )
                    if reviews_response.status == 200:
                        reviews_data = await reviews_response.json()
                        if reviews_data:
                            output.append(f"\nReviews ({len(reviews_data)}):")
                            for review in reviews_data[-5:]:  # Show last 5
                                state_emoji = {
                                    "APPROVED": "✅",
                                    "CHANGES_REQUESTED": "❌",
                                    "COMMENTED": "💬",
                                }.get(review.get("state"), "❓")
                                output.append(
                                    f"  {state_emoji} {review.get('user', {}).get('login', 'N/A')}: {review.get('state', 'N/A')}"
                                )
                except (ConnectionError, ValueError) as reviews_error:
                    logger.warning(
                        f"Failed to get reviews for PR #{pr_number}: {reviews_error}"
                    )
                    output.append("\n⚠️ Could not retrieve reviews information")

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error getting PR details: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error getting PR details: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error getting PR details for PR #{pr_number}: {e}",
            exc_info=True,
        )
        return f"❌ Error getting PR details: {str(e)}"


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
                return f"❌ GitHub API error 401: {response_text}"
            elif response.status != 200:
                response_text = await response.text()
                logger.error(f"❌ GitHub API error {response.status}: {response_text}")
                return f"❌ Failed to list pull requests: {response.status} - {response_text}"

            prs = await response.json()

            if not prs:
                return f"No {state} pull requests found"

            output = [f"{state.title()} Pull Requests for {repo_owner}/{repo_name}:\n"]

            for pr in prs:
                state_emoji = {"open": "🟢", "closed": "🔴", "merged": "🟣"}.get(
                    pr.get("state"), "❓"
                )
                output.append(f"{state_emoji} #{pr['number']}: {pr['title']}")
                output.append(f"   Author: {pr.get('user', {}).get('login', 'N/A')}")
                base_ref = pr.get("base", {}).get("ref", "N/A")
                head_ref = pr.get("head", {}).get("ref", "N/A")
                output.append(f"   Base: {base_ref} ← Head: {head_ref}")
                output.append(f"   Created: {pr.get('created_at', 'N/A')}")
                output.append("")

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error listing pull requests: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error listing pull requests: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error listing pull requests for {repo_owner}/{repo_name}: {e}",
            exc_info=True,
        )
        return f"❌ Error listing pull requests: {str(e)}"


async def github_get_pr_status(repo_owner: str, repo_name: str, pr_number: int) -> str:
    """Get the status and check runs for a pull request"""
    try:
        async with github_client_context() as client:
            # Get PR details
            pr_response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}"
            )
            if pr_response.status != 200:
                return f"❌ Failed to get PR #{pr_number}: {pr_response.status}"

            pr_data = await pr_response.json()
            head_sha = pr_data["head"]["sha"]

            output = [f"Status for PR #{pr_number}:\n"]
            output.append(f"State: {pr_data.get('state', 'N/A')}")
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
                        status_emoji = {
                            "completed": "✅"
                            if run.get("conclusion") == "success"
                            else "❌",
                            "in_progress": "🔄",
                            "queued": "⏳",
                        }.get(run["status"], "❓")

                        output.append(
                            f"  {status_emoji} {run['name']}: {run['status']}"
                        )
                        if run.get("conclusion"):
                            output.append(f"    Conclusion: {run['conclusion']}")

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error getting PR status: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error getting PR status: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error getting PR status for PR #{pr_number}: {e}",
            exc_info=True,
        )
        return f"❌ Error getting PR status: {str(e)}"


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
                return f"❌ Failed to get PR files: {response.status}"

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
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error getting PR files: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error getting PR files for PR #{pr_number}: {e}", exc_info=True
        )
        return f"❌ Error getting PR files: {str(e)}"

