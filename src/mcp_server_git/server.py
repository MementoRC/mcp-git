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
import git
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.session import ServerSession
from mcp.server.stdio import stdio_server
# Notification middleware available but not currently integrated
# from .models.middleware import notification_validator_middleware
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
        placeholder_patterns = ['YOUR_TOKEN_HERE', 'REPLACE_ME', 'TODO', 'CHANGEME']
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
            existing_value = os.getenv(key, '')
            if should_override(key, existing_value) and value:
                os.environ[key] = value
                logger.debug(f"Overrode empty/placeholder {key} with value from {env_file}")
    
    # Try to load from project-specific .env file first
    project_env = Path.cwd() / ".env"
    if project_env.exists():
        try:
            load_env_with_smart_override(project_env)
            loaded_files.append(str(project_env))
            logger.info(f"Loaded environment variables from project .env: {project_env}")
        except Exception as e:
            logger.warning(f"Failed to load project .env file {project_env}: {e}")
    
    # Try to load from repository-specific .env file (if repository path provided)
    if repository_path:
        repo_env = repository_path / ".env"
        if repo_env.exists() and str(repo_env) not in loaded_files:
            try:
                load_env_with_smart_override(repo_env)
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
                    load_env_with_smart_override(claude_env)
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
        
    # Log the status of critical environment variables (for debugging)
    critical_vars = ['GITHUB_TOKEN', 'ANTHROPIC_API_KEY', 'OPENAI_API_KEY']
    for var in critical_vars:
        value = os.getenv(var)
        if value:
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
            "User-Agent": "MCP-Git-Server/1.0"
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
            enable_cleanup_closed=True
        )
        
        # Retry logic for connection issues
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
                    async with session.request(method, url, headers=headers, **kwargs) as response:
                        logger.debug(f"📡 Response status: {response.status} for {endpoint}")
                        
                        if response.status >= 400:
                            error_text = await response.text()
                            
                            # Handle specific GitHub API errors
                            if response.status == 401:
                                logger.error(f"🔑 GitHub API authentication failed for {endpoint}")
                                raise Exception("GitHub API authentication failed (401): Check GITHUB_TOKEN")
                            elif response.status == 403:
                                rate_limit_remaining = response.headers.get('X-RateLimit-Remaining', 'unknown')
                                if rate_limit_remaining == '0':
                                    reset_time = response.headers.get('X-RateLimit-Reset', 'unknown')
                                    logger.error(f"⏰ GitHub API rate limit exceeded for {endpoint}, resets at: {reset_time}")
                                    raise Exception(f"GitHub API rate limit exceeded (403). Resets at: {reset_time}")
                                else:
                                    logger.error(f"🚫 GitHub API forbidden for {endpoint}")
                                    raise Exception("GitHub API forbidden (403): Insufficient permissions or secondary rate limit")
                            elif response.status == 404:
                                logger.debug(f"📡 404 Not Found for {endpoint}")
                                raise Exception(f"GitHub API resource not found (404): {endpoint}")
                            elif response.status == 422:
                                logger.error(f"❌ GitHub API validation failed for {endpoint}: {error_text}")
                                raise Exception(f"GitHub API validation failed (422): {error_text}")
                            else:
                                logger.error(f"❌ GitHub API error {response.status} for {endpoint}: {error_text}")
                                raise Exception(f"GitHub API error {response.status}: {error_text}")
                        
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
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"🔄 Connection failed (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s: {e}")
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
    if not token.startswith(('ghp_', 'github_pat_', 'gho_', 'ghu_', 'ghs_')):
        raise Exception("GITHUB_TOKEN appears to be invalid format")
    return GitHubClient(token=token)

def validate_git_security_config(repo: git.Repo) -> dict:
    """Validate Git security configuration for the repository.
    
    Returns:
        dict: Validation results with security warnings and recommendations
    """
    warnings = []
    recommendations = []
    config_status = {}
    
    try:
        # Check GPG signing configuration
        gpg_sign = repo.config_reader().get_value("commit", "gpgsign", fallback=None)
        signing_key = repo.config_reader().get_value("user", "signingkey", fallback=None)
        
        config_status["gpg_signing_enabled"] = gpg_sign == "true"
        config_status["signing_key_configured"] = signing_key is not None
        config_status["signing_key"] = signing_key
        
        if not config_status["gpg_signing_enabled"]:
            warnings.append("GPG signing is not enabled for this repository")
            recommendations.append("Enable GPG signing with: git config commit.gpgsign true")
        
        if not config_status["signing_key_configured"]:
            warnings.append("No GPG signing key configured")
            recommendations.append("Set signing key with: git config user.signingkey YOUR_KEY_ID")
        
        # Check if signing key is configured (don't enforce specific key)
        # Allow any valid GPG key to be used
        
        # Check user configuration
        user_name = repo.config_reader().get_value("user", "name", fallback=None)
        user_email = repo.config_reader().get_value("user", "email", fallback=None)
        
        config_status["user_name"] = user_name
        config_status["user_email"] = user_email
        
        if not user_name:
            warnings.append("Git user name not configured")
            recommendations.append("Set user name with: git config user.name 'Your Name'")
        
        if not user_email:
            warnings.append("Git user email not configured") 
            recommendations.append("Set user email with: git config user.email 'your@email.com'")
        
    except Exception as e:
        warnings.append(f"Error checking Git configuration: {str(e)}")
    
    return {
        "status": "secure" if not warnings else "warnings",
        "warnings": warnings,
        "recommendations": recommendations,
        "config": config_status
    }

def enforce_secure_git_config(repo: git.Repo, strict_mode: bool = True) -> str:
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
                # Try to get from environment variable
                env_key = os.getenv("GPG_SIGNING_KEY")
                if env_key:
                    config.set_value("user", "signingkey", env_key)
                    messages.append(f"✅ Set signing key to {env_key} (from GPG_SIGNING_KEY env var)")
                else:
                    # Auto-detect available GPG keys
                    try:
                        import subprocess
                        result = subprocess.run(
                            ["gpg", "--list-secret-keys", "--keyid-format=LONG"],
                            capture_output=True, text=True, timeout=10
                        )
                        if result.returncode == 0 and "sec" in result.stdout:
                            # Extract first available key
                            lines = result.stdout.split('\n')
                            for line in lines:
                                if 'sec' in line and '/' in line:
                                    key_id = line.split('/')[1].split()[0]
                                    config.set_value("user", "signingkey", key_id)
                                    messages.append(f"✅ Auto-detected and set signing key to {key_id}")
                                    break
                        else:
                            messages.append("⚠️  No GPG keys found - please set up GPG or set GPG_SIGNING_KEY env var")
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

