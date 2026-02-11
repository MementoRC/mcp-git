"""GitHub API operations for MCP Git Server"""

import asyncio
import json
import logging
import mimetypes
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from .client import get_github_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def github_client_context():
    """Async context manager for GitHub client with guaranteed resource cleanup."""
    client = None
    try:
        client = get_github_client()
        if not client:
            raise ValueError(
                "GitHub token not configured. Set GITHUB_TOKEN environment variable."
            )
        yield client
    finally:
        if client and client.session:
            try:
                await client.session.close()
            except Exception as cleanup_error:
                logger.warning(f"Error during client cleanup: {cleanup_error}")


class PatchMemoryManager:
    """Memory-aware patch content manager with configurable limits and streaming support."""

    def __init__(self, max_patch_size: int = 1000, max_total_memory: int = 50000):
        self.max_patch_size = max_patch_size
        self.max_total_memory = max_total_memory
        self.current_memory_usage = 0
        self.patches_processed = 0

    def can_include_patch(self, patch_size: int) -> bool:
        """Check if patch can be included within memory constraints."""
        return (self.current_memory_usage + patch_size) <= self.max_total_memory

    def process_patch(self, patch_content: str) -> tuple[str, bool]:
        """Process patch content with memory management and truncation.

        Returns:
            tuple[str, bool]: (processed_content, was_truncated)
        """
        patch_size = len(patch_content)
        self.patches_processed += 1

        # Check memory budget first
        if not self.can_include_patch(patch_size):
            logger.warning(
                f"Patch #{self.patches_processed} skipped: exceeds memory budget ({patch_size} bytes, {self.current_memory_usage}/{self.max_total_memory} used)"
            )
            return (
                f"[Patch skipped - memory limit reached ({self.current_memory_usage}/{self.max_total_memory} bytes used)]",
                True,
            )

        # Apply individual patch size limit
        if patch_size > self.max_patch_size:
            truncated_patch = patch_content[: self.max_patch_size]
            self.current_memory_usage += self.max_patch_size
            logger.info(
                f"Patch #{self.patches_processed} truncated: {patch_size} -> {self.max_patch_size} bytes"
            )
            return (
                f"```diff\n{truncated_patch}\n... [truncated {patch_size - self.max_patch_size} chars]\n```",
                True,
            )
        else:
            self.current_memory_usage += patch_size
            return f"```diff\n{patch_content}\n```", False


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


async def github_update_pr(
    repo_owner: str,
    repo_name: str,
    pr_number: int,
    title: str | None = None,
    body: str | None = None,
    state: str | None = None,
    base: str | None = None,
) -> str:
    """Update a pull request's title, body, state, or base branch."""
    logger.debug(f"🚀 Updating PR #{pr_number} in {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            payload: dict[str, Any] = {}
            if title is not None:
                payload["title"] = title
            if body is not None:
                payload["body"] = body
            if state is not None:
                if state not in ["open", "closed"]:
                    return "❌ State must be 'open' or 'closed'"
                payload["state"] = state
            if base is not None:
                payload["base"] = base

            if not payload:
                return "⚠️ No update parameters provided. Please specify title, body, state, or base."

            response = await client.patch(
                f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}", json=payload
            )

            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to update PR #{pr_number}: {response.status} - {error_text}"

            result = await response.json()
            logger.info(f"✅ Successfully updated PR #{pr_number}")
            return (
                f"✅ Successfully updated PR #{result['number']}: {result['html_url']}"
            )

    except ValueError as auth_error:
        logger.error(f"Authentication error updating PR: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error updating PR: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error updating PR #{pr_number}: {e}", exc_info=True)
        return f"❌ Error updating PR: {str(e)}"


async def github_create_pr(
    repo_owner: str,
    repo_name: str,
    title: str,
    head: str,
    base: str,
    body: str | None = None,
    draft: bool = False,
) -> str:
    """Create a new pull request."""
    logger.debug(f"🚀 Creating PR in {repo_owner}/{repo_name} from {head} to {base}")

    try:
        async with github_client_context() as client:
            payload = {"title": title, "head": head, "base": base, "draft": draft}
            if body is not None:
                payload["body"] = body

            response = await client.post(
                f"/repos/{repo_owner}/{repo_name}/pulls", json=payload
            )

            if response.status != 201:
                error_text = await response.text()
                # Provide more helpful error for common cases
                if (
                    "No commits between" in error_text
                    or "A pull request already exists" in error_text
                ):
                    return f"❌ Could not create PR. Reason: {error_text}"
                return f"❌ Failed to create PR: {response.status} - {error_text}"

            result = await response.json()
            logger.info(f"✅ Successfully created PR #{result['number']}")
            return (
                f"✅ Successfully created PR #{result['number']}: {result['html_url']}"
            )

    except ValueError as auth_error:
        logger.error(f"Authentication error creating PR: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error creating PR: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error creating PR: {e}", exc_info=True)
        return f"❌ Error creating PR: {str(e)}"


async def github_merge_pr(
    repo_owner: str,
    repo_name: str,
    pr_number: int,
    commit_title: str | None = None,
    commit_message: str | None = None,
    merge_method: str = "merge",
) -> str:
    """Merge a pull request."""
    logger.debug(
        f"🚀 Merging PR #{pr_number} in {repo_owner}/{repo_name} using '{merge_method}' method"
    )

    try:
        async with github_client_context() as client:
            if merge_method not in ["merge", "squash", "rebase"]:
                return "❌ merge_method must be one of 'merge', 'squash', or 'rebase'"

            payload = {"merge_method": merge_method}
            if commit_title:
                payload["commit_title"] = commit_title
            if commit_message:
                payload["commit_message"] = commit_message

            response = await client.put(
                f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}/merge", json=payload
            )

            if response.status != 200:
                error_text = await response.text()
                if response.status in [405, 409]:
                    return f"❌ Could not merge PR. Reason: {error_text}. This may be due to merge conflicts or failing status checks."
                return f"❌ Failed to merge PR: {response.status} - {error_text}"

            result = await response.json()
            if result.get("merged"):
                logger.info(f"✅ Successfully merged PR #{pr_number}")
                return f"✅ {result['message']}"
            else:
                logger.warning(
                    f"⚠️ Merge attempt for PR #{pr_number} returned 200 OK but 'merged' is false: {result.get('message')}"
                )
                return f"⚠️ {result.get('message', 'Merge was not successful but API returned 200 OK. Check PR status.')}"

    except ValueError as auth_error:
        logger.error(f"Authentication error merging PR: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error merging PR: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error merging PR #{pr_number}: {e}", exc_info=True)
        return f"❌ Error merging PR: {str(e)}"


