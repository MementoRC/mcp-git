import logging
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Sequence

import aiohttp
import git
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.session import ServerSession
from mcp.server.stdio import stdio_server
from mcp.types import (
    ClientCapabilities,
    GetPromptResult,
    ListRootsResult,
    Prompt,
    PromptArgument,
    PromptMessage,
    RootsCapability,
    TextContent,
    Tool,
)
from pydantic import BaseModel

def load_environment_variables(repository_path: Path | None = None):
    """Load environment variables from .env files with proper precedence.
    
    Order of precedence:
    1. Project-specific .env file (current working directory)
    2. Repository-specific .env file (if repository path provided)
    3. ClaudeCode working directory .env file (if available)
    4. System environment variables (existing behavior)
    
    Special handling for GITHUB_TOKEN:
    - Empty tokens ("") are overridden
    - Placeholder tokens are overridden (YOUR_TOKEN_HERE, REPLACE_ME, TODO, CHANGEME)
    - Whitespace-only tokens are overridden
    
    Args:
        repository_path: Optional path to the repository being used
    """
    logger = logging.getLogger(__name__)
    loaded_files = []
    
    # Common placeholder values that should be overridden
    GITHUB_TOKEN_PLACEHOLDERS = ["", "YOUR_TOKEN_HERE", "REPLACE_ME", "TODO", "CHANGEME"]
    
    def should_override_github_token(token: str | None) -> bool:
        """Check if a GitHub token should be overridden."""
        if token is None:
            return True
        if token.strip() in GITHUB_TOKEN_PLACEHOLDERS:
            return True
        if not token.strip():  # Whitespace-only
            return True
        return False
    
    # Try to load from project-specific .env file first
    project_env = Path.cwd() / ".env"
    if project_env.exists():
        try:
            # Special handling for GITHUB_TOKEN - override placeholders and empty tokens
            github_token_before = os.getenv("GITHUB_TOKEN")
            load_dotenv(project_env, override=False)  # Don't override existing env vars
            
            # If GITHUB_TOKEN should be overridden and .env file has a value, override it
            if should_override_github_token(github_token_before):
                from dotenv import dotenv_values
                env_values = dotenv_values(project_env)
                if "GITHUB_TOKEN" in env_values and env_values["GITHUB_TOKEN"] and not should_override_github_token(env_values["GITHUB_TOKEN"]):
                    os.environ["GITHUB_TOKEN"] = env_values["GITHUB_TOKEN"]
            
            loaded_files.append(str(project_env))
            logger.info(f"Loaded environment variables from project .env: {project_env}")
        except Exception as e:
            logger.warning(f"Failed to load project .env file {project_env}: {e}")
    
    # Try to load from repository-specific .env file (if repository path provided)
    if repository_path:
        repo_env = repository_path / ".env"
        if repo_env.exists() and str(repo_env) not in loaded_files:
            try:
                # Special handling for GITHUB_TOKEN - override placeholders and empty tokens
                github_token_before = os.getenv("GITHUB_TOKEN")
                load_dotenv(repo_env, override=False)  # Don't override existing env vars
                
                # If GITHUB_TOKEN should be overridden and .env file has a value, override it
                if should_override_github_token(github_token_before):
                    from dotenv import dotenv_values
                    env_values = dotenv_values(repo_env)
                    if "GITHUB_TOKEN" in env_values and env_values["GITHUB_TOKEN"] and not should_override_github_token(env_values["GITHUB_TOKEN"]):
                        os.environ["GITHUB_TOKEN"] = env_values["GITHUB_TOKEN"]
                
                loaded_files.append(str(repo_env))
                logger.info(f"Loaded environment variables from repository .env: {repo_env}")
            except Exception as e:
                logger.warning(f"Failed to load repository .env file {repo_env}: {e}")
    
    # Try to load from ClaudeCode working directory .env file
    # Check if we're in a ClaudeCode context by looking for typical ClaudeCode paths
    claude_code_dirs = []
    
    # Method 1: Check if current path contains ClaudeCode and traverse up to find it
    current_path = Path.cwd()
    if "ClaudeCode" in str(current_path):
        for parent in [current_path] + list(current_path.parents):
            if parent.name == "ClaudeCode":
                claude_code_dirs.append(parent)
                break
    
    # Method 2: Check if repository path contains ClaudeCode and traverse up to find it
    if repository_path and "ClaudeCode" in str(repository_path):
        for parent in [repository_path] + list(repository_path.parents):
            if parent.name == "ClaudeCode":
                claude_code_dirs.append(parent)
                break
    
    # Method 3: Standard Claude directories
    claude_code_dirs.extend([
        Path.home() / ".claude",
        Path("/tmp/claude-code") if Path("/tmp/claude-code").exists() else None
    ])
    
    # Remove None values and duplicates
    claude_code_dirs = list(dict.fromkeys([d for d in claude_code_dirs if d]))
    
    for claude_dir in claude_code_dirs:
        if claude_dir and claude_dir.exists():
            claude_env = claude_dir / ".env"
            if claude_env.exists():
                try:
                    # Special handling for GITHUB_TOKEN - override placeholders and empty tokens
                    github_token_before = os.getenv("GITHUB_TOKEN")
                    load_dotenv(claude_env, override=False)  # Don't override existing env vars
                    
                    # If GITHUB_TOKEN should be overridden and .env file has a value, override it
                    if should_override_github_token(github_token_before):
                        from dotenv import dotenv_values
                        env_values = dotenv_values(claude_env)
                        if "GITHUB_TOKEN" in env_values and env_values["GITHUB_TOKEN"] and not should_override_github_token(env_values["GITHUB_TOKEN"]):
                            os.environ["GITHUB_TOKEN"] = env_values["GITHUB_TOKEN"]
                    
                    if str(claude_env) not in loaded_files:
                        loaded_files.append(str(claude_env))
                        logger.info(f"Loaded environment variables from ClaudeCode .env: {claude_env}")
                except Exception as e:
                    logger.warning(f"Failed to load ClaudeCode .env file {claude_env}: {e}")
                break  # Only load from the first found ClaudeCode directory
    
    if not loaded_files:
        logger.info("No .env files found, using system environment variables only")
    else:
        logger.info(f"Environment variables loaded from: {', '.join(loaded_files)}")