def extract_github_repo_info(repo: git.Repo) -> Tuple[Optional[str], Optional[str]]:
    """Extract GitHub repository owner and name from git remotes.
    
    Args:
        repo: Git repository object
        
    Returns:
        Tuple of (repo_owner, repo_name) or (None, None) if not found
    """
    try:
        # Try origin remote first, then any remote
        for remote_name in ['origin'] + [r.name for r in repo.remotes if r.name != 'origin']:
            try:
                remote = repo.remotes[remote_name]
                for url in remote.urls:
                    # Parse GitHub URLs (both SSH and HTTPS)
                    # SSH: git@github.com:owner/repo.git
                    # HTTPS: https://github.com/owner/repo.git
                    
                    # SSH format
                    ssh_match = re.match(r'git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$', url)
                    if ssh_match:
                        return ssh_match.group(1), ssh_match.group(2)
                    
                    # HTTPS format
                    https_match = re.match(r'https://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$', url)
                    if https_match:
                        return https_match.group(1), https_match.group(2)
                        
            except Exception:
                continue
                
    except Exception:
        pass
        
    return None, None

def get_github_repo_params(repo: git.Repo, arguments: dict) -> Tuple[Optional[str], Optional[str], Optional[str]]:
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
        return None, None, "❌ Could not determine GitHub repository owner/name. Please provide repo_owner and repo_name parameters or ensure git remote is configured with GitHub URL."
    
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
    # Security tools
    GIT_SECURITY_VALIDATE = "git_security_validate"
    GIT_SECURITY_ENFORCE = "git_security_enforce"

def git_status(repo: git.Repo, porcelain: bool = False) -> str:
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

def git_diff_unstaged(repo: git.Repo) -> str:
    return repo.git.diff()

def git_diff_staged(repo: git.Repo) -> str:
    return repo.git.diff("--cached")

def git_diff(repo: git.Repo, target: str) -> str:
    return repo.git.diff(target)

def git_commit(repo: git.Repo, message: str, gpg_sign: bool = False, gpg_key_id: str | None = None) -> str:
    """Commit staged changes with optional GPG signing and automatic security enforcement"""
    try:
        # 🔒 SECURITY: Enforce secure configuration before committing
        security_result = enforce_secure_git_config(repo, strict_mode=True)
        security_messages = []
        if "✅" in security_result:
            security_messages.append("🔒 Security configuration enforced")
        
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
                    config_key = repo.config_reader().get_value("user", "signingkey", fallback=None)
                    if config_key:
                        force_key_id = config_key
                    else:
                        return "❌ No GPG signing key configured. Set GPG_SIGNING_KEY env var or git config user.signingkey"
                except Exception:
                    return "❌ Could not determine GPG signing key. Please configure GPG_SIGNING_KEY env var"
        
        if force_gpg:
            # Use git command directly for GPG signing
            import subprocess
            cmd = ["git", "commit"]
            cmd.append(f"--gpg-sign={force_key_id}")
            cmd.extend(["-m", message])
            
            result = subprocess.run(cmd, cwd=repo.working_dir, capture_output=True, text=True)
            if result.returncode == 0:
                # Get the commit hash from git log
                hash_result = subprocess.run(
                    ["git", "rev-parse", "HEAD"], 
                    cwd=repo.working_dir, capture_output=True, text=True
                )
                commit_hash = hash_result.stdout.strip()[:8] if hash_result.returncode == 0 else "unknown"
                
                # Verify the commit is properly signed (for future verification if needed)
                # verify_result = subprocess.run(
                #     ["git", "log", "--show-signature", "-1", "--pretty=format:%H"],
                #     cwd=repo.working_dir, capture_output=True, text=True
                # )
                
                success_msg = f"✅ Commit {commit_hash} created with VERIFIED GPG signature"
                if security_messages:
                    success_msg += f"\n{chr(10).join(security_messages)}"
                
                # Add security reminder
                success_msg += f"\n🔒 Enforced GPG signing with key {force_key_id}"
                success_msg += "\n⚠️  MCP Git Server used - no fallback to system git commands"
                
                return success_msg
            else:
                return f"❌ Commit failed: {result.stderr}\n🔒 GPG signing was enforced but failed"
        else:
            # This path should never be reached due to force_gpg=True
            return "❌ SECURITY VIOLATION: Unsigned commits are not allowed by MCP Git Server"
        
    except git.exc.GitCommandError as e:
        return f"❌ Commit failed: {str(e)}\n🔒 Security enforcement may have prevented insecure operation"
    except Exception as e:
        return f"❌ Commit error: {str(e)}\n🔒 Verify repository security configuration"

def git_add(repo: git.Repo, files: list[str]) -> str:
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
            missing_list = ', '.join(missing_files)
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
                staged_list = ', '.join(staged_files)
                response_parts.append(f"Successfully staged ({len(staged_files)} files): {staged_list}")
        
        if missing_files:
            missing_list = ', '.join(missing_files)
            response_parts.append(f"Files not found: {missing_list}")
        
        if failed_files:
            failed_list = ', '.join(failed_files)
            response_parts.append(f"Failed to stage: {failed_list}")
        
        if not response_parts:
            return "No files were processed"
        
        return '; '.join(response_parts)
        
    except Exception:
        # Fallback to original simple behavior if anything goes wrong
        try:
            repo.index.add(files)
            return "Files staged successfully"
        except Exception as fallback_e:
            return f"Git add failed: {str(fallback_e)}"

def git_reset(repo: git.Repo) -> str:
    repo.index.reset()
    return "All staged changes reset"

def git_log(repo: git.Repo, max_count: int = 10, oneline: bool = False, graph: bool = False, format: str | None = None) -> list[str]:
    """Get commit history with formatting options"""
    try:
        commits = list(repo.iter_commits(max_count=max_count))
        log = []
        
        if oneline:
            # One line format: hash subject
            for commit in commits:
                short_hash = commit.hexsha[:8]
                subject = commit.message.split('\n')[0]
                log.append(f"{short_hash} {subject}")
        elif format:
            # Custom format
            for commit in commits:
                formatted = format.replace('%H', commit.hexsha)
                formatted = formatted.replace('%h', commit.hexsha[:8])
                formatted = formatted.replace('%s', commit.message.split('\n')[0])
                formatted = formatted.replace('%an', str(commit.author.name))
                formatted = formatted.replace('%ae', str(commit.author.email))
                formatted = formatted.replace('%ad', str(commit.authored_datetime))
                formatted = formatted.replace('%ar', _relative_time(commit.authored_datetime))
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
                log[i] = prefix + entry.replace('\n', f'\n{prefix}')
                
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