async def github_add_pr_comment(
    repo_owner: str, repo_name: str, pr_number: int, body: str
) -> str:
    """Add a comment to a pull request."""
    logger.debug(f"🚀 Adding comment to PR #{pr_number} in {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            # Comments are added to the corresponding issue
            payload = {"body": body}

            response = await client.post(
                f"/repos/{repo_owner}/{repo_name}/issues/{pr_number}/comments",
                json=payload,
            )

            if response.status != 201:
                error_text = await response.text()
                return f"❌ Failed to add comment: {response.status} - {error_text}"

            result = await response.json()
            logger.info(f"✅ Successfully added comment to PR #{pr_number}")
            return f"✅ Successfully added comment: {result['html_url']}"

    except ValueError as auth_error:
        logger.error(f"Authentication error adding PR comment: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error adding PR comment: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error adding comment to PR #{pr_number}: {e}", exc_info=True
        )
        return f"❌ Error adding comment: {str(e)}"


async def github_close_pr(repo_owner: str, repo_name: str, pr_number: int) -> str:
    """Close a pull request."""
    logger.debug(f"🚀 Closing PR #{pr_number} in {repo_owner}/{repo_name}")
    return await github_update_pr(repo_owner, repo_name, pr_number, state="closed")


async def github_reopen_pr(repo_owner: str, repo_name: str, pr_number: int) -> str:
    """Reopen a closed pull request."""
    logger.debug(f"🚀 Reopening PR #{pr_number} in {repo_owner}/{repo_name}")
    return await github_update_pr(repo_owner, repo_name, pr_number, state="open")


# GitHub Issues API Functions
async def github_create_issue(
    repo_owner: str,
    repo_name: str,
    title: str,
    body: str | None = None,
    labels: list[str] | None = None,
    assignees: list[str] | None = None,
    milestone: int | None = None,
) -> str:
    """Create a new GitHub issue."""
    logger.debug(f"🚀 Creating issue in {repo_owner}/{repo_name}: {title}")

    try:
        async with github_client_context() as client:
            payload: dict[str, Any] = {"title": title}
            if body is not None:
                payload["body"] = body
            if labels is not None:
                payload["labels"] = labels
            if assignees is not None:
                payload["assignees"] = assignees
            if milestone is not None:
                payload["milestone"] = milestone

            response = await client.post(
                f"/repos/{repo_owner}/{repo_name}/issues", json=payload
            )

            if response.status != 201:
                error_text = await response.text()
                return f"❌ Failed to create issue: {response.status} - {error_text}"

            result = await response.json()
            logger.info(f"✅ Successfully created issue #{result['number']}")
            return f"✅ Successfully created issue #{result['number']}: {result['html_url']}"

    except ValueError as auth_error:
        logger.error(f"Authentication error creating issue: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error creating issue: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error creating issue: {e}", exc_info=True)
        return f"❌ Error creating issue: {str(e)}"


async def github_list_issues(
    repo_owner: str,
    repo_name: str,
    state: str = "open",
    labels: list[str] | None = None,
    assignee: str | None = None,
    creator: str | None = None,
    mentioned: str | None = None,
    milestone: str | None = None,
    sort: str = "created",
    direction: str = "desc",
    since: str | None = None,
    per_page: int = 30,
    page: int = 1,
) -> str:
    """List issues for a repository."""
    logger.debug(f"🔍 Listing issues for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            params = {
                "state": state,
                "sort": sort,
                "direction": direction,
                "per_page": per_page,
                "page": page,
            }

            if labels:
                params["labels"] = ",".join(labels)
            if assignee:
                params["assignee"] = assignee
            if creator:
                params["creator"] = creator
            if mentioned:
                params["mentioned"] = mentioned
            if milestone:
                params["milestone"] = milestone
            if since:
                params["since"] = since

            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/issues", params=params
            )

            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to list issues: {response.status} - {error_text}"

            issues = await response.json()

            if not issues:
                return f"No {state} issues found"

            output = [f"{state.title()} Issues for {repo_owner}/{repo_name}:\n"]

            for issue in issues:
                # Skip pull requests (they appear in issues API but have 'pull_request' key)
                if issue.get("pull_request"):
                    continue

                state_emoji = {"open": "🟢", "closed": "🔴"}.get(
                    issue.get("state"), "❓"
                )
                output.append(f"{state_emoji} #{issue['number']}: {issue['title']}")
                output.append(f"   Author: {issue.get('user', {}).get('login', 'N/A')}")

                # Show labels if any
                if issue.get("labels"):
                    label_names = [label["name"] for label in issue["labels"]]
                    output.append(f"   Labels: {', '.join(label_names)}")

                # Show assignees if any
                if issue.get("assignees"):
                    assignee_names = [
                        assignee["login"] for assignee in issue["assignees"]
                    ]
                    output.append(f"   Assignees: {', '.join(assignee_names)}")

                output.append(f"   Created: {issue.get('created_at', 'N/A')}")
                output.append("")

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error listing issues: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error listing issues: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error listing issues: {e}", exc_info=True)
        return f"❌ Error listing issues: {str(e)}"


async def github_get_issue(
    repo_owner: str,
    repo_name: str,
    issue_number: int,
) -> str:
    """Get a single GitHub issue by number.

    Returns full issue details including title, body, state, labels,
    assignees, milestone, comments count, and timestamps.
    """
    BODY_TRUNCATION_LIMIT = 2000
    logger.debug(f"🔍 Getting issue #{issue_number} for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/issues/{issue_number}"
            )

            if response.status == 404:
                return f"❌ Issue #{issue_number} not found in {repo_owner}/{repo_name}. Check issue number and repository access."

            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to get issue: {response.status} - {error_text}"

            issue = await response.json()

            # Check if this is a pull request (issues API returns PRs too)
            if issue.get("pull_request"):
                return f"❌ #{issue_number} is a pull request, not an issue"

            # Format the issue details
            state_emoji = {"open": "🟢", "closed": "🔴"}.get(issue.get("state"), "❓")

            output = [
                f"Issue #{issue['number']}: {issue['title']}",
                f"State: {state_emoji} {issue.get('state', 'unknown')}",
                f"Author: {(issue.get('user') or {}).get('login', 'N/A')}",
                f"Created: {issue.get('created_at', 'N/A')}",
                f"Updated: {issue.get('updated_at', 'N/A')}",
            ]

            # Add closed_at if closed
            if issue.get("closed_at"):
                output.append(f"Closed: {issue['closed_at']}")

            # Add labels
            if issue.get("labels"):
                label_names = [label["name"] for label in issue["labels"]]
                output.append(f"Labels: {', '.join(label_names)}")

            # Add assignees
            if issue.get("assignees"):
                assignee_names = [a["login"] for a in issue["assignees"]]
                output.append(f"Assignees: {', '.join(assignee_names)}")

            # Add milestone
            if issue.get("milestone"):
                output.append(f"Milestone: {issue['milestone'].get('title', 'N/A')}")

            # Add comments count
            output.append(f"Comments: {issue.get('comments', 0)}")

            # Add URL
            output.append(f"URL: {issue.get('html_url', 'N/A')}")

            # Add body (with truncation for very long bodies)
            body = issue.get("body") or "(No description provided)"
            output.append("")
            output.append("Description:")
            output.append("-" * 40)
            # Truncate very long bodies
            if len(body) > BODY_TRUNCATION_LIMIT:
                output.append(body[:BODY_TRUNCATION_LIMIT] + "\n\n... (truncated)")
            else:
                output.append(body)

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error getting issue: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error getting issue: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error getting issue: {e}", exc_info=True)
        return f"❌ Error getting issue: {str(e)}"


