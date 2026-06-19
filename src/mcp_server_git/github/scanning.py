"""GitHub GHAS forensics — rulesets, code scanning, and secret scanning."""

from __future__ import annotations

import logging
from typing import Any

from mcp_server_git.github.client import github_client_context

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_params(**kwargs: Any) -> dict[str, str]:
    """Build query-param dict omitting None values."""
    return {k: str(v) for k, v in kwargs.items() if v is not None}


# ---------------------------------------------------------------------------
# Rulesets
# ---------------------------------------------------------------------------


async def github_list_rulesets(
    repo_owner: str,
    repo_name: str,
) -> list[dict[str, Any]] | str:
    """List rulesets defined on a repository."""
    logger.debug("Getting rulesets for %s/%s", repo_owner, repo_name)

    try:
        async with github_client_context() as client:
            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/rulesets"
            )

            if response.status == 200:
                return await response.json()
            elif response.status == 404:
                return f"❌ Repository not found: {repo_owner}/{repo_name}"
            else:
                error_text = await response.text()
                return f"❌ Failed to list rulesets: {response.status} - {error_text}"

    except ValueError as auth_error:
        logger.error("Authentication error listing rulesets: %s", auth_error)
        return f"❌ {auth_error}"
    except ConnectionError as conn_error:
        logger.error("Connection error listing rulesets: %s", conn_error)
        return f"❌ Network connection failed: {conn_error}"
    except Exception as exc:
        logger.error("Unexpected error listing rulesets: %s", exc, exc_info=True)
        return f"❌ Error listing rulesets: {exc}"


async def github_get_ruleset(
    repo_owner: str,
    repo_name: str,
    ruleset_id: int,
) -> dict[str, Any] | str:
    """Get a specific ruleset by ID (includes required_status_checks, code_scanning, bypass actors)."""
    logger.debug(
        "Getting ruleset %d for %s/%s", ruleset_id, repo_owner, repo_name
    )

    try:
        async with github_client_context() as client:
            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/rulesets/{ruleset_id}"
            )

            if response.status == 200:
                return await response.json()
            elif response.status == 404:
                return (
                    f"❌ Ruleset {ruleset_id} not found for {repo_owner}/{repo_name}"
                )
            else:
                error_text = await response.text()
                return f"❌ Failed to get ruleset: {response.status} - {error_text}"

    except ValueError as auth_error:
        logger.error("Authentication error getting ruleset: %s", auth_error)
        return f"❌ {auth_error}"
    except ConnectionError as conn_error:
        logger.error("Connection error getting ruleset: %s", conn_error)
        return f"❌ Network connection failed: {conn_error}"
    except Exception as exc:
        logger.error("Unexpected error getting ruleset: %s", exc, exc_info=True)
        return f"❌ Error getting ruleset: {exc}"


async def github_get_branch_rules(
    repo_owner: str,
    repo_name: str,
    branch: str,
) -> list[dict[str, Any]] | str:
    """Get all rules (classic + ruleset-based) that apply to a branch."""
    logger.debug(
        "Getting branch rules for %s/%s#%s", repo_owner, repo_name, branch
    )

    try:
        async with github_client_context() as client:
            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/rules/branches/{branch}"
            )

            if response.status == 200:
                return await response.json()
            elif response.status == 404:
                return (
                    f"❌ Branch or repository not found: {repo_owner}/{repo_name}#{branch}"
                )
            else:
                error_text = await response.text()
                return f"❌ Failed to get branch rules: {response.status} - {error_text}"

    except ValueError as auth_error:
        logger.error("Authentication error getting branch rules: %s", auth_error)
        return f"❌ {auth_error}"
    except ConnectionError as conn_error:
        logger.error("Connection error getting branch rules: %s", conn_error)
        return f"❌ Network connection failed: {conn_error}"
    except Exception as exc:
        logger.error("Unexpected error getting branch rules: %s", exc, exc_info=True)
        return f"❌ Error getting branch rules: {exc}"


# ---------------------------------------------------------------------------
# Code Scanning
# ---------------------------------------------------------------------------


async def github_list_code_scanning_alerts(
    repo_owner: str,
    repo_name: str,
    state: str | None = None,
    severity: str | None = None,
    tool_name: str | None = None,
    ref: str | None = None,
) -> list[dict[str, Any]] | str:
    """List code scanning alerts with optional filters.

    Args:
        state: Filter by alert state ('open', 'closed', 'dismissed', 'fixed').
        severity: Filter by severity ('critical', 'high', 'medium', 'low', 'warning', 'note', 'error').
        tool_name: Filter by code-scanning tool name (e.g. 'CodeQL').
        ref: Filter by Git ref (branch name or refs/pull/N/head).
    """
    logger.debug(
        "Listing code scanning alerts for %s/%s", repo_owner, repo_name
    )

    params = _build_params(
        state=state, severity=severity, tool_name=tool_name, ref=ref
    )

    try:
        async with github_client_context() as client:
            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/code-scanning/alerts",
                params=params if params else None,
            )

            if response.status == 200:
                return await response.json()
            elif response.status == 404:
                return (
                    f"❌ Repository not found or code scanning not enabled: "
                    f"{repo_owner}/{repo_name}"
                )
            else:
                error_text = await response.text()
                return (
                    f"❌ Failed to list code scanning alerts: "
                    f"{response.status} - {error_text}"
                )

    except ValueError as auth_error:
        logger.error(
            "Authentication error listing code scanning alerts: %s", auth_error
        )
        return f"❌ {auth_error}"
    except ConnectionError as conn_error:
        logger.error(
            "Connection error listing code scanning alerts: %s", conn_error
        )
        return f"❌ Network connection failed: {conn_error}"
    except Exception as exc:
        logger.error(
            "Unexpected error listing code scanning alerts: %s", exc, exc_info=True
        )
        return f"❌ Error listing code scanning alerts: {exc}"