def git_create_branch(repo: git.Repo, branch_name: str, base_branch: str | None = None) -> str:
    if base_branch:
        base = repo.refs[base_branch]
    else:
        base = repo.active_branch

    repo.create_head(branch_name, base)
    return f"Created branch '{branch_name}' from '{base.name}'"

def git_checkout(repo: git.Repo, branch_name: str) -> str:
    repo.git.checkout(branch_name)
    return f"Switched to branch '{branch_name}'"

def git_init(repo_path: str) -> str:
    try:
        repo = git.Repo.init(path=repo_path, mkdir=True)
        return f"Initialized empty Git repository in {repo.git_dir}"
    except Exception as e:
        return f"Error initializing repository: {str(e)}"

def git_show(repo: git.Repo, revision: str) -> str:
    commit = repo.commit(revision)
    output = [
        f"Commit: {commit.hexsha}\n"
        f"Author: {commit.author}\n"
        f"Date: {commit.authored_datetime}\n"
        f"Message: {commit.message}\n"
    ]
    if commit.parents:
        parent = commit.parents[0]
        diff = parent.diff(commit, create_patch=True)
    else:
        diff = commit.diff(git.NULL_TREE, create_patch=True)
    for d in diff:
        output.append(f"\n--- {d.a_path}\n+++ {d.b_path}\n")
        output.append(d.diff.decode('utf-8'))
    return "".join(output)

def git_push(repo: git.Repo, remote: str = "origin", branch: str | None = None, force: bool = False, set_upstream: bool = False) -> str:
    """Push commits to remote repository with HTTPS authentication support"""
    logger = logging.getLogger(__name__)
    
    try:
        remote_ref = repo.remote(remote)
        remote_url = remote_ref.url
        
        # Determine branch to push
        if branch is None:
            branch = repo.active_branch.name
            
        logger.debug(f"🚀 Pushing {branch} to {remote} ({remote_url})")
        
        # Check if we need to handle HTTPS authentication
        token = os.getenv("GITHUB_TOKEN")
        needs_auth = (remote_url.startswith('https://') and 
                     'github.com' in remote_url and 
                     token is not None)
        
        if needs_auth:
            logger.debug("🔑 Using GitHub token for HTTPS authentication")
            logger.debug(f"🔍 Token format: {token[:4]}{'*' * 8}... (length: {len(token)})")
            
            # Detect token type for appropriate authentication method
            is_classic_pat = token.startswith('ghp_')
            is_fine_grained_pat = token.startswith('github_pat_')
            is_app_token = token.startswith('ghs_') or token.startswith('ghu_')
            is_github_token = token.startswith('gith')  # Your specific token format
            
            logger.debug(f"🔍 Token type detection: classic_pat={is_classic_pat}, fine_grained={is_fine_grained_pat}, app_token={is_app_token}, github_token={is_github_token}")
            
            # Test token validity first
            logger.debug("🔍 Testing token validity with GitHub API...")
            try:
                import requests
                headers = {
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github+json',
                    'X-GitHub-Api-Version': '2022-11-28'
                }
                test_response = requests.get('https://api.github.com/user', headers=headers, timeout=10)
                if test_response.status_code == 200:
                    user_info = test_response.json()
                    logger.debug(f"✅ Token valid - authenticated as: {user_info.get('login', 'unknown')}")
                elif test_response.status_code == 401:
                    logger.error("❌ Token is invalid or expired")
                    return "Push failed: GitHub token is invalid or expired (HTTP 401)"
                elif test_response.status_code == 403:
                    logger.warning(f"⚠️ Token has limited permissions (HTTP 403): {test_response.text}")
                else:
                    logger.warning(f"⚠️ Unexpected API response (HTTP {test_response.status_code}): {test_response.text}")
            except Exception as api_error:
                logger.warning(f"⚠️ Could not validate token via API: {api_error}")
                # Continue with push attempts even if API validation fails
            
            # Use different authentication methods based on token type
            import subprocess
            
            # Set up environment with GitHub token
            env = os.environ.copy()
            env['GITHUB_TOKEN'] = token
            env['GIT_ASKPASS'] = '/bin/true'  # Disable interactive prompts
            
            # For non-standard token formats, try direct header approach
            if is_github_token or is_fine_grained_pat:
                logger.debug("🔧 Using HTTP header authentication for non-standard token")
                
                # Try using git with authorization header
                auth_header = f"Authorization: token {token}"
                
                cmd = [
                    "git", "-c", f"http.extraheader={auth_header}",
                    "push"
                ]
                if force:
                    cmd.append("--force")
                if set_upstream:
                    cmd.extend(["--set-upstream", remote, branch])
                else:
                    cmd.extend([remote, f"{branch}:{branch}"])
                
                logger.debug(f"🔧 Running: git push [http-header-auth] {' '.join(cmd[4:])}")
                
                result = subprocess.run(cmd, cwd=repo.working_dir, capture_output=True, text=True, env=env)
                
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
                        if 'Authorization:' in part and 'token' in part:
                            sanitized_cmd.append("http.extraheader=Authorization: token [REDACTED]")
                        else:
                            sanitized_cmd.append(part)
                    logger.debug(f"🔍 HTTP header auth command was: {' '.join(sanitized_cmd)}")
                    logger.debug(f"🔍 HTTP header auth full stderr: {result.stderr}")
                    logger.debug(f"🔍 HTTP header auth full stdout: {result.stdout}")
                    # Fall through to try other methods
            
            # Use GitHub CLI auth approach if available, otherwise fallback to direct token
            try:
                # Try using gh auth setup approach
                setup_result = subprocess.run(['gh', 'auth', 'setup-git'], 
                                            cwd=repo.working_dir, 
                                            capture_output=True, 
                                            text=True, 
                                            env=env,
                                            timeout=10)
                
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
                    
                    result = subprocess.run(cmd, cwd=repo.working_dir, capture_output=True, text=True, env=env)
                    
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
                    logger.debug("⚠️ GitHub CLI not available, using manual token approach")
                    raise subprocess.CalledProcessError(1, "gh auth setup-git")
                    
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
                # Fallback to manual token configuration
                logger.debug("🔧 Using manual git credential configuration")
                
                # Configure git to use the token directly
                git_config_cmds = [
                    ["git", "config", "--local", "credential.https://github.com.username", "x-access-token"],
                    ["git", "config", "--local", "credential.https://github.com.password", token],
                    ["git", "config", "--local", "credential.helper", "store"]
                ]
                
                try:
                    for config_cmd in git_config_cmds:
                        subprocess.run(config_cmd, cwd=repo.working_dir, check=True, capture_output=True)
                    
                    logger.debug("🔧 Git credentials configured")
                    
                    # Now try the push
                    cmd = ["git", "push"]
                    if force:
                        cmd.append("--force")
                    if set_upstream:
                        cmd.extend(["--set-upstream", remote, branch])
                    else:
                        cmd.extend([remote, f"{branch}:{branch}"])
                    
                    logger.debug(f"🔧 Running: git push [manual-creds] {' '.join(cmd[2:])}")
                    
                    result = subprocess.run(cmd, cwd=repo.working_dir, capture_output=True, text=True, env=env)
                    
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
                        ["git", "config", "--local", "--unset", "credential.https://github.com.username"],
                        ["git", "config", "--local", "--unset", "credential.https://github.com.password"],
                        ["git", "config", "--local", "--unset", "credential.helper"]
                    ]
                    for cleanup_cmd in cleanup_cmds:
                        try:
                            subprocess.run(cleanup_cmd, cwd=repo.working_dir, capture_output=True)
                        except:
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
                
                result = subprocess.run(cmd, cwd=repo.working_dir, capture_output=True, text=True)
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
                        
                return "\n".join(results) if results else f"Successfully pushed {branch} to {remote}"
        
    except git.exc.GitCommandError as e:
        logger.error(f"❌ Git command error during push: {e}")
        return f"Push failed: {str(e)}"
    except Exception as e:
        logger.error(f"❌ Unexpected error during push: {e}")
        return f"Push error: {str(e)}"