async def github_update_issue(
    repo_owner: str,
    repo_name: str,
    issue_number: int,
    title: str | None = None,
    body: str | None = None,
    state: str | None = None,
    labels: list[str] | None = None,
    assignees: list[str] | None = None,
    milestone: int | None = None,
) -> str:
    """Update a GitHub issue."""
    logger.debug(f"🚀 Updating issue #{issue_number} in {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            payload: dict[str, Any] = {}
            if title is not None:
                payload["title"] = title
            if body is not None:
                payload["body"] = body
            if state is not None:
                if state not in ["open", "closed"]:
                    return "❌ State must be 'open' or 'closed'"
                payload["state"] = state
            if labels is not None:
                payload["labels"] = labels
            if assignees is not None:
                payload["assignees"] = assignees
            if milestone is not None:
                payload["milestone"] = milestone

            if not payload:
                return "⚠️ No update parameters provided. Please specify title, body, state, labels, assignees, or milestone."

            response = await client.patch(
                f"/repos/{repo_owner}/{repo_name}/issues/{issue_number}", json=payload
            )

            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to update issue #{issue_number}: {response.status} - {error_text}"

            result = await response.json()
            logger.info(f"✅ Successfully updated issue #{issue_number}")
            return f"✅ Successfully updated issue #{result['number']}: {result['html_url']}"

    except ValueError as auth_error:
        logger.error(f"Authentication error updating issue: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error updating issue: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error updating issue #{issue_number}: {e}", exc_info=True
        )
        return f"❌ Error updating issue: {str(e)}"


async def github_edit_pr_description(
    repo_owner: str,
    repo_name: str,
    pr_number: int,
    description: str,
) -> str:
    """Edit a pull request's description/body."""
    logger.debug(f"🚀 Updating PR #{pr_number} description in {repo_owner}/{repo_name}")

    # Use the existing github_update_pr function to update just the body
    return await github_update_pr(
        repo_owner=repo_owner,
        repo_name=repo_name,
        pr_number=pr_number,
        body=description,
    )


async def github_search_issues(
    repo_owner: str,
    repo_name: str,
    query: str,
    sort: str = "created",
    order: str = "desc",
    per_page: int = 30,
    page: int = 1,
) -> str:
    """Search issues using GitHub's advanced search API.

    Supports GitHub's search qualifiers like:
    - is:issue is:open author:username
    - label:bug label:"help wanted"
    - created:2023-01-01..2023-12-31
    - updated:>2023-06-01
    - milestone:"v1.0" assignee:username
    """
    logger.debug(f"🔍 Searching issues in {repo_owner}/{repo_name}: {query}")

    try:
        async with github_client_context() as client:
            # Add repository scope to query
            search_query = f"repo:{repo_owner}/{repo_name} is:issue {query}"

            params = {
                "q": search_query,
                "sort": sort,
                "order": order,
                "per_page": per_page,
                "page": page,
            }

            response = await client.get("/search/issues", params=params)

            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to search issues: {response.status} - {error_text}"

            data = await response.json()
            issues = data.get("items", [])
            total_count = data.get("total_count", 0)

            if not issues:
                return f"No issues found matching query: {query}"

            output = [f"Search Results for '{query}' in {repo_owner}/{repo_name}:\n"]
            output.append(f"Found {total_count} total issues (showing page {page})\n")

            for issue in issues:
                # Skip pull requests
                if issue.get("pull_request"):
                    continue

                state_emoji = {"open": "🟢", "closed": "🔴"}.get(
                    issue.get("state"), "❓"
                )
                output.append(f"{state_emoji} #{issue['number']}: {issue['title']}")
                output.append(f"   Author: {issue.get('user', {}).get('login', 'N/A')}")

                # Show labels
                if issue.get("labels"):
                    label_names = [label["name"] for label in issue["labels"]]
                    output.append(f"   Labels: {', '.join(label_names)}")

                # Show assignees
                if issue.get("assignees"):
                    assignee_names = [
                        assignee["login"] for assignee in issue["assignees"]
                    ]
                    output.append(f"   Assignees: {', '.join(assignee_names)}")

                # Show milestone
                if issue.get("milestone"):
                    output.append(f"   Milestone: {issue['milestone']['title']}")

                output.append(f"   Created: {issue.get('created_at', 'N/A')}")
                output.append(
                    f"   Score: {issue.get('score', 'N/A')}"
                )  # Search relevance score
                output.append("")

            # Add pagination info
            max_results = min(1000, total_count)  # GitHub limits search to 1000 results
            if total_count > len(issues):
                max_page = (max_results + per_page - 1) // per_page
                output.append(
                    f"📄 Page {page} of {max_page} (max {max_results} results from GitHub)"
                )

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error searching issues: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error searching issues: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error searching issues: {e}", exc_info=True)
        return f"❌ Error searching issues: {str(e)}"


async def github_create_issue_from_template(
    repo_owner: str,
    repo_name: str,
    title: str,
    template_name: str = "bug_report",
    template_data: dict | None = None,
) -> str:
    """Create a GitHub issue using a predefined template.

    Templates include:
    - bug_report: Bug report with reproduction steps
    - feature_request: Feature request with use cases
    - question: Question or discussion starter
    - custom: Use template_data to define custom format
    """
    logger.debug(
        f"🚀 Creating issue from template '{template_name}' in {repo_owner}/{repo_name}"
    )

    templates = {
        "bug_report": {
            "body": f"""## Bug Report

**Describe the bug**
A clear and concise description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:
1. Go to '...'
2. Click on '....'
3. Scroll down to '....'
4. See error

**Expected behavior**
A clear and concise description of what you expected to happen.

**Additional context**
Add any other context about the problem here.

**Environment**
- OS: [e.g. iOS]
- Browser [e.g. chrome, safari]
- Version [e.g. 22]

{template_data.get("additional_info", "") if template_data else ""}
""",
            "labels": ["bug", "triage"],
        },
        "feature_request": {
            "body": f"""## Feature Request

**Is your feature request related to a problem? Please describe.**
A clear and concise description of what the problem is. Ex. I'm always frustrated when [...]

**Describe the solution you'd like**
A clear and concise description of what you want to happen.

**Describe alternatives you've considered**
A clear and concise description of any alternative solutions or features you've considered.

**Additional context**
Add any other context or screenshots about the feature request here.

{template_data.get("additional_info", "") if template_data else ""}
""",
            "labels": ["enhancement", "feature-request"],
        },
        "question": {
            "body": f"""## Question

**What would you like to know?**
Please describe your question clearly.

**Context**
Provide any relevant context that might help answer your question.

**What have you tried?**
Let us know what research or attempts you've already made.

{template_data.get("additional_info", "") if template_data else ""}
""",
            "labels": ["question"],
        },
    }

    if template_name == "custom" and template_data:
        template = {
            "body": template_data.get("body", ""),
            "labels": template_data.get("labels", []),
        }
    else:
        template = templates.get(template_name)
        if not template:
            available = ", ".join(templates.keys()) + ", custom"
            return f"❌ Unknown template '{template_name}'. Available templates: {available}"

    # Apply template data customizations
    if template_data:
        if "labels" in template_data:
            template["labels"] = template["labels"] + template_data["labels"]
        if "assignees" in template_data:
            template["assignees"] = template_data["assignees"]
        if "milestone" in template_data:
            template["milestone"] = template_data["milestone"]

    # Create issue using template
    return await github_create_issue(
        repo_owner=repo_owner,
        repo_name=repo_name,
        title=title,
        body=template["body"],
        labels=template.get("labels"),
        assignees=template.get("assignees"),
        milestone=template.get("milestone"),
    )


async def github_bulk_update_issues(
    repo_owner: str,
    repo_name: str,
    issue_numbers: list[int],
    labels: list[str] | None = None,
    assignees: list[str] | None = None,
    milestone: int | None = None,
    state: str | None = None,
) -> str:
    """Bulk update multiple issues with common properties.

    Useful for:
    - Adding labels to multiple issues
    - Assigning multiple issues to same milestone
    - Bulk closing/reopening issues
    - Mass assignment operations
    """
    logger.debug(
        f"🚀 Bulk updating {len(issue_numbers)} issues in {repo_owner}/{repo_name}"
    )

    if not issue_numbers:
        return "⚠️ No issue numbers provided for bulk update"

    if not any([labels, assignees, milestone is not None, state]):
        return "⚠️ No update parameters provided. Specify labels, assignees, milestone, or state"

    results = []
    successful_updates = 0
    failed_updates = 0

    for issue_number in issue_numbers:
        try:
            result = await github_update_issue(
                repo_owner=repo_owner,
                repo_name=repo_name,
                issue_number=issue_number,
                labels=labels,
                assignees=assignees,
                milestone=milestone,
                state=state,
            )

            if result.startswith("✅"):
                successful_updates += 1
                results.append(f"✅ Issue #{issue_number}: Updated")
            else:
                failed_updates += 1
                results.append(f"❌ Issue #{issue_number}: {result}")

        except Exception as e:
            failed_updates += 1
            results.append(f"❌ Issue #{issue_number}: Error - {str(e)}")

    # Summary
    summary = [
        f"Bulk Update Results for {len(issue_numbers)} issues:",
        f"✅ Successful: {successful_updates}",
        f"❌ Failed: {failed_updates}",
        "",
    ]

    # Detailed results (limit to first 10 for readability)
    summary.append("Details:")
    for result in results[:10]:
        summary.append(f"  {result}")

    if len(results) > 10:
        summary.append(f"  ... and {len(results) - 10} more results")

    return "\n".join(summary)


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


# ============================================================================
# Repository Settings Management (Issue #41)
# ============================================================================


async def github_get_repo_settings(
    repo_owner: str,
    repo_name: str,
) -> str:
    """Get repository settings including features, merge options, and security settings."""
    logger.debug(f"🔍 Getting repository settings for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            response = await client.get(f"/repos/{repo_owner}/{repo_name}")

            if response.status == 404:
                return f"❌ Repository {repo_owner}/{repo_name} not found"
            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to get repository settings: {response.status} - {error_text}"

            repo = await response.json()

            output = [f"Repository Settings for {repo_owner}/{repo_name}:\n"]

            # Basic info
            output.append("📋 Basic Information:")
            output.append(f"   Name: {repo.get('name')}")
            output.append(f"   Description: {repo.get('description') or '(none)'}")
            output.append(f"   Visibility: {repo.get('visibility', 'unknown')}")
            output.append(f"   Default Branch: {repo.get('default_branch')}")
            output.append(f"   Homepage: {repo.get('homepage') or '(none)'}")
            output.append("")

            # Features
            output.append("🔧 Features:")
            output.append(f"   Issues: {'✅' if repo.get('has_issues') else '❌'}")
            output.append(f"   Wiki: {'✅' if repo.get('has_wiki') else '❌'}")
            output.append(f"   Projects: {'✅' if repo.get('has_projects') else '❌'}")
            output.append(
                f"   Discussions: {'✅' if repo.get('has_discussions') else '❌'}"
            )
            output.append("")

            # Merge settings
            output.append("🔀 Merge Settings:")
            output.append(
                f"   Allow Merge Commits: {'✅' if repo.get('allow_merge_commit') else '❌'}"
            )
            output.append(
                f"   Allow Squash Merging: {'✅' if repo.get('allow_squash_merge') else '❌'}"
            )
            output.append(
                f"   Allow Rebase Merging: {'✅' if repo.get('allow_rebase_merge') else '❌'}"
            )
            output.append(
                f"   Allow Auto-merge: {'✅' if repo.get('allow_auto_merge') else '❌'}"
            )
            output.append(
                f"   Delete Branch on Merge: {'✅' if repo.get('delete_branch_on_merge') else '❌'}"
            )
            output.append(
                f"   Allow Update Branch: {'✅' if repo.get('allow_update_branch') else '❌'}"
            )
            output.append("")

            # Security
            output.append("🔒 Security:")
            output.append(f"   Archived: {'✅' if repo.get('archived') else '❌'}")
            output.append(
                f"   Web Commit Signoff Required: {'✅' if repo.get('web_commit_signoff_required') else '❌'}"
            )
            output.append("")

            # URLs
            output.append("🔗 URLs:")
            output.append(f"   HTML: {repo.get('html_url')}")
            output.append(f"   Clone: {repo.get('clone_url')}")

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error getting repo settings: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error getting repo settings: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error getting repo settings: {e}", exc_info=True)
        return f"❌ Error getting repository settings: {str(e)}"


async def github_update_repo_settings(
    repo_owner: str,
    repo_name: str,
    description: str | None = None,
    homepage: str | None = None,
    private: bool | None = None,
    visibility: str | None = None,
    has_issues: bool | None = None,
    has_projects: bool | None = None,
    has_wiki: bool | None = None,
    has_discussions: bool | None = None,
    allow_squash_merge: bool | None = None,
    allow_merge_commit: bool | None = None,
    allow_rebase_merge: bool | None = None,
    allow_auto_merge: bool | None = None,
    delete_branch_on_merge: bool | None = None,
    allow_update_branch: bool | None = None,
    squash_merge_commit_title: str | None = None,
    squash_merge_commit_message: str | None = None,
    merge_commit_title: str | None = None,
    merge_commit_message: str | None = None,
    archived: bool | None = None,
    web_commit_signoff_required: bool | None = None,
) -> str:
    """Update repository settings."""
    logger.debug(f"🚀 Updating repository settings for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            payload: dict[str, Any] = {}

            # Build payload with only provided values
            if description is not None:
                payload["description"] = description
            if homepage is not None:
                payload["homepage"] = homepage
            if private is not None:
                payload["private"] = private
            if visibility is not None:
                payload["visibility"] = visibility
            if has_issues is not None:
                payload["has_issues"] = has_issues
            if has_projects is not None:
                payload["has_projects"] = has_projects
            if has_wiki is not None:
                payload["has_wiki"] = has_wiki
            if has_discussions is not None:
                payload["has_discussions"] = has_discussions
            if allow_squash_merge is not None:
                payload["allow_squash_merge"] = allow_squash_merge
            if allow_merge_commit is not None:
                payload["allow_merge_commit"] = allow_merge_commit
            if allow_rebase_merge is not None:
                payload["allow_rebase_merge"] = allow_rebase_merge
            if allow_auto_merge is not None:
                payload["allow_auto_merge"] = allow_auto_merge
            if delete_branch_on_merge is not None:
                payload["delete_branch_on_merge"] = delete_branch_on_merge
            if allow_update_branch is not None:
                payload["allow_update_branch"] = allow_update_branch
            if squash_merge_commit_title is not None:
                payload["squash_merge_commit_title"] = squash_merge_commit_title
            if squash_merge_commit_message is not None:
                payload["squash_merge_commit_message"] = squash_merge_commit_message
            if merge_commit_title is not None:
                payload["merge_commit_title"] = merge_commit_title
            if merge_commit_message is not None:
                payload["merge_commit_message"] = merge_commit_message
            if archived is not None:
                payload["archived"] = archived
            if web_commit_signoff_required is not None:
                payload["web_commit_signoff_required"] = web_commit_signoff_required

            if not payload:
                return "⚠️ No update parameters provided"

            response = await client.patch(
                f"/repos/{repo_owner}/{repo_name}", json=payload
            )

            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to update repository settings: {response.status} - {error_text}"

            result = await response.json()
            updated_fields = list(payload.keys())
            logger.info(
                f"✅ Successfully updated repository settings: {updated_fields}"
            )
            return f"✅ Successfully updated repository settings for {result['full_name']}\nUpdated fields: {', '.join(updated_fields)}"

    except ValueError as auth_error:
        logger.error(f"Authentication error updating repo settings: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error updating repo settings: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error updating repo settings: {e}", exc_info=True)
        return f"❌ Error updating repository settings: {str(e)}"


# ============================================================================
# GitHub Actions Configuration (Issue #41)
# ============================================================================


async def github_get_actions_permissions(
    repo_owner: str,
    repo_name: str,
) -> str:
    """Get GitHub Actions permissions for a repository."""
    logger.debug(f"🔍 Getting Actions permissions for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/actions/permissions"
            )

            if response.status == 404:
                return f"❌ Repository {repo_owner}/{repo_name} not found or Actions not enabled"
            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to get Actions permissions: {response.status} - {error_text}"

            data = await response.json()

            output = [f"GitHub Actions Permissions for {repo_owner}/{repo_name}:\n"]
            output.append(f"Enabled: {'✅' if data.get('enabled') else '❌'}")
            output.append(f"Allowed Actions: {data.get('allowed_actions', 'N/A')}")

            if data.get("selected_actions_url"):
                output.append(f"Selected Actions URL: {data['selected_actions_url']}")

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error getting Actions permissions: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error getting Actions permissions: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error getting Actions permissions: {e}", exc_info=True
        )
        return f"❌ Error getting Actions permissions: {str(e)}"


async def github_update_actions_permissions(
    repo_owner: str,
    repo_name: str,
    enabled: bool | None = None,
    allowed_actions: str | None = None,
) -> str:
    """Update GitHub Actions permissions for a repository."""
    logger.debug(f"🚀 Updating Actions permissions for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            payload: dict[str, Any] = {}

            if enabled is not None:
                payload["enabled"] = enabled
            if allowed_actions is not None:
                if allowed_actions not in ["all", "local_only", "selected"]:
                    return (
                        "❌ allowed_actions must be 'all', 'local_only', or 'selected'"
                    )
                payload["allowed_actions"] = allowed_actions

            if not payload:
                return "⚠️ No update parameters provided"

            response = await client.put(
                f"/repos/{repo_owner}/{repo_name}/actions/permissions", json=payload
            )

            if response.status not in [200, 204]:
                error_text = await response.text()
                return f"❌ Failed to update Actions permissions: {response.status} - {error_text}"

            logger.info("Successfully updated Actions permissions")
            return f"✅ Successfully updated GitHub Actions permissions for {repo_owner}/{repo_name}"

    except ValueError as auth_error:
        logger.error(f"Authentication error updating Actions permissions: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error updating Actions permissions: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error updating Actions permissions: {e}", exc_info=True
        )
        return f"❌ Error updating Actions permissions: {str(e)}"


async def github_get_workflow_permissions(
    repo_owner: str,
    repo_name: str,
) -> str:
    """Get default workflow permissions for a repository."""
    logger.debug(f"🔍 Getting workflow permissions for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/actions/permissions/workflow"
            )

            if response.status == 404:
                return f"❌ Repository {repo_owner}/{repo_name} not found"
            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to get workflow permissions: {response.status} - {error_text}"

            data = await response.json()

            output = [f"Workflow Permissions for {repo_owner}/{repo_name}:\n"]
            output.append(
                f"Default Permissions: {data.get('default_workflow_permissions', 'N/A')}"
            )
            output.append(
                f"Can Approve PR Reviews: {'✅' if data.get('can_approve_pull_request_reviews') else '❌'}"
            )

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error getting workflow permissions: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error getting workflow permissions: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error getting workflow permissions: {e}", exc_info=True
        )
        return f"❌ Error getting workflow permissions: {str(e)}"


async def github_update_workflow_permissions(
    repo_owner: str,
    repo_name: str,
    default_workflow_permissions: str | None = None,
    can_approve_pull_request_reviews: bool | None = None,
) -> str:
    """Update default workflow permissions for a repository."""
    logger.debug(f"🚀 Updating workflow permissions for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            payload: dict[str, Any] = {}

            if default_workflow_permissions is not None:
                if default_workflow_permissions not in ["read", "write"]:
                    return "❌ default_workflow_permissions must be 'read' or 'write'"
                payload["default_workflow_permissions"] = default_workflow_permissions
            if can_approve_pull_request_reviews is not None:
                payload["can_approve_pull_request_reviews"] = (
                    can_approve_pull_request_reviews
                )

            if not payload:
                return "⚠️ No update parameters provided"

            response = await client.put(
                f"/repos/{repo_owner}/{repo_name}/actions/permissions/workflow",
                json=payload,
            )

            if response.status not in [200, 204]:
                error_text = await response.text()
                return f"❌ Failed to update workflow permissions: {response.status} - {error_text}"

            logger.info("Successfully updated workflow permissions")
            return f"✅ Successfully updated workflow permissions for {repo_owner}/{repo_name}"

    except ValueError as auth_error:
        logger.error(
            f"Authentication error updating workflow permissions: {auth_error}"
        )
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error updating workflow permissions: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error updating workflow permissions: {e}", exc_info=True
        )
        return f"❌ Error updating workflow permissions: {str(e)}"


# ============================================================================
# Branch Protection Rules (Issue #41)
# ============================================================================


async def github_get_branch_protection(
    repo_owner: str,
    repo_name: str,
    branch: str,
) -> str:
    """Get branch protection rules for a specific branch."""
    logger.debug(f"🔍 Getting branch protection for {repo_owner}/{repo_name}:{branch}")

    try:
        async with github_client_context() as client:
            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/branches/{branch}/protection"
            )

            if response.status == 404:
                return f"❌ Branch protection not found for {branch}. The branch may not exist or have no protection rules."
            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to get branch protection: {response.status} - {error_text}"

            data = await response.json()

            output = [f"Branch Protection for {repo_owner}/{repo_name}:{branch}\n"]

            # Required status checks
            if data.get("required_status_checks"):
                checks = data["required_status_checks"]
                output.append("✅ Required Status Checks:")
                output.append(f"   Strict: {'✅' if checks.get('strict') else '❌'}")
                contexts = checks.get("contexts", [])
                if contexts:
                    output.append(f"   Contexts: {', '.join(contexts)}")
                else:
                    output.append("   Contexts: (none)")
            else:
                output.append("❌ Required Status Checks: Not configured")

            # Required PR reviews
            if data.get("required_pull_request_reviews"):
                reviews = data["required_pull_request_reviews"]
                output.append("\n✅ Required Pull Request Reviews:")
                output.append(
                    f"   Dismiss Stale Reviews: {'✅' if reviews.get('dismiss_stale_reviews') else '❌'}"
                )
                output.append(
                    f"   Require Code Owner Reviews: {'✅' if reviews.get('require_code_owner_reviews') else '❌'}"
                )
                output.append(
                    f"   Required Approving Review Count: {reviews.get('required_approving_review_count', 0)}"
                )
                output.append(
                    f"   Require Last Push Approval: {'✅' if reviews.get('require_last_push_approval') else '❌'}"
                )
            else:
                output.append("\n❌ Required Pull Request Reviews: Not configured")

            # Enforce admins
            if data.get("enforce_admins"):
                output.append(
                    f"\n👮 Enforce Admins: {'✅' if data['enforce_admins'].get('enabled') else '❌'}"
                )

            # Restrictions
            if data.get("restrictions"):
                output.append("\n🔒 Push Restrictions: Enabled")
                restrictions = data["restrictions"]
                if restrictions.get("users"):
                    users = [u["login"] for u in restrictions["users"]]
                    output.append(f"   Users: {', '.join(users)}")
                if restrictions.get("teams"):
                    teams = [t["slug"] for t in restrictions["teams"]]
                    output.append(f"   Teams: {', '.join(teams)}")
            else:
                output.append("\n🔓 Push Restrictions: Not configured")

            # Other settings
            output.append("\n📋 Other Settings:")
            output.append(
                f"   Required Linear History: {'✅' if data.get('required_linear_history', {}).get('enabled') else '❌'}"
            )
            output.append(
                f"   Allow Force Pushes: {'✅' if data.get('allow_force_pushes', {}).get('enabled') else '❌'}"
            )
            output.append(
                f"   Allow Deletions: {'✅' if data.get('allow_deletions', {}).get('enabled') else '❌'}"
            )
            output.append(
                f"   Required Conversation Resolution: {'✅' if data.get('required_conversation_resolution', {}).get('enabled') else '❌'}"
            )
            output.append(
                f"   Lock Branch: {'✅' if data.get('lock_branch', {}).get('enabled') else '❌'}"
            )

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error getting branch protection: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error getting branch protection: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error getting branch protection: {e}", exc_info=True)
        return f"❌ Error getting branch protection: {str(e)}"


async def github_update_branch_protection(
    repo_owner: str,
    repo_name: str,
    branch: str,
    required_status_checks_strict: bool | None = None,
    required_status_checks_contexts: list[str] | None = None,
    require_pull_request_reviews: bool | None = None,
    dismiss_stale_reviews: bool | None = None,
    require_code_owner_reviews: bool | None = None,
    required_approving_review_count: int | None = None,
    require_last_push_approval: bool | None = None,
    enforce_admins: bool | None = None,
    restrict_pushes: bool | None = None,
    push_allowances_users: list[str] | None = None,
    push_allowances_teams: list[str] | None = None,
    required_linear_history: bool | None = None,
    allow_force_pushes: bool | None = None,
    allow_deletions: bool | None = None,
    block_creations: bool | None = None,
    required_conversation_resolution: bool | None = None,
    lock_branch: bool | None = None,
    allow_fork_syncing: bool | None = None,
) -> str:
    """Create or update branch protection rules."""
    logger.debug(f"🚀 Updating branch protection for {repo_owner}/{repo_name}:{branch}")

    try:
        async with github_client_context() as client:
            # Build the protection rules payload
            # GitHub API requires specific structure for branch protection
            payload: dict[str, Any] = {}

            # Required status checks
            if (
                required_status_checks_strict is not None
                or required_status_checks_contexts is not None
            ):
                payload["required_status_checks"] = {
                    "strict": required_status_checks_strict or False,
                    "contexts": required_status_checks_contexts or [],
                }
            else:
                payload["required_status_checks"] = None

            # Required pull request reviews
            if require_pull_request_reviews:
                pr_reviews: dict[str, Any] = {}
                if dismiss_stale_reviews is not None:
                    pr_reviews["dismiss_stale_reviews"] = dismiss_stale_reviews
                if require_code_owner_reviews is not None:
                    pr_reviews["require_code_owner_reviews"] = (
                        require_code_owner_reviews
                    )
                if required_approving_review_count is not None:
                    pr_reviews["required_approving_review_count"] = (
                        required_approving_review_count
                    )
                if require_last_push_approval is not None:
                    pr_reviews["require_last_push_approval"] = (
                        require_last_push_approval
                    )
                payload["required_pull_request_reviews"] = pr_reviews or None
            else:
                payload["required_pull_request_reviews"] = None

            # Enforce admins
            payload["enforce_admins"] = (
                enforce_admins if enforce_admins is not None else False
            )

            # Restrictions
            if restrict_pushes:
                restrictions: dict[str, Any] = {
                    "users": push_allowances_users or [],
                    "teams": push_allowances_teams or [],
                }
                payload["restrictions"] = restrictions
            else:
                payload["restrictions"] = None

            # Other settings
            if required_linear_history is not None:
                payload["required_linear_history"] = required_linear_history
            if allow_force_pushes is not None:
                payload["allow_force_pushes"] = allow_force_pushes
            if allow_deletions is not None:
                payload["allow_deletions"] = allow_deletions
            if block_creations is not None:
                payload["block_creations"] = block_creations
            if required_conversation_resolution is not None:
                payload["required_conversation_resolution"] = (
                    required_conversation_resolution
                )
            if lock_branch is not None:
                payload["lock_branch"] = lock_branch
            if allow_fork_syncing is not None:
                payload["allow_fork_syncing"] = allow_fork_syncing

            response = await client.put(
                f"/repos/{repo_owner}/{repo_name}/branches/{branch}/protection",
                json=payload,
            )

            if response.status not in [200, 201]:
                error_text = await response.text()
                return f"❌ Failed to update branch protection: {response.status} - {error_text}"

            logger.info(f"✅ Successfully updated branch protection for {branch}")
            return f"✅ Successfully updated branch protection for {repo_owner}/{repo_name}:{branch}"

    except ValueError as auth_error:
        logger.error(f"Authentication error updating branch protection: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error updating branch protection: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error updating branch protection: {e}", exc_info=True)
        return f"❌ Error updating branch protection: {str(e)}"


async def github_delete_branch_protection(
    repo_owner: str,
    repo_name: str,
    branch: str,
) -> str:
    """Delete branch protection rules."""
    logger.debug(f"🚀 Deleting branch protection for {repo_owner}/{repo_name}:{branch}")

    try:
        async with github_client_context() as client:
            response = await client.delete(
                f"/repos/{repo_owner}/{repo_name}/branches/{branch}/protection"
            )

            if response.status == 404:
                return f"❌ Branch protection not found for {branch}"
            if response.status != 204:
                error_text = await response.text()
                return f"❌ Failed to delete branch protection: {response.status} - {error_text}"

            logger.info(f"✅ Successfully deleted branch protection for {branch}")
            return f"✅ Successfully deleted branch protection for {repo_owner}/{repo_name}:{branch}"

    except ValueError as auth_error:
        logger.error(f"Authentication error deleting branch protection: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error deleting branch protection: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error deleting branch protection: {e}", exc_info=True)
        return f"❌ Error deleting branch protection: {str(e)}"


# ============================================================================
# Security & Compliance (Issue #41)
# ============================================================================


async def github_get_vulnerability_alerts(
    repo_owner: str,
    repo_name: str,
) -> str:
    """Check if vulnerability alerts (Dependabot alerts) are enabled."""
    logger.debug(f"🔍 Getting vulnerability alerts status for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/vulnerability-alerts"
            )

            if response.status == 204:
                return f"✅ Vulnerability alerts (Dependabot) are ENABLED for {repo_owner}/{repo_name}"
            elif response.status == 404:
                return f"❌ Vulnerability alerts (Dependabot) are DISABLED for {repo_owner}/{repo_name}"
            else:
                error_text = await response.text()
                return f"❌ Failed to check vulnerability alerts: {response.status} - {error_text}"

    except ValueError as auth_error:
        logger.error(
            f"Authentication error checking vulnerability alerts: {auth_error}"
        )
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error checking vulnerability alerts: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error checking vulnerability alerts: {e}", exc_info=True
        )
        return f"❌ Error checking vulnerability alerts: {str(e)}"