@dataclass
class GitHubClient:
    """GitHub API client for interacting with GitHub"""
    token: str
    base_url: str = "https://api.github.com"
    
    def get_headers(self) -> dict:
        return {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "MCP-Git-Server/1.0"
        }
    
    async def make_request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Make authenticated request to GitHub API"""
        url = f"{self.base_url}{endpoint}"
        headers = self.get_headers()
        
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, headers=headers, **kwargs) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    raise Exception(f"GitHub API error {response.status}: {error_text}")
                return await response.json()

def get_github_client() -> GitHubClient:
    """Get GitHub client from environment variables"""
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise Exception("GITHUB_TOKEN environment variable not set")
    
    # Validate GitHub token format
    # GitHub tokens typically start with: ghp_, gho_, ghu_, ghs_, github_pat_, or ghr_ (GitHub App)
    valid_prefixes = ["ghp_", "gho_", "ghu_", "ghs_", "github_pat_", "ghr_"]
    if not any(token.startswith(prefix) for prefix in valid_prefixes):
        raise Exception("GITHUB_TOKEN appears to be invalid format")
    
    return GitHubClient(token=token)

def validate_gpg_environment() -> dict:
    """Validate GPG environment for headless operations and provide diagnostics"""
    import subprocess
    import os
    
    issues = []
    suggestions = []
    warnings = []
    
    # Check GPG_TTY environment variable
    gpg_tty = os.getenv("GPG_TTY")
    if not gpg_tty:
        issues.append("GPG_TTY environment variable not set")
        suggestions.append("Set GPG_TTY with: export GPG_TTY=$(tty) or export GPG_TTY=/dev/null for headless operation")
    else:
        warnings.append(f"GPG_TTY set to: {gpg_tty}")
    
    # Check if gpg command is available
    try:
        result = subprocess.run(["gpg", "--version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            gpg_version = result.stdout.split('\n')[0] if result.stdout else "Unknown version"
            warnings.append(f"GPG available: {gpg_version}")
        else:
            issues.append("GPG command failed")
            suggestions.append("Install GPG package or check PATH configuration")
    except FileNotFoundError:
        issues.append("GPG command not found")
        suggestions.append("Install GPG: apt-get install gnupg (Debian/Ubuntu) or brew install gnupg (macOS)")
    except subprocess.TimeoutExpired:
        issues.append("GPG command timed out")
        suggestions.append("Check GPG installation and system performance")
    except Exception as e:
        issues.append(f"GPG check failed: {str(e)}")
        suggestions.append("Verify GPG installation and configuration")
    
    # Check gpg-agent availability
    try:
        result = subprocess.run(["gpg-agent", "--version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            warnings.append("gpg-agent is available")
        else:
            issues.append("gpg-agent not responding properly")
            suggestions.append("Start gpg-agent or configure GPG for headless operation")
    except FileNotFoundError:
        issues.append("gpg-agent not found")
        suggestions.append("Install GPG suite or start gpg-agent manually")
    except subprocess.TimeoutExpired:
        issues.append("gpg-agent check timed out")
        suggestions.append("Check gpg-agent configuration and system resources")
    except Exception:
        warnings.append("gpg-agent status unknown")
    
    # Check for common GPG directories
    home_dir = os.path.expanduser("~")
    gnupg_dir = os.path.join(home_dir, ".gnupg")
    if os.path.exists(gnupg_dir):
        warnings.append(f"GPG home directory exists: {gnupg_dir}")
        # Check for keys
        try:
            result = subprocess.run(["gpg", "--list-secret-keys"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                warnings.append("Secret keys found in keyring")
            else:
                issues.append("No secret keys found")
                suggestions.append("Import or generate GPG keys for signing")
        except Exception:
            warnings.append("Could not check GPG keys")
    else:
        issues.append("GPG home directory not found")
        suggestions.append("Initialize GPG with: gpg --gen-key or import existing keys")
    
    # Determine overall status
    if not issues:
        status = "healthy"
    elif len(issues) <= 2:
        status = "warning"
    else:
        status = "critical"
    
    return {
        "status": status,
        "issues": issues,
        "suggestions": suggestions,
        "warnings": warnings,
        "environment": {
            "GPG_TTY": gpg_tty,
            "HOME": home_dir,
            "GNUPG_HOME": gnupg_dir if os.path.exists(gnupg_dir) else None
        }
    }

class GitStatus(BaseModel):
    repo_path: str

class GitDiffUnstaged(BaseModel):
    repo_path: str

class GitDiffStaged(BaseModel):
    repo_path: str

class GitDiff(BaseModel):
    repo_path: str
    target: str

class GitCommit(BaseModel):
    repo_path: str
    message: str
    gpg_sign: bool = False
    gpg_key_id: str | None = None

class GitAdd(BaseModel):
    repo_path: str
    files: list[str]

class GitReset(BaseModel):
    repo_path: str

class GitLog(BaseModel):
    repo_path: str
    max_count: int = 10
    oneline: bool = False
    graph: bool = False
    format: str | None = None

class GitCreateBranch(BaseModel):
    repo_path: str
    branch_name: str
    base_branch: str | None = None

class GitCheckout(BaseModel):
    repo_path: str
    branch_name: str

class GitShow(BaseModel):
    repo_path: str
    revision: str

class GitInit(BaseModel):
    repo_path: str

class GitPush(BaseModel):
    repo_path: str
    remote: str = "origin"
    branch: str | None = None
    force: bool = False
    set_upstream: bool = False

class GitPull(BaseModel):
    repo_path: str
    remote: str = "origin"
    branch: str | None = None

class GitDiffBranches(BaseModel):
    repo_path: str
    base_branch: str
    compare_branch: str

# GitHub API Models
class GitHubGetPRChecks(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int
    status: str | None = None  # "completed", "in_progress", "queued"
    conclusion: str | None = None  # "failure", "success", "cancelled"

class GitHubGetFailingJobs(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int
    include_logs: bool = True
    include_annotations: bool = True

class GitHubGetWorkflowRun(BaseModel):
    repo_owner: str
    repo_name: str
    run_id: int
    include_logs: bool = False

class GitHubGetPRDetails(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int
    include_files: bool = False
    include_reviews: bool = False

class GitHubListPullRequests(BaseModel):
    repo_owner: str
    repo_name: str
    state: str = "open"  # "open", "closed", "all"
    head: str | None = None  # Filter by head branch
    base: str | None = None  # Filter by base branch
    sort: str = "created"  # "created", "updated", "popularity"
    direction: str = "desc"  # "asc", "desc"
    per_page: int = 30  # Max 100
    page: int = 1

class GitHubGetPRStatus(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int

class GitHubGetPRFiles(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int
    per_page: int = 30  # Max 100, default 30 to avoid token limits
    page: int = 1
    include_patch: bool = False  # Include patch data (can be large)

class GitTools(str, Enum):
    STATUS = "git_status"
    DIFF_UNSTAGED = "git_diff_unstaged"
    DIFF_STAGED = "git_diff_staged"
    DIFF = "git_diff"
    COMMIT = "git_commit"
    ADD = "git_add"
    RESET = "git_reset"
    LOG = "git_log"
    CREATE_BRANCH = "git_create_branch"
    CHECKOUT = "git_checkout"
    SHOW = "git_show"
    INIT = "git_init"
    PUSH = "git_push"
    PULL = "git_pull"
    DIFF_BRANCHES = "git_diff_branches"
    # GitHub API Tools
    GITHUB_GET_PR_CHECKS = "github_get_pr_checks"
    GITHUB_GET_FAILING_JOBS = "github_get_failing_jobs"
    GITHUB_GET_WORKFLOW_RUN = "github_get_workflow_run"
    GITHUB_GET_PR_DETAILS = "github_get_pr_details"
    GITHUB_LIST_PULL_REQUESTS = "github_list_pull_requests"
    GITHUB_GET_PR_STATUS = "github_get_pr_status"
    GITHUB_GET_PR_FILES = "github_get_pr_files"

# Import canonical git operations from git/operations.py
from mcp_server_git.git.operations import (
    git_status,
    git_diff_unstaged,
    git_diff_staged,
    git_diff,
    git_commit,
    git_add,
    git_reset,
    git_log,
    git_create_branch,
    git_checkout,
    git_show,
    git_init,
    git_push,
    git_pull,
    git_diff_branches,
)

async def github_get_pr_checks(repo_owner: str, repo_name: str, pr_number: int, status: str | None = None, conclusion: str | None = None) -> str:
    """Get check runs for a pull request"""
    try:
        client = get_github_client()
        
        # First get the PR to get the head SHA
        pr_endpoint = f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}"
        pr_data = await client.make_request("GET", pr_endpoint)
        head_sha = pr_data["head"]["sha"]
        
        # Get check runs for the head commit
        checks_endpoint = f"/repos/{repo_owner}/{repo_name}/commits/{head_sha}/check-runs"
        params = {}
        if status:
            params["status"] = status
        
        checks_data = await client.make_request("GET", checks_endpoint, params=params)
        
        # Filter by conclusion if specified
        check_runs = checks_data["check_runs"]
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
        return f"Error getting PR checks: {str(e)}"

async def github_get_failing_jobs(repo_owner: str, repo_name: str, pr_number: int, include_logs: bool = True, include_annotations: bool = True) -> str:
    """Get detailed information about failing jobs in a PR"""
    try:
        client = get_github_client()
        
        # Get PR details
        pr_endpoint = f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}"
        pr_data = await client.make_request("GET", pr_endpoint)
        head_sha = pr_data["head"]["sha"]
        
        # Get check runs and filter for failures
        checks_endpoint = f"/repos/{repo_owner}/{repo_name}/commits/{head_sha}/check-runs"
        checks_data = await client.make_request("GET", checks_endpoint)
        
        failing_runs = [
            run for run in checks_data["check_runs"]
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
            if include_annotations and run.get("check_suite", {}).get("id"):
                annotations_endpoint = f"/repos/{repo_owner}/{repo_name}/check-runs/{run['id']}/annotations"
                try:
                    annotations_data = await client.make_request("GET", annotations_endpoint)
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
        return f"Error getting failing jobs: {str(e)}"

async def github_get_workflow_run(repo_owner: str, repo_name: str, run_id: int, include_logs: bool = False) -> str:
    """Get detailed workflow run information"""
    try:
        client = get_github_client()
        
        # Get workflow run details
        run_endpoint = f"/repos/{repo_owner}/{repo_name}/actions/runs/{run_id}"
        run_data = await client.make_request("GET", run_endpoint)
        
        # Get jobs for this run
        jobs_endpoint = f"/repos/{repo_owner}/{repo_name}/actions/runs/{run_id}/jobs"
        jobs_data = await client.make_request("GET", jobs_endpoint)
        
        output = [f"Workflow Run #{run_id}:\n"]
        output.append(f"Name: {run_data.get('name', 'Unknown')}")
        output.append(f"Status: {run_data['status']}")
        output.append(f"Conclusion: {run_data.get('conclusion', 'N/A')}")
        output.append(f"Created: {run_data.get('created_at', 'N/A')}")
        output.append(f"URL: {run_data.get('html_url', 'N/A')}")
        output.append(f"\nJobs ({len(jobs_data['jobs'])}):")
        
        for job in jobs_data["jobs"]:
            status_emoji = {
                "completed": "✅" if job.get("conclusion") == "success" else "❌",
                "in_progress": "🔄",
                "queued": "⏳"
            }.get(job["status"], "❓")
            
            output.append(f"  {status_emoji} {job['name']}")
            output.append(f"     Status: {job['status']}")
            if job.get("conclusion"):
                output.append(f"     Conclusion: {job['conclusion']}")
            
            if job["status"] == "completed" and job.get("conclusion") != "success":
                output.append(f"     Started: {job.get('started_at', 'N/A')}")
                output.append(f"     Completed: {job.get('completed_at', 'N/A')}")
                
                # Show failed steps
                if job.get("steps"):
                    failed_steps = [step for step in job["steps"] if step.get("conclusion") == "failure"]
                    if failed_steps:
                        output.append("     Failed steps:")
                        for step in failed_steps:
                            output.append(f"       • {step['name']}")
        
        return "\n".join(output)
        
    except Exception as e:
        return f"Error getting workflow run: {str(e)}"

async def github_get_pr_details(repo_owner: str, repo_name: str, pr_number: int, include_files: bool = False, include_reviews: bool = False) -> str:
    """Get comprehensive PR details"""
    try:
        client = get_github_client()
        
        # Get PR details
        pr_endpoint = f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}"
        pr_data = await client.make_request("GET", pr_endpoint)
        
        output = [f"Pull Request #{pr_number}:\n"]
        output.append(f"Title: {pr_data['title']}")
        output.append(f"Author: {pr_data['user']['login']}")
        output.append(f"State: {pr_data['state']}")
        output.append(f"Created: {pr_data['created_at']}")
        output.append(f"Updated: {pr_data['updated_at']}")
        output.append(f"Base: {pr_data['base']['ref']} ← Head: {pr_data['head']['ref']}")
        output.append(f"Commits: {pr_data['commits']}")
        output.append(f"Additions: +{pr_data['additions']}, Deletions: -{pr_data['deletions']}")
        output.append(f"Changed files: {pr_data['changed_files']}")
        
        if pr_data.get("body"):
            output.append(f"\nDescription:\n{pr_data['body'][:500]}{'...' if len(pr_data['body']) > 500 else ''}")
        
        # Get changed files if requested
        if include_files:
            files_endpoint = f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}/files"
            files_data = await client.make_request("GET", files_endpoint)
            
            output.append(f"\nChanged Files ({len(files_data)}):")
            for file in files_data[:10]:  # Limit to first 10 files
                status_emoji = {"added": "🟢", "modified": "🟡", "removed": "🔴"}.get(file["status"], "❓")
                output.append(f"  {status_emoji} {file['filename']}")
                output.append(f"     +{file['additions']} -{file['deletions']}")
        
        # Get reviews if requested
        if include_reviews:
            reviews_endpoint = f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}/reviews"
            reviews_data = await client.make_request("GET", reviews_endpoint)
            
            if reviews_data:
                output.append(f"\nReviews ({len(reviews_data)}):")
                for review in reviews_data[-5:]:  # Last 5 reviews
                    state_emoji = {"APPROVED": "✅", "CHANGES_REQUESTED": "❌", "COMMENTED": "💬"}.get(review["state"], "❓")
                    output.append(f"  {state_emoji} {review['user']['login']}: {review['state']}")
                    if review.get("body"):
                        output.append(f"     {review['body'][:100]}{'...' if len(review['body']) > 100 else ''}")
        
        return "\n".join(output)
        
    except Exception as e:
        return f"Error getting PR details: {str(e)}"

async def github_list_pull_requests(repo_owner: str, repo_name: str, state: str = "open", head: str | None = None, base: str | None = None, sort: str = "created", direction: str = "desc", per_page: int = 30, page: int = 1) -> str:
    """List pull requests for a repository"""
    try:
        client = get_github_client()
        
        # Build query parameters
        params = {
            "state": state,
            "sort": sort,
            "direction": direction,
            "per_page": min(per_page, 100),  # GitHub max is 100
            "page": page
        }
        
        if head:
            params["head"] = head
        if base:
            params["base"] = base
        
        # Get pull requests
        prs_endpoint = f"/repos/{repo_owner}/{repo_name}/pulls"
        prs_data = await client.make_request("GET", prs_endpoint, params=params)
        
        if not prs_data:
            return f"No pull requests found for {repo_owner}/{repo_name} (state: {state})"
        
        output = [f"Pull Requests for {repo_owner}/{repo_name} (state: {state}, page: {page}):\n"]
        
        for pr in prs_data:
            state_emoji = {"open": "🟢", "closed": "🔴", "merged": "🟣"}.get(pr["state"], "❓")
            
            output.append(f"{state_emoji} #{pr['number']}: {pr['title']}")
            output.append(f"   Author: {pr['user']['login']}")
            output.append(f"   State: {pr['state']}")
            if pr.get("merged_at"):
                output.append(f"   Merged: {pr['merged_at']}")
            output.append(f"   Created: {pr['created_at']}")
            output.append(f"   Base: {pr['base']['ref']} ← Head: {pr['head']['ref']}")
            output.append(f"   URL: {pr['html_url']}")
            output.append("")
        
        if len(prs_data) == per_page:
            output.append(f"Note: Showing page {page} with {per_page} results per page. Use page={page + 1} for more results.")
        
        return "\n".join(output)
        
    except Exception as e:
        return f"Error listing pull requests: {str(e)}"

async def github_get_pr_status(repo_owner: str, repo_name: str, pr_number: int) -> str:
    """Get the status/checks for a pull request"""
    try:
        client = get_github_client()
        
        # Get PR details to get the head SHA
        pr_endpoint = f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}"
        pr_data = await client.make_request("GET", pr_endpoint)
        head_sha = pr_data["head"]["sha"]
        
        # Get status for the head commit
        status_endpoint = f"/repos/{repo_owner}/{repo_name}/commits/{head_sha}/status"
        status_data = await client.make_request("GET", status_endpoint)
        
        # Get check runs for the head commit
        checks_endpoint = f"/repos/{repo_owner}/{repo_name}/commits/{head_sha}/check-runs"
        checks_data = await client.make_request("GET", checks_endpoint)
        
        output = [f"Status for PR #{pr_number} (commit {head_sha[:8]}):\n"]
        
        # Overall status
        overall_state = status_data.get("state", "unknown")
        state_emoji = {"success": "✅", "pending": "🟡", "failure": "❌", "error": "❌"}.get(overall_state, "❓")
        output.append(f"Overall Status: {state_emoji} {overall_state}")
        output.append(f"Total Statuses: {status_data.get('total_count', 0)}")
        
        # Individual statuses
        if status_data.get("statuses"):
            output.append("\nStatuses:")
            for status in status_data["statuses"]:
                status_emoji = {"success": "✅", "pending": "🟡", "failure": "❌", "error": "❌"}.get(status["state"], "❓")
                output.append(f"  {status_emoji} {status.get('context', 'Unknown')}: {status['state']}")
                if status.get("description"):
                    output.append(f"     {status['description']}")
        
        # Check runs
        if checks_data.get("check_runs"):
            output.append(f"\nCheck Runs ({len(checks_data['check_runs'])}):")
            for run in checks_data["check_runs"]:
                status_emoji = {
                    "completed": "✅" if run.get("conclusion") == "success" else "❌",
                    "in_progress": "🔄",
                    "queued": "⏳"
                }.get(run["status"], "❓")
                
                output.append(f"  {status_emoji} {run['name']}: {run['status']}")
                if run.get("conclusion"):
                    output.append(f"     Conclusion: {run['conclusion']}")
        
        return "\n".join(output)
        
    except Exception as e:
        return f"Error getting PR status: {str(e)}"

async def github_get_pr_files(repo_owner: str, repo_name: str, pr_number: int, per_page: int = 30, page: int = 1, include_patch: bool = False) -> str:
    """Get files changed in a pull request with pagination to handle large responses"""
    try:
        client = get_github_client()
        
        # Build query parameters for pagination
        params = {
            "per_page": min(per_page, 100),  # GitHub max is 100
            "page": page
        }
        
        # Get changed files
        files_endpoint = f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}/files"
        files_data = await client.make_request("GET", files_endpoint, params=params)
        
        if not files_data:
            return f"No files found for PR #{pr_number}"
        
        output = [f"Files changed in PR #{pr_number} (page {page}, {len(files_data)} files):\n"]
        
        total_additions = 0
        total_deletions = 0
        
        for file in files_data:
            status_emoji = {
                "added": "🟢", 
                "modified": "🟡", 
                "removed": "🔴", 
                "renamed": "🔄"
            }.get(file["status"], "❓")
            
            output.append(f"{status_emoji} {file['filename']}")
            output.append(f"   Status: {file['status']}")
            output.append(f"   Changes: +{file['additions']} -{file['deletions']}")
            
            total_additions += file["additions"]
            total_deletions += file["deletions"]
            
            if file.get("previous_filename") and file["status"] == "renamed":
                output.append(f"   Previous: {file['previous_filename']}")
            
            # Include patch data only if requested and for small files
            if include_patch and file.get("patch") and len(file["patch"]) < 2000:
                output.append("   Patch preview (first 2000 chars):")
                output.append(f"   {file['patch'][:2000]}{'...' if len(file['patch']) > 2000 else ''}")
            
            output.append("")
        
        # Summary
        output.append(f"Summary for page {page}:")
        output.append(f"  Files: {len(files_data)}")
        output.append(f"  Total additions: +{total_additions}")
        output.append(f"  Total deletions: -{total_deletions}")
        
        # Pagination hint
        if len(files_data) == per_page:
            output.append(f"\nNote: This is page {page} with {per_page} files per page.")
            output.append(f"Use page={page + 1} to see more files.")
            output.append("Tip: Reduce per_page or disable include_patch to avoid token limits.")
        
        return "\n".join(output)
        
    except Exception as e:
        return f"Error getting PR files: {str(e)}"

async def serve(repository: Path | None) -> None:
    logger = logging.getLogger(__name__)
    
    # Load environment variables from .env files with proper precedence
    load_environment_variables(repository)

    if repository is not None:
        try:
            git.Repo(repository)
            logger.info(f"Using repository at {repository}")
        except git.InvalidGitRepositoryError:
            logger.error(f"{repository} is not a valid Git repository")
            return

    server = Server("mcp-git")

    @server.list_prompts()
    async def list_prompts() -> list[Prompt]:
        """Return available git workflow prompts"""
        return [
            Prompt(
                name="commit-message",
                description="Generate a conventional commit message based on staged changes",
                arguments=[
                    PromptArgument(
                        name="changes",
                        description="Description of the changes made",
                        required=True
                    ),
                    PromptArgument(
                        name="type",
                        description="Type of change (feat, fix, docs, refactor, test, chore)",
                        required=False
                    ),
                    PromptArgument(
                        name="scope",
                        description="Scope of the change (component/area affected)",
                        required=False
                    )
                ]
            ),
            Prompt(
                name="pr-description",
                description="Generate a comprehensive pull request description",
                arguments=[
                    PromptArgument(
                        name="title",
                        description="Title of the pull request",
                        required=True
                    ),
                    PromptArgument(
                        name="changes",
                        description="Summary of changes made",
                        required=True
                    ),
                    PromptArgument(
                        name="breaking",
                        description="Any breaking changes (optional)",
                        required=False
                    )
                ]
            ),
            Prompt(
                name="release-notes",
                description="Generate release notes from commit history",
                arguments=[
                    PromptArgument(
                        name="version",
                        description="Version being released",
                        required=True
                    ),
                    PromptArgument(
                        name="commits",
                        description="Commit history since last release",
                        required=True
                    ),
                    PromptArgument(
                        name="previous_version",
                        description="Previous version (optional)",
                        required=False
                    )
                ]
            ),
            Prompt(
                name="code-review",
                description="Generate a code review prompt for a diff",
                arguments=[
                    PromptArgument(
                        name="diff",
                        description="The diff to review",
                        required=True
                    ),
                    PromptArgument(
                        name="context",
                        description="Additional context about the changes",
                        required=False
                    )
                ]
            ),
            Prompt(
                name="merge-conflict-resolution",
                description="Help resolve merge conflicts systematically",
                arguments=[
                    PromptArgument(
                        name="conflicts",
                        description="The conflicted files or sections",
                        required=True
                    ),
                    PromptArgument(
                        name="branch_info",
                        description="Information about the branches being merged",
                        required=False
                    )
                ]
            ),
            Prompt(
                name="git-workflow-guide",
                description="Guide for Git workflow best practices",
                arguments=[
                    PromptArgument(
                        name="workflow_type",
                        description="Type of workflow (gitflow, github-flow, gitlab-flow)",
                        required=False
                    ),
                    PromptArgument(
                        name="team_size",
                        description="Size of the development team",
                        required=False
                    )
                ]
            ),
            Prompt(
                name="branch-strategy",
                description="Recommend branching strategy for a project",
                arguments=[
                    PromptArgument(
                        name="project_type",
                        description="Type of project (library, application, microservice)",
                        required=True
                    ),
                    PromptArgument(
                        name="deployment_frequency",
                        description="How often deployments happen",
                        required=False
                    )
                ]
            ),
            Prompt(
                name="git-troubleshooting",
                description="Help troubleshoot common Git issues",
                arguments=[
                    PromptArgument(
                        name="issue",
                        description="Description of the Git issue encountered",
                        required=True
                    ),
                    PromptArgument(
                        name="git_status",
                        description="Output of git status command",
                        required=False
                    )
                ]
            ),
            Prompt(
                name="changelog-generation",
                description="Generate changelog from commit history",
                arguments=[
                    PromptArgument(
                        name="commits",
                        description="Commit history to include",
                        required=True
                    ),
                    PromptArgument(
                        name="format",
                        description="Changelog format (keep-a-changelog, conventional)",
                        required=False
                    )
                ]
            ),
            Prompt(
                name="rebase-interactive",
                description="Guide for interactive rebase operations",
                arguments=[
                    PromptArgument(
                        name="commits",
                        description="Commits to be rebased",
                        required=True
                    ),
                    PromptArgument(
                        name="goal",
                        description="What you want to achieve with the rebase",
                        required=False
                    )
                ]
            ),
            # GitHub Actions Prompts
            Prompt(
                name="github-actions-failure-analysis",
                description="Analyze GitHub Actions failures and suggest fixes",
                arguments=[
                    PromptArgument(
                        name="failure_logs",
                        description="Raw failure logs from GitHub Actions",
                        required=True
                    ),
                    PromptArgument(
                        name="workflow_file",
                        description="YAML workflow file content",
                        required=False
                    ),
                    PromptArgument(
                        name="changed_files",
                        description="Files changed in the PR",
                        required=False
                    )
                ]
            ),
            Prompt(
                name="ci-failure-root-cause",
                description="Identify root cause of CI failures and provide solutions",
                arguments=[
                    PromptArgument(
                        name="error_message",
                        description="Primary error message",
                        required=True
                    ),
                    PromptArgument(
                        name="stack_trace",
                        description="Full stack trace if available",
                        required=False
                    ),
                    PromptArgument(
                        name="environment_info",
                        description="CI environment details",
                        required=False
                    )
                ]
            ),
            Prompt(
                name="pr-readiness-assessment",
                description="Assess PR readiness and suggest improvements",
                arguments=[
                    PromptArgument(
                        name="pr_details",
                        description="PR information including changes",
                        required=True
                    ),
                    PromptArgument(
                        name="ci_status",
                        description="Current CI status",
                        required=False
                    ),
                    PromptArgument(
                        name="review_comments",
                        description="Existing review comments",
                        required=False
                    )
                ]
            )
        ]

    @server.get_prompt()
    async def get_prompt(name: str, arguments: dict[str, str] | None) -> GetPromptResult:
        """Generate specific git workflow prompts"""
        args = arguments or {}
        
        match name:
            case "commit-message":
                changes = args.get("changes", "")
                commit_type = args.get("type", "")
                scope = args.get("scope", "")
                
                type_guidance = ""
                if not commit_type:
                    type_guidance = """
