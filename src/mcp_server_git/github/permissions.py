"""GitHub Actions permissions and branch protection operations."""
from __future__ import annotations
import logging
from typing import Any
from mcp_server_git.github.client import github_client_context
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