async def github_enable_vulnerability_alerts(
    repo_owner: str,
    repo_name: str,
) -> str:
    """Enable vulnerability alerts (Dependabot alerts) for a repository."""
    logger.debug(f"🚀 Enabling vulnerability alerts for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            response = await client.put(
                f"/repos/{repo_owner}/{repo_name}/vulnerability-alerts"
            )

            if response.status == 204:
                logger.info(
                    f"✅ Enabled vulnerability alerts for {repo_owner}/{repo_name}"
                )
                return f"✅ Successfully enabled vulnerability alerts (Dependabot) for {repo_owner}/{repo_name}"
            else:
                error_text = await response.text()
                return f"❌ Failed to enable vulnerability alerts: {response.status} - {error_text}"

    except ValueError as auth_error:
        logger.error(
            f"Authentication error enabling vulnerability alerts: {auth_error}"
        )
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error enabling vulnerability alerts: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error enabling vulnerability alerts: {e}", exc_info=True
        )
        return f"❌ Error enabling vulnerability alerts: {str(e)}"


async def github_disable_vulnerability_alerts(
    repo_owner: str,
    repo_name: str,
) -> str:
    """Disable vulnerability alerts (Dependabot alerts) for a repository."""
    logger.debug(f"🚀 Disabling vulnerability alerts for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            response = await client.delete(
                f"/repos/{repo_owner}/{repo_name}/vulnerability-alerts"
            )

            if response.status == 204:
                logger.info(
                    f"✅ Disabled vulnerability alerts for {repo_owner}/{repo_name}"
                )
                return f"✅ Successfully disabled vulnerability alerts (Dependabot) for {repo_owner}/{repo_name}"
            else:
                error_text = await response.text()
                return f"❌ Failed to disable vulnerability alerts: {response.status} - {error_text}"

    except ValueError as auth_error:
        logger.error(
            f"Authentication error disabling vulnerability alerts: {auth_error}"
        )
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error disabling vulnerability alerts: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error disabling vulnerability alerts: {e}", exc_info=True
        )
        return f"❌ Error disabling vulnerability alerts: {str(e)}"