First, determine the appropriate type:
- feat: A new feature
- fix: A bug fix
- docs: Documentation only changes
- style: Changes that do not affect the meaning of the code (white-space, formatting, etc)
- refactor: A code change that neither fixes a bug nor adds a feature
- test: Adding missing tests or correcting existing tests
- chore: Changes to the build process or auxiliary tools and libraries

"""
                
                scope_guidance = ""
                if not scope:
                    scope_guidance = "Consider adding a scope to indicate the area of change (e.g., auth, api, ui, docs).\n\n"
                
                prompt_text = f"""{type_guidance}{scope_guidance}Generate a conventional commit message for these changes:

{changes}

The commit message should follow this format:
{commit_type + '(' + scope + ')' if commit_type and scope else '<type>(<scope>)' if not commit_type else commit_type + '(<scope>)' if scope else '<type>' if not commit_type else commit_type}: <subject>

<optional body>

<optional footer>

Guidelines:
- Subject line should be 50 characters or less
- Use imperative mood ("Add feature" not "Added feature")
- Don't end the subject line with a period
- Body should explain what and why, not how
- Reference any relevant issues in the footer"""

                return GetPromptResult(
                    description="Conventional commit message generator",
                    messages=[
                        PromptMessage(
                            role="user",
                            content=TextContent(type="text", text=prompt_text)
                        )
                    ]
                )
            
            case "pr-description":
                title = args.get("title", "")
                changes = args.get("changes", "")
                breaking = args.get("breaking", "")
                
                breaking_section = f"\n## ⚠️ Breaking Changes\n{breaking}\n" if breaking else ""
                
                prompt_text = f"""Generate a comprehensive pull request description for:

**Title:** {title}

**Changes Made:**
{changes}
{breaking_section}
The PR description should include:

1. **Summary** - Brief overview of what this PR does
2. **Changes** - Detailed list of changes made
3. **Testing** - How the changes were tested
4. **Screenshots/Videos** - If applicable (placeholder)
5. **Breaking Changes** - If any (you mentioned: {breaking or 'none'})
6. **Checklist** - Standard PR checklist

Format using GitHub-flavored markdown with appropriate headers, lists, and formatting."""

                return GetPromptResult(
                    description="Pull request description generator",
                    messages=[
                        PromptMessage(
                            role="user",
                            content=TextContent(type="text", text=prompt_text)
                        )
                    ]
                )
            
            case "release-notes":
                version = args.get("version", "")
                commits = args.get("commits", "")
                previous_version = args.get("previous_version", "")
                
                version_info = f"from {previous_version} to {version}" if previous_version else f"for version {version}"
                
                prompt_text = f"""Generate release notes {version_info} based on this commit history:

{commits}

The release notes should include:

1. **Version Header** - Clear version and date
2. **Summary** - High-level overview of the release
3. **Features** - New features added (from feat: commits)
4. **Bug Fixes** - Issues resolved (from fix: commits)
5. **Improvements** - Enhancements and refactoring
6. **Breaking Changes** - Any breaking changes
7. **Dependencies** - Updated dependencies if applicable
8. **Contributors** - Acknowledge contributors

