"""GitHub repository settings, permissions, and branch protection operations."""
from __future__ import annotations
import logging
from typing import Any
from mcp_server_git.github.client import github_client_context
logger = logging.getLogger(__name__)


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


async def github_create_repo(
    name: str,
    org: str | None = None,
    description: str | None = None,
    private: bool = False,
    auto_init: bool = False,
    gitignore_template: str | None = None,
    license_template: str | None = None,
    has_issues: bool = True,
    has_projects: bool = True,
    has_wiki: bool = True,
) -> str:
    """Create a new GitHub repository.

    Creates a repository for the authenticated user or an organization.
    Returns the repository URL and clone URLs on success.

    Args:
        name: Repository name (required)
        org: Organization name (None = personal repo)
        description: Repository description
        private: True for private, False for public
        auto_init: Initialize with README
        gitignore_template: e.g., "Python", "Node"
        license_template: e.g., "mit", "apache-2.0"
        has_issues: Enable issues
        has_projects: Enable projects
        has_wiki: Enable wiki

    Returns:
        Success message with repository URLs or error message
    """
    target = f"{org}/{name}" if org else name
    logger.debug(f"Creating repository: {target} (private={private})")

    try:
        async with github_client_context() as client:
            # Build payload with only non-None values
            payload: dict[str, Any] = {
                "name": name,
                "private": private,
                "auto_init": auto_init,
                "has_issues": has_issues,
                "has_projects": has_projects,
                "has_wiki": has_wiki,
            }

            if description is not None:
                payload["description"] = description
            if gitignore_template is not None:
                payload["gitignore_template"] = gitignore_template
            if license_template is not None:
                payload["license_template"] = license_template

            # Use different endpoint for org vs personal repos
            if org:
                endpoint = f"/orgs/{org}/repos"
            else:
                endpoint = "/user/repos"

            response = await client.post(endpoint, json=payload)

            if response.status == 201:
                result = await response.json()
                logger.info(f"Successfully created repository: {result['full_name']}")

                output = [
                    f"Successfully created repository: {result['full_name']}",
                    "",
                    f"URL: {result['html_url']}",
                    f"Clone (HTTPS): {result['clone_url']}",
                    f"Clone (SSH): {result['ssh_url']}",
                ]

                if result.get("private"):
                    output.append("Visibility: Private")
                else:
                    output.append("Visibility: Public")

                if auto_init:
                    output.append("Initialized with README")

                return "\n".join(output)

            elif response.status == 422:
                # Validation error - usually repo already exists
                error_data = await response.json()
                errors = error_data.get("errors", [])
                if errors and any(
                    e.get("message", "").startswith("name already exists")
                    for e in errors
                ):
                    return f"Error: Repository '{target}' already exists"
                return f"Validation error: {error_data.get('message', 'Unknown error')}"

            elif response.status == 403:
                return "Error: Permission denied. Check your token has 'repo' scope."

            elif response.status == 404:
                if org:
                    return f"Error: Organization '{org}' not found or you don't have access."
                return f"Error: Not found - {await response.text()}"

            else:
                error_text = await response.text()
                return f"Error: Failed to create repository: {response.status} - {error_text}"

    except ValueError as auth_error:
        logger.error(f"Authentication error creating repo: {auth_error}")
        return f"Error: {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error creating repo: {conn_error}")
        return f"Error: Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error creating repo: {e}", exc_info=True)
        return f"Error: Failed to create repository: {str(e)}"