async def github_get_automated_security_fixes(
    repo_owner: str,
    repo_name: str,
) -> str:
    """Check if automated security fixes (Dependabot security updates) are enabled."""
    logger.debug(
        f"🔍 Getting automated security fixes status for {repo_owner}/{repo_name}"
    )

    try:
        async with github_client_context() as client:
            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/automated-security-fixes"
            )

            if response.status == 200:
                data = await response.json()
                enabled = data.get("enabled", False)
                paused = data.get("paused", False)

                status_parts = []
                if enabled:
                    status_parts.append("ENABLED")
                else:
                    status_parts.append("DISABLED")
                if paused:
                    status_parts.append("(PAUSED)")

                return f"{'✅' if enabled else '❌'} Automated security fixes (Dependabot security updates) are {' '.join(status_parts)} for {repo_owner}/{repo_name}"
            elif response.status == 404:
                return f"❌ Automated security fixes feature not available or disabled for {repo_owner}/{repo_name}"
            else:
                error_text = await response.text()
                return f"❌ Failed to check automated security fixes: {response.status} - {error_text}"

    except ValueError as auth_error:
        logger.error(
            f"Authentication error checking automated security fixes: {auth_error}"
        )
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(
            f"Connection error checking automated security fixes: {conn_error}"
        )
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error checking automated security fixes: {e}", exc_info=True
        )
        return f"❌ Error checking automated security fixes: {str(e)}"