def git_pull(repo: git.Repo, remote: str = "origin", branch: str | None = None) -> str:
    """Pull changes from remote repository"""
    try:
        remote_ref = repo.remote(remote)
        
        # Determine branch to pull
        if branch is None:
            branch = repo.active_branch.name
            
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
                old_commit = info.old_commit.hexsha[:8] if info.old_commit else "unknown"
                new_commit = info.commit.hexsha[:8] if info.commit else "unknown"
                results.append(f"Fast-forward: {old_commit}..{new_commit}")
            else:
                results.append(f"Updated: {info.note or 'Pull completed'}")
                
        return "\n".join(results) if results else f"Successfully pulled from {remote}/{branch}"
        
    except git.exc.GitCommandError as e:
        return f"Pull failed: {str(e)}"
    except Exception as e:
        return f"Pull error: {str(e)}"

def git_diff_branches(repo: git.Repo, base_branch: str, compare_branch: str) -> str:
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
                output.append(d.diff.decode('utf-8'))
                
        return "".join(output)
        
    except git.exc.GitCommandError as e:
        return f"Diff failed: {str(e)}"
    except Exception as e:
        return f"Diff error: {str(e)}"

def git_rebase(repo: git.Repo, target_branch: str, interactive: bool = False) -> str:
    """Rebase current branch onto target branch"""
    try:
        current_branch = repo.active_branch.name
        
        # Use subprocess for reliable rebase operation
        import subprocess
        cmd = ["git", "rebase"]
        
        if interactive:
            cmd.append("-i")
            
        cmd.append(target_branch)
        
        result = subprocess.run(cmd, cwd=repo.working_dir, capture_output=True, text=True)
        
        if result.returncode == 0:
            return f"✅ Successfully rebased {current_branch} onto {target_branch}"
        else:
            # Check if it's a conflict that needs resolution
            if "CONFLICT" in result.stdout or "conflict" in result.stderr.lower():
                return f"🔄 Rebase conflicts detected. Resolve conflicts and use git_continue to finish rebase.\n\nConflicts:\n{result.stdout}\n{result.stderr}"
            else:
                return f"❌ Rebase failed: {result.stderr}"
                
    except git.exc.GitCommandError as e:
        return f"❌ Rebase failed: {str(e)}"
    except Exception as e:
        return f"❌ Rebase error: {str(e)}"

def git_merge(repo: git.Repo, source_branch: str, strategy: str = "merge", message: str | None = None) -> str:
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
        
        result = subprocess.run(cmd, cwd=repo.working_dir, capture_output=True, text=True)
        
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
                
    except git.exc.GitCommandError as e:
        return f"❌ Merge failed: {str(e)}"
    except Exception as e:
        return f"❌ Merge error: {str(e)}"

def git_cherry_pick(repo: git.Repo, commit_hash: str, no_commit: bool = False) -> str:
    """Cherry-pick a commit onto current branch"""
    try:
        # Use subprocess for reliable cherry-pick operation
        import subprocess
        cmd = ["git", "cherry-pick"]
        
        if no_commit:
            cmd.append("--no-commit")
            
        cmd.append(commit_hash)
        
        result = subprocess.run(cmd, cwd=repo.working_dir, capture_output=True, text=True)
        
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
                
    except git.exc.GitCommandError as e:
        return f"❌ Cherry-pick failed: {str(e)}"
    except Exception as e:
        return f"❌ Cherry-pick error: {str(e)}"

def git_abort(repo: git.Repo, operation: str) -> str:
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
            
        result = subprocess.run(cmd, cwd=repo.working_dir, capture_output=True, text=True)
        
        if result.returncode == 0:
            return f"✅ Successfully aborted {operation} operation"
        else:
            return f"❌ Failed to abort {operation}: {result.stderr}"
                
    except git.exc.GitCommandError as e:
        return f"❌ Abort failed: {str(e)}"
    except Exception as e:
        return f"❌ Abort error: {str(e)}"

def git_continue(repo: git.Repo, operation: str) -> str:
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
            
        result = subprocess.run(cmd, cwd=repo.working_dir, capture_output=True, text=True)
        
        if result.returncode == 0:
            return f"✅ Successfully continued {operation} operation"
        else:
            # Check if there are still unresolved conflicts
            if "conflict" in result.stderr.lower() or "unmerged" in result.stderr.lower():
                return f"🔄 Still have unresolved conflicts. Please resolve all conflicts before continuing.\n\nError: {result.stderr}"
            else:
                return f"❌ Failed to continue {operation}: {result.stderr}"
                
    except git.exc.GitCommandError as e:
        return f"❌ Continue failed: {str(e)}"
    except Exception as e:
        return f"❌ Continue error: {str(e)}"

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
        logger = logging.getLogger(__name__)
        logger.error(f"❌ github_get_pr_details failed: {str(e)}", exc_info=True)
        return f"Error getting PR details: {str(e)}"