Use a clear, professional format suitable for users and developers. Group changes by type and importance."""

                return GetPromptResult(
                    description="Release notes generator",
                    messages=[
                        PromptMessage(
                            role="user",
                            content=TextContent(type="text", text=prompt_text)
                        )
                    ]
                )
            
            case "code-review":
                diff = args.get("diff", "")
                context = args.get("context", "")
                
                context_section = f"\n**Context:**\n{context}\n" if context else ""
                
                prompt_text = f"""Perform a thorough code review of this diff:

```diff
{diff}
```
{context_section}
Please review for:

1. **Code Quality**
   - Readability and maintainability
   - Consistent coding style and conventions
   - Appropriate abstractions and patterns

2. **Functionality**  
   - Logic correctness
   - Edge cases handling
   - Performance implications

3. **Security**
   - Input validation
   - Authentication/authorization
   - Data exposure risks

4. **Testing**
   - Test coverage adequacy
   - Test quality and scenarios

5. **Documentation**
   - Code comments where needed
   - API documentation updates
   - README or other doc updates

Provide specific, actionable feedback with line references where possible."""

                return GetPromptResult(
                    description="Code review assistant",
                    messages=[
                        PromptMessage(
                            role="user",
                            content=TextContent(type="text", text=prompt_text)
                        )
                    ]
                )
            
            case "merge-conflict-resolution":
                conflicts = args.get("conflicts", "")
                branch_info = args.get("branch_info", "")
                
                branch_section = f"\n**Branch Information:**\n{branch_info}\n" if branch_info else ""
                
                prompt_text = f"""Help resolve these merge conflicts systematically:

```
{conflicts}
```
{branch_section}
Provide guidance on:

1. **Understanding the Conflict**
   - What changes are conflicting
   - Why the conflict occurred
   - Context of each conflicting section

2. **Resolution Strategy**
   - Which changes to keep/combine
   - How to merge conflicting logic
   - Testing approach after resolution

3. **Step-by-Step Resolution**
   - Specific commands to run
   - How to edit conflicted files
   - Verification steps

4. **Prevention**
   - How to avoid similar conflicts
   - Better merge practices
   - Communication strategies

Be specific about which sections to keep, modify, or combine."""

                return GetPromptResult(
                    description="Merge conflict resolution guide",
                    messages=[
                        PromptMessage(
                            role="user",
                            content=TextContent(type="text", text=prompt_text)
                        )
                    ]
                )
            
            case "git-workflow-guide":
                workflow_type = args.get("workflow_type", "")
                team_size = args.get("team_size", "")
                
                workflow_context = f" for {workflow_type}" if workflow_type else ""
                team_context = f" with a team of {team_size}" if team_size else ""
                
                prompt_text = f"""Provide a comprehensive Git workflow guide{workflow_context}{team_context}.

Include:

1. **Workflow Overview**
   - Main branches and their purposes
   - Branch naming conventions
   - When to create branches

2. **Development Process**
   - Feature development workflow
   - Code review process
   - Integration and deployment

3. **Branch Management**
   - Creating and managing branches
   - Merging strategies
   - Cleanup procedures

4. **Best Practices**
   - Commit message conventions
   - When to rebase vs merge
   - Handling conflicts

5. **Team Collaboration**
   - Communication protocols
   - Review assignments
   - Release coordination

6. **Tools and Automation**
   - Helpful Git aliases
   - CI/CD integration
   - Automated checks

Make it practical with specific commands and examples."""

                return GetPromptResult(
                    description="Git workflow best practices guide",
                    messages=[
                        PromptMessage(
                            role="user",
                            content=TextContent(type="text", text=prompt_text)
                        )
                    ]
                )
            
            case "branch-strategy":
                project_type = args.get("project_type", "")
                deployment_frequency = args.get("deployment_frequency", "")
                
                deploy_context = f" with {deployment_frequency} deployments" if deployment_frequency else ""
                
                prompt_text = f"""Recommend an optimal branching strategy for a {project_type} project{deploy_context}.

Consider:

1. **Project Characteristics**
   - Type: {project_type}
   - Deployment frequency: {deployment_frequency or 'not specified'}

2. **Strategy Recommendation**
   - Recommended workflow (Git Flow, GitHub Flow, GitLab Flow, etc.)
   - Rationale for the choice
   - Adaptations for project specifics

3. **Branch Structure**
   - Main branches and their purposes
   - Supporting branches and lifecycle
   - Protection rules and policies

4. **Release Management**
   - How releases are managed
   - Hotfix procedures
   - Version tagging strategy

5. **Team Workflow**
   - Developer workflow steps
   - Code review integration
   - Continuous integration setup