async def github_enable_automated_security_fixes(
    repo_owner: str,
    repo_name: str,
) -> str:
    """Enable automated security fixes (Dependabot security updates) for a repository."""
    logger.debug(f"🚀 Enabling automated security fixes for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            response = await client.put(
                f"/repos/{repo_owner}/{repo_name}/automated-security-fixes"
            )

            if response.status == 204:
                logger.info(
                    f"✅ Enabled automated security fixes for {repo_owner}/{repo_name}"
                )
                return f"✅ Successfully enabled automated security fixes (Dependabot security updates) for {repo_owner}/{repo_name}"
            else:
                error_text = await response.text()
                return f"❌ Failed to enable automated security fixes: {response.status} - {error_text}"

    except ValueError as auth_error:
        logger.error(
            f"Authentication error enabling automated security fixes: {auth_error}"
        )
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(
            f"Connection error enabling automated security fixes: {conn_error}"
        )
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error enabling automated security fixes: {e}", exc_info=True
        )
        return f"❌ Error enabling automated security fixes: {str(e)}"


async def github_disable_automated_security_fixes(
    repo_owner: str,
    repo_name: str,
) -> str:
    """Disable automated security fixes (Dependabot security updates) for a repository."""
    logger.debug(f"🚀 Disabling automated security fixes for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            response = await client.delete(
                f"/repos/{repo_owner}/{repo_name}/automated-security-fixes"
            )

            if response.status == 204:
                logger.info(
                    f"✅ Disabled automated security fixes for {repo_owner}/{repo_name}"
                )
                return f"✅ Successfully disabled automated security fixes (Dependabot security updates) for {repo_owner}/{repo_name}"
            else:
                error_text = await response.text()
                return f"❌ Failed to disable automated security fixes: {response.status} - {error_text}"

    except ValueError as auth_error:
        logger.error(
            f"Authentication error disabling automated security fixes: {auth_error}"
        )
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(
            f"Connection error disabling automated security fixes: {conn_error}"
        )
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error disabling automated security fixes: {e}", exc_info=True
        )
        return f"❌ Error disabling automated security fixes: {str(e)}"


