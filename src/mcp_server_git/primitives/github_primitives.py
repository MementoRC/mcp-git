"""GitHub primitive operations for MCP Git Server.

This module provides atomic GitHub API operations that serve as building blocks
for higher-level GitHub functionality. Primitives are focused, single-purpose
operations that handle the core mechanics of GitHub API interaction.

Design principles:
    - Atomicity: Each function performs a single, focused operation
    - Simplicity: Functions are small and easy to understand
    - Composability: Functions can be combined to create complex operations
    - Error transparency: Functions propagate errors without hiding them
    - Type safety: Functions use proper type annotations

Critical for TDD Compliance:
    This module implements the interface defined by test specifications.
    DO NOT modify tests to match this implementation - this implementation
    must satisfy the test requirements to prevent LLM compliance issues.
"""

import logging
import os
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


class GitHubPrimitiveError(Exception):
    """Base exception for GitHub primitive operations."""

    pass


class GitHubAuthenticationError(GitHubPrimitiveError):
    """Exception raised for GitHub authentication failures."""

    pass


class GitHubRateLimitError(GitHubPrimitiveError):
    """Exception raised when GitHub rate limit is exceeded."""

    pass


class GitHubAPIError(GitHubPrimitiveError):
    """Exception raised for GitHub API errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def get_github_token() -> str | None:
    """Get GitHub token from environment variables.

    Returns:
        GitHub token if found, None otherwise

    Example:
        >>> token = get_github_token()
        >>> if token:
        ...     print("Token found")
        ... else:
        ...     print("No token available")
    """
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        logger.debug("No GITHUB_TOKEN found in environment")
        return None

    logger.debug("GitHub token retrieved from environment")
    return token


def validate_github_token(token: str) -> bool:
    """Validate GitHub token format.

    Args:
        token: GitHub token to validate

    Returns:
        True if token format is valid, False otherwise

    Example:
        >>> validate_github_token("ghp_1234567890abcdef1234567890abcdef12345678")
        True
        >>> validate_github_token("invalid_token")
        False
    """
    if not token or len(token.strip()) == 0:
        return False

    # GitHub token patterns
    import re

    patterns = [
        r"^ghp_[a-zA-Z0-9]{36}$",  # Personal access tokens (classic)
        r"^github_pat_[a-zA-Z0-9_]{82}$",  # Fine-grained personal access tokens
        r"^ghs_[a-zA-Z0-9]{36}$",  # GitHub App installation tokens
        r"^ghu_[a-zA-Z0-9]{36}$",  # GitHub App user tokens
    ]

    return any(re.match(pattern, token.strip()) for pattern in patterns)


def build_github_headers(token: str) -> dict[str, str]:
    """Build standard GitHub API request headers.

    Args:
        token: GitHub authentication token

    Returns:
        Dictionary of HTTP headers for GitHub API requests

    Raises:
        GitHubAuthenticationError: If token is invalid

    Example:
        >>> headers = build_github_headers("ghp_token123")
        >>> assert "Authorization" in headers
        >>> assert "Accept" in headers
    """
    if not validate_github_token(token):
        raise GitHubAuthenticationError("Invalid GitHub token format")

    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MCP-Git-Server/1.1.0",
    }


def build_github_url(endpoint: str, base_url: str = "https://api.github.com") -> str:
    """Build complete GitHub API URL from endpoint.

    Args:
        endpoint: API endpoint path
        base_url: GitHub API base URL

    Returns:
        Complete URL for GitHub API request

    Example:
        >>> url = build_github_url("/repos/owner/repo/pulls")
        >>> assert url == "https://api.github.com/repos/owner/repo/pulls"
    """
    endpoint = endpoint.lstrip("/").rstrip("/")
    base_url = base_url.rstrip("/")
    return f"{base_url}/{endpoint}"


async def make_github_request(
    method: str,
    endpoint: str,
    token: str | None = None,
    params: dict[str, Any] | None = None,
    json_data: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Make authenticated GitHub API request.

    Args:
        method: HTTP method (GET, POST, PATCH, PUT, DELETE)
        endpoint: GitHub API endpoint
        token: GitHub authentication token (optional, will try to get from env)
        params: URL parameters
        json_data: JSON payload for request body
        timeout: Request timeout in seconds

    Returns:
        Response data as dictionary

    Raises:
        GitHubAuthenticationError: If authentication fails
        GitHubRateLimitError: If rate limit is exceeded
        GitHubAPIError: For other API errors

    Example:
        >>> data = await make_github_request("GET", "/user")
        >>> print(data["login"])  # GitHub username
    """
    if token is None:
        token = get_github_token()
        if not token:
            raise GitHubAuthenticationError(
                "No GitHub token available. Set GITHUB_TOKEN environment variable."
            )

    headers = build_github_headers(token)
    url = build_github_url(endpoint)

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=timeout)
    ) as session:
        try:
            logger.debug(f"Making {method} request to {url}")

            async with session.request(
                method=method.upper(),
                url=url,
                headers=headers,
                params=params,
                json=json_data,
            ) as response:
                response_text = await response.text()

                # Handle rate limiting
                if response.status == 403 and "rate limit" in response_text.lower():
                    rate_limit_reset = response.headers.get("X-RateLimit-Reset")
                    raise GitHubRateLimitError(
                        f"GitHub rate limit exceeded. Reset at: {rate_limit_reset}"
                    )

                # Handle authentication errors
                if response.status == 401:
                    raise GitHubAuthenticationError(
                        f"GitHub authentication failed: {response_text}"
                    )

                # Handle other client/server errors
                if response.status >= 400:
                    raise GitHubAPIError(
                        f"GitHub API error: {response_text}",
                        status_code=response.status,
                    )

                # Parse JSON response
                try:
                    return await response.json()
                except Exception as e:
                    logger.warning(f"Failed to parse JSON response: {e}")
                    return {"text": response_text}

        except aiohttp.ClientError as e:
            raise GitHubAPIError(f"Network error during GitHub API request: {e}") from e