6. **Migration Plan**
   - If changing from existing strategy
   - Steps to implement
   - Training requirements

Provide specific, actionable recommendations."""

                return GetPromptResult(
                    description="Branching strategy recommendation",
                    messages=[
                        PromptMessage(
                            role="user",
                            content=TextContent(type="text", text=prompt_text)
                        )
                    ]
                )
            
            case "git-troubleshooting":
                issue = args.get("issue", "")
                git_status = args.get("git_status", "")
                
                status_section = f"\n**Git Status Output:**\n```\n{git_status}\n```\n" if git_status else ""
                
                prompt_text = f"""Help troubleshoot this Git issue:

**Issue Description:**
{issue}
{status_section}
Provide troubleshooting guidance:

1. **Issue Analysis**
   - What likely caused this issue
   - Understanding the current state
   - Potential risks of different solutions

2. **Diagnostic Commands**
   - Commands to run to gather more information
   - What to look for in the output
   - How to interpret the results

3. **Solution Options**
   - Primary recommended solution
   - Alternative approaches
   - When to use each approach

4. **Step-by-Step Resolution**
   - Exact commands to run
   - Expected output at each step
   - How to verify the fix

5. **Prevention**
   - How to avoid this issue in the future
   - Best practices to follow
   - Warning signs to watch for

Be specific about commands and include safety considerations."""

                return GetPromptResult(
                    description="Git troubleshooting assistant",
                    messages=[
                        PromptMessage(
                            role="user",
                            content=TextContent(type="text", text=prompt_text)
                        )
                    ]
                )
            
            case "changelog-generation":
                commits = args.get("commits", "")
                format_type = args.get("format", "keep-a-changelog")
                
                prompt_text = f"""Generate a changelog in {format_type} format from this commit history:

{commits}

Requirements:

1. **Format:** {format_type}
   - Use appropriate formatting conventions
   - Include proper headers and structure
   - Follow semantic versioning principles

2. **Categorization:**
   - Added (new features)
   - Changed (changes in existing functionality)
   - Deprecated (soon-to-be removed features)
   - Removed (removed features)
   - Fixed (bug fixes)
   - Security (security improvements)

3. **Content Guidelines:**
   - Write for end users, not developers
   - Focus on impact and benefits
   - Group related changes together
   - Use clear, non-technical language where possible

4. **Structure:**
   - Proper version headers
   - Date information
   - Logical grouping of changes
   - Consistent formatting

Transform technical commit messages into user-friendly changelog entries."""

                return GetPromptResult(
                    description="Changelog generator",
                    messages=[
                        PromptMessage(
                            role="user",
                            content=TextContent(type="text", text=prompt_text)
                        )
                    ]
                )
            
            case "rebase-interactive":
                commits = args.get("commits", "")
                goal = args.get("goal", "")
                
                goal_section = f"\n**Goal:** {goal}\n" if goal else ""
                
                prompt_text = f"""Guide me through an interactive rebase for these commits:

{commits}
{goal_section}
Provide comprehensive rebase guidance:

1. **Rebase Planning**
   - Analysis of current commits
   - Recommended rebase actions
   - Potential risks and considerations

2. **Interactive Rebase Commands**
   - pick: keep commit as-is
   - reword: change commit message
   - edit: modify commit content
   - squash: combine with previous commit
   - fixup: combine with previous, discard message
   - drop: remove commit entirely

3. **Step-by-Step Process**
   - Command to start interactive rebase
   - How to edit the rebase todo list
   - Resolving conflicts during rebase
   - Completing the rebase process

4. **Best Practices**
   - When to use each rebase action
   - Maintaining commit history clarity
   - Testing between rebase steps
   - Safety with force pushing

5. **Troubleshooting**
   - Common rebase issues
   - How to abort if needed
   - Recovering from mistakes

Include specific commands and editor instructions."""

                return GetPromptResult(
                    description="Interactive rebase guide",
                    messages=[
                        PromptMessage(
                            role="user",
                            content=TextContent(type="text", text=prompt_text)
                        )
                    ]
                )
            
            case "github-actions-failure-analysis":
                failure_logs = args.get("failure_logs", "")
                workflow_file = args.get("workflow_file", "")
                changed_files = args.get("changed_files", "")
                
                workflow_section = f"\n**Workflow File:**\n```yaml\n{workflow_file}\n```\n" if workflow_file else ""
                files_section = f"\n**Changed Files:**\n{changed_files}\n" if changed_files else ""
                
                prompt_text = f"""Analyze this GitHub Actions failure and provide actionable solutions:

**Failure Logs:**
```
{failure_logs}
```
{workflow_section}{files_section}
Please provide:

1. **Root Cause Analysis**
   - Identify the primary cause of the failure
   - Analyze error patterns and symptoms
   - Consider environmental factors

2. **Immediate Fixes**
   - Specific code changes needed
   - Configuration adjustments
   - Dependency updates

3. **Workflow Improvements**
   - Better error handling
   - More robust testing
   - Optimization opportunities

4. **Prevention Strategies**
   - How to avoid similar failures
   - Monitoring and alerting improvements
   - Documentation updates

5. **Testing Plan**
   - How to verify the fix
   - Additional test cases needed
   - Regression prevention

Focus on actionable, specific solutions with code examples where applicable."""

                return GetPromptResult(
                    description="GitHub Actions failure analysis",
                    messages=[
                        PromptMessage(
                            role="user",
                            content=TextContent(type="text", text=prompt_text)
                        )
                    ]
                )
            
            case "ci-failure-root-cause":
                error_message = args.get("error_message", "")
                stack_trace = args.get("stack_trace", "")
                environment_info = args.get("environment_info", "")
                
                stack_section = f"\n**Stack Trace:**\n```\n{stack_trace}\n```\n" if stack_trace else ""
                env_section = f"\n**Environment:**\n{environment_info}\n" if environment_info else ""
                
                prompt_text = f"""Identify the root cause of this CI failure and provide solutions:

**Error Message:**
```
{error_message}
```
{stack_section}{env_section}
Provide comprehensive analysis:

1. **Error Classification**
   - Type of error (compilation, runtime, test, dependency, etc.)
   - Severity level and impact
   - Frequency (new vs recurring)

2. **Root Cause Investigation**
   - Primary cause identification
   - Contributing factors
   - Underlying system issues

3. **Solution Strategy**
   - Immediate hotfix (if applicable)
   - Proper long-term solution
   - Alternative approaches

4. **Implementation Steps**
   - Exact code changes needed
   - Configuration modifications
   - Deployment considerations

5. **Verification Process**
   - How to test the fix
   - Success criteria
   - Rollback plan if needed

6. **Prevention Measures**
   - Code quality improvements
   - Better testing strategies
   - Monitoring enhancements

Be specific about technical solutions and include code examples."""

                return GetPromptResult(
                    description="CI failure root cause analysis",
                    messages=[
                        PromptMessage(
                            role="user",
                            content=TextContent(type="text", text=prompt_text)
                        )
                    ]
                )
            
            case "pr-readiness-assessment":
                pr_details = args.get("pr_details", "")
                ci_status = args.get("ci_status", "")
                review_comments = args.get("review_comments", "")
                
                ci_section = f"\n**CI Status:**\n{ci_status}\n" if ci_status else ""
                reviews_section = f"\n**Review Comments:**\n{review_comments}\n" if review_comments else ""
                
                prompt_text = f"""Assess this pull request's readiness for review and merge:

**PR Details:**
{pr_details}
{ci_section}{reviews_section}
Provide comprehensive readiness assessment:

1. **Code Quality Assessment**
   - Code style and conventions
   - Architecture and design patterns
   - Performance considerations
   - Security implications

2. **Completeness Check**
   - Feature implementation completeness
   - Edge cases coverage
   - Error handling adequacy
   - Documentation updates

3. **Testing Analysis**
   - Test coverage assessment
   - Test quality and scenarios
   - Integration test considerations
   - Performance test needs

4. **CI/CD Status**
   - Build and test results
   - Static analysis findings
   - Security scans results
   - Deployment readiness

5. **Review Readiness**
   - PR description quality
   - Commit message standards
   - Change scope appropriateness
   - Reviewer assignment suggestions

