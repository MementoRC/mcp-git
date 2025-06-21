"""GitHub API operations for MCP Git Server"""

import logging
from typing import Optional

from .client import get_github_client

logger = logging.getLogger(__name__)


async def github_get_pr_checks(repo_owner: str, repo_name: str, pr_number: int, status: Optional[str] = None, conclusion: Optional[str] = None) -> str:
    """Get check runs for a pull request"""
    try:
        client = get_github_client()
        if not client:
            return "❌ GitHub token not configured. Set GITHUB_TOKEN environment variable."
        
        # First get the PR to get the head SHA
        pr_response = await client.get(f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}")
        if pr_response.status != 200:
            return f"❌ Failed to get PR #{pr_number}: {pr_response.status}"
        
        pr_data = await pr_response.json()
        head_sha = pr_data["head"]["sha"]
        
        # Get check runs for the head commit
        params = {}
        if status:
            params["status"] = status
        
        checks_response = await client.get(f"/repos/{repo_owner}/{repo_name}/commits/{head_sha}/check-runs", params=params)
        if checks_response.status != 200:
            return f"❌ Failed to get check runs: {checks_response.status}"
        
        checks_data = await checks_response.json()
        
        # Filter by conclusion if specified
        check_runs = checks_data.get("check_runs", [])
        if conclusion:
            check_runs = [run for run in check_runs if run.get("conclusion") == conclusion]
        
        # Format the output
        if not check_runs:
            return f"No check runs found for PR #{pr_number}"
        
        output = [f"Check runs for PR #{pr_number} (commit {head_sha[:8]}):\n"]
        
        for run in check_runs:
            status_emoji = {
                "completed": "✅" if run.get("conclusion") == "success" else "❌",
                "in_progress": "🔄",
                "queued": "⏳"
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
        
    except Exception as e:
        return f"❌ Error getting PR checks: {str(e)}"
    finally:
        if client and client.session:
            await client.session.close()


async def github_get_failing_jobs(repo_owner: str, repo_name: str, pr_number: int, include_logs: bool = True, include_annotations: bool = True) -> str:
    """Get detailed information about failing jobs in a PR"""
    try:
        client = get_github_client()
        if not client:
            return "❌ GitHub token not configured. Set GITHUB_TOKEN environment variable."
        
        # Get PR details
        pr_response = await client.get(f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}")
        if pr_response.status != 200:
            return f"❌ Failed to get PR #{pr_number}: {pr_response.status}"
        
        pr_data = await pr_response.json()
        head_sha = pr_data["head"]["sha"]
        
        # Get check runs and filter for failures
        checks_response = await client.get(f"/repos/{repo_owner}/{repo_name}/commits/{head_sha}/check-runs")
        if checks_response.status != 200:
            return f"❌ Failed to get check runs: {checks_response.status}"
        
        checks_data = await checks_response.json()
        
        failing_runs = [
            run for run in checks_data.get("check_runs", [])
            if run["status"] == "completed" and run.get("conclusion") in ["failure", "cancelled", "timed_out"]
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
                    annotations_response = await client.get(f"/repos/{repo_owner}/{repo_name}/check-runs/{run['id']}/annotations")
                    if annotations_response.status == 200:
                        annotations_data = await annotations_response.json()
                        if annotations_data:
                            output.append("   Annotations:")
                            for annotation in annotations_data[:5]:  # Limit to first 5
                                output.append(f"     • {annotation.get('title', 'Error')}: {annotation.get('message', 'No message')}")
                                if annotation.get("path"):
                                    output.append(f"       File: {annotation['path']} (line {annotation.get('start_line', 'unknown')})")
                except Exception:
                    pass  # Annotations might not be available
            
            # Get logs if requested (simplified)
            if include_logs and run.get("html_url"):
                output.append(f"   Details: {run['html_url']}")
            
            output.append("")
        
        return "\n".join(output)
        
    except Exception as e:
        return f"❌ Error getting failing jobs: {str(e)}"
    finally:
        if client and client.session:
            await client.session.close()


async def github_get_workflow_run(repo_owner: str, repo_name: str, run_id: int, include_logs: bool = False) -> str:
    """Get detailed workflow run information"""
    try:
        client = get_github_client()
        if not client:
            return "❌ GitHub token not configured. Set GITHUB_TOKEN environment variable."
        
        # Get workflow run details
        run_response = await client.get(f"/repos/{repo_owner}/{repo_name}/actions/runs/{run_id}")
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
        jobs_response = await client.get(f"/repos/{repo_owner}/{repo_name}/actions/runs/{run_id}/jobs")
        if jobs_response.status == 200:
            jobs_data = await jobs_response.json()
            jobs = jobs_data.get("jobs", [])
            
            if jobs:
                output.append("\nJobs:")
                for job in jobs:
                    status_emoji = {
                        "completed": "✅" if job.get("conclusion") == "success" else "❌",
                        "in_progress": "🔄",
                        "queued": "⏳"
                    }.get(job["status"], "❓")
                    
                    output.append(f"  {status_emoji} {job['name']}")
                    output.append(f"    Status: {job['status']}")
                    if job.get("conclusion"):
                        output.append(f"    Conclusion: {job['conclusion']}")
        
        return "\n".join(output)
        
    except Exception as e:
        return f"❌ Error getting workflow run: {str(e)}"
    finally:
        if client and client.session:
            await client.session.close()


async def github_get_pr_details(repo_owner: str, repo_name: str, pr_number: int, include_files: bool = False, include_reviews: bool = False) -> str:
    """Get comprehensive PR details"""
    try:
        client = get_github_client()
        if not client:
            return "❌ GitHub token not configured. Set GITHUB_TOKEN environment variable."
        
        # Get PR details
        pr_response = await client.get(f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}")
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
            output.append(f"\nDescription:\n{pr_data['body'][:500]}{'...' if len(pr_data['body']) > 500 else ''}")
        
        if pr_data.get("html_url"):
            output.append(f"\nURL: {pr_data['html_url']}")
        
        # Get files if requested
        if include_files:
            files_response = await client.get(f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}/files")
            if files_response.status == 200:
                files_data = await files_response.json()
                if files_data:
                    output.append(f"\nFiles ({len(files_data)}):")
                    for file in files_data[:10]:  # Limit to first 10
                        output.append(f"  {file['status'][0].upper()} {file['filename']} (+{file['additions']}, -{file['deletions']})")
                    if len(files_data) > 10:
                        output.append(f"  ... and {len(files_data) - 10} more files")
        
        # Get reviews if requested
        if include_reviews:
            reviews_response = await client.get(f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}/reviews")
            if reviews_response.status == 200:
                reviews_data = await reviews_response.json()
                if reviews_data:
                    output.append(f"\nReviews ({len(reviews_data)}):")
                    for review in reviews_data[-5:]:  # Show last 5
                        state_emoji = {"APPROVED": "✅", "CHANGES_REQUESTED": "❌", "COMMENTED": "💬"}.get(review.get("state"), "❓")
                        output.append(f"  {state_emoji} {review.get('user', {}).get('login', 'N/A')}: {review.get('state', 'N/A')}")
        
        return "\n".join(output)
        
    except Exception as e:
        return f"❌ Error getting PR details: {str(e)}"
    finally:
        if client and client.session:
            await client.session.close()


async def github_list_pull_requests(repo_owner: str, repo_name: str, state: str = "open", head: Optional[str] = None, base: Optional[str] = None, sort: str = "created", direction: str = "desc", per_page: int = 30, page: int = 1) -> str:
    """List pull requests for a repository"""
    try:
        client = get_github_client()
        if not client:
            return "❌ GitHub token not configured. Set GITHUB_TOKEN environment variable."
        
        params = {
            "state": state,
            "sort": sort,
            "direction": direction,
            "per_page": per_page,
            "page": page
        }
        
        if head:
            params["head"] = head
        if base:
            params["base"] = base
        
        response = await client.get(f"/repos/{repo_owner}/{repo_name}/pulls", params=params)
        if response.status != 200:
            return f"❌ Failed to list pull requests: {response.status}"
        
        prs = await response.json()
        
        if not prs:
            return f"No {state} pull requests found"
        
        output = [f"{state.title()} Pull Requests for {repo_owner}/{repo_name}:\n"]
        
        for pr in prs:
            state_emoji = {"open": "🟢", "closed": "🔴", "merged": "🟣"}.get(pr.get("state"), "❓")
            output.append(f"{state_emoji} #{pr['number']}: {pr['title']}")
            output.append(f"   Author: {pr.get('user', {}).get('login', 'N/A')}")
            output.append(f"   Base: {pr.get('base', {}).get('ref', 'N/A')} ← Head: {pr.get('head', {}).get('ref', 'N/A')}")
            output.append(f"   Created: {pr.get('created_at', 'N/A')}")
            output.append("")
        
        return "\n".join(output)
        
    except Exception as e:
        return f"❌ Error listing pull requests: {str(e)}"
    finally:
        if client and client.session:
            await client.session.close()


async def github_get_pr_status(repo_owner: str, repo_name: str, pr_number: int) -> str:
    """Get the status and check runs for a pull request"""
    try:
        client = get_github_client()
        if not client:
            return "❌ GitHub token not configured. Set GITHUB_TOKEN environment variable."
        
        # Get PR details
        pr_response = await client.get(f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}")
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
        checks_response = await client.get(f"/repos/{repo_owner}/{repo_name}/commits/{head_sha}/check-runs")
        if checks_response.status == 200:
            checks_data = await checks_response.json()
            check_runs = checks_data.get("check_runs", [])
            
            if check_runs:
                output.append("Check Runs:")
                for run in check_runs:
                    status_emoji = {
                        "completed": "✅" if run.get("conclusion") == "success" else "❌",
                        "in_progress": "🔄",
                        "queued": "⏳"
                    }.get(run["status"], "❓")
                    
                    output.append(f"  {status_emoji} {run['name']}: {run['status']}")
                    if run.get("conclusion"):
                        output.append(f"    Conclusion: {run['conclusion']}")
        
        return "\n".join(output)
        
    except Exception as e:
        return f"❌ Error getting PR status: {str(e)}"
    finally:
        if client and client.session:
            await client.session.close()


async def github_get_pr_files(repo_owner: str, repo_name: str, pr_number: int, per_page: int = 30, page: int = 1, include_patch: bool = False) -> str:
    """Get files changed in a pull request"""
    try:
        client = get_github_client()
        if not client:
            return "❌ GitHub token not configured. Set GITHUB_TOKEN environment variable."
        
        params = {
            "per_page": per_page,
            "page": page
        }
        
        response = await client.get(f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}/files", params=params)
        if response.status != 200:
            return f"❌ Failed to get PR files: {response.status}"
        
        files = await response.json()
        
        if not files:
            return f"No files found for PR #{pr_number}"
        
        output = [f"Files changed in PR #{pr_number}:\n"]
        
        total_additions = 0
        total_deletions = 0
        
        for file in files:
            status_emoji = {
                "added": "➕",
                "modified": "📝", 
                "removed": "➖",
                "renamed": "📝"
            }.get(file.get("status"), "❓")
            
            additions = file.get("additions", 0)
            deletions = file.get("deletions", 0)
            total_additions += additions
            total_deletions += deletions
            
            output.append(f"{status_emoji} {file['filename']} (+{additions}, -{deletions})")
            
            if include_patch and file.get("patch"):
                output.append(f"```diff\n{file['patch'][:500]}{'...' if len(file['patch']) > 500 else ''}\n```")
            
            output.append("")
        
        output.append(f"Total: +{total_additions}, -{total_deletions}")
        
        return "\n".join(output)
        
    except Exception as e:
        return f"❌ Error getting PR files: {str(e)}"
    finally:
        if client and client.session:
            await client.session.close()


async def github_update_pr(repo_owner: str, repo_name: str, pr_number: int, title: Optional[str] = None, body: Optional[str] = None, state: Optional[str] = None) -> str:
    """Update a pull request's title, body, or state."""
    logger.debug(f"🚀 Updating PR #{pr_number} in {repo_owner}/{repo_name}")
    
    try:
        client = get_github_client()
        if not client:
            return "❌ GitHub token not configured. Set GITHUB_TOKEN environment variable."
        
        payload = {}
        if title is not None:
            payload["title"] = title
        if body is not None:
            payload["body"] = body
        if state is not None:
            if state not in ["open", "closed"]:
                return "❌ State must be 'open' or 'closed'"
            payload["state"] = state
            
        if not payload:
            return "⚠️ No update parameters provided. Please specify title, body, or state."
        
        response = await client.patch(f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}", json=payload)
        
        if response.status != 200:
            error_text = await response.text()
            return f"❌ Failed to update PR #{pr_number}: {response.status} - {error_text}"
        
        result = await response.json()
        logger.info(f"✅ Successfully updated PR #{pr_number}")
        return f"✅ Successfully updated PR #{result['number']}: {result['html_url']}"
        
    except Exception as e:
        logger.error(f"❌ Failed to update PR #{pr_number}: {e}", exc_info=True)
        return f"❌ Error updating PR: {str(e)}"
    finally:
        if client and client.session:
            await client.session.close()


async def github_create_pr(repo_owner: str, repo_name: str, title: str, head: str, base: str, body: Optional[str] = None, draft: bool = False) -> str:
    """Create a new pull request."""
    logger.debug(f"🚀 Creating PR in {repo_owner}/{repo_name} from {head} to {base}")
    
    try:
        client = get_github_client()
        if not client:
            return "❌ GitHub token not configured. Set GITHUB_TOKEN environment variable."
        
        payload = {
            "title": title,
            "head": head,
            "base": base,
            "draft": draft
        }
        if body is not None:
            payload["body"] = body
        
        response = await client.post(f"/repos/{repo_owner}/{repo_name}/pulls", json=payload)
        
        if response.status != 201:
            error_text = await response.text()
            # Provide more helpful error for common cases
            if "No commits between" in error_text or "A pull request already exists" in error_text:
                return f"❌ Could not create PR. Reason: {error_text}"
            return f"❌ Failed to create PR: {response.status} - {error_text}"
        
        result = await response.json()
        logger.info(f"✅ Successfully created PR #{result['number']}")
        return f"✅ Successfully created PR #{result['number']}: {result['html_url']}"
        
    except Exception as e:
        logger.error(f"❌ Failed to create PR: {e}", exc_info=True)
        return f"❌ Error creating PR: {str(e)}"
    finally:
        if client and client.session:
            await client.session.close()


async def github_merge_pr(repo_owner: str, repo_name: str, pr_number: int, commit_title: Optional[str] = None, commit_message: Optional[str] = None, merge_method: str = "merge") -> str:
    """Merge a pull request."""
    logger.debug(f"🚀 Merging PR #{pr_number} in {repo_owner}/{repo_name} using '{merge_method}' method")
    
    try:
        client = get_github_client()
        if not client:
            return "❌ GitHub token not configured. Set GITHUB_TOKEN environment variable."
        
        if merge_method not in ["merge", "squash", "rebase"]:
            return "❌ merge_method must be one of 'merge', 'squash', or 'rebase'"
            
        payload = {
            "merge_method": merge_method
        }
        if commit_title:
            payload["commit_title"] = commit_title
        if commit_message:
            payload["commit_message"] = commit_message
        
        response = await client.put(f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}/merge", json=payload)
        
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
            logger.warning(f"⚠️ Merge attempt for PR #{pr_number} returned 200 OK but 'merged' is false: {result.get('message')}")
            return f"⚠️ {result.get('message', 'Merge was not successful but API returned 200 OK. Check PR status.')}"
            
    except Exception as e:
        logger.error(f"❌ Failed to merge PR #{pr_number}: {e}", exc_info=True)
        return f"❌ Error merging PR: {str(e)}"
    finally:
        if client and client.session:
            await client.session.close()


async def github_add_pr_comment(repo_owner: str, repo_name: str, pr_number: int, body: str) -> str:
    """Add a comment to a pull request."""
    logger.debug(f"🚀 Adding comment to PR #{pr_number} in {repo_owner}/{repo_name}")
    
    try:
        client = get_github_client()
        if not client:
            return "❌ GitHub token not configured. Set GITHUB_TOKEN environment variable."
        
        # Comments are added to the corresponding issue
        payload = {"body": body}
        
        response = await client.post(f"/repos/{repo_owner}/{repo_name}/issues/{pr_number}/comments", json=payload)
        
        if response.status != 201:
            error_text = await response.text()
            return f"❌ Failed to add comment: {response.status} - {error_text}"
        
        result = await response.json()
        logger.info(f"✅ Successfully added comment to PR #{pr_number}")
        return f"✅ Successfully added comment: {result['html_url']}"
        
    except Exception as e:
        logger.error(f"❌ Failed to add comment to PR #{pr_number}: {e}", exc_info=True)
        return f"❌ Error adding comment: {str(e)}"
    finally:
        if client and client.session:
            await client.session.close()


async def github_close_pr(repo_owner: str, repo_name: str, pr_number: int) -> str:
    """Close a pull request."""
    logger.debug(f"🚀 Closing PR #{pr_number} in {repo_owner}/{repo_name}")
    return await github_update_pr(repo_owner, repo_name, pr_number, state="closed")


async def github_reopen_pr(repo_owner: str, repo_name: str, pr_number: int) -> str:
    """Reopen a closed pull request."""
    logger.debug(f"🚀 Reopening PR #{pr_number} in {repo_owner}/{repo_name}")
    return await github_update_pr(repo_owner, repo_name, pr_number, state="open")