async def github_get_security_analysis(
    repo_owner: str,
    repo_name: str,
) -> str:
    """Get comprehensive security analysis status for a repository.

    Checks and reports on:
    - Vulnerability alerts (Dependabot alerts)
    - Automated security fixes (Dependabot security updates)
    - Secret scanning (if available)
    - Repository security settings

    Each check is performed independently with graceful error handling,
    so partial failures don't prevent other checks from completing.
    """
    logger.debug(f"🔍 Getting security analysis for {repo_owner}/{repo_name}")

    output = [f"Security Analysis for {repo_owner}/{repo_name}:\n"]
    checks_succeeded = 0
    checks_failed = 0

    try:
        async with github_client_context() as client:
            # Check vulnerability alerts
            try:
                vuln_response = await client.get(
                    f"/repos/{repo_owner}/{repo_name}/vulnerability-alerts"
                )
                if vuln_response.status == 204:
                    output.append("✅ Vulnerability Alerts (Dependabot): ENABLED")
                elif vuln_response.status == 404:
                    output.append("❌ Vulnerability Alerts (Dependabot): DISABLED")
                else:
                    output.append(
                        f"⚠️ Vulnerability Alerts: Unable to determine (HTTP {vuln_response.status})"
                    )
                checks_succeeded += 1
            except Exception as e:
                logger.warning(f"Failed to check vulnerability alerts: {e}")
                output.append(f"⚠️ Vulnerability Alerts: Check failed ({e})")
                checks_failed += 1

            # Check automated security fixes
            try:
                auto_response = await client.get(
                    f"/repos/{repo_owner}/{repo_name}/automated-security-fixes"
                )
                if auto_response.status == 200:
                    auto_data = await auto_response.json()
                    enabled = auto_data.get("enabled", False)
                    paused = auto_data.get("paused", False)
                    status = "ENABLED" if enabled else "DISABLED"
                    if paused:
                        status += " (PAUSED)"
                    output.append(
                        f"{'✅' if enabled else '❌'} Automated Security Fixes: {status}"
                    )
                else:
                    output.append(
                        "❌ Automated Security Fixes: DISABLED or unavailable"
                    )
                checks_succeeded += 1
            except Exception as e:
                logger.warning(f"Failed to check automated security fixes: {e}")
                output.append(f"⚠️ Automated Security Fixes: Check failed ({e})")
                checks_failed += 1

            # Get repository settings for additional security info
            try:
                repo_response = await client.get(f"/repos/{repo_owner}/{repo_name}")
                if repo_response.status == 200:
                    repo_data = await repo_response.json()

                    # Security-related repo settings
                    output.append("\n📋 Repository Security Settings:")
                    output.append(
                        f"   Visibility: {repo_data.get('visibility', 'unknown')}"
                    )
                    output.append(
                        f"   Private: {'✅' if repo_data.get('private') else '❌'}"
                    )
                    output.append(
                        f"   Archived: {'✅' if repo_data.get('archived') else '❌'}"
                    )

                    # Check for security policy
                    security_policy = repo_data.get("security_and_analysis", {})
                    if security_policy:
                        output.append("\n🔐 Security & Analysis Features:")

                        # Secret scanning
                        secret_scanning = security_policy.get("secret_scanning", {})
                        if secret_scanning.get("status") == "enabled":
                            output.append("   ✅ Secret Scanning: ENABLED")
                        else:
                            output.append("   ❌ Secret Scanning: DISABLED")

                        # Secret scanning push protection
                        push_protection = security_policy.get(
                            "secret_scanning_push_protection", {}
                        )
                        if push_protection.get("status") == "enabled":
                            output.append(
                                "   ✅ Secret Scanning Push Protection: ENABLED"
                            )
                        else:
                            output.append(
                                "   ❌ Secret Scanning Push Protection: DISABLED"
                            )

                        # Dependabot security updates
                        dependabot = security_policy.get(
                            "dependabot_security_updates", {}
                        )
                        if dependabot.get("status") == "enabled":
                            output.append("   ✅ Dependabot Security Updates: ENABLED")
                        else:
                            output.append("   ❌ Dependabot Security Updates: DISABLED")
                else:
                    output.append(
                        f"\n⚠️ Repository Settings: Unable to fetch (HTTP {repo_response.status})"
                    )
                checks_succeeded += 1
            except Exception as e:
                logger.warning(f"Failed to get repository settings: {e}")
                output.append(f"\n⚠️ Repository Settings: Check failed ({e})")
                checks_failed += 1

            # Add summary if there were any failures
            if checks_failed > 0:
                output.append(
                    f"\n⚠️ Note: {checks_failed} of {checks_succeeded + checks_failed} checks failed"
                )

            output.append(
                f"\n🔗 Security Settings: https://github.com/{repo_owner}/{repo_name}/settings/security_analysis"
            )

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error getting security analysis: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error getting security analysis: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error getting security analysis: {e}", exc_info=True)
        return f"❌ Error getting security analysis: {str(e)}"


# ============================================================================
# Release Management Functions
# ============================================================================


async def github_create_release(
    repo_owner: str,
    repo_name: str,
    tag_name: str,
    name: str | None = None,
    body: str | None = None,
    draft: bool = False,
    prerelease: bool = False,
    target_commitish: str | None = None,
    generate_release_notes: bool = False,
) -> str:
    """Create a new GitHub release.

    Args:
        repo_owner: Repository owner
        repo_name: Repository name
        tag_name: Git tag name for the release
        name: Release title (defaults to tag_name if not provided)
        body: Release description/notes
        draft: If true, creates a draft (unpublished) release
        prerelease: If true, marks as pre-release
        target_commitish: Branch or commit SHA for the release (defaults to default branch)
        generate_release_notes: Auto-generate release notes from commits
    """
    logger.debug(f"🚀 Creating release {tag_name} for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            payload: dict[str, Any] = {
                "tag_name": tag_name,
                "draft": draft,
                "prerelease": prerelease,
            }

            if name:
                payload["name"] = name
            if body:
                payload["body"] = body
            if target_commitish:
                payload["target_commitish"] = target_commitish
            if generate_release_notes:
                payload["generate_release_notes"] = generate_release_notes

            response = await client.post(
                f"/repos/{repo_owner}/{repo_name}/releases",
                json=payload,
            )

            if response.status == 404:
                return f"❌ Repository {repo_owner}/{repo_name} not found"
            if response.status == 422:
                error_data = await response.json()
                error_msg = error_data.get("message", "Validation failed")
                return f"❌ Failed to create release: {error_msg}"
            if response.status not in (200, 201):
                error_text = await response.text()
                return f"❌ Failed to create release: {response.status} - {error_text}"

            release = await response.json()
            release_url = release.get("html_url", "")
            release_id = release.get("id", "")

            status = []
            if draft:
                status.append("draft")
            if prerelease:
                status.append("pre-release")
            status_str = f" ({', '.join(status)})" if status else ""

            return f"✅ Release {tag_name} created successfully{status_str}\n🔗 URL: {release_url}\n📋 Release ID: {release_id}"

    except ValueError as auth_error:
        logger.error(f"Authentication error creating release: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error creating release: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error creating release: {e}", exc_info=True)
        return f"❌ Error creating release: {str(e)}"


async def github_get_release(
    repo_owner: str,
    repo_name: str,
    release_id: int | None = None,
    tag: str | None = None,
) -> str:
    """Get a GitHub release by ID or tag.

    Args:
        repo_owner: Repository owner
        repo_name: Repository name
        release_id: Release ID (mutually exclusive with tag)
        tag: Tag name (mutually exclusive with release_id)
    """
    if not release_id and not tag:
        return "❌ Either release_id or tag must be provided"
    if release_id and tag:
        return "❌ Only one of release_id or tag can be provided"

    identifier = f"ID: {release_id}" if release_id else f"tag: {tag}"
    logger.debug(f"🔍 Getting release for {repo_owner}/{repo_name} ({identifier})")

    try:
        async with github_client_context() as client:
            if release_id:
                endpoint = f"/repos/{repo_owner}/{repo_name}/releases/{release_id}"
            else:
                endpoint = f"/repos/{repo_owner}/{repo_name}/releases/tags/{tag}"

            response = await client.get(endpoint)

            if response.status == 404:
                identifier = f"ID {release_id}" if release_id else f"tag '{tag}'"
                return f"❌ Release {identifier} not found in {repo_owner}/{repo_name}"
            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to get release: {response.status} - {error_text}"

            release = await response.json()

            output = [f"Release Information for {repo_owner}/{repo_name}:\n"]
            output.append(f"📦 Tag: {release.get('tag_name')}")
            output.append(f"📋 Name: {release.get('name') or '(none)'}")

            status = []
            if release.get("draft"):
                status.append("draft")
            if release.get("prerelease"):
                status.append("pre-release")
            if status:
                output.append(f"🏷️  Status: {', '.join(status)}")

            output.append(f"🔗 URL: {release.get('html_url')}")
            output.append(f"📅 Created: {release.get('created_at')}")
            output.append(
                f"📅 Published: {release.get('published_at') or 'Not published'}"
            )

            author = release.get("author", {})
            if author:
                output.append(f"👤 Author: {author.get('login')}")

            body = release.get("body")
            if body:
                output.append(f"\n📝 Description:\n{body}")

            assets = release.get("assets", [])
            if assets:
                output.append(f"\n📎 Assets ({len(assets)}):")
                for asset in assets:
                    output.append(
                        f"   • {asset.get('name')} ({asset.get('size')} bytes)"
                    )
            else:
                output.append("\n📎 Assets: None")

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error getting release: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error getting release: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error getting release: {e}", exc_info=True)
        return f"❌ Error getting release: {str(e)}"


async def github_list_releases(
    repo_owner: str,
    repo_name: str,
    per_page: int = 30,
    page: int = 1,
) -> str:
    """List releases for a repository.

    Args:
        repo_owner: Repository owner
        repo_name: Repository name
        per_page: Number of releases per page (max 100)
        page: Page number to retrieve
    """
    logger.debug(f"🔍 Listing releases for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/releases",
                params={"per_page": per_page, "page": page},
            )

            if response.status == 404:
                return f"❌ Repository {repo_owner}/{repo_name} not found"
            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to list releases: {response.status} - {error_text}"

            releases = await response.json()

            if not releases:
                return f"No releases found for {repo_owner}/{repo_name}"

            output = [f"Releases for {repo_owner}/{repo_name}:\n"]

            for release in releases:
                tag = release.get("tag_name")
                name = release.get("name") or tag
                created = release.get("created_at", "")[:10]  # Just the date

                status = []
                if release.get("draft"):
                    status.append("draft")
                if release.get("prerelease"):
                    status.append("pre-release")
                status_str = f" [{', '.join(status)}]" if status else ""

                output.append(f"📦 {tag}: {name}{status_str}")
                output.append(f"   📅 Created: {created}")
                output.append(f"   🔗 {release.get('html_url')}")
                output.append("")

            # Add pagination info
            link_header = response.headers.get("Link", "")
            if "next" in link_header or page > 1:
                output.append(f"📄 Page {page} (use page parameter to see more)")

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error listing releases: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error listing releases: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error listing releases: {e}", exc_info=True)
        return f"❌ Error listing releases: {str(e)}"