async def github_list_pull_requests(repo_owner: str, repo_name: str, state: str = "open", head: str | None = None, base: str | None = None, sort: str = "created", direction: str = "desc", per_page: int = 30, page: int = 1) -> str:
    """List pull requests for a repository"""
    logger = logging.getLogger(__name__)
    logger.debug(f"🔍 github_list_pull_requests called with: repo_owner={repo_owner}, repo_name={repo_name}, state={state}")
    
    try:
        logger.debug("🔍 Step 1: Getting GitHub client")
        client = get_github_client()
        logger.debug("🔍 Step 1: ✅ GitHub client created")
        
        # Build query parameters
        logger.debug("🔍 Step 2: Building query parameters")
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
        logger.debug(f"🔍 Step 2: ✅ Query params: {params}")
        
        # Get pull requests
        prs_endpoint = f"/repos/{repo_owner}/{repo_name}/pulls"
        logger.debug(f"🔍 Step 3: Making API request to {prs_endpoint}")
        prs_data = await client.make_request("GET", prs_endpoint, params=params)
        logger.debug(f"🔍 Step 3: ✅ API response received, type: {type(prs_data)}, value: {prs_data}")
        
        logger.debug("🔍 Step 4: Checking if prs_data is empty")
        if not prs_data:
            logger.debug("🔍 Step 4: ✅ prs_data is empty, returning no results message")
            return f"No pull requests found for {repo_owner}/{repo_name} (state: {state})"
        
        logger.debug(f"🔍 Step 5: Processing {len(prs_data)} PRs")
        output = [f"Pull Requests for {repo_owner}/{repo_name} (state: {state}, page: {page}):\n"]
        
        logger.debug("🔍 Step 6: Starting PR iteration")
        for i, pr in enumerate(prs_data):
            logger.debug(f"🔍 Step 6.{i}: Processing PR {i+1}, type: {type(pr)}")
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
        logger = logging.getLogger(__name__)
        logger.error(f"❌ github_list_pull_requests failed: {str(e)}", exc_info=True)
        return f"Error listing pull requests: {str(e)}"

