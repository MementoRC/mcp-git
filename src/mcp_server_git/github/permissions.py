"""GitHub Actions permissions and branch protection operations."""

from __future__ import annotations

import logging
from typing import Any

from mcp_server_git.github._branch_protection import (
    format_branch_protection,
    pr_reviews_payload,
    restrictions_payload,
    status_checks_payload,
)
from mcp_server_git.github._failures import http_failure
from mcp_server_git.github._payload import provided_fields
from mcp_server_git.github.check_markers import bool_marker
from mcp_server_git.github.client import github_client_context
from mcp_server_git.utils.tool_failure import fail

logger = logging.getLogger(__name__)


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
                return fail(
                    f"❌ Repository {repo_owner}/{repo_name} not found or Actions not enabled"
                )
            if response.status != 200:
                return await http_failure("get Actions permissions", response)

            data = await response.json()

            output = [f"GitHub Actions Permissions for {repo_owner}/{repo_name}:\n"]
            output.append(f"Enabled: {bool_marker(data.get('enabled'))}")
            output.append(f"Allowed Actions: {data.get('allowed_actions', 'N/A')}")

            if data.get("selected_actions_url"):
                output.append(f"Selected Actions URL: {data['selected_actions_url']}")

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error getting Actions permissions: {auth_error}")
        return fail(f"❌ {str(auth_error)}")
    except ConnectionError as conn_error:
        logger.error(f"Connection error getting Actions permissions: {conn_error}")
        return fail(f"❌ Network connection failed: {str(conn_error)}")
    except Exception as e:
        logger.error(
            f"Unexpected error getting Actions permissions: {e}", exc_info=True
        )
        return fail(f"❌ Error getting Actions permissions: {str(e)}")


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
                    return fail(
                        "❌ allowed_actions must be 'all', 'local_only', or 'selected'"
                    )
                payload["allowed_actions"] = allowed_actions

            if not payload:
                return "⚠️ No update parameters provided"

            response = await client.put(
                f"/repos/{repo_owner}/{repo_name}/actions/permissions", json=payload
            )

            if response.status not in [200, 204]:
                return await http_failure("update Actions permissions", response)

            logger.info("Successfully updated Actions permissions")
            return f"✅ Successfully updated GitHub Actions permissions for {repo_owner}/{repo_name}"

    except ValueError as auth_error:
        logger.error(f"Authentication error updating Actions permissions: {auth_error}")
        return fail(f"❌ {str(auth_error)}")
    except ConnectionError as conn_error:
        logger.error(f"Connection error updating Actions permissions: {conn_error}")
        return fail(f"❌ Network connection failed: {str(conn_error)}")
    except Exception as e:
        logger.error(
            f"Unexpected error updating Actions permissions: {e}", exc_info=True
        )
        return fail(f"❌ Error updating Actions permissions: {str(e)}")


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
                return fail(f"❌ Repository {repo_owner}/{repo_name} not found")
            if response.status != 200:
                return await http_failure("get workflow permissions", response)

            data = await response.json()

            output = [f"Workflow Permissions for {repo_owner}/{repo_name}:\n"]
            output.append(
                f"Default Permissions: {data.get('default_workflow_permissions', 'N/A')}"
            )
            output.append(
                f"Can Approve PR Reviews: {bool_marker(data.get('can_approve_pull_request_reviews'))}"
            )

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error getting workflow permissions: {auth_error}")
        return fail(f"❌ {str(auth_error)}")
    except ConnectionError as conn_error:
        logger.error(f"Connection error getting workflow permissions: {conn_error}")
        return fail(f"❌ Network connection failed: {str(conn_error)}")
    except Exception as e:
        logger.error(
            f"Unexpected error getting workflow permissions: {e}", exc_info=True
        )
        return fail(f"❌ Error getting workflow permissions: {str(e)}")


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
                    return fail(
                        "❌ default_workflow_permissions must be 'read' or 'write'"
                    )
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
                return await http_failure("update workflow permissions", response)

            logger.info("Successfully updated workflow permissions")
            return f"✅ Successfully updated workflow permissions for {repo_owner}/{repo_name}"

    except ValueError as auth_error:
        logger.error(
            f"Authentication error updating workflow permissions: {auth_error}"
        )
        return fail(f"❌ {str(auth_error)}")
    except ConnectionError as conn_error:
        logger.error(f"Connection error updating workflow permissions: {conn_error}")
        return fail(f"❌ Network connection failed: {str(conn_error)}")
    except Exception as e:
        logger.error(
            f"Unexpected error updating workflow permissions: {e}", exc_info=True
        )
        return fail(f"❌ Error updating workflow permissions: {str(e)}")


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
                return fail(
                    f"❌ Branch protection not found for {branch}. The branch may not exist or have no protection rules."
                )
            if response.status != 200:
                return await http_failure("get branch protection", response)

            data = await response.json()

            return format_branch_protection(repo_owner, repo_name, branch, data)

    except ValueError as auth_error:
        logger.error(f"Authentication error getting branch protection: {auth_error}")
        return fail(f"❌ {str(auth_error)}")
    except ConnectionError as conn_error:
        logger.error(f"Connection error getting branch protection: {conn_error}")
        return fail(f"❌ Network connection failed: {str(conn_error)}")
    except Exception as e:
        logger.error(f"Unexpected error getting branch protection: {e}", exc_info=True)
        return fail(f"❌ Error getting branch protection: {str(e)}")


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
            # GitHub API requires specific structure for branch protection
            payload: dict[str, Any] = {
                "required_status_checks": status_checks_payload(
                    required_status_checks_strict, required_status_checks_contexts
                ),
                "required_pull_request_reviews": pr_reviews_payload(
                    require_pull_request_reviews,
                    dismiss_stale_reviews=dismiss_stale_reviews,
                    require_code_owner_reviews=require_code_owner_reviews,
                    required_approving_review_count=required_approving_review_count,
                    require_last_push_approval=require_last_push_approval,
                ),
                "enforce_admins": (
                    enforce_admins if enforce_admins is not None else False
                ),
                "restrictions": restrictions_payload(
                    restrict_pushes, push_allowances_users, push_allowances_teams
                ),
                **provided_fields(
                    required_linear_history=required_linear_history,
                    allow_force_pushes=allow_force_pushes,
                    allow_deletions=allow_deletions,
                    block_creations=block_creations,
                    required_conversation_resolution=required_conversation_resolution,
                    lock_branch=lock_branch,
                    allow_fork_syncing=allow_fork_syncing,
                ),
            }

            response = await client.put(
                f"/repos/{repo_owner}/{repo_name}/branches/{branch}/protection",
                json=payload,
            )

            if response.status not in [200, 201]:
                return await http_failure("update branch protection", response)

            logger.info(f"✅ Successfully updated branch protection for {branch}")
            return f"✅ Successfully updated branch protection for {repo_owner}/{repo_name}:{branch}"

    except ValueError as auth_error:
        logger.error(f"Authentication error updating branch protection: {auth_error}")
        return fail(f"❌ {str(auth_error)}")
    except ConnectionError as conn_error:
        logger.error(f"Connection error updating branch protection: {conn_error}")
        return fail(f"❌ Network connection failed: {str(conn_error)}")
    except Exception as e:
        logger.error(f"Unexpected error updating branch protection: {e}", exc_info=True)
        return fail(f"❌ Error updating branch protection: {str(e)}")


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
                return fail(f"❌ Branch protection not found for {branch}")
            if response.status != 204:
                return await http_failure("delete branch protection", response)

            logger.info(f"✅ Successfully deleted branch protection for {branch}")
            return f"✅ Successfully deleted branch protection for {repo_owner}/{repo_name}:{branch}"

    except ValueError as auth_error:
        logger.error(f"Authentication error deleting branch protection: {auth_error}")
        return fail(f"❌ {str(auth_error)}")
    except ConnectionError as conn_error:
        logger.error(f"Connection error deleting branch protection: {conn_error}")
        return fail(f"❌ Network connection failed: {str(conn_error)}")
    except Exception as e:
        logger.error(f"Unexpected error deleting branch protection: {e}", exc_info=True)
        return fail(f"❌ Error deleting branch protection: {str(e)}")