async def get_authenticated_user() -> dict[str, Any]:
    """Get information about the authenticated GitHub user.

    Returns:
        User information dictionary

    Raises:
        GitHubAuthenticationError: If authentication fails
        GitHubAPIError: For other API errors

    Example:
        >>> user = await get_authenticated_user()
        >>> print(f"Authenticated as: {user['login']}")
    """
    return await make_github_request("GET", "/user")


async def check_repository_access(repo_owner: str, repo_name: str) -> bool:
    """Check if authenticated user has access to a repository.

    Args:
        repo_owner: Repository owner username
        repo_name: Repository name

    Returns:
        True if user has access, False otherwise

    Example:
        >>> has_access = await check_repository_access("owner", "repo")
        >>> if has_access:
        ...     print("Access granted")
    """
    try:
        await make_github_request("GET", f"/repos/{repo_owner}/{repo_name}")
        return True
    except GitHubAPIError:
        return False


async def get_repository_info(repo_owner: str, repo_name: str) -> dict[str, Any]:
    """Get repository information.

    Args:
        repo_owner: Repository owner username
        repo_name: Repository name

    Returns:
        Repository information dictionary

    Raises:
        GitHubAPIError: If repository not found or access denied

    Example:
        >>> repo = await get_repository_info("owner", "repo")
        >>> print(f"Repository: {repo['full_name']}")
        >>> print(f"Default branch: {repo['default_branch']}")
    """
    return await make_github_request("GET", f"/repos/{repo_owner}/{repo_name}")


async def get_pull_request_info(
    repo_owner: str, repo_name: str, pr_number: int
) -> dict[str, Any]:
    """Get pull request information.

    Args:
        repo_owner: Repository owner username
        repo_name: Repository name
        pr_number: Pull request number

    Returns:
        Pull request information dictionary

    Raises:
        GitHubAPIError: If pull request not found

    Example:
        >>> pr = await get_pull_request_info("owner", "repo", 123)
        >>> print(f"PR #{pr['number']}: {pr['title']}")
        >>> print(f"State: {pr['state']}")
    """
    return await make_github_request(
        "GET", f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}"
    )


async def get_commit_info(
    repo_owner: str, repo_name: str, commit_sha: str
) -> dict[str, Any]:
    """Get commit information.

    Args:
        repo_owner: Repository owner username
        repo_name: Repository name
        commit_sha: Commit SHA hash

    Returns:
        Commit information dictionary

    Raises:
        GitHubAPIError: If commit not found

    Example:
        >>> commit = await get_commit_info("owner", "repo", "abc123...")
        >>> print(f"Author: {commit['commit']['author']['name']}")
        >>> print(f"Message: {commit['commit']['message']}")
    """
    return await make_github_request(
        "GET", f"/repos/{repo_owner}/{repo_name}/commits/{commit_sha}"
    )