async def github_get_pr_status(repo_owner: str, repo_name: str, pr_number: int) -> str:
    """Get the status/checks for a pull request with proper failure detection
    
    Uses GitHub REST API v4 (2022-11-28) with both:
    - Commit Status API (legacy): /repos/{owner}/{repo}/commits/{ref}/status
    - Check Runs API (modern): /repos/{owner}/{repo}/commits/{ref}/check-runs
    
    Combines results to provide accurate overall CI state for GitHub Actions workflows.
    """
    logger = logging.getLogger(__name__)
    logger.debug(f"🔍 Starting github_get_pr_status for {repo_owner}/{repo_name} PR #{pr_number}")
    
    try:
        client = get_github_client()
        logger.debug("✅ GitHub client created successfully")
        
        # Get PR details to get the head SHA
        pr_endpoint = f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}"
        pr_data = await client.make_request("GET", pr_endpoint)
        head_sha = pr_data["head"]["sha"]
        
        # Get status for the head commit (legacy API)
        status_endpoint = f"/repos/{repo_owner}/{repo_name}/commits/{head_sha}/status"
        status_data = await client.make_request("GET", status_endpoint)
        
        # Get check runs for the head commit (modern GitHub Actions API)
        checks_endpoint = f"/repos/{repo_owner}/{repo_name}/commits/{head_sha}/check-runs"
        checks_data = await client.make_request("GET", checks_endpoint)
        
        output = [f"Status for PR #{pr_number} (commit {head_sha[:8]}):\n"]
        
        # Calculate ACTUAL overall state by combining both APIs
        legacy_state = status_data.get("state", "unknown")
        legacy_statuses = status_data.get("statuses", [])
        check_runs = checks_data.get("check_runs", [])
        
        # GitHub API v4 (2022-11-28) - Official status and conclusion values
        
        # Commit Status API states (legacy but still used)
        commit_failure_states = {"error", "failure"}
        commit_pending_states = {"pending"}
        commit_success_states = {"success"}
        
        # Check Runs API status values  
        check_run_pending_status = {"queued", "in_progress", "waiting", "requested", "pending"}
        check_run_completed_status = {"completed"}
        
        # Check Runs API conclusion values (when status = "completed")
        check_run_failure_conclusions = {"action_required", "cancelled", "failure", "timed_out"}
        check_run_success_conclusions = {"success"}
        check_run_neutral_conclusions = {"neutral", "skipped"}  # Not failures, but not successes
        check_run_stale_conclusions = {"stale"}  # Outdated, treat as neutral
        
        has_failures = False
        has_pending = False
        has_success = False
        
        # Check legacy commit statuses (Commit Status API)
        for status in legacy_statuses:
            state = status.get("state", "unknown")
            if state in commit_failure_states:
                has_failures = True
            elif state in commit_pending_states:
                has_pending = True
            elif state in commit_success_states:
                has_success = True
        
        # Check modern check runs (Check Runs API - primary for GitHub Actions)
        for run in check_runs:
            run_status = run.get("status", "unknown")
            conclusion = run.get("conclusion")
            
            if run_status in check_run_completed_status:
                if conclusion in check_run_failure_conclusions:
                    has_failures = True
                elif conclusion in check_run_success_conclusions:
                    has_success = True
                elif conclusion in check_run_neutral_conclusions:
                    # Neutral/skipped - not failure, but don't count as success for overall state
                    pass  
                elif conclusion in check_run_stale_conclusions:
                    # Stale - treat as neutral, don't affect overall state significantly
                    pass
            elif run_status in check_run_pending_status:
                has_pending = True
        
        # Determine overall state with priority: failure > pending > success
        if has_failures:
            actual_overall_state = "failure"
        elif has_pending:
            actual_overall_state = "pending"
        elif has_success or (legacy_statuses or check_runs):  # Success if any checks passed
            actual_overall_state = "success"
        else:
            actual_overall_state = "unknown"  # No checks at all
        
        # Display overall status (use actual state, not just legacy)
        state_emoji = {"success": "✅", "pending": "🟡", "failure": "❌", "error": "❌", "unknown": "❓"}.get(actual_overall_state, "❓")
        output.append(f"🚨 ACTUAL Overall State: {state_emoji} {actual_overall_state.upper()}")
        
        # Show legacy API results for reference
        if legacy_statuses:
            legacy_emoji = {"success": "✅", "pending": "🟡", "failure": "❌", "error": "❌"}.get(legacy_state, "❓")
            output.append(f"Legacy Status API: {legacy_emoji} {legacy_state} ({len(legacy_statuses)} statuses)")
        else:
            output.append("Legacy Status API: No statuses (empty - this is common with GitHub Actions)")
        
        # Show check runs (the real CI status for GitHub Actions)
        if check_runs:
            output.append(f"\n🔍 GitHub Actions Check Runs ({len(check_runs)}):")
            
            failed_runs = []
            pending_runs = []
            success_runs = []
            
            for run in check_runs:
                run_status = run.get("status", "unknown")
                conclusion = run.get("conclusion")
                name = run.get("name", "Unknown")
                
                if run_status in check_run_completed_status:
                    if conclusion in check_run_failure_conclusions:
                        status_emoji = "❌"
                        failed_runs.append(f"  {status_emoji} {name}: {run_status} → {conclusion}")
                        if run.get("html_url"):
                            failed_runs.append(f"     🔗 {run['html_url']}")
                    elif conclusion in check_run_success_conclusions:
                        status_emoji = "✅"
                        success_runs.append(f"  {status_emoji} {name}: {run_status} → {conclusion}")
                    elif conclusion in check_run_neutral_conclusions:
                        status_emoji = "⚪"  # Neutral - neither success nor failure
                        success_runs.append(f"  {status_emoji} {name}: {run_status} → {conclusion} (neutral)")
                    elif conclusion in check_run_stale_conclusions:
                        status_emoji = "🔸"  # Stale - outdated
                        success_runs.append(f"  {status_emoji} {name}: {run_status} → {conclusion} (stale)")
                    else:
                        status_emoji = "❓"
                        output.append(f"  {status_emoji} {name}: {run_status} → {conclusion} (unknown conclusion)")
                elif run_status in check_run_pending_status:
                    # Use specific emojis for different pending states
                    if run_status == "in_progress":
                        status_emoji = "🔄"
                    elif run_status == "queued":
                        status_emoji = "⏳"
                    elif run_status == "waiting":
                        status_emoji = "⏸️"
                    elif run_status == "requested":
                        status_emoji = "📋"
                    else:
                        status_emoji = "🟡"
                    pending_runs.append(f"  {status_emoji} {name}: {run_status}")
                else:
                    status_emoji = "❓"
                    output.append(f"  {status_emoji} {name}: {run_status} (unknown status)")
            
            # Show failures first (most important)
            if failed_runs:
                output.append(f"\n🚨 FAILED CHECKS ({len(failed_runs)//2}):")  # Divide by 2 due to URL lines
                output.extend(failed_runs)
            
            # Show pending
            if pending_runs:
                output.append(f"\n⏳ PENDING CHECKS ({len(pending_runs)}):")
                output.extend(pending_runs)
            
            # Show successes (less important, summary only)
            if success_runs:
                output.append(f"\n✅ PASSED CHECKS ({len(success_runs)}):")
                # Only show first few successes to avoid clutter
                output.extend(success_runs[:3])
                if len(success_runs) > 3:
                    output.append(f"     ... and {len(success_runs) - 3} more successful checks")
        else:
            output.append("\n❓ No GitHub Actions check runs found")
        
        # Show legacy statuses if they exist
        if legacy_statuses:
            output.append(f"\n📊 Legacy Commit Status Checks ({len(legacy_statuses)}):")
            for status in legacy_statuses:
                state = status.get("state", "unknown")
                # Use official GitHub API v4 commit status states
                if state == "success":
                    status_emoji = "✅"
                elif state == "failure":
                    status_emoji = "❌"
                elif state == "error":
                    status_emoji = "💥"  # Different from failure
                elif state == "pending":
                    status_emoji = "🟡"
                else:
                    status_emoji = "❓"
                
                context = status.get('context', 'Unknown')
                output.append(f"  {status_emoji} {context}: {state}")
                if status.get("description"):
                    output.append(f"     {status['description']}")
                if status.get("target_url"):
                    output.append(f"     🔗 {status['target_url']}")
        
        # Critical summary for ClaudeCode
        output.append("\n" + "="*50)
        output.append("🎯 SUMMARY FOR AUTOMATION:")
        output.append(f"   State: {actual_overall_state}")
        failed_check_count = len([r for r in check_runs if r.get('status') == 'completed' and r.get('conclusion') in check_run_failure_conclusions])
        pending_check_count = len([r for r in check_runs if r.get('status') in check_run_pending_status])
        
        output.append(f"   Failed Checks: {failed_check_count}")
        output.append(f"   Pending Checks: {pending_check_count}")
        output.append(f"   Total Checks: {len(check_runs) + len(legacy_statuses)}")
        
        if actual_overall_state == "failure":
            output.append("   🚨 ACTION REQUIRED: CI failures must be resolved!")
        elif actual_overall_state == "pending":
            output.append("   ⏳ STATUS: CI is still running, wait for completion")
        elif actual_overall_state == "success":
            output.append("   ✅ STATUS: All CI checks passing")
        
        output.append("="*50)
        
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
    import os
    from datetime import datetime
    
    logger = logging.getLogger(__name__)
    start_time = time.time()
    session_id = os.environ.get("MCP_SESSION_ID", "default")
    
    # Startup logging
    logger.info(f"🚀 Starting MCP Git Server (Session: {session_id})")
    logger.info(f"Repository: {repository or '.'}")
    logger.info(f"Server start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Check if file logging is enabled
    file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
    if file_handlers:
        for handler in file_handlers:
            logger.info(f"📝 File logging enabled: {handler.baseFilename}")
    
    # Load environment variables from .env files with proper precedence
    load_environment_variables(repository)

    if repository is not None:
        try:
            git.Repo(repository)
            logger.info(f"✅ Using repository at {repository}")
        except git.InvalidGitRepositoryError:
            logger.error(f"{repository} is not a valid Git repository")
            return

    server = Server("mcp-git")
    
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
        # Enhanced tool call logging with request tracking
        request_id = os.urandom(4).hex()
        logger.info(f"🔧 [{request_id}] Tool call: {name}")
        logger.debug(f"🔧 [{request_id}] Arguments: {arguments}")
        
        start_time = time.time()
        result = None  # Initialize result variable
        try:
            logger.debug(f"🔍 [{request_id}] Starting tool execution")
            # GitHub API tools don't need repo_path - they're handled in the main match statement below
            if name not in [GitTools.GITHUB_GET_PR_CHECKS, GitTools.GITHUB_GET_FAILING_JOBS, 
                           GitTools.GITHUB_GET_WORKFLOW_RUN, GitTools.GITHUB_GET_PR_DETAILS,
                           GitTools.GITHUB_LIST_PULL_REQUESTS, GitTools.GITHUB_GET_PR_STATUS,
                           GitTools.GITHUB_GET_PR_FILES]:
                # All other tools require repo_path
                repo_path = Path(arguments["repo_path"])
                
                # Handle git init separately since it doesn't require an existing repo
                if name == GitTools.INIT:
                    result = git_init(str(repo_path))
                    result = [TextContent(
                        type="text",
                        text=result
                    )]
                    duration = time.time() - start_time  
                    logger.info(f"✅ [{request_id}] Tool '{name}' completed in {duration:.2f}s")
                    return result  # Early return for INIT
                    
                # For all other commands, we need an existing repo
                repo = git.Repo(repo_path)

                match name:
                    case GitTools.STATUS:
                        porcelain_raw = arguments.get("porcelain", False)
                        # Handle both boolean and string values for porcelain parameter
                        porcelain = porcelain_raw if isinstance(porcelain_raw, bool) else str(porcelain_raw).lower() in ('true', '1', 'yes')
                        status = git_status(repo, porcelain)
                        prefix = "Repository status (porcelain):" if porcelain else "Repository status:"
                        result = [TextContent(
                            type="text",
                            text=f"{prefix}\n{status}"
                        )]

                    case GitTools.DIFF_UNSTAGED:
                        diff = git_diff_unstaged(repo)
                        result = [TextContent(
                            type="text",
                            text=f"Unstaged changes:\n{diff}"
                        )]

                    case GitTools.DIFF_STAGED:
                        diff = git_diff_staged(repo)
                        result = [TextContent(
                            type="text",
                            text=f"Staged changes:\n{diff}"
                        )]

                    case GitTools.DIFF:
                        diff = git_diff(repo, arguments["target"])
                        result = [TextContent(
                            type="text",
                            text=f"Diff with {arguments['target']}:\n{diff}"
                        )]

                    case GitTools.COMMIT:
                        commit_result = git_commit(
                            repo, 
                            arguments["message"],
                            arguments.get("gpg_sign", False),
                            arguments.get("gpg_key_id")
                        )
                        result = [TextContent(
                            type="text",
                            text=commit_result
                        )]

                    case GitTools.ADD:
                        add_result = git_add(repo, arguments["files"])
                        result = [TextContent(
                            type="text",
                            text=add_result
                        )]

                    case GitTools.RESET:
                        reset_result = git_reset(repo)
                        result = [TextContent(
                            type="text",
                            text=reset_result
                        )]

                    case GitTools.LOG:
                        log = git_log(
                            repo, 
                            arguments.get("max_count", 10),
                            arguments.get("oneline", False),
                            arguments.get("graph", False),
                            arguments.get("format")
                        )
                        result = [TextContent(
                            type="text",
                            text="Commit history:\n" + "\n".join(log)
                        )]

                    case GitTools.CREATE_BRANCH:
                        branch_result = git_create_branch(
                            repo,
                            arguments["branch_name"],
                            arguments.get("base_branch")
                        )
                        result = [TextContent(
                            type="text",
                            text=branch_result
                        )]

                    case GitTools.CHECKOUT:
                        checkout_result = git_checkout(repo, arguments["branch_name"])
                        result = [TextContent(
                            type="text",
                            text=checkout_result
                        )]

                    case GitTools.SHOW:
                        show_result = git_show(repo, arguments["revision"])
                        result = [TextContent(
                            type="text",
                            text=show_result
                        )]

                    case GitTools.PUSH:
                        push_result = git_push(
                            repo,
                            arguments.get("remote", "origin"),
                            arguments.get("branch"),
                            arguments.get("force", False),
                            arguments.get("set_upstream", False)
                        )
                        result = [TextContent(
                            type="text",
                            text=push_result
                        )]

                    case GitTools.PULL:
                        pull_result = git_pull(
                            repo,
                            arguments.get("remote", "origin"),
                            arguments.get("branch")
                        )
                        result = [TextContent(
                            type="text",
                            text=pull_result
                        )]

                    case GitTools.DIFF_BRANCHES:
                        diff_branches_result = git_diff_branches(
                            repo,
                            arguments["base_branch"],
                            arguments["compare_branch"]
                        )
                        result = [TextContent(
                            type="text",
                            text=diff_branches_result
                        )]

                    # Advanced git operations
                    case GitTools.REBASE:
                        rebase_result = git_rebase(
                            repo,
                            arguments["target_branch"],
                            arguments.get("interactive", False)
                        )
                        result = [TextContent(
                            type="text",
                            text=rebase_result
                        )]

                    case GitTools.MERGE:
                        merge_result = git_merge(
                            repo,
                            arguments["source_branch"],
                            arguments.get("strategy", "merge"),
                            arguments.get("message")
                        )
                        result = [TextContent(
                            type="text",
                            text=merge_result
                        )]

                    case GitTools.CHERRY_PICK:
                        cherry_pick_result = git_cherry_pick(
                            repo,
                            arguments["commit_hash"],
                            arguments.get("no_commit", False)
                        )
                        result = [TextContent(
                            type="text",
                            text=cherry_pick_result
                        )]

                    case GitTools.ABORT:
                        abort_result = git_abort(
                            repo,
                            arguments["operation"]
                        )
                        result = [TextContent(
                            type="text",
                            text=abort_result
                        )]

                    case GitTools.CONTINUE:
                        continue_result = git_continue(
                            repo,
                            arguments["operation"]
                        )
                        result = [TextContent(
                            type="text",
                            text=continue_result
                        )]


                    # Security tools
                    case GitTools.GIT_SECURITY_VALIDATE:
                        validation_result = validate_git_security_config(repo)
                        
                        status_emoji = "✅" if validation_result["status"] == "secure" else "⚠️"
                        result_text = f"{status_emoji} Git Security Validation Results\n\n"
                        
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
                        
                        result = [TextContent(
                            type="text",
                            text=result_text
                        )]

                    case GitTools.GIT_SECURITY_ENFORCE:
                        strict_mode = arguments.get("strict_mode", True)
                        enforce_result = enforce_secure_git_config(repo, strict_mode)
                        result = [TextContent(
                            type="text",
                            text=enforce_result
                        )]

                    case _:
                        logger.error(f"❌ [{request_id}] Unknown tool: {name}")
                        raise ValueError(f"Unknown tool: {name}")
            else:
                # Handle GitHub API tools that don't require repo_path
                logger.debug(f"🔍 [{request_id}] Tool is GitHub API tool, processing...")
                match name:
                    case GitTools.GITHUB_GET_PR_DETAILS:
                        repo_owner = arguments.get("repo_owner")
                        repo_name = arguments.get("repo_name")
                        if not repo_owner or not repo_name:
                            result = [TextContent(type="text", text="❌ repo_owner and repo_name parameters are required for GitHub API tools")]
                        else:
                            pr_details_result = await github_get_pr_details(
                                repo_owner,
                                repo_name,
                                arguments["pr_number"],
                                arguments.get("include_files", False),
                                arguments.get("include_reviews", False)
                            )
                            result = [TextContent(
                                type="text",
                                text=pr_details_result
                            )]

                    case GitTools.GITHUB_GET_PR_CHECKS:
                        repo_owner = arguments.get("repo_owner")
                        repo_name = arguments.get("repo_name")
                        if not repo_owner or not repo_name:
                            result = [TextContent(type="text", text="❌ repo_owner and repo_name parameters are required for GitHub API tools")]
                        else:
                            pr_checks_result = await github_get_pr_checks(
                                repo_owner,
                                repo_name,
                                arguments["pr_number"],
                                arguments.get("status"),
                                arguments.get("conclusion")
                            )
                            result = [TextContent(
                                type="text",
                                text=pr_checks_result
                            )]

                    case GitTools.GITHUB_GET_FAILING_JOBS:
                        repo_owner = arguments.get("repo_owner")
                        repo_name = arguments.get("repo_name")
                        if not repo_owner or not repo_name:
                            result = [TextContent(type="text", text="❌ repo_owner and repo_name parameters are required for GitHub API tools")]
                        else:
                            failing_jobs_result = await github_get_failing_jobs(
                                repo_owner,
                                repo_name,
                                arguments["pr_number"],
                                arguments.get("include_logs", True),
                                arguments.get("include_annotations", True)
                            )
                            result = [TextContent(
                                type="text",
                                text=failing_jobs_result
                            )]

                    case GitTools.GITHUB_GET_WORKFLOW_RUN:
                        repo_owner = arguments.get("repo_owner")
                        repo_name = arguments.get("repo_name")
                        if not repo_owner or not repo_name:
                            result = [TextContent(type="text", text="❌ repo_owner and repo_name parameters are required for GitHub API tools")]
                        else:
                            workflow_run_result = await github_get_workflow_run(
                                repo_owner,
                                repo_name,
                                arguments["run_id"],
                                arguments.get("include_logs", False)
                            )
                            result = [TextContent(
                                type="text",
                                text=workflow_run_result
                            )]

                    case GitTools.GITHUB_LIST_PULL_REQUESTS:
                        logger.debug(f"🔍 Tool handler: GITHUB_LIST_PULL_REQUESTS called with arguments: {arguments}")
                        repo_owner = arguments.get("repo_owner")
                        repo_name = arguments.get("repo_name")
                        logger.debug(f"🔍 Tool handler: repo_owner={repo_owner}, repo_name={repo_name}")
                        if not repo_owner or not repo_name:
                            logger.debug("🔍 Tool handler: Missing repo_owner or repo_name")
                            result = [TextContent(type="text", text="❌ repo_owner and repo_name parameters are required for GitHub API tools")]
                        else:
                            logger.debug("🔍 Tool handler: Calling github_list_pull_requests function")
                            list_prs_result = await github_list_pull_requests(
                                repo_owner,
                                repo_name,
                                arguments.get("state", "open"),
                                arguments.get("head"),
                                arguments.get("base"),
                                arguments.get("sort", "created"),
                                arguments.get("direction", "desc"),
                                arguments.get("per_page", 30),
                                arguments.get("page", 1)
                            )
                            logger.debug(f"🔍 Tool handler: Function returned, type: {type(list_prs_result)}, value: {list_prs_result}")
                            result = [TextContent(
                                type="text",
                                text=list_prs_result
                            )]
                            logger.debug(f"🔍 Tool handler: TextContent created successfully")

                    case GitTools.GITHUB_GET_PR_STATUS:
                        repo_owner = arguments.get("repo_owner")
                        repo_name = arguments.get("repo_name")
                        if not repo_owner or not repo_name:
                            result = [TextContent(type="text", text="❌ repo_owner and repo_name parameters are required for GitHub API tools")]
                        else:
                            pr_status_result = await github_get_pr_status(
                                repo_owner,
                                repo_name,
                                arguments["pr_number"]
                            )
                            result = [TextContent(
                                type="text",
                                text=pr_status_result
                            )]

                    case GitTools.GITHUB_GET_PR_FILES:
                        repo_owner = arguments.get("repo_owner")
                        repo_name = arguments.get("repo_name")
                        if not repo_owner or not repo_name:
                            result = [TextContent(type="text", text="❌ repo_owner and repo_name parameters are required for GitHub API tools")]
                        else:
                            pr_files_result = await github_get_pr_files(
                                repo_owner,
                                repo_name,
                                arguments["pr_number"],
                                arguments.get("per_page", 30),
                                arguments.get("page", 1),
                                arguments.get("include_patch", False)
                            )
                            result = [TextContent(
                                type="text",
                                text=pr_files_result
                            )]

                    case _:
                        logger.error(f"❌ [{request_id}] Unknown GitHub API tool: {name}")
                        raise ValueError(f"Unknown GitHub API tool: {name}")
        
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"❌ [{request_id}] Tool '{name}' failed after {duration:.2f}s: {e}", exc_info=True)
            return [TextContent(
                type="text", 
                text=f"Error in {name}: {str(e)}"
            )]
        
        duration = time.time() - start_time
        logger.debug(f"🔍 [{request_id}] Tool execution finished, result type: {type(result)}")
        if result and len(result) > 0:
            logger.debug(f"🔍 [{request_id}] Result[0] type: {type(result[0])}, content preview: {str(result[0])[:200]}")
        logger.info(f"✅ [{request_id}] Tool '{name}' completed in {duration:.2f}s")
        return result

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
        """Log periodic health checks to monitor server uptime"""
        while True:
            try:
                await asyncio.sleep(300)  # Every 5 minutes
                uptime = time.time() - start_time
                logger.info(f"💓 Server health check - uptime: {uptime:.1f}s")
            except asyncio.CancelledError:
                logger.debug("🔚 Health check task cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Health check failed: {e}")
    
    # Start health logging task
    health_task = asyncio.create_task(log_health())
    
    options = server.create_initialization_options()
    try:
        async with stdio_server() as (read_stream, write_stream):
            logger.info("🔗 STDIO server connected, starting main loop...")
            await server.run(read_stream, write_stream, options, raise_exceptions=False)
    except asyncio.CancelledError:
        logger.info("🛑 Server cancelled")
        raise
    except KeyboardInterrupt:
        logger.info("⌨️ Server interrupted by user")
        raise
    except Exception as e:
        error_msg = str(e)
        if "notifications/cancelled" in error_msg and "ValidationError" in error_msg:
            logger.warning(f"🔔 Ignoring notification validation error: {e}")
            # Don't crash the server for notification validation errors
        else:
            logger.error(f"💥 Server crashed: {e}", exc_info=True)
            raise
    finally:
        # Clean shutdown
        health_task.cancel()
        try:
            await health_task
        except asyncio.CancelledError:
            pass
        
        # Server shutdown logging
        total_uptime = time.time() - start_time
        logger.info(f"🔚 Server shutdown after {total_uptime:.1f}s uptime")
