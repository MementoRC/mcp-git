import asyncio
import logging
import os
import re
import signal
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Sequence, Tuple, Optional

import aiohttp
from git import Repo, GitCommandError, InvalidGitRepositoryError
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.session import ServerSession
import subprocess  # Added this import

# Logging and metrics
from .logging_config import configure_logging
from .metrics import global_metrics_collector

# Notification middleware for handling cancelled notifications
from .core.notification_interceptor import wrap_read_stream, log_interception_stats
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

# Heartbeat/session management
from .session import HeartbeatManager, SessionManager

# Import GitHub API functions
from .github.api import (
    github_get_pr_checks,
    github_get_failing_jobs,
    github_get_workflow_run,
    github_get_pr_details,
    github_list_pull_requests,
    github_get_pr_status,
    github_get_pr_files,
    github_update_pr,
    github_create_pr,
    github_merge_pr,
    github_add_pr_comment,
    github_close_pr,
    github_reopen_pr,
)


def load_environment_variables(repository_path: Path | None = None):
    """Load environment variables from .env files with proper precedence.

    Order of precedence:
    1. Project-specific .env file (current working directory)
    2. Repository-specific .env file (if repository path provided)
    3. ClaudeCode working directory .env file (if available)
    4. System environment variables (existing behavior)

    Note: Empty or whitespace-only environment variables will be overridden by .env file values
    to handle cases where MCP clients set empty environment variables.

    Args:
        repository_path: Optional path to the repository being used
    """
    logger = logging.getLogger(__name__)
    loaded_files = []

    def should_override(key: str, value: str) -> bool:
        """Determine if an environment variable should be overridden.

        Returns True if the environment variable is empty, whitespace-only,
        or appears to be a placeholder value that should be replaced.
        """
        if not value or value.isspace():
            return True
        # Check for common placeholder patterns
        placeholder_patterns = ["YOUR_TOKEN_HERE", "REPLACE_ME", "TODO", "CHANGEME"]
        if any(pattern.lower() in value.lower() for pattern in placeholder_patterns):
            return True
        return False

    def load_env_with_smart_override(env_file: Path) -> None:
        """Load environment file with smart override logic for empty/placeholder values."""
        # First load without override to get new variables
        load_dotenv(env_file, override=False)

        # Then check for empty/placeholder environment variables and override them
        from dotenv import dotenv_values

        env_vars = dotenv_values(env_file)

        for key, value in env_vars.items():
            existing_value = os.getenv(key, "")
            if should_override(key, existing_value) and value:
                os.environ[key] = value
                logger.debug(
                    f"Overrode empty/placeholder {key} with value from {env_file}"
                )

    # Try to load from project-specific .env file first
    project_env = Path.cwd() / ".env"
    if project_env.exists():
        try:
            load_env_with_smart_override(project_env)
            loaded_files.append(str(project_env))
            logger.info(
                f"Loaded environment variables from project .env: {project_env}"
            )
        except Exception as e:
            logger.warning(f"Failed to load project .env file {project_env}: {e}")

    # Try to load from repository-specific .env file (if repository path provided)
    if repository_path:
        repo_env = repository_path / ".env"
        if repo_env.exists() and str(repo_env) not in loaded_files:
            try:
                load_env_with_smart_override(repo_env)
                loaded_files.append(str(repo_env))
                logger.info(
                    f"Loaded environment variables from repository .env: {repo_env}"
                )
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
    claude_code_dirs.extend(
        [
            Path.home() / ".claude",
            Path("/tmp/claude-code") if Path("/tmp/claude-code").exists() else None,
        ]
    )

    # Remove None values and duplicates
    claude_code_dirs = list(dict.fromkeys([d for d in claude_code_dirs if d]))

    for claude_dir in claude_code_dirs:
        if claude_dir and claude_dir.exists():
            claude_env = claude_dir / ".env"
            if claude_env.exists():
                try:
                    load_env_with_smart_override(claude_env)
                    if str(claude_env) not in loaded_files:
                        loaded_files.append(str(claude_env))
                        logger.info(
                            f"Loaded environment variables from ClaudeCode .env: {claude_env}"
                        )
                except Exception as e:
                    logger.warning(
                        f"Failed to load ClaudeCode .env file {claude_env}: {e}"
                    )
                break  # Only load from the first found ClaudeCode directory

    if not loaded_files:
        logger.info("No .env files found, using system environment variables only")
    else:
        logger.info(f"Environment variables loaded from: {', '.join(loaded_files)}")

    # Log the status of critical environment variables (for debugging)
    critical_vars = ["GITHUB_TOKEN", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"]
    for var in critical_vars:
        value = os.getenv(var)
        if value is not None:
            logger.debug(f"{var} is set (length: {len(value)})")
        else:
            logger.debug(f"{var} is not set or empty")


@dataclass
class GitHubClient:
    """GitHub API client for interacting with GitHub REST API v4 (2022-11-28)"""

    token: str
    base_url: str = "https://api.github.com"
    api_version: str = "2022-11-28"

    def get_headers(self) -> dict:
        return {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github+json",  # Current stable format
            "X-GitHub-Api-Version": self.api_version,  # Latest stable API version
            "User-Agent": "MCP-Git-Server/1.0",
        }

    async def make_request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Make authenticated request to GitHub API with proper error handling"""
        logger = logging.getLogger(__name__)
        url = f"{self.base_url}{endpoint}"
        headers = self.get_headers()

        logger.debug(f"🌐 Making {method} request to {endpoint}")

        # Configure timeout and connection settings
        timeout = aiohttp.ClientTimeout(total=60, connect=15, sock_read=30)
        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=30,
            keepalive_timeout=30,
            enable_cleanup_closed=True,
        )

        # Retry logic for connection issues
        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession(
                    timeout=timeout, connector=connector
                ) as session:
                    async with session.request(
                        method, url, headers=headers, **kwargs
                    ) as response:
                        logger.debug(
                            f"📡 Response status: {response.status} for {endpoint}"
                        )

                        if response.status >= 400:
                            error_text = await response.text()

                            # Handle specific GitHub API errors
                            if response.status == 401:
                                logger.error(
                                    f"🔑 GitHub API authentication failed for {endpoint}"
                                )
                                raise Exception(
                                    "GitHub API authentication failed (401): Check GITHUB_TOKEN"
                                )
                            elif response.status == 403:
                                rate_limit_remaining = response.headers.get(
                                    "X-RateLimit-Remaining", "unknown"
                                )
                                if rate_limit_remaining == "0":
                                    reset_time = response.headers.get(
                                        "X-RateLimit-Reset", "unknown"
                                    )
                                    logger.error(
                                        f"⏰ GitHub API rate limit exceeded for {endpoint}, resets at: {reset_time}"
                                    )
                                    raise Exception(
                                        f"GitHub API rate limit exceeded (403). Resets at: {reset_time}"
                                    )
                                else:
                                    logger.error(
                                        f"🚫 GitHub API forbidden for {endpoint}"
                                    )
                                    raise Exception(
                                        "GitHub API forbidden (403): Insufficient permissions or secondary rate limit"
                                    )
                            elif response.status == 404:
                                logger.debug(f"📡 404 Not Found for {endpoint}")
                                raise Exception(
                                    f"GitHub API resource not found (404): {endpoint}"
                                )
                            elif response.status == 422:
                                logger.error(
                                    f"❌ GitHub API validation failed for {endpoint}: {error_text}"
                                )
                                raise Exception(
                                    f"GitHub API validation failed (422): {error_text}"
                                )
                            else:
                                logger.error(
                                    f"❌ GitHub API error {response.status} for {endpoint}: {error_text}"
                                )
                                raise Exception(
                                    f"GitHub API error {response.status}: {error_text}"
                                )

                        result = await response.json()
                        logger.debug(f"✅ Successful request to {endpoint}")

                        # Validate response structure for common API endpoints
                        if result is None:
                            logger.warning(f"⚠️ GitHub API returned None for {endpoint}")
                            return {}

                        return result

            except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = 2**attempt  # Exponential backoff
                    logger.warning(
                        f"🔄 Connection failed (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s: {e}"
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(f"🌐 Max retries exceeded for {endpoint}: {e}")
                    raise
            except Exception as e:
                logger.error(f"❌ Unexpected error making request to {endpoint}: {e}")
                raise

        # This should never be reached due to the exception handling above
        if last_error:
            raise last_error


def get_github_client() -> GitHubClient:
    """Get GitHub client from environment variables"""
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise Exception("GITHUB_TOKEN environment variable not set")
    if not token.startswith(("ghp_", "github_pat_", "gho_", "ghu_", "ghs_")):
        raise Exception("GITHUB_TOKEN appears to be invalid format")
    return GitHubClient(token=token)


def validate_git_security_config(repo: Repo) -> dict:
    """Validate Git security configuration for the repository.

    Returns:
        dict: Validation results with security warnings and recommendations
    """
    warnings = []
    recommendations = []
    config_status = {}

    try:
        # Check GPG signing configuration
        try:
            gpg_sign = repo.config_reader().get_value("commit", "gpgsign")
        except Exception:
            gpg_sign = None
        try:
            signing_key = repo.config_reader().get_value("user", "signingkey")
        except Exception:
            signing_key = None

        config_status["gpg_signing_enabled"] = gpg_sign == "true"
        config_status["signing_key_configured"] = signing_key is not None
        config_status["signing_key"] = signing_key

        if not config_status["gpg_signing_enabled"]:
            warnings.append("GPG signing is not enabled for this repository")
            recommendations.append(
                "Enable GPG signing with: git config commit.gpgsign true"
            )

        if not config_status["signing_key_configured"]:
            warnings.append("No GPG signing key configured")
            recommendations.append(
                "Set signing key with: git config user.signingkey YOUR_KEY_ID"
            )

        # Check if signing key is configured (don't enforce specific key)
        # Allow any valid GPG key to be used

        # Check user configuration
        try:
            user_name = repo.config_reader().get_value("user", "name")
        except Exception:
            user_name = None
        try:
            user_email = repo.config_reader().get_value("user", "email")
        except Exception:
            user_email = None

        config_status["user_name"] = user_name
        config_status["user_email"] = user_email

        if not user_name:
            warnings.append("Git user name not configured")
            recommendations.append(
                "Set user name with: git config user.name 'Your Name'"
            )

        if not user_email:
            warnings.append("Git user email not configured")
            recommendations.append(
                "Set user email with: git config user.email 'your@email.com'"
            )

    except Exception as e:
        warnings.append(f"Error checking Git configuration: {str(e)}")

    return {
        "status": "secure" if not warnings else "warnings",
        "warnings": warnings,
        "recommendations": recommendations,
        "config": config_status,
    }


def enforce_secure_git_config(repo: Repo, strict_mode: bool = True) -> str:
    """Enforce secure Git configuration for the repository.

    Args:
        repo: Git repository object
        strict_mode: If True, automatically fix insecure configurations

    Returns:
        str: Status message about configuration changes
    """
    validation = validate_git_security_config(repo)
    messages = []

    if validation["status"] == "secure":
        return "✅ Git security configuration is already secure"

    if not strict_mode:
        warning_msg = "⚠️  Git security warnings detected:\n"
        for warning in validation["warnings"]:
            warning_msg += f"  - {warning}\n"
        warning_msg += "\nRecommendations:\n"
        for rec in validation["recommendations"]:
            warning_msg += f"  - {rec}\n"
        return warning_msg

    # Strict mode: automatically fix security issues
    try:
        with repo.config_writer() as config:
            # Enable GPG signing
            if not validation["config"]["gpg_signing_enabled"]:
                config.set_value("commit", "gpgsign", "true")
                messages.append("✅ Enabled GPG signing")

            # Set signing key from environment or detect available key
            current_key = validation["config"]["signing_key"]
            if not current_key:
                # Try environment variable first
                env_key = os.getenv("GPG_SIGNING_KEY")
                if env_key:
                    config.set_value("user", "signingkey", env_key)
                    messages.append(
                        f"✅ Set signing key to {env_key} (from GPG_SIGNING_KEY env var)"
                    )
                else:
                    # Auto-detect available GPG keys
                    try:
                        import subprocess

                        result = subprocess.run(
                            ["gpg", "--list-secret-keys", "--keyid-format=LONG"],
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )
                        if result.returncode == 0 and "sec" in result.stdout:
                            # Extract first available key
                            lines = result.stdout.split("\n")
                            for line in lines:
                                if "sec" in line and "/" in line:
                                    key_id = line.split("/")[1].split()[0]
                                    config.set_value("user", "signingkey", key_id)
                                    messages.append(
                                        f"✅ Auto-detected and set signing key to {key_id}"
                                    )
                                    break
                        else:
                            messages.append(
                                "⚠️  No GPG keys found - please set up GPG or set GPG_SIGNING_KEY env var"
                            )
                    except Exception as e:
                        messages.append(f"⚠️  Could not auto-detect GPG key: {e}")

            # Set user info from environment or use defaults
            if not validation["config"]["user_name"]:
                env_name = os.getenv("GIT_USER_NAME", "Claude Developer")
                config.set_value("user", "name", env_name)
                messages.append(f"✅ Set user name to '{env_name}'")

            if not validation["config"]["user_email"]:
                env_email = os.getenv("GIT_USER_EMAIL", "claude.dev@example.com")
                config.set_value("user", "email", env_email)
                messages.append(f"✅ Set user email to '{env_email}'")

        messages.append("🔒 Repository security configuration enforced")

    except Exception as e:
        messages.append(f"❌ Failed to enforce security configuration: {str(e)}")

    return "\n".join(messages)


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
        suggestions.append(
            "Set GPG_TTY with: export GPG_TTY=$(tty) or export GPG_TTY=/dev/null for headless operation"
        )
    else:
        warnings.append(f"GPG_TTY set to: {gpg_tty}")

    # Check if gpg command is available
    try:
        result = subprocess.run(
            ["gpg", "--version"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            gpg_version = (
                result.stdout.split("\n")[0] if result.stdout else "Unknown version"
            )
            warnings.append(f"GPG available: {gpg_version}")
        else:
            issues.append("GPG command failed")
            suggestions.append("Install GPG package or check PATH configuration")
    except FileNotFoundError:
        issues.append("GPG command not found")
        suggestions.append(
            "Install GPG: apt-get install gnupg (Debian/Ubuntu) or brew install gnupg (macOS)"
        )
    except subprocess.TimeoutExpired:
        issues.append("GPG command timed out")
        suggestions.append("Check GPG installation and system performance")
    except Exception as e:
        issues.append(f"GPG check failed: {str(e)}")
        suggestions.append("Verify GPG installation and configuration")

    # Check gpg-agent availability
    try:
        result = subprocess.run(
            ["gpg-agent", "--version"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            warnings.append("gpg-agent is available")
        else:
            issues.append("gpg-agent not responding properly")
            suggestions.append(
                "Start gpg-agent or configure GPG for headless operation"
            )
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
            result = subprocess.run(
                ["gpg", "--list-secret-keys"],
                capture_output=True,
                text=True,
                timeout=10,
            )
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
            "GNUPG_HOME": gnupg_dir if os.path.exists(gnupg_dir) else None,
        },
    }


def extract_github_repo_info(repo: Repo) -> Tuple[Optional[str], Optional[str]]:
    """Extract GitHub repository owner and name from git remotes.

    Args:
        repo: Git repository object

    Returns:
        Tuple of (repo_owner, repo_name) or (None, None) if not found
    """
    try:
        # Try origin remote first, then any remote
        for remote_name in ["origin"] + [
            r.name for r in repo.remotes if r.name != "origin"
        ]:
            try:
                remote = repo.remotes[remote_name]
                for url in remote.urls:
                    # Parse GitHub URLs (both SSH and HTTPS)
                    # SSH: git@github.com:owner/repo.git
                    # HTTPS: https://github.com/owner/repo.git

                    # SSH format
                    ssh_match = re.match(
                        r"git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$", url
                    )
                    if ssh_match:
                        return ssh_match.group(1), ssh_match.group(2)

                    # HTTPS format
                    https_match = re.match(
                        r"https://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", url
                    )
                    if https_match:
                        return https_match.group(1), https_match.group(2)

            except Exception:
                continue

    except Exception:
        pass

    return None, None


def get_github_repo_params(
    repo: Repo, arguments: dict
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Get GitHub repository parameters with auto-detection fallback.

    Args:
        repo: Git repository object
        arguments: Arguments dictionary from MCP call

    Returns:
        Tuple of (repo_owner, repo_name, error_message) where error_message is None if successful
    """
    repo_owner = arguments.get("repo_owner")
    repo_name = arguments.get("repo_name")

    if not repo_owner or not repo_name:
        detected_owner, detected_name = extract_github_repo_info(repo)
        repo_owner = repo_owner or detected_owner
        repo_name = repo_name or detected_name

    if not repo_owner or not repo_name:
        return (
            None,
            None,
            "❌ Could not determine GitHub repository owner/name. Please provide repo_owner and repo_name parameters or ensure git remote is configured with GitHub URL.",
        )

    return repo_owner, repo_name, None


class GitStatus(BaseModel):
    repo_path: str
    porcelain: bool = False


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
    format_str: str | None = None  # Renamed from 'format'


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


class GitHubUpdatePR(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int
    title: str | None = None
    body: str | None = None
    state: str | None = None  # "open" or "closed"


class GitHubCreatePR(BaseModel):
    repo_owner: str
    repo_name: str
    title: str
    head: str  # The name of the branch where your changes are implemented.
    base: str  # The name of the branch you want the changes pulled into.
    body: str | None = None
    draft: bool = False


class GitHubMergePR(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int
    commit_title: str | None = None
    commit_message: str | None = None
    merge_method: str = "merge"  # "merge", "squash", or "rebase"


class GitHubAddPRComment(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int
    body: str


class GitHubClosePR(BaseModel):
    repo_owner: str
    repo_name: int


class GitHubReopenPR(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int


# Security validation models
class GitSecurityValidate(BaseModel):
    repo_path: str


class GitSecurityEnforce(BaseModel):
    repo_path: str
    strict_mode: bool = True


# Advanced git operation models
class GitRebase(BaseModel):
    repo_path: str
    target_branch: str
    interactive: bool = False


class GitMerge(BaseModel):
    repo_path: str
    source_branch: str
    strategy: str = "merge"  # "merge", "squash", "rebase"
    message: str | None = None


class GitCherryPick(BaseModel):
    repo_path: str
    commit_hash: str
    no_commit: bool = False


class GitAbort(BaseModel):
    repo_path: str
    operation: str  # "rebase", "merge", "cherry-pick"


class GitContinue(BaseModel):
    repo_path: str
    operation: str  # "rebase", "merge", "cherry-pick"


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
    # Advanced git operations
    REBASE = "git_rebase"
    MERGE = "git_merge"
    CHERRY_PICK = "git_cherry_pick"
    ABORT = "git_abort"
    CONTINUE = "git_continue"
    # GitHub API Tools
    GITHUB_GET_PR_CHECKS = "github_get_pr_checks"
    GITHUB_GET_FAILING_JOBS = "github_get_failing_jobs"
    GITHUB_GET_WORKFLOW_RUN = "github_get_workflow_run"
    GITHUB_GET_PR_DETAILS = "github_get_pr_details"
    GITHUB_LIST_PULL_REQUESTS = "github_list_pull_requests"
    GITHUB_GET_PR_STATUS = "github_get_pr_status"
    GITHUB_GET_PR_FILES = "github_get_pr_files"
    GITHUB_UPDATE_PR = "github_update_pr"
    GITHUB_CREATE_PR = "github_create_pr"
    GITHUB_MERGE_PR = "github_merge_pr"
    GITHUB_ADD_PR_COMMENT = "github_add_pr_comment"
    GITHUB_CLOSE_PR = "github_close_pr"
    GITHUB_REOPEN_PR = "github_reopen_pr"
    # Security tools
    GIT_SECURITY_VALIDATE = "git_security_validate"
    GIT_SECURITY_ENFORCE = "git_security_enforce"


def git_status(repo: Repo, porcelain: bool = False) -> str:
    """Get repository status in either human-readable or machine-readable format.

    Args:
        repo: Git repository object
        porcelain: If True, return porcelain (machine-readable) format

    Returns:
        Status output string
    """
    if porcelain:
        return repo.git.status("--porcelain")
    else:
        return repo.git.status()


def git_diff_unstaged(repo: Repo) -> str:
    return repo.git.diff()


def git_diff_staged(repo: Repo) -> str:
    return repo.git.diff("--cached")


def git_diff(repo: Repo, target: str) -> str:
    return repo.git.diff(target)


def git_commit(
    repo: Repo, message: str, gpg_sign: bool = False, gpg_key_id: str | None = None
) -> str:
    """Commit staged changes with optional GPG signing and automatic security enforcement"""
    import subprocess
    import logging

    logger = logging.getLogger(__name__)

    try:
        # 🔒 SECURITY: Enforce secure configuration before committing
        security_result = enforce_secure_git_config(repo, strict_mode=True)
        security_messages = []
        if "✅" in security_result:
            security_messages.append("🔒 Security configuration enforced")
        else:
            # If enforcement failed or had warnings, include them in the message
            security_messages.append(security_result)

        # Force GPG signing for all commits (SECURITY REQUIREMENT)
        force_gpg = True

        # Get GPG key from parameters, environment, or git config
        if gpg_key_id:
            force_key_id = gpg_key_id
        else:
            # Try environment variable first
            env_key = os.getenv("GPG_SIGNING_KEY")
            if env_key:
                force_key_id = env_key
            else:
                # Fall back to git config
                try:
                    config_key = repo.config_reader().get_value("user", "signingkey")
                    force_key_id = config_key
                except Exception:
                    # If no key is found, this is a critical error for forced GPG signing
                    return "❌ No GPG signing key configured. Set GPG_SIGNING_KEY env var or git config user.signingkey"

        if force_gpg:  # This will always be true due to the security requirement
            # Use git command directly for GPG signing with comprehensive error handling
            cmd = ["git", "commit"]
            # Ensure the key ID is passed correctly
            if force_key_id:
                cmd.append(f"--gpg-sign={force_key_id}")
            else:
                # This case should ideally be caught by the check above, but as a fallback
                cmd.append("--gpg-sign")  # Let git pick default key if none specified

            cmd.extend(["-m", message])

            try:
                result = subprocess.run(
                    cmd,
                    cwd=repo.working_dir,
                    capture_output=True,
                    text=True,
                    timeout=30,  # Prevent hanging on GPG operations
                )

                if result.returncode == 0:
                    # Get the commit hash from git log
                    hash_result = subprocess.run(
                        ["git", "rev-parse", "HEAD"],
                        cwd=repo.working_dir,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    commit_hash = (
                        hash_result.stdout.strip()[:8]
                        if hash_result.returncode == 0
                        else "unknown"
                    )

                    success_msg = (
                        f"✅ Commit {commit_hash} created with VERIFIED GPG signature"
                    )
                    if security_messages:
                        success_msg += f"\n{chr(10).join(security_messages)}"

                    # Add security reminder
                    success_msg += f"\n🔒 Enforced GPG signing with key {force_key_id or 'default'}"
                    success_msg += (
                        "\n⚠️  MCP Git Server used - no fallback to system git commands"
                    )

                    return success_msg
                else:
                    # Enhanced error reporting for GPG failures
                    error_details = []
                    if result.stderr:
                        error_details.append(f"STDERR: {result.stderr.strip()}")
                    if result.stdout:
                        error_details.append(f"STDOUT: {result.stdout.strip()}")
                    error_details.append(f"Return code: {result.returncode}")

                    error_msg = f"❌ GPG commit failed: {'; '.join(error_details)}"

                    # Check for specific GPG issues and provide guidance
                    combined_output = (result.stderr + result.stdout).lower()
                    if "gpg" in combined_output and (
                        "failed" in combined_output or "error" in combined_output
                    ):
                        error_msg += "\n💡 GPG Troubleshooting: Check GPG_TTY environment, gpg-agent status, and key availability"
                    elif (
                        "no secret key" in combined_output
                        or "secret key not available" in combined_output
                    ):
                        error_msg += f"\n💡 GPG key not available. Verify key ID '{force_key_id or 'default'}' exists and gpg-agent is running"
                    elif (
                        "inappropriate ioctl" in combined_output
                        or "no tty" in combined_output
                    ):
                        error_msg += "\n💡 GPG TTY issue. Try: export GPG_TTY=$(tty) or export GPG_TTY=/dev/null for headless operation"
                    elif "timeout" in combined_output or "expired" in combined_output:
                        error_msg += "\n💡 GPG operation timed out. Check gpg-agent configuration and key passphrase handling"

                    logger.error(f"GPG commit failed: {error_msg}")
                    return error_msg

            except subprocess.TimeoutExpired:
                logger.error("GPG commit timed out after 30 seconds")
                return "❌ GPG commit timed out after 30 seconds. Check gpg-agent status and key availability"
            except subprocess.SubprocessError as e:
                logger.error(f"GPG subprocess error: {e}")
                return f"❌ GPG subprocess error: {str(e)}"
        else:
            # This path should never be reached due to force_gpg=True
            return "❌ SECURITY VIOLATION: Unsigned commits are not allowed by MCP Git Server"

    except GitCommandError as e:
        logger.error(f"Git command error in commit: {e}")
        return f"❌ Commit failed: {str(e)}\n🔒 Security enforcement may have prevented insecure operation"
    except Exception as e:
        logger.error(f"❌ Unexpected error in git_commit: {e}", exc_info=True)
        return f"❌ Unexpected commit error: {str(e)}. Check repository state and permissions"


def git_add(repo: Repo, files: list[str]) -> str:
    """
    Add files to git staging area with robust error handling

    Args:
        repo: GitPython repository object
        files: List of file paths to add

    Returns:
        Detailed status message about the add operation
    """
    try:
        if not files:
            return "No files specified to add"

        from pathlib import Path

        # Validate and categorize files
        existing_files = []
        missing_files = []
        staged_files = []
        failed_files = []

        repo_path = Path(repo.working_dir)

        # Check file existence and normalize paths
        for file_path in files:
            try:
                full_path = repo_path / file_path
                if full_path.exists() or full_path.is_dir():
                    existing_files.append(file_path)
                else:
                    missing_files.append(file_path)
            except Exception:
                missing_files.append(file_path)

        # Early return for all missing files
        if missing_files and not existing_files:
            missing_list = ", ".join(missing_files)
            return f"Cannot add files - not found: {missing_list}"

        # Attempt to add existing files
        if existing_files:
            try:
                # Try batch add first (more efficient)
                repo.index.add(existing_files)
                staged_files = existing_files[:]
            except Exception:
                # Fallback to individual file processing
                for file_path in existing_files:
                    try:
                        repo.index.add([file_path])
                        staged_files.append(file_path)
                    except Exception as e:
                        failed_files.append(f"{file_path}: {str(e)}")

        # Build response
        response_parts = []

        if staged_files:
            if len(staged_files) == 1:
                response_parts.append(f"Successfully staged: {staged_files[0]}")
            else:
                staged_list = ", ".join(staged_files)
                response_parts.append(
                    f"Successfully staged ({len(staged_files)} files): {staged_list}"
                )

        if missing_files:
            missing_list = ", ".join(missing_files)
            response_parts.append(f"Files not found: {missing_list}")

        if failed_files:
            failed_list = ", ".join(failed_files)
            response_parts.append(f"Failed to stage: {failed_list}")

        if not response_parts:
            return "No files were processed"

        return "; ".join(response_parts)

    except Exception:
        # Fallback to original simple behavior if anything goes wrong
        try:
            repo.index.add(files)
            return "Files staged successfully"
        except Exception as fallback_e:
            return f"Git add failed: {str(fallback_e)}"


def git_reset(repo: Repo) -> str:
    repo.index.reset()
    return "All staged changes reset"


def git_log(
    repo: Repo,
    max_count: int = 10,
    oneline: bool = False,
    graph: bool = False,
    format_str: str | None = None,  # Renamed from 'format'
) -> list[str]:
    """Get commit history with formatting options"""
    try:
        commits = list(repo.iter_commits(max_count=max_count))
        log = []

        if oneline:
            # One line format: hash subject
            for commit in commits:
                short_hash = commit.hexsha[:8]
                subject = str(commit.message).split("\n")[0]
                log.append(f"{short_hash} {subject}")
        elif format_str:  # Use format_str
            # Custom format
            for commit in commits:
                formatted = format_str.replace("%H", commit.hexsha)  # Use format_str
                formatted = formatted.replace("%h", commit.hexsha[:8])
                formatted = formatted.replace("%s", str(commit.message).split("\n")[0])
                formatted = formatted.replace("%an", str(commit.author.name))
                formatted = formatted.replace("%ae", str(commit.author.email))
                formatted = formatted.replace("%ad", str(commit.authored_datetime))
                formatted = formatted.replace(
                    "%ar", _relative_time(commit.authored_datetime)
                )
                log.append(formatted)
        else:
            # Default detailed format
            for commit in commits:
                entry = (
                    f"Commit: {commit.hexsha}\n"
                    f"Author: {commit.author}\n"
                    f"Date: {commit.authored_datetime}\n"
                    f"Message: {commit.message}"
                )
                log.append(entry)

        # Add graph visualization if requested (simplified)
        if graph and not oneline:
            for i, entry in enumerate(log):
                prefix = "* " if i == 0 else "| "
                log[i] = prefix + entry.replace("\n", f"\n{prefix}")

        return log

    except Exception as e:
        return [f"Log error: {str(e)}"]


def _relative_time(dt) -> str:
    """Helper function to format relative time"""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    diff = now - dt.replace(tzinfo=timezone.utc)

    days = diff.days
    hours = diff.seconds // 3600
    minutes = (diff.seconds % 3600) // 60

    if days > 0:
        return f"{days} days ago"
    elif hours > 0:
        return f"{hours} hours ago"
    elif minutes > 0:
        return f"{minutes} minutes ago"
    else:
        return "just now"


def git_create_branch(
    repo: Repo, branch_name: str, base_branch: str | None = None
) -> str:
    if base_branch:
        try:
            base = repo.refs[base_branch]
        except IndexError:
            return f"❌ Base branch '{base_branch}' not found."
    else:
        base = repo.active_branch

    repo.create_head(branch_name, base)
    return f"Created branch '{branch_name}' from '{base.name}'"


def git_checkout(repo: Repo, branch_name: str) -> str:
    repo.git.checkout(branch_name)
    return f"Switched to branch '{branch_name}'"


def git_init(repo_path: str) -> str:
    try:
        repo = Repo.init(path=repo_path, mkdir=True)
        return f"Initialized empty Git repository in {repo.git_dir}"
    except Exception as e:
        return f"Error initializing repository: {str(e)}"


def git_show(repo: Repo, revision: str) -> str:
    commit = repo.commit(revision)
    output = [
        f"Commit: {commit.hexsha}\n"
        f"Author: {commit.author}\n"
        f"Date: {commit.authored_datetime}\n"
        f"Message: {commit.message}\n"
    ]
    if commit.parents:  # Check if parents exist
        parent = commit.parents[0]
        diff = parent.diff(commit, create_patch=True)
    else:
        diff = commit.diff(Repo.NULL_TREE, create_patch=True)  # Use Repo.NULL_TREE
    for d in diff:
        output.append(f"\n--- {d.a_path}\n+++ {d.b_path}\n")
        diff_bytes = d.diff
        if isinstance(diff_bytes, bytes):
            output.append(diff_bytes.decode("utf-8", errors="replace"))
        else:
            output.append(str(diff_bytes))
    return "".join(output)


def git_push(
    repo: Repo,
    remote: str = "origin",
    branch: str | None = None,
    force: bool = False,
    set_upstream: bool = False,
) -> str:
    """Push commits to remote repository with HTTPS authentication support"""
    logger = logging.getLogger(__name__)

    try:
        try:
            remote_ref = repo.remote(remote)
            remote_url = remote_ref.url
        except ValueError:
            return f"❌ Remote '{remote}' not found."

        # Determine branch to push
        if branch is None:
            try:
                branch = repo.active_branch.name
            except TypeError:  # Detached HEAD or no commits
                return "❌ No active branch found. Please specify a branch to push."

        logger.debug(f"🚀 Pushing {branch} to {remote} ({remote_url})")

        # Check if we need to handle HTTPS authentication
        token = os.getenv("GITHUB_TOKEN")
        needs_auth = (
            remote_url.startswith("https://")
            and "github.com" in remote_url
            and token is not None
        )

        if needs_auth:
            logger.debug("🔑 Using GitHub token for HTTPS authentication")
            logger.debug(
                f"🔍 Token format: {token[:4]}{'*' * 8}... (length: {len(token)})"
            )

            # Detect token type for appropriate authentication method
            is_classic_pat = token.startswith("ghp_")
            is_fine_grained_pat = token.startswith("github_pat_")
            is_app_token = token.startswith("ghs_") or token.startswith("ghu_")
            is_github_token = token.startswith("gith")  # Your specific token format

            logger.debug(
                f"🔍 Token type detection: classic_pat={is_classic_pat}, fine_grained={is_fine_grained_pat}, app_token={is_app_token}, github_token={is_github_token}"
            )

            # Test token validity first
            logger.debug("🔍 Testing token validity with GitHub API...")
            try:
                import requests

                headers = {
                    "Authorization": f"token {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                }
                test_response = requests.get(
                    "https://api.github.com/user", headers=headers, timeout=10
                )
                if test_response.status_code == 200:
                    user_info = test_response.json()
                    logger.debug(
                        f"✅ Token valid - authenticated as: {user_info.get('login', 'unknown')}"
                    )
                elif test_response.status_code == 401:
                    logger.error("❌ Token is invalid or expired")
                    return "Push failed: GitHub token is invalid or expired (HTTP 401)"
                elif test_response.status_code == 403:
                    logger.warning(
                        f"⚠️ Token has limited permissions (HTTP 403): {test_response.text}"
                    )
                else:
                    logger.warning(
                        f"⚠️ Unexpected API response (HTTP {test_response.status_code}): {test_response.text}"
                    )
            except Exception as api_error:
                logger.warning(f"⚠️ Could not validate token via API: {api_error}")
                # Continue with push attempts even if API validation fails

            # Use different authentication methods based on token type
            import subprocess

            # Set up environment with GitHub token
            env = os.environ.copy()
            env["GITHUB_TOKEN"] = token
            env["GIT_ASKPASS"] = "/bin/true"  # Disable interactive prompts

            # For non-standard token formats, try direct header approach
            if is_github_token or is_fine_grained_pat:
                logger.debug(
                    "🔧 Using HTTP header authentication for non-standard token"
                )

                # Try using git with authorization header
                auth_header = f"Authorization: token {token}"

                cmd = ["git", "-c", f"http.extraheader={auth_header}", "push"]
                if force:
                    cmd.append("--force")
                if set_upstream:
                    cmd.extend(["--set-upstream", remote, branch])
                else:
                    cmd.extend([remote, f"{branch}:{branch}"])

                logger.debug(
                    f"🔧 Running: git push [http-header-auth] {' '.join(cmd[4:])}"
                )

                result = subprocess.run(
                    cmd, cwd=repo.working_dir, capture_output=True, text=True, env=env
                )

                if result.returncode == 0:
                    success_msg = f"Successfully pushed {branch} to {remote}"
                    if set_upstream:
                        success_msg += " and set upstream tracking"
                    logger.info(f"✅ {success_msg}")
                    return success_msg
                else:
                    error_output = result.stderr.strip() or result.stdout.strip()
                    logger.warning(f"⚠️ HTTP header auth failed: {error_output}")
                    # Sanitize command for logging (hide token)
                    sanitized_cmd = []
                    for part in cmd:
                        if "Authorization:" in part and "token" in part:
                            sanitized_cmd.append(
                                "http.extraheader=Authorization: token [REDACTED]"
                            )
                        else:
                            sanitized_cmd.append(part)
                    logger.debug(
                        f"🔍 HTTP header auth command was: {' '.join(sanitized_cmd)}"
                    )
                    logger.debug(f"🔍 HTTP header auth full stderr: {result.stderr}")
                    logger.debug(f"🔍 HTTP header auth full stdout: {result.stdout}")
                    # Fall through to try other methods

            # Use GitHub CLI auth approach if available, otherwise fallback to direct token
            try:
                # Try using gh auth setup approach
                setup_result = subprocess.run(
                    ["gh", "auth", "setup-git"],
                    cwd=repo.working_dir,
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=10,
                )

                if setup_result.returncode == 0:
                    logger.debug("🔧 GitHub CLI auth setup successful")
                    # Now try the push with GitHub CLI authentication
                    cmd = ["git", "push"]
                    if force:
                        cmd.append("--force")
                    if set_upstream:
                        cmd.extend(["--set-upstream", remote, branch])
                    else:
                        cmd.extend([remote, f"{branch}:{branch}"])

                    logger.debug(f"🔧 Running: git push [gh-auth] {' '.join(cmd[2:])}")

                    result = subprocess.run(
                        cmd,
                        cwd=repo.working_dir,
                        capture_output=True,
                        text=True,
                        env=env,
                    )

                    if result.returncode == 0:
                        success_msg = f"Successfully pushed {branch} to {remote}"
                        if set_upstream:
                            success_msg += " and set upstream tracking"
                        logger.info(f"✅ {success_msg}")
                        return success_msg
                    else:
                        error_msg = f"Push failed: {result.stderr.strip() or result.stdout.strip()}"
                        logger.error(f"❌ {error_msg}")
                        return error_msg
                else:
                    logger.debug(
                        "⚠️ GitHub CLI not available, using manual token approach"
                    )
                    raise subprocess.CalledProcessError(1, "gh auth setup-git")

            except (
                subprocess.CalledProcessError,
                subprocess.TimeoutExpired,
                FileNotFoundError,
            ):
                # Fallback to manual token configuration
                logger.debug("🔧 Using manual git credential configuration")

                # Configure git to use the token directly
                git_config_cmds = [
                    [
                        "git",
                        "config",
                        "--local",
                        "credential.https://github.com.username",
                        "x-access-token",
                    ],
                    [
                        "git",
                        "config",
                        "--local",
                        "credential.https://github.com.password",
                        token,
                    ],
                    ["git", "config", "--local", "credential.helper", "store"],
                ]

                try:
                    for config_cmd in git_config_cmds:
                        subprocess.run(
                            config_cmd,
                            cwd=repo.working_dir,
                            check=True,
                            capture_output=True,
                        )

                    logger.debug("🔧 Git credentials configured")

                    # Now try the push
                    cmd = ["git", "push"]
                    if force:
                        cmd.append("--force")
                    if set_upstream:
                        cmd.extend(["--set-upstream", remote, branch])
                    else:
                        cmd.extend([remote, f"{branch}:{branch}"])

                    logger.debug(
                        f"🔧 Running: git push [manual-creds] {' '.join(cmd[2:])}"
                    )

                    result = subprocess.run(
                        cmd,
                        cwd=repo.working_dir,
                        capture_output=True,
                        text=True,
                        env=env,
                    )

                    if result.returncode == 0:
                        success_msg = f"Successfully pushed {branch} to {remote}"
                        if set_upstream:
                            success_msg += " and set upstream tracking"
                        logger.info(f"✅ {success_msg}")
                        return success_msg
                    else:
                        error_msg = f"Push failed: {result.stderr.strip() or result.stdout.strip()}"
                        logger.error(f"❌ {error_msg}")
                        return error_msg

                finally:
                    # Clean up the credential configuration
                    cleanup_cmds = [
                        [
                            "git",
                            "config",
                            "--local",
                            "--unset",
                            "credential.https://github.com.username",
                        ],
                        [
                            "git",
                            "config",
                            "--local",
                            "--unset",
                            "credential.https://github.com.password",
                        ],
                        ["git", "config", "--local", "--unset", "credential.helper"],
                    ]
                    for cleanup_cmd in cleanup_cmds:
                        try:
                            subprocess.run(
                                cleanup_cmd, cwd=repo.working_dir, capture_output=True
                            )
                        except Exception:
                            pass
                    logger.debug("🧹 Cleaned up git credential configuration")

        else:
            # Use standard GitPython approach for non-HTTPS or when no token available
            logger.debug("🔧 Using standard git push (no authentication needed)")

            if set_upstream:
                # Use git command directly for set-upstream functionality
                import subprocess

                cmd = ["git", "push", "--set-upstream", remote, branch]
                if force:
                    cmd.insert(2, "--force")

                result = subprocess.run(
                    cmd, cwd=repo.working_dir, capture_output=True, text=True
                )
                if result.returncode == 0:
                    return f"Successfully pushed {branch} to {remote} and set upstream tracking"
                else:
                    return f"Push failed: {result.stderr}"
            else:
                # Use GitPython for regular push
                refspec = f"{branch}:{branch}"
                push_info = remote_ref.push(refspec, force=force)

                # Process results
                results = []
                for info in push_info:
                    if info.flags & info.ERROR:
                        results.append(f"Error: {info.summary}")
                    elif info.flags & info.REJECTED:
                        results.append(f"Rejected: {info.summary}")
                    elif info.flags & info.UP_TO_DATE:
                        results.append(f"Up to date: {info.summary}")
                    else:
                        results.append(f"Success: {info.summary}")

                return (
                    "\n".join(results)
                    if results
                    else f"Successfully pushed {branch} to {remote}"
                )

    except GitCommandError as e:
        logger.error(f"❌ Git command error during push: {e}")
        return f"Push failed: {str(e)}"
    except Exception as e:
        logger.error(f"❌ Unexpected error during push: {e}")
        return f"Push error: {str(e)}"


def git_pull(repo: Repo, remote: str = "origin", branch: str | None = None) -> str:
    """Pull changes from remote repository"""
    try:
        remote_ref = repo.remote(remote)

        # Determine branch to pull
        if branch is None:  # Corrected from === to is
            try:
                branch = repo.active_branch.name
            except TypeError:  # Detached HEAD or no commits
                return "❌ No active branch found. Please specify a branch to pull."

        # Execute pull
        pull_info = remote_ref.pull(branch)

        # Process results
        results = []
        for info in pull_info:
            if info.flags & info.ERROR:
                results.append(f"Error: {info.note or 'Pull failed'}")
            elif info.flags & info.REJECTED:
                results.append(f"Rejected: {info.note or 'Changes rejected'}")
            elif info.flags & info.HEAD_UPTODATE:
                results.append("Already up to date")
            elif info.flags & info.FAST_FORWARD:
                old_commit = (
                    info.old_commit.hexsha[:8] if info.old_commit else "unknown"
                )
                new_commit = info.commit.hexsha[:8] if info.commit else "unknown"
                results.append(f"Fast-forward: {old_commit}..{new_commit}")
            else:
                results.append(f"Updated: {info.note or 'Pull completed'}")

        return (
            "\n".join(results)
            if results
            else f"Successfully pulled from {remote}/{branch}"
        )

    except GitCommandError as e:
        return f"Pull failed: {str(e)}"
    except Exception as e:
        return f"Pull error: {str(e)}"


def git_diff_branches(repo: Repo, base_branch: str, compare_branch: str) -> str:
    """Show differences between two branches"""
    try:
        # Get the commits for both branches
        base_commit = repo.commit(base_branch)
        compare_commit = repo.commit(compare_branch)

        # Get the diff between branches
        diff = base_commit.diff(compare_commit, create_patch=True)

        if not diff:
            return f"No differences between {base_branch} and {compare_branch}"

        output = [f"Diff between {base_branch} and {compare_branch}:\n"]

        for d in diff:
            change_type = "modified"
            if d.new_file:
                change_type = "added"
            elif d.deleted_file:
                change_type = "deleted"
            elif d.renamed_file:
                change_type = "renamed"

            output.append(f"\n{change_type}: {d.a_path or d.b_path}")
            if d.diff:
                output.append(d.diff.decode("utf-8"))

        return "".join(output)

    except GitCommandError as e:
        return f"Diff failed: {str(e)}"
    except Exception as e:
        return f"Diff error: {str(e)}"


def git_rebase(repo: Repo, target_branch: str, interactive: bool = False) -> str:
    """Rebase current branch onto target branch"""
    try:
        current_branch = repo.active_branch.name

        # Use subprocess for reliable rebase operation
        import subprocess

        cmd = ["git", "rebase"]

        if interactive:
            cmd.append("-i")

        cmd.append(target_branch)

        result = subprocess.run(
            cmd, cwd=repo.working_dir, capture_output=True, text=True
        )

        if result.returncode == 0:
            return f"✅ Successfully rebased {current_branch} onto {target_branch}"
        else:
            # Check if it's a conflict that needs resolution
            if "CONFLICT" in result.stdout or "conflict" in result.stderr.lower():
                return f"🔄 Rebase conflicts detected. Resolve conflicts and use git_continue to finish rebase.\n\nConflicts:\n{result.stdout}\n{result.stderr}"
            else:
                return f"❌ Rebase failed: {result.stderr}"

    except GitCommandError as e:
        return f"❌ Rebase failed: {str(e)}"
    except Exception as e:
        return f"❌ Rebase error: {str(e)}"


def git_merge(
    repo: Repo,
    source_branch: str,
    strategy: str = "merge",
    message: str | None = None,
) -> str:
    """Merge source branch into current branch"""
    try:
        current_branch = repo.active_branch.name

        # Use subprocess for reliable merge operation
        import subprocess

        cmd = ["git", "merge"]

        if strategy == "squash":
            cmd.append("--squash")
        elif strategy == "rebase":
            # For rebase strategy, we actually do a rebase
            return git_rebase(repo, source_branch)

        if message:
            cmd.extend(["-m", message])
        else:
            cmd.extend(["-m", f"Merge {source_branch} into {current_branch}"])

        cmd.append(source_branch)

        result = subprocess.run(
            cmd, cwd=repo.working_dir, capture_output=True, text=True
        )

        if result.returncode == 0:
            if strategy == "squash":
                return f"✅ Successfully squashed {source_branch} into {current_branch}. Changes staged but not committed."
            else:
                return f"✅ Successfully merged {source_branch} into {current_branch}"
        else:
            # Check if it's a conflict that needs resolution
            if "CONFLICT" in result.stdout or "conflict" in result.stderr.lower():
                return f"🔄 Merge conflicts detected. Resolve conflicts and use git_continue to finish merge.\n\nConflicts:\n{result.stdout}\n{result.stderr}"
            else:
                return f"❌ Merge failed: {result.stderr}"

    except GitCommandError as e:
        return f"❌ Merge failed: {str(e)}"
    except Exception as e:
        return f"❌ Merge error: {str(e)}"


def git_cherry_pick(repo: Repo, commit_hash: str, no_commit: bool = False) -> str:
    """Cherry-pick a commit onto current branch"""
    try:
        # Use subprocess for reliable cherry-pick operation
        import subprocess

        cmd = ["git", "cherry-pick"]

        if no_commit:
            cmd.append("--no-commit")

        cmd.append(commit_hash)

        result = subprocess.run(
            cmd, cwd=repo.working_dir, capture_output=True, text=True
        )

        if result.returncode == 0:
            if no_commit:
                return f"✅ Successfully cherry-picked {commit_hash[:8]} (changes staged but not committed)"
            else:
                return f"✅ Successfully cherry-picked {commit_hash[:8]}"
        else:
            # Check if it's a conflict that needs resolution
            if "CONFLICT" in result.stdout or "conflict" in result.stderr.lower():
                return f"🔄 Cherry-pick conflicts detected. Resolve conflicts and use git_continue to finish cherry-pick.\n\nConflicts:\n{result.stdout}\n{result.stderr}"
            else:
                return f"❌ Cherry-pick failed: {result.stderr}"

    except GitCommandError as e:
        return f"❌ Cherry-pick failed: {str(e)}"
    except Exception as e:
        return f"❌ Cherry-pick error: {str(e)}"


def git_abort(repo: Repo, operation: str) -> str:
    """Abort an ongoing git operation (rebase, merge, cherry-pick)"""
    try:
        # Use subprocess for reliable abort operation
        import subprocess

        if operation == "rebase":
            cmd = ["git", "rebase", "--abort"]
        elif operation == "merge":
            cmd = ["git", "merge", "--abort"]
        elif operation == "cherry-pick":
            cmd = ["git", "cherry-pick", "--abort"]
        else:
            return f"❌ Unknown operation '{operation}'. Supported: rebase, merge, cherry-pick"

        result = subprocess.run(
            cmd, cwd=repo.working_dir, capture_output=True, text=True
        )

        if result.returncode == 0:
            return f"✅ Successfully aborted {operation} operation"
        else:
            return f"❌ Failed to abort {operation}: {result.stderr}"

    except GitCommandError as e:
        return f"❌ Abort failed: {str(e)}"
    except Exception as e:
        return f"❌ Abort error: {str(e)}"


def git_continue(repo: Repo, operation: str) -> str:
    """Continue an ongoing git operation after resolving conflicts"""
    try:
        # Use subprocess for reliable continue operation
        import subprocess

        if operation == "rebase":
            cmd = ["git", "rebase", "--continue"]
        elif operation == "merge":
            # For merge, we just need to commit (no explicit continue)
            cmd = ["git", "commit", "--no-edit"]
        elif operation == "cherry-pick":
            cmd = ["git", "cherry-pick", "--continue"]
        else:
            return f"❌ Unknown operation '{operation}'. Supported: rebase, merge, cherry-pick"

        result = subprocess.run(
            cmd, cwd=repo.working_dir, capture_output=True, text=True
        )

        if result.returncode == 0:
            return f"✅ Successfully continued {operation} operation"
        else:
            # Check if there are still unresolved conflicts
            if (
                "conflict" in result.stderr.lower()
                or "unmerged" in result.stderr.lower()
            ):
                return f"🔄 Still have unresolved conflicts. Please resolve all conflicts before continuing.\n\nError: {result.stderr}"
            else:
                return f"❌ Failed to continue {operation}: {result.stderr}"

    except GitCommandError as e:
        return f"❌ Continue failed: {str(e)}"
    except Exception as e:
        return f"❌ Continue error: {str(e)}"


async def main(repository: Path | None, test_mode: bool = False) -> None:
    import os
    from datetime import datetime

    # Centralized logging configuration
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
    logger = logging.getLogger(__name__)
    start_time = time.time()
    session_id = os.environ.get("MCP_SESSION_ID", "default")

    # Startup logging
    logger.info(
        f"🚀 Starting MCP Git Server (Session: {session_id})",
        extra={"session_id": session_id},
    )
    logger.info(f"Repository: {repository or '.'}", extra={"session_id": session_id})
    logger.info(
        f"Server start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        extra={"session_id": session_id},
    )

    # Load environment variables from .env files with proper precedence
    load_environment_variables(repository)

    if repository is not None:
        try:
            Repo(repository)
            logger.info(f"✅ Using repository at {repository}")
        except InvalidGitRepositoryError:
            logger.error(f"{repository} is not a valid Git repository")
            return

    server = Server("mcp-git")

    # Heartbeat/session manager setup
    session_manager = SessionManager()
    heartbeat_manager = HeartbeatManager(session_manager)
    session_manager.heartbeat_manager = heartbeat_manager
    await heartbeat_manager.start()

    # Metrics: record server startup
    await global_metrics_collector.record_session_event("server_started")

    # Note: Enhanced notification handling for cancelled notifications
    # The middleware infrastructure is available in models/notifications.py and models/middleware.py
    # but integrating it into the MCP framework requires careful session handling
    logger.debug("🔧 Notification middleware available for cancelled notifications")

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
                        required=True,
                    ),
                    PromptArgument(
                        name="type",
                        description="Type of change (feat, fix, docs, refactor, test, chore)",
                        required=False,
                    ),
                    PromptArgument(
                        name="scope",
                        description="Scope of the change (component/area affected)",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="pr-description",
                description="Generate a comprehensive pull request description",
                arguments=[
                    PromptArgument(
                        name="title",
                        description="Title of the pull request",
                        required=True,
                    ),
                    PromptArgument(
                        name="changes",
                        description="Summary of changes made",
                        required=True,
                    ),
                    PromptArgument(
                        name="breaking",
                        description="Any breaking changes (optional)",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="release-notes",
                description="Generate release notes from commit history",
                arguments=[
                    PromptArgument(
                        name="version",
                        description="Version being released",
                        required=True,
                    ),
                    PromptArgument(
                        name="commits",
                        description="Commit history since last release",
                        required=True,
                    ),
                    PromptArgument(
                        name="previous_version",
                        description="Previous version (optional)",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="code-review",
                description="Generate a code review prompt for a diff",
                arguments=[
                    PromptArgument(
                        name="diff", description="The diff to review", required=True
                    ),
                    PromptArgument(
                        name="context",
                        description="Additional context about the changes",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="merge-conflict-resolution",
                description="Help resolve merge conflicts systematically",
                arguments=[
                    PromptArgument(
                        name="conflicts",
                        description="The conflicted files or sections",
                        required=True,
                    ),
                    PromptArgument(
                        name="branch_info",
                        description="Information about the branches being merged",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="git-workflow-guide",
                description="Guide for Git workflow best practices",
                arguments=[
                    PromptArgument(
                        name="workflow_type",
                        description="Type of workflow (gitflow, github-flow, gitlab-flow)",
                        required=False,
                    ),
                    PromptArgument(
                        name="team_size",
                        description="Size of the development team",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="branch-strategy",
                description="Recommend branching strategy for a project",
                arguments=[
                    PromptArgument(
                        name="project_type",
                        description="Type of project (library, application, microservice)",
                        required=True,
                    ),
                    PromptArgument(
                        name="deployment_frequency",
                        description="How often deployments happen",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="git-troubleshooting",
                description="Help troubleshoot common Git issues",
                arguments=[
                    PromptArgument(
                        name="issue",
                        description="Description of the Git issue encountered",
                        required=True,
                    ),
                    PromptArgument(
                        name="git_status",
                        description="Output of git status command",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="changelog-generation",
                description="Generate changelog from commit history",
                arguments=[
                    PromptArgument(
                        name="commits",
                        description="Commit history to include",
                        required=True,
                    ),
                    PromptArgument(
                        name="format",
                        description="Changelog format (keep-a-changelog, conventional)",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="rebase-interactive",
                description="Guide for interactive rebase operations",
                arguments=[
                    PromptArgument(
                        name="commits",
                        description="Commits to be rebased",
                        required=True,
                    ),
                    PromptArgument(
                        name="goal",
                        description="What you want to achieve with the rebase",
                        required=False,
                    ),
                ],
            ),
            # GitHub Actions Prompts
            Prompt(
                name="github-actions-failure-analysis",
                description="Analyze GitHub Actions failures and suggest fixes",
                arguments=[
                    PromptArgument(
                        name="failure_logs",
                        description="Raw failure logs from GitHub Actions",
                        required=True,
                    ),
                    PromptArgument(
                        name="workflow_file",
                        description="YAML workflow file content",
                        required=False,
                    ),
                    PromptArgument(
                        name="changed_files",
                        description="Files changed in the PR",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="ci-failure-root-cause",
                description="Identify root cause of CI failures and provide solutions",
                arguments=[
                    PromptArgument(
                        name="error_message",
                        description="Primary error message",
                        required=True,
                    ),
                    PromptArgument(
                        name="stack_trace",
                        description="Full stack trace if available",
                        required=False,
                    ),
                    PromptArgument(
                        name="environment_info",
                        description="CI environment details",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="pr-readiness-assessment",
                description="Assess PR readiness and suggest improvements",
                arguments=[
                    PromptArgument(
                        name="pr_details",
                        description="PR information including changes",
                        required=True,
                    ),
                    PromptArgument(
                        name="ci_status",
                        description="Current CI status",
                        required=False,
                    ),
                    PromptArgument(
                        name="review_comments",
                        description="Existing review comments",
                        required=False,
                    ),
                ],
            ),
            # GitHub Write Prompts
            Prompt(
                name="github-pr-creation",
                description="Generate optimal PR creation content (title, body, labels, reviewers)",
                arguments=[
                    PromptArgument(
                        name="branch_name",
                        description="Name of the branch with changes",
                        required=True,
                    ),
                    PromptArgument(
                        name="changes_summary",
                        description="Summary of changes made in the branch",
                        required=True,
                    ),
                    PromptArgument(
                        name="breaking_changes",
                        description="Description of any breaking changes",
                        required=False,
                    ),
                    PromptArgument(
                        name="target_audience",
                        description="Audience for the PR (e.g., developers, QA, product)",
                        required=False,
                    ),
                    PromptArgument(
                        name="urgency",
                        description="Urgency of the PR (e.g., high, medium, low)",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="github-pr-comment-generation",
                description="Generate meaningful PR comments for reviews",
                arguments=[
                    PromptArgument(
                        name="diff_content",
                        description="The diff or code snippet to comment on",
                        required=True,
                    ),
                    PromptArgument(
                        name="comment_type",
                        description="Type of comment (review, suggestion, approval, request_changes)",
                        required=True,
                    ),
                    PromptArgument(
                        name="specific_focus",
                        description="Area of focus for the comment (e.g., logic, style, security)",
                        required=False,
                    ),
                    PromptArgument(
                        name="tone",
                        description="Desired tone of the comment (e.g., formal, constructive, friendly)",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="github-merge-strategy-recommendation",
                description="Recommend merge strategies based on PR analysis",
                arguments=[
                    PromptArgument(
                        name="pr_details",
                        description="Details of the pull request (title, description, size)",
                        required=True,
                    ),
                    PromptArgument(
                        name="commit_history",
                        description="Commit history of the PR branch",
                        required=True,
                    ),
                    PromptArgument(
                        name="team_preferences",
                        description="Team's preferred merge strategies (e.g., prefer squash)",
                        required=False,
                    ),
                    PromptArgument(
                        name="risk_level",
                        description="Assessed risk level of the changes (e.g., low, high)",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="github-pr-update-guidance",
                description="Guide systematic PR updates based on feedback",
                arguments=[
                    PromptArgument(
                        name="review_feedback",
                        description="Feedback received from code reviews",
                        required=True,
                    ),
                    PromptArgument(
                        name="current_pr_state",
                        description="Current state of the PR (e.g., code, tests, description)",
                        required=True,
                    ),
                    PromptArgument(
                        name="priority_issues",
                        description="High-priority issues to address first",
                        required=False,
                    ),
                    PromptArgument(
                        name="timeline",
                        description="Expected timeline for updates",
                        required=False,
                    ),
                ],
            ),
        ]

    @server.get_prompt()
    async def get_prompt(
        name: str, arguments: dict[str, str] | None
    ) -> GetPromptResult:
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
{commit_type + "(" + scope + ")" if commit_type and scope else "<type>(<scope>)" if not commit_type else commit_type + "(<scope>)" if scope else "<type>" if not commit_type else commit_type}: <subject>

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
                            content=TextContent(type="text", text=prompt_text),
                        )
                    ],
                )

            case "pr-description":
                title = args.get("title", "")
                changes = args.get("changes", "")
                breaking = args.get("breaking", "")

                breaking_section = (
                    f"\n## ⚠️ Breaking Changes\n{breaking}\n" if breaking else ""
                )

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
5. **Breaking Changes** - If any (you mentioned: {breaking or "none"})
6. **Checklist** - Standard PR checklist

Format using GitHub-flavored markdown with appropriate headers, lists, and formatting."""

                return GetPromptResult(
                    description="Pull request description generator",
                    messages=[
                        PromptMessage(
                            role="user",
                            content=TextContent(type="text", text=prompt_text),
                        )
                    ],
                )

            case "release-notes":
                version = args.get("version", "")
                commits = args.get("commits", "")
                previous_version = args.get("previous_version", "")

                version_info = (
                    f"from {previous_version} to {version}"
                    if previous_version
                    else f"for version {version}"
                )

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
                            content=TextContent(type="text", text=prompt_text),
                        )
                    ],
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
                            content=TextContent(type="text", text=prompt_text),
                        )
                    ],
                )

            case "merge-conflict-resolution":
                conflicts = args.get("conflicts", "")
                branch_info = args.get("branch_info", "")

                branch_section = (
                    f"\n**Branch Information:**\n{branch_info}\n" if branch_info else ""
                )

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
                            content=TextContent(type="text", text=prompt_text),
                        )
                    ],
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
                            content=TextContent(type="text", text=prompt_text),
                        )
                    ],
                )

            case "branch-strategy":
                project_type = args.get("project_type", "")
                deployment_frequency = args.get("deployment_frequency", "")

                deploy_context = (
                    f" with {deployment_frequency} deployments"
                    if deployment_frequency
                    else ""
                )

                prompt_text = f"""Recommend an optimal branching strategy for a {project_type} project{deploy_context}.

Consider:

1. **Project Characteristics**
   - Type: {project_type}
   - Deployment frequency: {deployment_frequency or "not specified"}

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
                            content=TextContent(type="text", text=prompt_text),
                        )
                    ],
                )

            case "git-troubleshooting":
                issue = args.get("issue", "")
                git_status = args.get("git_status", "")

                status_section = (
                    f"\n**Git Status Output:**\n```\n{git_status}\n```\n"
                    if git_status
                    else ""
                )

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
                            content=TextContent(type="text", text=prompt_text),
                        )
                    ],
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
   - Write for end users, not for developers
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
                            content=TextContent(type="text", text=prompt_text),
                        )
                    ],
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
                            content=TextContent(type="text", text=prompt_text),
                        )
                    ],
                )

            case "github-actions-failure-analysis":
                failure_logs = args.get("failure_logs", "")
                workflow_file = args.get("workflow_file", "")
                changed_files = args.get("changed_files", "")

                workflow_section = (
                    f"\n**Workflow File:**\n```yaml\n{workflow_file}\n```\n"
                    if workflow_file
                    else ""
                )
                files_section = (
                    f"\n**Changed Files:**\n{changed_files}\n" if changed_files else ""
                )

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
                            content=TextContent(type="text", text=prompt_text),
                        )
                    ],
                )

            case "ci-failure-root-cause":
                error_message = args.get("error_message", "")
                stack_trace = args.get("stack_trace", "")
                environment_info = args.get("environment_info", "")

                stack_section = (
                    f"\n**Stack Trace:**\n```\n{stack_trace}\n```\n"
                    if stack_trace
                    else ""
                )
                env_section = (
                    f"\n**Environment:**\n{environment_info}\n"
                    if environment_info
                    else ""
                )

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
                            content=TextContent(type="text", text=prompt_text),
                        )
                    ],
                )

            case "pr-readiness-assessment":
                pr_details = args.get("pr_details", "")
                ci_status = args.get("ci_status", "")
                review_comments = args.get("review_comments", "")

                ci_section = f"\n**CI Status:**\n{ci_status}\n" if ci_status else ""
                reviews_section = (
                    f"\n**Review Comments:**\n{review_comments}\n"
                    if review_comments
                    else ""
                )

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
                            content=TextContent(type="text", text=prompt_text),
                        )
                    ],
                )

            case "github-pr-creation":
                branch_name = args.get("branch_name", "")
                changes_summary = args.get("changes_summary", "")
                breaking_changes = args.get("breaking_changes", "")
                target_audience = args.get("target_audience", "developers")
                urgency = args.get("urgency", "medium")

                breaking_section = (
                    f"\n**Breaking Changes:**\n{breaking_changes}\n"
                    if breaking_changes
                    else ""
                )

                prompt_text = f"""Generate comprehensive content for a new GitHub Pull Request.

**Context:**
- **Source Branch:** `{branch_name}`
- **Urgency:** {urgency.capitalize()}
- **Target Audience:** {target_audience}

**Summary of Changes:**
```
{changes_summary}
```
{breaking_section}
**Request:**

Based on the provided context and changes, generate the following components for the `github_create_pr` tool:

1.  **PR Title:**
    - A concise, descriptive title following Conventional Commits format (e.g., `feat(api): Add user authentication endpoint`).
    - The title should be clear and immediately understandable.

2.  **PR Body (in Markdown):**
    - **Description:** A detailed explanation of *what* was changed and *why*.
    - **Changes Made:** A bulleted list of specific changes.
    - **Testing Strategy:** How these changes have been tested (e.g., unit tests, integration tests, manual testing).
    - **Related Issues:** A section to link any related issues (e.g., `Closes #123`).
    - **Screenshots/GIFs:** Placeholders for visual evidence, if applicable.
    - **Checklist:** A self-review checklist for the author.

3.  **Suggested Labels (as a comma-separated list):**
    - Suggest relevant labels from this list: `feature`, `bug`, `documentation`, `refactor`, `tests`, `ci`, `breaking-change`, `needs-review`, `wip`.
    - Consider the changes summary and urgency.

4.  **Suggested Reviewers (as a comma-separated list of GitHub usernames):**
    - Based on the `target_audience` and type of changes, suggest 1-3 potential reviewers (use placeholder usernames like `dev-lead`, `qa-specialist`, `security-expert`).

**Example Output Format:**

**Title:**
feat(auth): Implement password reset functionality

**Body:**
### Description
This PR introduces a secure password reset flow for users who have forgotten their password. It includes API endpoints, email notifications, and a frontend interface.

### Changes Made
- Added `POST /api/auth/forgot-password` endpoint.
- Added `POST /api/auth/reset-password` endpoint.
- Created a new `PasswordReset` model and database table.
- Implemented email service to send reset links.
- Built React components for the password reset form.

### Testing Strategy
- Unit tests for all new API endpoints (100% coverage).
- Integration tests for the full reset flow.
- Manually tested in staging environment.

### Related Issues
- Closes #45

**Labels:**
feature, needs-review, security

**Reviewers:**
dev-lead, security-expert
"""
                return GetPromptResult(
                    description="GitHub PR creation content generator",
                    messages=[
                        PromptMessage(
                            role="user",
                            content=TextContent(type="text", text=prompt_text),
                        )
                    ],
                )

            case "github-pr-comment-generation":
                diff_content = args.get("diff_content", "")
                comment_type = args.get("comment_type", "review")
                specific_focus = args.get("specific_focus", "general")
                tone = args.get("tone", "constructive")

                prompt_text = f"""Generate a high-quality, professional comment for a GitHub Pull Request review.

**Context:**
- **Comment Type:** {comment_type}
- **Specific Focus:** {specific_focus}
- **Desired Tone:** {tone}

**Code Snippet / Diff to Review:**
```diff
{diff_content}
```

**Request:**

Based on the provided code and context, generate a comment for the `github_add_pr_comment` tool.

**Guidelines for the comment:**
1.  **Be Specific:** Refer to specific lines or logic in the provided diff.
2.  **Explain the "Why":** Don't just say something is wrong; explain *why* it's a concern and what the impact is (e.g., performance, security, maintainability).
3.  **Offer Solutions:** When possible, suggest concrete improvements or alternative approaches. Use GitHub's suggestion syntax for code changes.
4.  **Use the Right Tone:** The comment should be `{tone}`. Frame feedback as questions or suggestions to foster collaboration (e.g., "Have you considered...?" or "What do you think about...?").
5.  **Structure based on `comment_type`:**
    - **review:** A general review comment pointing out a specific issue or area for improvement.
    - **suggestion:** A direct code suggestion using GitHub's suggestion syntax (```suggestion\n...code...\n```).
    - **approval:** A positive comment confirming that the code looks good, perhaps with minor nits.
    - **request_changes:** A clear, non-blocking comment that explains what changes are needed before approval.

**Example for a 'suggestion' comment:**

This logic for fetching the user seems a bit inefficient as it could make multiple database calls in a loop.

What do you think about fetching all users in a single batch request outside the loop to improve performance?

```suggestion
const userIds = items.map(item => item.userId);
const users = await db.users.getByIds(userIds);
const userMap = new Map(users.map(u => [u.id, u]));

for (const item of items) {{
  const user = userMap.get(item.userId);
  // ...
}}
```
This approach should be more performant, especially with a large number of items. Let me know your thoughts!
"""
                return GetPromptResult(
                    description="GitHub PR comment generator",
                    messages=[
                        PromptMessage(
                            role="user",
                            content=TextContent(type="text", text=prompt_text),
                        )
                    ],
                )

            case "github-merge-strategy-recommendation":
                pr_details = args.get("pr_details", "")
                commit_history = args.get("commit_history", "")
                team_preferences = args.get("team_preferences", "no preference")
                risk_level = args.get("risk_level", "medium")

                prompt_text = f"""Analyze the provided Pull Request information and recommend the best merge strategy.

**PR Context:**
- **PR Details:** {pr_details}
- **Commit History:**
```
{commit_history}
```
- **Team Preferences:** {team_preferences}
- **Risk Level:** {risk_level}

**Request:**

Recommend a merge strategy for the `github_merge_pr` tool. The options are `merge`, `squash`, or `rebase`.

Provide a structured recommendation including:

1.  **Recommended Strategy:** State the recommended strategy clearly (e.g., "Recommended Strategy: `squash`").
2.  **Rationale:** Provide a detailed justification for your recommendation. Consider the following factors:
    - **Commit History Clarity:** Is the commit history messy with many small, incremental, or "fixup" commits? (Favors `squash` or `rebase`).
    - **Feature Atomicity:** Does the PR represent a single, atomic feature? (Favors `squash`).
    - **Historical Record:** Is it important to preserve the detailed development history of this branch? (Favors `merge` or `rebase`).
    - **Risk and Rollback:** How does the strategy affect the ease of identifying and reverting changes?
    - **Team Workflow:** How does the recommendation align with the team's preferences?
3.  **`github_merge_pr` Parameters:**
    - **`merge_method`**: The recommended strategy (`merge`, `squash`, or `rebase`).
    - **`commit_title`**: A well-crafted commit title for the merge. For `squash`, this will be the title of the squashed commit.
    - **`commit_message`**: A detailed commit message. For `squash`, this should summarize the changes from the PR.

**Example Output:**

**Recommended Strategy:** `squash`

**Rationale:**
The commit history for this PR contains several small, incremental commits (e.g., "fix typo", "wip"). Squashing these into a single, atomic commit will create a cleaner and more readable history on the `main` branch. Since the PR represents a single feature ("Add User Profile Page"), a single commit accurately reflects the change. This aligns with the team's preference for a linear history.

**`github_merge_pr` Parameters:**
- **`merge_method`**: `squash`
- **`commit_title`**: `feat(profile): Add user profile page`
- **`commit_message`**:
  - Implements a new user profile page accessible at `/profile/:username`.
  - Displays user information, recent activity, and profile settings.
  - Includes backend API endpoints to fetch user data.
  - Closes #78.
"""
                return GetPromptResult(
                    description="GitHub merge strategy recommender",
                    messages=[
                        PromptMessage(
                            role="user",
                            content=TextContent(type="text", text=prompt_text),
                        )
                    ],
                )

            case "github-pr-update-guidance":
                review_feedback = args.get("review_feedback", "")
                current_pr_state = args.get("current_pr_state", "")
                priority_issues = args.get("priority_issues", "")
                timeline = args.get("timeline", "not specified")

                priority_section = (
                    f"\n**High-Priority Issues:**\n{priority_issues}\n"
                    if priority_issues
                    else ""
                )
                timeline_section = f"\n**Timeline:** {timeline}\n" if timeline else ""

                prompt_text = f"""Generate a systematic plan to update a GitHub Pull Request based on review feedback.

**Context:**
- **Current PR State:**
```
{current_pr_state}
```
- **Review Feedback Received:**
```
{review_feedback}
```
{priority_section}{timeline_section}
**Request:**

Create a structured action plan for updating the PR. The plan should help the developer use tools like `git_add`, `git_commit`, and `git_push` effectively.

The output should be a clear, actionable checklist in Markdown format.

**The plan should include:**
1.  **Feedback Triage:**
    - Group related feedback items.
    - Prioritize changes, starting with blocking issues or those identified as high-priority.
    - Acknowledge all feedback points, even if no change is made (with a justification).

2.  **Actionable Checklist:**
    - Create a task list (`- [ ]`) for each required code change, test update, or documentation adjustment.
    - For each task, specify the file(s) to be modified.
    - Suggest logical commit points. For example, group related changes into a single commit.

3.  **Communication Plan:**
    - Suggest how to communicate progress to the reviewers.
    - Recommend pushing changes and then re-requesting a review.
    - Provide a template for a summary comment to post on the PR after updates are pushed, explaining what was changed.

**Example Output:**

### PR Update Action Plan

Here is a plan to address the review feedback for your PR.

#### 1. Feedback Triage & Prioritization
- **High Priority (Blocking):**
  - Address the security vulnerability in `auth.py`.
  - Fix the failing unit test in `test_user_model.py`.
- **Medium Priority:**
  - Refactor the `calculate_stats` function for better readability.
  - Add missing documentation for the `/api/data` endpoint.
- **Low Priority (Nits):
  - Correct typos in code comments.

#### 2. Implementation Checklist
- [ ] **Security Fix:** In `src/auth.py`, replace the use of `eval()` with a safer data parsing method.
- [ ] **Commit 1:** Create a commit for the security fix: `git commit -m "fix(auth): Remove insecure use of eval()"`
- [ ] **Test Fix:** In `tests/test_user_model.py`, correct the assertion to match the expected output.
- [ ] **Refactor:** In `src/utils.py`, break down the `calculate_stats` function into smaller, helper functions.
- [ ] **Documentation:** Add OpenAPI-compliant docstrings to the `get_data` function in `src/api.py`.
- [ ] **Commit 2:** Group the test fix, refactor, and documentation changes into a single commit: `git commit -m "refactor(stats): Improve readability and add docs"`
- [ ] **Push Changes:** Push both new commits to your branch: `git push`

#### 3. Communication with Reviewers
After pushing your changes, post the following summary comment on the PR and re-request a review:

> Thanks for the feedback! I've pushed updates to address the points raised:
> - The security vulnerability in `auth.py` has been resolved.
> - The failing unit test is now passing.
> - I've refactored `calculate_stats` and added the missing API documentation.
>
> Ready for another look!
"""
                return GetPromptResult(
                    description="GitHub PR update guidance generator",
                    messages=[
                        PromptMessage(
                            role="user",
                            content=TextContent(type="text", text=prompt_text),
                        )
                    ],
                )

            case _:
                raise ValueError(f"Unknown prompt: {name}")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name=GitTools.STATUS,
                description="Shows the working tree status with optional porcelain (machine-readable) format",
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
            # Advanced git operations
            Tool(
                name=GitTools.REBASE,
                description="Rebase current branch onto target branch",
                inputSchema=GitRebase.model_json_schema(),
            ),
            Tool(
                name=GitTools.MERGE,
                description="Merge source branch into current branch with strategy options",
                inputSchema=GitMerge.model_json_schema(),
            ),
            Tool(
                name=GitTools.CHERRY_PICK,
                description="Cherry-pick a commit onto current branch",
                inputSchema=GitCherryPick.model_json_schema(),
            ),
            Tool(
                name=GitTools.ABORT,
                description="Abort an ongoing git operation (rebase, merge, cherry-pick)",
                inputSchema=GitAbort.model_json_schema(),
            ),
            Tool(
                name=GitTools.CONTINUE,
                description="Continue an ongoing git operation after resolving conflicts",
                inputSchema=GitContinue.model_json_schema(),
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
            ),
            Tool(
                name=GitTools.GITHUB_CREATE_PR,
                description="Create a new pull request",
                inputSchema=GitHubCreatePR.model_json_schema(),
            ),
            Tool(
                name=GitTools.GITHUB_UPDATE_PR,
                description="Update a pull request's title, body, or state",
                inputSchema=GitHubUpdatePR.model_json_schema(),
            ),
            Tool(
                name=GitTools.GITHUB_MERGE_PR,
                description="Merge a pull request with a specified method (merge, squash, rebase)",
                inputSchema=GitHubMergePR.model_json_schema(),
            ),
            Tool(
                name=GitTools.GITHUB_ADD_PR_COMMENT,
                description="Add a comment to a pull request",
                inputSchema=GitHubAddPRComment.model_json_schema(),
            ),
            Tool(
                name=GitTools.GITHUB_CLOSE_PR,
                description="Close a pull request",
                inputSchema=GitHubClosePR.model_json_schema(),
            ),
            Tool(
                name=GitTools.GITHUB_REOPEN_PR,
                description="Reopen a closed pull request",
                inputSchema=GitHubReopenPR.model_json_schema(),
            ),
            # Security tools
            Tool(
                name=GitTools.GIT_SECURITY_VALIDATE,
                description="Validate Git security configuration for the repository",
                inputSchema=GitSecurityValidate.model_json_schema(),
            ),
            Tool(
                name=GitTools.GIT_SECURITY_ENFORCE,
                description="Enforce secure Git configuration (GPG signing, proper user config)",
                inputSchema=GitSecurityEnforce.model_json_schema(),
            ),
        ]

    async def list_repos() -> Sequence[str]:
        async def by_roots() -> Sequence[str]:
            if not isinstance(server.request_context.session, ServerSession):
                raise TypeError(
                    "server.request_context.session must be a ServerSession"
                )

            if not server.request_context.session.check_client_capability(
                ClientCapabilities(roots=RootsCapability())
            ):
                return []

            roots_result: ListRootsResult = (
                await server.request_context.session.list_roots()
            )
            logger.debug(f"Roots result: {roots_result}")
            repo_paths = []
            for root in roots_result.roots:
                path = root.uri.path
                try:
                    Repo(path)
                    repo_paths.append(str(path))
                except InvalidGitRepositoryError:
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
        logger = logging.getLogger(__name__)
        request_id = os.urandom(4).hex()
        start_time = time.time()
        session_id = arguments.get("session_id") or os.environ.get(
            "MCP_SESSION_ID", "default"
        )

        logger.info(
            f"🔧 [{request_id}] Tool call: {name}",
            extra={"request_id": request_id, "session_id": session_id},
        )
        logger.debug(
            f"🔧 [{request_id}] Arguments: {arguments}",
            extra={"request_id": request_id, "session_id": session_id},
        )

        # Heartbeat tool: allow explicit heartbeat calls (optional, for test/monitoring)
        if name == "heartbeat":
            session_id = arguments.get("session_id")
            if session_id:
                await heartbeat_manager.record_heartbeat(session_id)
                await global_metrics_collector.record_message("heartbeat", 0)
                return [
                    TextContent(
                        type="text", text=f"Heartbeat received for session {session_id}"
                    )
                ]
            else:
                return [
                    TextContent(
                        type="text", text="No session_id provided for heartbeat"
                    )
                ]
        try:
            result: list[TextContent] | None = None  # Initialize result variable

            # Determine if the tool requires a repo_path or is a GitHub API tool
            is_github_api_tool = name in [
                GitTools.GITHUB_GET_PR_CHECKS,
                GitTools.GITHUB_GET_FAILING_JOBS,
                GitTools.GITHUB_GET_WORKFLOW_RUN,
                GitTools.GITHUB_GET_PR_DETAILS,
                GitTools.GITHUB_LIST_PULL_REQUESTS,
                GitTools.GITHUB_GET_PR_STATUS,
                GitTools.GITHUB_GET_PR_FILES,
                GitTools.GITHUB_CREATE_PR,
                GitTools.GITHUB_UPDATE_PR,
                GitTools.GITHUB_MERGE_PR,
                GitTools.GITHUB_ADD_PR_COMMENT,
                GitTools.GITHUB_CLOSE_PR,
                GitTools.GITHUB_REOPEN_PR,
            ]

            repo = None
            if not is_github_api_tool:
                # All other tools require repo_path
                repo_path = Path(arguments["repo_path"])

                # Handle git init separately since it doesn't require an existing repo
                if name == GitTools.INIT:
                    result = [TextContent(type="text", text=git_init(str(repo_path)))]
                    duration = time.time() - start_time
                    await global_metrics_collector.record_message(name, duration * 1000)
                    logger.info(
                        f"✅ [{request_id}] Tool '{name}' completed in {duration:.2f}s",
                        extra={
                            "request_id": request_id,
                            "session_id": session_id,
                            "duration_ms": int(duration * 1000),
                        },
                    )
                    return result

                # For all other non-GitHub commands, we need an existing repo
                try:
                    repo = Repo(repo_path)
                except InvalidGitRepositoryError as e:
                    duration = time.time() - start_time
                    await global_metrics_collector.record_operation(
                        name, False, duration * 1000
                    )
                    logger.error(
                        f"📁 [{request_id}] Invalid git repository at {repo_path}: {e}",
                        extra={
                            "request_id": request_id,
                            "session_id": session_id,
                            "duration_ms": int(duration * 1000),
                        },
                    )
                    return [
                        TextContent(
                            type="text",
                            text=f"❌ Invalid git repository at {repo_path}. Please ensure the path contains a valid git repository.",
                        )
                    ]

            # Now, execute the tool based on its name
            if not is_github_api_tool:
                # Git operations
                match name:
                    case GitTools.STATUS:
                        porcelain_raw = arguments.get("porcelain", False)
                        porcelain = (
                            porcelain_raw
                            if isinstance(porcelain_raw, bool)
                            else str(porcelain_raw).lower() in ("true", "1", "yes")
                        )
                        status = git_status(repo, porcelain)
                        prefix = (
                            "Repository status (porcelain):"
                            if porcelain
                            else "Repository status:"
                        )
                        result = [TextContent(type="text", text=f"{prefix}\n{status}")]

                    case GitTools.DIFF_UNSTAGED:
                        diff = git_diff_unstaged(repo)
                        result = [
                            TextContent(type="text", text=f"Unstaged changes:\n{diff}")
                        ]

                    case GitTools.DIFF_STAGED:
                        diff = git_diff_staged(repo)
                        result = [
                            TextContent(type="text", text=f"Staged changes:\n{diff}")
                        ]

                    case GitTools.DIFF:
                        diff = git_diff(repo, arguments["target"])
                        result = [
                            TextContent(
                                type="text",
                                text=f"Diff with {arguments['target']}:\n{diff}",
                            )
                        ]

                    case GitTools.COMMIT:
                        commit_result = git_commit(
                            repo,
                            arguments["message"],
                            arguments.get("gpg_sign", False),
                            arguments.get("gpg_key_id"),
                        )
                        result = [TextContent(type="text", text=commit_result)]

                    case GitTools.ADD:
                        add_result = git_add(repo, arguments["files"])
                        result = [TextContent(type="text", text=add_result)]

                    case GitTools.RESET:
                        reset_result = git_reset(repo)
                        result = [TextContent(type="text", text=reset_result)]

                    case GitTools.LOG:
                        log = git_log(
                            repo,
                            arguments.get("max_count", 10),
                            arguments.get("oneline", False),
                            arguments.get("graph", False),
                            arguments.get("format_str"),
                        )
                        result = [
                            TextContent(
                                type="text", text="Commit history:\n" + "\n".join(log)
                            )
                        ]

                    case GitTools.CREATE_BRANCH:
                        branch_result = git_create_branch(
                            repo, arguments["branch_name"], arguments.get("base_branch")
                        )
                        result = [TextContent(type="text", text=branch_result)]

                    case GitTools.CHECKOUT:
                        checkout_result = git_checkout(repo, arguments["branch_name"])
                        result = [TextContent(type="text", text=checkout_result)]

                    case GitTools.SHOW:
                        show_result = git_show(repo, arguments["revision"])
                        result = [TextContent(type="text", text=show_result)]

                    case GitTools.PUSH:
                        push_result = git_push(
                            repo,
                            arguments.get("remote", "origin"),
                            arguments.get("branch"),
                            arguments.get("force", False),
                            arguments.get("set_upstream", False),
                        )
                        result = [TextContent(type="text", text=push_result)]

                    case GitTools.PULL:
                        pull_result = git_pull(
                            repo,
                            arguments.get("remote", "origin"),
                            arguments.get("branch"),
                        )
                        result = [TextContent(type="text", text=pull_result)]

                    case GitTools.DIFF_BRANCHES:
                        diff_branches_result = git_diff_branches(
                            repo, arguments["base_branch"], arguments["compare_branch"]
                        )
                        result = [TextContent(type="text", text=diff_branches_result)]

                    # Advanced git operations
                    case GitTools.REBASE:
                        rebase_result = git_rebase(
                            repo,
                            arguments["target_branch"],
                            arguments.get("interactive", False),
                        )
                        result = [TextContent(type="text", text=rebase_result)]

                    case GitTools.MERGE:
                        merge_result = git_merge(
                            repo,
                            arguments["source_branch"],
                            arguments.get("strategy", "merge"),
                            arguments.get("message"),
                        )
                        result = [TextContent(type="text", text=merge_result)]

                    case GitTools.CHERRY_PICK:
                        cherry_pick_result = git_cherry_pick(
                            repo,
                            arguments["commit_hash"],
                            arguments.get("no_commit", False),
                        )
                        result = [TextContent(type="text", text=cherry_pick_result)]

                    case GitTools.ABORT:
                        abort_result = git_abort(repo, arguments["operation"])
                        result = [TextContent(type="text", text=abort_result)]

                    case GitTools.CONTINUE:
                        continue_result = git_continue(repo, arguments["operation"])
                        result = [TextContent(type="text", text=continue_result)]

                    # Security tools
                    case GitTools.GIT_SECURITY_VALIDATE:
                        validation_result = validate_git_security_config(repo)

                        status_emoji = (
                            "✅" if validation_result["status"] == "secure" else "⚠️"
                        )
                        result_text = (
                            f"{status_emoji} Git Security Validation Results\n\n"
                        )

                        if validation_result["warnings"]:
                            result_text += "Security Warnings:\n"
                            for warning in validation_result["warnings"]:
                                result_text += f"  - {warning}\n"
                            result_text += "\n"

                        if validation_result["recommendations"]:
                            result_text += "Recommendations:\n"
                            for rec in validation_result["recommendations"]:
                                result_text += f"  - {rec}\n"
                            result_text += "\n"

                        result_text += "Current Configuration:\n"
                        for key, value in validation_result["config"].items():
                            result_text += f"  - {key}: {value}\n"

                        result = [TextContent(type="text", text=result_text)]

                    case GitTools.GIT_SECURITY_ENFORCE:
                        strict_mode = arguments.get("strict_mode", True)
                        enforce_result = enforce_secure_git_config(repo, strict_mode)
                        result = [TextContent(type="text", text=enforce_result)]

                    case _:
                        logger.error(f"❌ [{request_id}] Unknown tool: {name}")
                        raise ValueError(f"Unknown tool: {name}")
            else:
                # GitHub API tools
                logger.debug(
                    f"🔍 [{request_id}] Tool is GitHub API tool, processing..."
                )
                # All GitHub API tools require repo_owner and repo_name
                repo_owner = arguments.get("repo_owner")
                repo_name = arguments.get("repo_name")
                if not repo_owner or not repo_name:
                    result = [
                        TextContent(
                            type="text",
                            text="❌ repo_owner and repo_name parameters are required for GitHub API tools",
                        )
                    ]
                else:
                    match name:
                        case GitTools.GITHUB_GET_PR_DETAILS:
                            pr_details_result = await github_get_pr_details(
                                repo_owner,
                                repo_name,
                                arguments["pr_number"],
                                arguments.get("include_files", False),
                                arguments.get("include_reviews", False),
                            )
                            result = [TextContent(type="text", text=pr_details_result)]

                        case GitTools.GITHUB_GET_PR_CHECKS:
                            pr_checks_result = await github_get_pr_checks(
                                repo_owner,
                                repo_name,
                                arguments["pr_number"],
                                arguments.get("status"),
                                arguments.get("conclusion"),
                            )
                            result = [TextContent(type="text", text=pr_checks_result)]

                        case GitTools.GITHUB_GET_FAILING_JOBS:
                            failing_jobs_result = await github_get_failing_jobs(
                                repo_owner,
                                repo_name,
                                arguments["pr_number"],
                                arguments.get("include_logs", True),
                                arguments.get("include_annotations", True),
                            )
                            result = [
                                TextContent(type="text", text=failing_jobs_result)
                            ]

                        case GitTools.GITHUB_GET_WORKFLOW_RUN:
                            workflow_run_result = await github_get_workflow_run(
                                repo_owner,
                                repo_name,
                                arguments["run_id"],
                                arguments.get("include_logs", False),
                            )
                            result = [
                                TextContent(type="text", text=workflow_run_result)
                            ]

                        case GitTools.GITHUB_LIST_PULL_REQUESTS:
                            logger.debug(
                                f"🔍 Tool handler: GITHUB_LIST_PULL_REQUESTS called with arguments: {arguments}"
                            )
                            logger.debug(
                                f"🔍 Tool handler: repo_owner={repo_owner}, repo_name={repo_name}"
                            )
                            list_prs_result = await github_list_pull_requests(
                                repo_owner,
                                repo_name,
                                arguments.get("state", "open"),
                                arguments.get("head"),
                                arguments.get("base"),
                                arguments.get("sort", "created"),
                                arguments.get("direction", "desc"),
                                arguments.get("per_page", 30),
                                arguments.get("page", 1),
                            )
                            logger.debug(
                                f"🔍 Tool handler: Function returned, type: {type(list_prs_result)}, value: {list_prs_result}"
                            )
                            result = [TextContent(type="text", text=list_prs_result)]
                            logger.debug(
                                "🔍 Tool handler: TextContent created successfully"
                            )

                        case GitTools.GITHUB_GET_PR_STATUS:
                            pr_status_result = await github_get_pr_status(
                                repo_owner, repo_name, arguments["pr_number"]
                            )
                            result = [TextContent(type="text", text=pr_status_result)]

                        case GitTools.GITHUB_GET_PR_FILES:
                            pr_files_result = await github_get_pr_files(
                                repo_owner,
                                repo_name,
                                arguments["pr_number"],
                                arguments.get("per_page", 30),
                                arguments.get("page", 1),
                                arguments.get("include_patch", False),
                            )
                            result = [TextContent(type="text", text=pr_files_result)]

                        case GitTools.GITHUB_CREATE_PR:
                            create_pr_result = await github_create_pr(
                                repo_owner,
                                repo_name,
                                arguments["title"],
                                arguments["head"],
                                arguments["base"],
                                arguments.get("body"),
                                arguments.get("draft", False),
                            )
                            result = [TextContent(type="text", text=create_pr_result)]

                        case GitTools.GITHUB_UPDATE_PR:
                            update_pr_result = await github_update_pr(
                                repo_owner,
                                repo_name,
                                arguments["pr_number"],
                                arguments.get("title"),
                                arguments.get("body"),
                                arguments.get("state"),
                            )
                            result = [TextContent(type="text", text=update_pr_result)]

                        case GitTools.GITHUB_MERGE_PR:
                            merge_pr_result = await github_merge_pr(
                                repo_owner,
                                repo_name,
                                arguments["pr_number"],
                                arguments.get("commit_title"),
                                arguments.get("commit_message"),
                                arguments.get("merge_method", "merge"),
                            )
                            result = [TextContent(type="text", text=merge_pr_result)]

                        case GitTools.GITHUB_ADD_PR_COMMENT:
                            add_comment_result = await github_add_pr_comment(
                                repo_owner,
                                repo_name,
                                arguments["pr_number"],
                                arguments["body"],
                            )
                            result = [TextContent(type="text", text=add_comment_result)]

                        case GitTools.GITHUB_CLOSE_PR:
                            close_pr_result = await github_close_pr(
                                repo_owner, repo_name, arguments["pr_number"]
                            )
                            result = [TextContent(type="text", text=close_pr_result)]

                        case GitTools.GITHUB_REOPEN_PR:
                            reopen_pr_result = await github_reopen_pr(
                                repo_owner, repo_name, arguments["pr_number"]
                            )
                            result = [TextContent(type="text", text=reopen_pr_result)]

                        case _:
                            logger.error(
                                f"❌ [{request_id}] Unknown GitHub API tool: {name}"
                            )
                            raise ValueError(f"Unknown GitHub API tool: {name}")

        except subprocess.TimeoutExpired as e:
            duration = time.time() - start_time
            await global_metrics_collector.record_operation(
                name, False, duration * 1000
            )
            logger.error(
                f"⏰ [{request_id}] Tool '{name}' timed out after {duration:.2f}s: {e}",
                extra={
                    "request_id": request_id,
                    "session_id": session_id,
                    "duration_ms": int(duration * 1000),
                },
            )
            return [
                TextContent(
                    type="text",
                    text=f"⏰ Tool '{name}' timed out. Operation may be too slow or system is under heavy load. Please try again.",
                )
            ]

        except subprocess.SubprocessError as e:
            duration = time.time() - start_time
            await global_metrics_collector.record_operation(
                name, False, duration * 1000
            )
            logger.error(
                f"🔧 [{request_id}] Tool '{name}' subprocess error after {duration:.2f}s: {e}",
                extra={
                    "request_id": request_id,
                    "session_id": session_id,
                    "duration_ms": int(duration * 1000),
                },
            )
            return [
                TextContent(
                    type="text",
                    text=f"🔧 Subprocess error in '{name}': {str(e)}. Check system configuration and permissions.",
                )
            ]

        except GitCommandError as e:
            duration = time.time() - start_time
            await global_metrics_collector.record_operation(
                name, False, duration * 1000
            )
            logger.error(
                f"📝 [{request_id}] Tool '{name}' git error after {duration:.2f}s: {e}",
                extra={
                    "request_id": request_id,
                    "session_id": session_id,
                    "duration_ms": int(duration * 1000),
                },
            )
            return [
                TextContent(
                    type="text",
                    text=f"📝 Git error in '{name}': {str(e)}. Verify repository state and git configuration.",
                )
            ]

        except PermissionError as e:
            duration = time.time() - start_time
            await global_metrics_collector.record_operation(
                name, False, duration * 1000
            )
            logger.error(
                f"🔒 [{request_id}] Tool '{name}' permission error after {duration:.2f}s: {e}",
                extra={
                    "request_id": request_id,
                    "session_id": session_id,
                    "duration_ms": int(duration * 1000),
                },
            )
            return [
                TextContent(
                    type="text",
                    text=f"🔒 Permission error in '{name}': {str(e)}. Check file and directory permissions.",
                )
            ]

        except FileNotFoundError as e:
            duration = time.time() - start_time
            await global_metrics_collector.record_operation(
                name, False, duration * 1000
            )
            logger.error(
                f"📁 [{request_id}] Tool '{name}' file not found after {duration:.2f}s: {e}",
                extra={
                    "request_id": request_id,
                    "session_id": session_id,
                    "duration_ms": int(duration * 1000),
                },
            )
            return [
                TextContent(
                    type="text",
                    text=f"📁 File not found in '{name}': {str(e)}. Verify paths and file existence.",
                )
            ]

        except Exception as e:
            duration = time.time() - start_time
            await global_metrics_collector.record_operation(
                name, False, duration * 1000
            )
            logger.error(
                f"❌ [{request_id}] Tool '{name}' unexpected error after {duration:.2f}s: {e}",
                exc_info=True,
                extra={
                    "request_id": request_id,
                    "session_id": session_id,
                    "duration_ms": int(duration * 1000),
                },
            )
            # Critical: Never let any exception crash the server
            return [
                TextContent(
                    type="text",
                    text=f"❌ Unexpected error in '{name}': {str(e)}. The server remains operational. Check logs for details.",
                )
            ]

        # This should always be reached if no exception occurred
        duration = time.time() - start_time
        await global_metrics_collector.record_message(name, duration * 1000)
        logger.debug(
            f"🔍 [{request_id}] Tool execution finished, result type: {type(result)}",
            extra={
                "request_id": request_id,
                "session_id": session_id,
                "duration_ms": int(duration * 1000),
            },
        )
        if result is not None and len(result) > 0:
            logger.debug(
                f"🔍 [{request_id}] Result[0] type: {type(result[0])}, content preview: {str(result[0])[:200]}",
                extra={
                    "request_id": request_id,
                    "session_id": session_id,
                    "duration_ms": int(duration * 1000),
                },
            )
        logger.info(
            f"✅ [{request_id}] Tool '{name}' completed in {duration:.2f}s",
            extra={
                "request_id": request_id,
                "session_id": session_id,
                "duration_ms": int(duration * 1000),
            },
        )
        return result if result is not None else []

    # Server initialization logging
    logger.info("🎯 MCP Git Server initialized and ready to listen...")

    initialization_time = time.time() - start_time
    logger.info(f"📡 Server listening (startup took {initialization_time:.2f}s)")

    # Signal handler for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"📡 Received signal {signum}, initiating graceful shutdown...")

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Add periodic health check logging
    async def log_health():
        """Log periodic health checks to monitor server uptime and metrics"""
        while True:
            try:
                await asyncio.sleep(300)  # Every 5 minutes
                uptime = time.time() - start_time
                metrics = await global_metrics_collector.get_health_status()
                logger.info(
                    f"💓 Server health check - uptime: {uptime:.1f}s, active_sessions: {metrics['active_sessions']}, messages_processed: {metrics['messages_processed']}, error_count: {metrics['error_count']}",
                    extra={
                        "uptime_sec": uptime,
                        "active_sessions": metrics["active_sessions"],
                        "messages_processed": metrics["messages_processed"],
                        "error_count": metrics["error_count"],
                    },
                )
            except asyncio.CancelledError:
                logger.debug("🔚 Health check task cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Health check failed: {e}")

    # Start health logging task
    health_task = asyncio.create_task(log_health())

    # options = server.create_initialization_options()  # Removed unused variable

    try:
        if test_mode:
            logger.info("🧪 Running in test mode - staying alive for CI testing.")
            # In test mode, just stay alive for a reasonable time for CI testing
            await asyncio.sleep(10)  # Stay alive for 10 seconds for CI test
            logger.info("🧪 Test mode completed successfully")
        else:
            async with stdio_server() as (read_stream, write_stream):
                logger.info("🔗 STDIO server connected, starting main loop...")

                # Wrap the read stream with notification interception
                intercepted_read_stream = wrap_read_stream(read_stream)
                logger.debug(
                    "🔔 Notification interception enabled for cancelled notifications"
                )

                # Heartbeat notification handler
                async def handle_heartbeat_notification(message, session_id):
                    logger.debug(
                        f"Received heartbeat notification for session {session_id}"
                    )
                    await heartbeat_manager.record_heartbeat(session_id)
                    session = await session_manager.get_session(session_id)
                    if session:
                        await session.handle_heartbeat()
                        logger.info(f"Heartbeat processed for session {session_id}")
                    else:
                        logger.warning(f"Heartbeat for unknown session {session_id}")

                # Patch server to handle heartbeat notifications (example: via notification hook)
                # This is a placeholder for integration with the actual MCP notification system.
                # In a real implementation, you would register this handler with the server's notification router.

                # Run server with error isolation - CRITICAL: raise_exceptions=False prevents crashes
                await server.run(
                    intercepted_read_stream,
                    write_stream,
                    server.create_initialization_options(),
                    raise_exceptions=False,
                )
    except asyncio.CancelledError:
        logger.info("🛑 Server cancelled")
        raise
    except KeyboardInterrupt:
        logger.info("⌨️ Server interrupted by user")
        raise
    except Exception as e:
        error_msg = str(e).lower()

        # Enhanced error categorization to prevent crashes
        if "transport" in error_msg and "closed" in error_msg:
            logger.error(f"🔌 Transport error: {e}")
            logger.info(
                "🔌 This is often due to client disconnection or tool execution failure - server recovering gracefully"
            )
        elif "gpg" in error_msg:
            logger.error(f"🔒 GPG-related server error: {e}")
            logger.info(
                "🔒 GPG configuration issue detected - server remains operational"
            )
        elif "notification" in error_msg and "validation" in error_msg:
            logger.warning(f"🔔 Notification validation error: {e}")
            logger.info("🔔 Client notification issue - server continues normally")
        else:
            logger.error(f"💥 Server error: {e}", exc_info=True)
            logger.info("💥 Unexpected server error - attempting graceful recovery")

        # Don't re-raise - let server shutdown gracefully instead of crashing
        pass
    finally:
        # Log interception statistics before shutdown
        log_interception_stats()

        # Clean shutdown
        health_task.cancel()
        try:
            await health_task
        except asyncio.CancelledError:
            pass

        # Stop heartbeat manager
        await heartbeat_manager.stop()

        # Server shutdown logging
        total_uptime = time.time() - start_time
        logger.info(f"🔚 Server shutdown after {total_uptime:.1f}s uptime")


if __name__ == "__main__":
    # This guard prevents the server from running when the module is imported,
    # for example by pytest. The server should only run when this script is
    # executed directly.

    # To run this script, we need to handle command-line arguments and logging.
    import argparse

    # Set up basic logging to see server output when run directly.
    # The main application entry point might have more sophisticated logging setup.
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(
        description="Run the MCP Git Server. This is typically started by the main application, but can be run directly for development."
    )
    parser.add_argument(
        "repository",
        nargs="?",
        default=None,
        help="The path to the git repository to serve. If not provided, the server will wait for the client to specify workspace roots.",
    )
    args = parser.parse_args()

    repo_path = Path(args.repository) if args.repository else None

    try:
        # Run the main async function of the server.
        logger.info(
            f"Starting server directly for repository: {repo_path or 'Not specified'}"
        )
        asyncio.run(main(repository=repo_path))
    except KeyboardInterrupt:
        logger.info("⌨️ Server process interrupted by user.")
    except Exception as e:
        logger.critical(f"💥 Server failed to run: {e}", exc_info=True)