async def github_update_release(
    repo_owner: str,
    repo_name: str,
    release_id: int,
    tag_name: str | None = None,
    name: str | None = None,
    body: str | None = None,
    draft: bool | None = None,
    prerelease: bool | None = None,
    target_commitish: str | None = None,
) -> str:
    """Update a GitHub release.

    Args:
        repo_owner: Repository owner
        repo_name: Repository name
        release_id: Release ID to update
        tag_name: New tag name
        name: New release title
        body: New release description
        draft: Update draft status
        prerelease: Update pre-release status
        target_commitish: Update target commitish
    """
    logger.debug(f"🚀 Updating release {release_id} for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            # Build payload with only provided fields
            payload: dict[str, Any] = {}
            if tag_name is not None:
                payload["tag_name"] = tag_name
            if name is not None:
                payload["name"] = name
            if body is not None:
                payload["body"] = body
            if draft is not None:
                payload["draft"] = draft
            if prerelease is not None:
                payload["prerelease"] = prerelease
            if target_commitish is not None:
                payload["target_commitish"] = target_commitish

            if not payload:
                return "❌ No fields provided to update"

            response = await client.patch(
                f"/repos/{repo_owner}/{repo_name}/releases/{release_id}",
                json=payload,
            )

            if response.status == 404:
                return f"❌ Release {release_id} not found in {repo_owner}/{repo_name}"
            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to update release: {response.status} - {error_text}"

            release = await response.json()
            release_url = release.get("html_url", "")
            tag = release.get("tag_name", "")

            return f"✅ Release {tag} (ID: {release_id}) updated successfully\n🔗 URL: {release_url}"

    except ValueError as auth_error:
        logger.error(f"Authentication error updating release: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error updating release: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error updating release: {e}", exc_info=True)
        return f"❌ Error updating release: {str(e)}"


async def github_delete_release(
    repo_owner: str,
    repo_name: str,
    release_id: int,
) -> str:
    """Delete a GitHub release.

    Args:
        repo_owner: Repository owner
        repo_name: Repository name
        release_id: Release ID to delete
    """
    logger.debug(f"🗑️  Deleting release {release_id} for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            response = await client.delete(
                f"/repos/{repo_owner}/{repo_name}/releases/{release_id}"
            )

            if response.status == 404:
                return f"❌ Release {release_id} not found in {repo_owner}/{repo_name}"
            if response.status != 204:
                error_text = await response.text()
                return f"❌ Failed to delete release: {response.status} - {error_text}"

            return f"✅ Release {release_id} deleted successfully from {repo_owner}/{repo_name}"

    except ValueError as auth_error:
        logger.error(f"Authentication error deleting release: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error deleting release: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error deleting release: {e}", exc_info=True)
        return f"❌ Error deleting release: {str(e)}"


async def github_upload_release_asset(
    repo_owner: str,
    repo_name: str,
    release_id: int,
    file_path: str,
    name: str | None = None,
    label: str | None = None,
) -> str:
    """Upload a file as a release asset.

    Args:
        repo_owner: Repository owner
        repo_name: Repository name
        release_id: Release ID to upload asset to
        file_path: Local path to file to upload
        name: Asset name (defaults to filename)
        label: Asset label/description
    """
    logger.debug(
        f"📤 Uploading asset {file_path} to release {release_id} for {repo_owner}/{repo_name}"
    )

    try:
        # Validate file exists
        path = Path(file_path)
        if not path.exists():
            return f"❌ File not found: {file_path}"
        if not path.is_file():
            return f"❌ Path is not a file: {file_path}"

        # Read file content
        try:
            with open(path, "rb") as f:
                file_content = f.read()
        except Exception as read_error:
            return f"❌ Failed to read file {file_path}: {read_error}"

        # Determine asset name
        asset_name = name or path.name

        # Determine content type (handle corrupt mimetypes database gracefully)
        try:
            content_type = (
                mimetypes.guess_type(asset_name)[0] or "application/octet-stream"
            )
        except Exception:
            content_type = "application/octet-stream"

        async with github_client_context() as client:
            # First get the release to get the upload_url
            release_response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/releases/{release_id}"
            )

            if release_response.status == 404:
                return f"❌ Release {release_id} not found in {repo_owner}/{repo_name}"
            if release_response.status != 200:
                error_text = await release_response.text()
                return f"❌ Failed to get release: {release_response.status} - {error_text}"

            release = await release_response.json()
            upload_url = release.get("upload_url", "")

            if not upload_url:
                return f"❌ Release {release_id} has no upload URL"

            # Remove the {?name,label} template from upload_url
            upload_url = upload_url.split("{")[0]

            # Build query params
            params = {"name": asset_name}
            if label:
                params["label"] = label

            # Upload the asset
            response = await client.post(
                upload_url,
                params=params,
                data=file_content,
                headers={"Content-Type": content_type},
            )

            if response.status == 422:
                error_data = await response.json()
                error_msg = error_data.get("message", "Validation failed")
                return f"❌ Failed to upload asset: {error_msg}"
            if response.status not in (200, 201):
                error_text = await response.text()
                return f"❌ Failed to upload asset: {response.status} - {error_text}"

            asset = await response.json()
            asset_url = asset.get("browser_download_url", "")
            asset_id = asset.get("id", "")
            asset_size = asset.get("size", 0)

            return f"✅ Asset '{asset_name}' uploaded successfully ({asset_size} bytes)\n🔗 URL: {asset_url}\n📋 Asset ID: {asset_id}"

    except ValueError as auth_error:
        logger.error(f"Authentication error uploading asset: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error uploading asset: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error uploading asset: {e}", exc_info=True)
        return f"❌ Error uploading asset: {str(e)}"


async def github_list_release_assets(
    repo_owner: str,
    repo_name: str,
    release_id: int,
    per_page: int = 30,
    page: int = 1,
) -> str:
    """List assets for a release.

    Args:
        repo_owner: Repository owner
        repo_name: Repository name
        release_id: Release ID
        per_page: Number of assets per page (max 100)
        page: Page number to retrieve
    """
    logger.debug(
        f"🔍 Listing assets for release {release_id} in {repo_owner}/{repo_name}"
    )

    try:
        async with github_client_context() as client:
            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/releases/{release_id}/assets",
                params={"per_page": per_page, "page": page},
            )

            if response.status == 404:
                return f"❌ Release {release_id} not found in {repo_owner}/{repo_name}"
            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to list assets: {response.status} - {error_text}"

            assets = await response.json()

            if not assets:
                return f"No assets found for release {release_id}"

            output = [f"Assets for Release {release_id} in {repo_owner}/{repo_name}:\n"]

            for asset in assets:
                name = asset.get("name")
                size = asset.get("size", 0)
                downloads = asset.get("download_count", 0)
                content_type = asset.get("content_type", "unknown")
                asset_id = asset.get("id")

                # Format size nicely
                if size < 1024:
                    size_str = f"{size} B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.1f} KB"
                else:
                    size_str = f"{size / (1024 * 1024):.1f} MB"

                output.append(f"📎 {name}")
                output.append(f"   ID: {asset_id}")
                output.append(f"   Size: {size_str}")
                output.append(f"   Type: {content_type}")
                output.append(f"   Downloads: {downloads}")
                output.append(f"   URL: {asset.get('browser_download_url')}")
                output.append("")

            # Add pagination info
            link_header = response.headers.get("Link", "")
            if "next" in link_header or page > 1:
                output.append(f"📄 Page {page} (use page parameter to see more)")

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error listing assets: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error listing assets: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error listing assets: {e}", exc_info=True)
        return f"❌ Error listing assets: {str(e)}"


async def github_delete_release_asset(
    repo_owner: str,
    repo_name: str,
    asset_id: int,
) -> str:
    """Delete a release asset.

    Args:
        repo_owner: Repository owner
        repo_name: Repository name
        asset_id: Asset ID to delete
    """
    logger.debug(f"🗑️  Deleting asset {asset_id} for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            response = await client.delete(
                f"/repos/{repo_owner}/{repo_name}/releases/assets/{asset_id}"
            )

            if response.status == 404:
                return f"❌ Asset {asset_id} not found in {repo_owner}/{repo_name}"
            if response.status != 204:
                error_text = await response.text()
                return f"❌ Failed to delete asset: {response.status} - {error_text}"

            return f"✅ Asset {asset_id} deleted successfully from {repo_owner}/{repo_name}"

    except ValueError as auth_error:
        logger.error(f"Authentication error deleting asset: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error deleting asset: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error deleting asset: {e}", exc_info=True)
        return f"❌ Error deleting asset: {str(e)}"


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