async def list_repository_contents(
    repo_owner: str, repo_name: str, path: str = "", ref: str | None = None
) -> list[dict[str, Any]]:
    """List repository contents at a specific path.

    Args:
        repo_owner: Repository owner username
        repo_name: Repository name
        path: Path within repository (default: root)
        ref: Git reference (branch, tag, commit SHA)

    Returns:
        List of content items

    Raises:
        GitHubAPIError: If path not found

    Example:
        >>> contents = await list_repository_contents("owner", "repo", "src")
        >>> for item in contents:
        ...     print(f"{item['type']}: {item['name']}")
    """
    params = {}
    if ref:
        params["ref"] = ref

    endpoint = f"/repos/{repo_owner}/{repo_name}/contents/{path.lstrip('/')}"
    result = await make_github_request("GET", endpoint, params=params)

    # Handle single file response (convert to list)
    if isinstance(result, dict) and result.get("type") == "file":
        return [result]

    return result if isinstance(result, list) else []


async def get_file_content(
    repo_owner: str, repo_name: str, file_path: str, ref: str | None = None
) -> dict[str, Any]:
    """Get file content from repository.

    Args:
        repo_owner: Repository owner username
        repo_name: Repository name
        file_path: Path to file in repository
        ref: Git reference (branch, tag, commit SHA)

    Returns:
        File content information including base64 encoded content

    Raises:
        GitHubAPIError: If file not found

    Example:
        >>> file_info = await get_file_content("owner", "repo", "README.md")
        >>> import base64
        >>> content = base64.b64decode(file_info['content']).decode('utf-8')
        >>> print(content)
    """
    params = {}
    if ref:
        params["ref"] = ref

    endpoint = f"/repos/{repo_owner}/{repo_name}/contents/{file_path.lstrip('/')}"
    return await make_github_request("GET", endpoint, params=params)


async def search_repositories(
    query: str,
    sort: str = "updated",
    order: str = "desc",
    per_page: int = 30,
    page: int = 1,
) -> dict[str, Any]:
    """Search GitHub repositories.

    Args:
        query: Search query string
        sort: Sort field (stars, forks, help-wanted-issues, updated)
        order: Sort order (asc, desc)
        per_page: Results per page (max 100)
        page: Page number

    Returns:
        Search results dictionary with 'items' list

    Raises:
        GitHubAPIError: If search fails

    Example:
        >>> results = await search_repositories("language:python stars:>1000")
        >>> for repo in results['items']:
        ...     print(f"{repo['full_name']}: {repo['stargazers_count']} stars")
    """
    params = {
        "q": query,
        "sort": sort,
        "order": order,
        "per_page": min(per_page, 100),  # GitHub limit
        "page": page,
    }

    return await make_github_request("GET", "/search/repositories", params=params)


def parse_github_url(url: str) -> dict[str, str] | None:
    """Parse GitHub repository URL to extract owner and repository name.

    Args:
        url: GitHub repository URL

    Returns:
        Dictionary with 'owner' and 'repo' keys, or None if invalid

    Example:
        >>> info = parse_github_url("https://github.com/owner/repo")
        >>> print(f"Owner: {info['owner']}, Repo: {info['repo']}")
        >>>
        >>> info = parse_github_url("git@github.com:owner/repo.git")
        >>> print(f"Owner: {info['owner']}, Repo: {info['repo']}")
    """
    import re

    # HTTPS URL pattern
    https_pattern = r"https://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$"
    match = re.match(https_pattern, url)
    if match:
        return {"owner": match.group(1), "repo": match.group(2)}

    # SSH URL pattern
    ssh_pattern = r"git@github\.com:([^/]+)/(.+?)(?:\.git)?$"
    match = re.match(ssh_pattern, url)
    if match:
        return {"owner": match.group(1), "repo": match.group(2)}

    logger.debug(f"Failed to parse GitHub URL: {url}")
    return None


def format_github_error(error: Exception) -> str:
    """Format GitHub API error for user-friendly display.

    Args:
        error: Exception from GitHub API operation

    Returns:
        Formatted error message

    Example:
        >>> try:
        ...     await make_github_request("GET", "/invalid")
        ... except GitHubAPIError as e:
        ...     print(format_github_error(e))
    """
    if isinstance(error, GitHubAuthenticationError):
        return f"🔒 Authentication failed: {error}"
    if isinstance(error, GitHubRateLimitError):
        return f"⏱️ Rate limit exceeded: {error}"
    if isinstance(error, GitHubAPIError):
        status_part = f" (HTTP {error.status_code})" if error.status_code else ""
        return f"❌ GitHub API error{status_part}: {error}"
    return f"💥 Unexpected error: {error}"