6. **Merge Readiness**
   - Branch protection compliance
   - Merge strategy recommendation
   - Post-merge considerations
   - Rollback planning

7. **Action Items**
   - Issues that must be resolved
   - Nice-to-have improvements
   - Follow-up tasks

Provide specific, actionable recommendations for each area."""

                return GetPromptResult(
                    description="PR readiness assessment",
                    messages=[
                        PromptMessage(
                            role="user",
                            content=TextContent(type="text", text=prompt_text)
                        )
                    ]
                )
            
            case _:
                raise ValueError(f"Unknown prompt: {name}")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name=GitTools.STATUS,
                description="Shows the working tree status",
                inputSchema=GitStatus.model_json_schema(),
            ),
            Tool(
                name=GitTools.DIFF_UNSTAGED,
                description="Shows changes in the working directory that are not yet staged",
                inputSchema=GitDiffUnstaged.model_json_schema(),
            ),
            Tool(
                name=GitTools.DIFF_STAGED,
                description="Shows changes that are staged for commit",
                inputSchema=GitDiffStaged.model_json_schema(),
            ),
            Tool(
                name=GitTools.DIFF,
                description="Shows differences between branches or commits",
                inputSchema=GitDiff.model_json_schema(),
            ),
            Tool(
                name=GitTools.COMMIT,
                description="Records changes to the repository",
                inputSchema=GitCommit.model_json_schema(),
            ),
            Tool(
                name=GitTools.ADD,
                description="Adds file contents to the staging area",
                inputSchema=GitAdd.model_json_schema(),
            ),
            Tool(
                name=GitTools.RESET,
                description="Unstages all staged changes",
                inputSchema=GitReset.model_json_schema(),
            ),
            Tool(
                name=GitTools.LOG,
                description="Shows the commit logs",
                inputSchema=GitLog.model_json_schema(),
            ),
            Tool(
                name=GitTools.CREATE_BRANCH,
                description="Creates a new branch from an optional base branch",
                inputSchema=GitCreateBranch.model_json_schema(),
            ),
            Tool(
                name=GitTools.CHECKOUT,
                description="Switches branches",
                inputSchema=GitCheckout.model_json_schema(),
            ),
            Tool(
                name=GitTools.SHOW,
                description="Shows the contents of a commit",
                inputSchema=GitShow.model_json_schema(),
            ),
            Tool(
                name=GitTools.INIT,
                description="Initialize a new Git repository",
                inputSchema=GitInit.model_json_schema(),
            ),
            Tool(
                name=GitTools.PUSH,
                description="Push commits to remote repository",
                inputSchema=GitPush.model_json_schema(),
            ),
            Tool(
                name=GitTools.PULL,
                description="Pull changes from remote repository",
                inputSchema=GitPull.model_json_schema(),
            ),
            Tool(
                name=GitTools.DIFF_BRANCHES,
                description="Show differences between two branches",
                inputSchema=GitDiffBranches.model_json_schema(),
            ),
            # GitHub API Tools
            Tool(
                name=GitTools.GITHUB_GET_PR_CHECKS,
                description="Get check runs for a pull request",
                inputSchema=GitHubGetPRChecks.model_json_schema(),
            ),
            Tool(
                name=GitTools.GITHUB_GET_FAILING_JOBS,
                description="Get detailed information about failing jobs in a PR",
                inputSchema=GitHubGetFailingJobs.model_json_schema(),
            ),
            Tool(
                name=GitTools.GITHUB_GET_WORKFLOW_RUN,
                description="Get detailed workflow run information",
                inputSchema=GitHubGetWorkflowRun.model_json_schema(),
            ),
            Tool(
                name=GitTools.GITHUB_GET_PR_DETAILS,
                description="Get comprehensive PR details",
                inputSchema=GitHubGetPRDetails.model_json_schema(),
            ),
            Tool(
                name=GitTools.GITHUB_LIST_PULL_REQUESTS,
                description="List pull requests for a repository with filtering and pagination",
                inputSchema=GitHubListPullRequests.model_json_schema(),
            ),
            Tool(
                name=GitTools.GITHUB_GET_PR_STATUS,
                description="Get the status and check runs for a pull request",
                inputSchema=GitHubGetPRStatus.model_json_schema(),
            ),
            Tool(
                name=GitTools.GITHUB_GET_PR_FILES,
                description="Get files changed in a pull request with pagination support",
                inputSchema=GitHubGetPRFiles.model_json_schema(),
            )
        ]

    async def list_repos() -> Sequence[str]:
        async def by_roots() -> Sequence[str]:
            if not isinstance(server.request_context.session, ServerSession):
                raise TypeError("server.request_context.session must be a ServerSession")

            if not server.request_context.session.check_client_capability(
                ClientCapabilities(roots=RootsCapability())
            ):
                return []

            roots_result: ListRootsResult = await server.request_context.session.list_roots()
            logger.debug(f"Roots result: {roots_result}")
            repo_paths = []
            for root in roots_result.roots:
                path = root.uri.path
                try:
                    git.Repo(path)
                    repo_paths.append(str(path))
                except git.InvalidGitRepositoryError:
                    pass
            return repo_paths

        def by_commandline() -> Sequence[str]:
            return [str(repository)] if repository is not None else []

        cmd_repos = by_commandline()
        root_repos = await by_roots()
        return [*root_repos, *cmd_repos]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        """Enhanced tool call handler with comprehensive error isolation to prevent server crashes"""
        import time
        import subprocess
        import os
        
        logger = logging.getLogger(__name__)
        request_id = os.urandom(4).hex()
        start_time = time.time()
        
        logger.info(f"🔧 [{request_id}] Tool call: {name}")
        logger.debug(f"🔧 [{request_id}] Arguments: {arguments}")
        
        try:
            # GitHub API tools don't need repo_path
            if name in [GitTools.GITHUB_GET_PR_CHECKS, GitTools.GITHUB_GET_FAILING_JOBS, 
                       GitTools.GITHUB_GET_WORKFLOW_RUN, GitTools.GITHUB_GET_PR_DETAILS,
                       GitTools.GITHUB_LIST_PULL_REQUESTS, GitTools.GITHUB_GET_PR_STATUS,
                       GitTools.GITHUB_GET_PR_FILES]:
                # Handle GitHub API tools that don't require repo_path
                pass
            else:
                # All other tools require repo_path
                repo_path = Path(arguments["repo_path"])
                
                # Handle git init separately since it doesn't require an existing repo
                if name == GitTools.INIT:
                    result = git_init(str(repo_path))
                    duration = time.time() - start_time
                    logger.info(f"✅ [{request_id}] Tool '{name}' completed in {duration:.2f}s")
                    return [TextContent(
                        type="text",
                        text=result
                    )]
                    
                # For all other commands, we need an existing repo
                try:
                    repo = git.Repo(repo_path)
                except git.InvalidGitRepositoryError as e:
                    duration = time.time() - start_time
                    logger.error(f"📁 [{request_id}] Invalid git repository at {repo_path}: {e}")
                    return [TextContent(
                        type="text",
                        text=f"❌ Invalid git repository at {repo_path}. Please ensure the path contains a valid git repository."
                    )]

            match name:
                case GitTools.STATUS:
                    status = git_status(repo)
                    return [TextContent(
                        type="text",
                        text=f"Repository status:\n{status}"
                    )]

                case GitTools.DIFF_UNSTAGED:
                    diff = git_diff_unstaged(repo)
                    return [TextContent(
                        type="text",
                        text=f"Unstaged changes:\n{diff}"
                    )]

                case GitTools.DIFF_STAGED:
                    diff = git_diff_staged(repo)
                    return [TextContent(
                        type="text",
                        text=f"Staged changes:\n{diff}"
                    )]

                case GitTools.DIFF:
                    diff = git_diff(repo, arguments["target"])
                    return [TextContent(
                        type="text",
                        text=f"Diff with {arguments['target']}:\n{diff}"
                    )]

                case GitTools.COMMIT:
                    result = git_commit(
                        repo, 
                        arguments["message"],
                        arguments.get("gpg_sign", False),
                        arguments.get("gpg_key_id")
                    )
                    return [TextContent(
                        type="text",
                        text=result
                    )]

                case GitTools.ADD:
                    result = git_add(repo, arguments["files"])
                    return [TextContent(
                        type="text",
                        text=result
                    )]

                case GitTools.RESET:
                    result = git_reset(repo)
                    return [TextContent(
                        type="text",
                        text=result
                    )]

                case GitTools.LOG:
                    log = git_log(
                        repo, 
                        arguments.get("max_count", 10),
                        arguments.get("oneline", False),
                        arguments.get("graph", False),
                        arguments.get("format")
                    )
                    return [TextContent(
                        type="text",
                        text="Commit history:\n" + "\n".join(log)
                    )]

                case GitTools.CREATE_BRANCH:
                    result = git_create_branch(
                        repo,
                        arguments["branch_name"],
                        arguments.get("base_branch")
                    )
                    return [TextContent(
                        type="text",
                        text=result
                    )]

                case GitTools.CHECKOUT:
                    result = git_checkout(repo, arguments["branch_name"])
                    return [TextContent(
                        type="text",
                        text=result
                    )]

                case GitTools.SHOW:
                    result = git_show(repo, arguments["revision"])
                    return [TextContent(
                        type="text",
                        text=result
                    )]

                case GitTools.PUSH:
                    result = git_push(
                        repo,
                        arguments.get("remote", "origin"),
                        arguments.get("branch"),
                        arguments.get("force", False),
                        arguments.get("set_upstream", False)
                    )
                    return [TextContent(
                        type="text",
                        text=result
                    )]

                case GitTools.PULL:
                    result = git_pull(
                        repo,
                        arguments.get("remote", "origin"),
                        arguments.get("branch")
                    )
                    return [TextContent(
                        type="text",
                        text=result
                    )]

                case GitTools.DIFF_BRANCHES:
                    result = git_diff_branches(
                        repo,
                        arguments["base_branch"],
                        arguments["compare_branch"]
                    )
                    return [TextContent(
                        type="text",
                        text=result
                    )]

                # GitHub API Tools
                case GitTools.GITHUB_GET_PR_CHECKS:
                    result = await github_get_pr_checks(
                        arguments["repo_owner"],
                        arguments["repo_name"],
                        arguments["pr_number"],
                        arguments.get("status"),
                        arguments.get("conclusion")
                    )
                    return [TextContent(
                        type="text",
                        text=result
                    )]

                case GitTools.GITHUB_GET_FAILING_JOBS:
                    result = await github_get_failing_jobs(
                        arguments["repo_owner"],
                        arguments["repo_name"],
                        arguments["pr_number"],
                        arguments.get("include_logs", True),
                        arguments.get("include_annotations", True)
                    )
                    return [TextContent(
                        type="text",
                        text=result
                    )]

                case GitTools.GITHUB_GET_WORKFLOW_RUN:
                    result = await github_get_workflow_run(
                        arguments["repo_owner"],
                        arguments["repo_name"],
                        arguments["run_id"],
                        arguments.get("include_logs", False)
                    )
                    return [TextContent(
                        type="text",
                        text=result
                    )]

                case GitTools.GITHUB_GET_PR_DETAILS:
                    result = await github_get_pr_details(
                        arguments["repo_owner"],
                        arguments["repo_name"],
                        arguments["pr_number"],
                        arguments.get("include_files", False),
                        arguments.get("include_reviews", False)
                    )
                    return [TextContent(
                        type="text",
                        text=result
                    )]

                case GitTools.GITHUB_LIST_PULL_REQUESTS:
                    result = await github_list_pull_requests(
                        arguments["repo_owner"],
                        arguments["repo_name"],
                        arguments.get("state", "open"),
                        arguments.get("head"),
                        arguments.get("base"),
                        arguments.get("sort", "created"),
                        arguments.get("direction", "desc"),
                        arguments.get("per_page", 30),
                        arguments.get("page", 1)
                    )
                    return [TextContent(
                        type="text",
                        text=result
                    )]

                case GitTools.GITHUB_GET_PR_STATUS:
                    result = await github_get_pr_status(
                        arguments["repo_owner"],
                        arguments["repo_name"],
                        arguments["pr_number"]
                    )
                    return [TextContent(
                        type="text",
                        text=result
                    )]

                case GitTools.GITHUB_GET_PR_FILES:
                    result = await github_get_pr_files(
                        arguments["repo_owner"],
                        arguments["repo_name"],
                        arguments["pr_number"],
                        arguments.get("per_page", 30),
                        arguments.get("page", 1),
                        arguments.get("include_patch", False)
                    )
                    return [TextContent(
                        type="text",
                        text=result
                    )]

                case _:
                    duration = time.time() - start_time
                    logger.error(f"❓ [{request_id}] Unknown tool '{name}' after {duration:.2f}s")
                    return [TextContent(
                        type="text",
                        text=f"❌ Unknown tool: {name}. Available tools: {', '.join([tool.value for tool in GitTools])}"
                    )]

        except subprocess.TimeoutExpired as e:
            duration = time.time() - start_time
            logger.error(f"⏰ [{request_id}] Tool '{name}' timed out after {duration:.2f}s: {e}")
            return [TextContent(
                type="text", 
                text=f"⏰ Tool '{name}' timed out. Operation may be too slow or system is under heavy load. Please try again."
            )]
            
        except subprocess.SubprocessError as e:
            duration = time.time() - start_time
            logger.error(f"🔧 [{request_id}] Tool '{name}' subprocess error after {duration:.2f}s: {e}")
            return [TextContent(
                type="text", 
                text=f"🔧 Subprocess error in '{name}': {str(e)}. Check system configuration and permissions."
            )]
            
        except git.exc.GitCommandError as e:
            duration = time.time() - start_time
            logger.error(f"📝 [{request_id}] Tool '{name}' git error after {duration:.2f}s: {e}")
            return [TextContent(
                type="text", 
                text=f"📝 Git error in '{name}': {str(e)}. Verify repository state and git configuration."
            )]
            
        except PermissionError as e:
            duration = time.time() - start_time
            logger.error(f"🔒 [{request_id}] Tool '{name}' permission error after {duration:.2f}s: {e}")
            return [TextContent(
                type="text", 
                text=f"🔒 Permission error in '{name}': {str(e)}. Check file and directory permissions."
            )]
            
        except FileNotFoundError as e:
            duration = time.time() - start_time
            logger.error(f"📁 [{request_id}] Tool '{name}' file not found after {duration:.2f}s: {e}")
            return [TextContent(
                type="text", 
                text=f"📁 File not found in '{name}': {str(e)}. Verify paths and file existence."
            )]
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"❌ [{request_id}] Tool '{name}' unexpected error after {duration:.2f}s: {e}", exc_info=True)
            # Critical: Never let any exception crash the server
            return [TextContent(
                type="text", 
                text=f"❌ Unexpected error in '{name}': {str(e)}. The server remains operational. Check logs for details."
            )]
        
        # This should not be reached, but added for completeness
        duration = time.time() - start_time
        logger.info(f"✅ [{request_id}] Tool '{name}' completed successfully in {duration:.2f}s")

    options = server.create_initialization_options()
    
    # Enhanced server run with transport-level error recovery
    try:
        async with stdio_server() as (read_stream, write_stream):
            logger.info("🔗 STDIO server connected, starting main loop with enhanced error handling...")
            
            # Run server with error isolation - CRITICAL: raise_exceptions=False prevents crashes
            await server.run(read_stream, write_stream, options, raise_exceptions=False)
            
    except KeyboardInterrupt:
        logger.info("⌨️ Server interrupted by user")
        raise
    except Exception as e:
        error_msg = str(e).lower()
        
        # Enhanced error categorization to prevent crashes
        if "transport" in error_msg and "closed" in error_msg:
            logger.error(f"🔌 Transport error: {e}")
            logger.info("🔌 This is often due to client disconnection or tool execution failure - server recovering gracefully")
        elif "gpg" in error_msg:
            logger.error(f"🔒 GPG-related server error: {e}")
            logger.info("🔒 GPG configuration issue detected - server remains operational")
        elif "notification" in error_msg and "validation" in error_msg:
            logger.warning(f"🔔 Notification validation error: {e}")
            logger.info("🔔 Client notification issue - server continues normally")
        else:
            logger.error(f"💥 Server error: {e}", exc_info=True)
            logger.info("💥 Unexpected server error - attempting graceful recovery")
        
        # Don't re-raise - let server shutdown gracefully instead of crashing


# Alias for backward compatibility
main = serve