async def github_list_code_scanning_analyses(
    repo_owner: str,
    repo_name: str,
    ref: str | None = None,
    tool_name: str | None = None,
) -> list[dict[str, Any]] | str:
    """List code scanning analyses for a repository.

    Args:
        ref: Git ref to filter by (branch name or refs/pull/N/head).
        tool_name: Code-scanning tool name to filter by (e.g. 'CodeQL').
    """
    logger.debug(
        "Listing code scanning analyses for %s/%s", repo_owner, repo_name
    )

    params = _build_params(ref=ref, tool_name=tool_name)

    try:
        async with github_client_context() as client:
            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/code-scanning/analyses",
                params=params if params else None,
            )

            if response.status == 200:
                return await response.json()
            elif response.status == 404:
                return (
                    f"❌ Repository not found or code scanning not enabled: "
                    f"{repo_owner}/{repo_name}"
                )
            else:
                error_text = await response.text()
                return (
                    f"❌ Failed to list code scanning analyses: "
                    f"{response.status} - {error_text}"
                )

    except ValueError as auth_error:
        logger.error(
            "Authentication error listing code scanning analyses: %s", auth_error
        )
        return f"❌ {auth_error}"
    except ConnectionError as conn_error:
        logger.error(
            "Connection error listing code scanning analyses: %s", conn_error
        )
        return f"❌ Network connection failed: {conn_error}"
    except Exception as exc:
        logger.error(
            "Unexpected error listing code scanning analyses: %s", exc, exc_info=True
        )
        return f"❌ Error listing code scanning analyses: {exc}"


async def github_get_code_scanning_default_setup(
    repo_owner: str,
    repo_name: str,
) -> dict[str, Any] | str:
    """Get the default-setup configuration for code scanning."""
    logger.debug(
        "Getting code scanning default setup for %s/%s", repo_owner, repo_name
    )

    try:
        async with github_client_context() as client:
            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/code-scanning/default-setup"
            )

            if response.status == 200:
                return await response.json()
            elif response.status == 404:
                return (
                    f"❌ Repository not found or code scanning not available: "
                    f"{repo_owner}/{repo_name}"
                )
            else:
                error_text = await response.text()
                return (
                    f"❌ Failed to get code scanning default setup: "
                    f"{response.status} - {error_text}"
                )

    except ValueError as auth_error:
        logger.error(
            "Authentication error getting code scanning default setup: %s", auth_error
        )
        return f"❌ {auth_error}"
    except ConnectionError as conn_error:
        logger.error(
            "Connection error getting code scanning default setup: %s", conn_error
        )
        return f"❌ Network connection failed: {conn_error}"
    except Exception as exc:
        logger.error(
            "Unexpected error getting code scanning default setup: %s",
            exc,
            exc_info=True,
        )
        return f"❌ Error getting code scanning default setup: {exc}"


# ---------------------------------------------------------------------------
# Secret Scanning
# ---------------------------------------------------------------------------


async def github_list_secret_scanning_alerts(
    repo_owner: str,
    repo_name: str,
    state: str | None = None,
) -> list[dict[str, Any]] | str:
    """List secret scanning alerts for a repository.

    Args:
        state: Filter by alert state ('open' or 'resolved').
    """
    logger.debug(
        "Listing secret scanning alerts for %s/%s", repo_owner, repo_name
    )

    params = _build_params(state=state)

    try:
        async with github_client_context() as client:
            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/secret-scanning/alerts",
                params=params if params else None,
            )

            if response.status == 200:
                return await response.json()
            elif response.status == 404:
                return (
                    f"❌ Repository not found or secret scanning not enabled: "
                    f"{repo_owner}/{repo_name}"
                )
            else:
                error_text = await response.text()
                return (
                    f"❌ Failed to list secret scanning alerts: "
                    f"{response.status} - {error_text}"
                )

    except ValueError as auth_error:
        logger.error(
            "Authentication error listing secret scanning alerts: %s", auth_error
        )
        return f"❌ {auth_error}"
    except ConnectionError as conn_error:
        logger.error(
            "Connection error listing secret scanning alerts: %s", conn_error
        )
        return f"❌ Network connection failed: {conn_error}"
    except Exception as exc:
        logger.error(
            "Unexpected error listing secret scanning alerts: %s", exc, exc_info=True
        )
        return f"❌ Error listing secret scanning alerts: {exc}"
