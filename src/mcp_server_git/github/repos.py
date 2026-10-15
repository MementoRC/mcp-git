"""GitHub repository settings operations."""

from __future__ import annotations

import logging
from typing import Any

from mcp_server_git.github._payload import provided_fields
from mcp_server_git.github.check_markers import bool_marker as _flag
from mcp_server_git.github.client import github_client_context
from mcp_server_git.utils.tool_failure import fail

from .permissions import *  # noqa: F401,F403

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
                return fail(f"❌ Repository {repo_owner}/{repo_name} not found")
            if response.status != 200:
                error_text = await response.text()
                return fail(
                    f"❌ Failed to get repository settings: {response.status} - {error_text}"
                )

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
            output.append(f"   Issues: {_flag(repo.get('has_issues'))}")
            output.append(f"   Wiki: {_flag(repo.get('has_wiki'))}")
            output.append(f"   Projects: {_flag(repo.get('has_projects'))}")
            output.append(f"   Discussions: {_flag(repo.get('has_discussions'))}")
            output.append("")

            # Merge settings
            output.append("🔀 Merge Settings:")
            output.append(
                f"   Allow Merge Commits: {_flag(repo.get('allow_merge_commit'))}"
            )
            output.append(
                f"   Allow Squash Merging: {_flag(repo.get('allow_squash_merge'))}"
            )
            output.append(
                f"   Allow Rebase Merging: {_flag(repo.get('allow_rebase_merge'))}"
            )
            output.append(f"   Allow Auto-merge: {_flag(repo.get('allow_auto_merge'))}")
            output.append(
                f"   Delete Branch on Merge: {_flag(repo.get('delete_branch_on_merge'))}"
            )
            output.append(
                f"   Allow Update Branch: {_flag(repo.get('allow_update_branch'))}"
            )
            output.append("")

            # Security
            output.append("🔒 Security:")
            output.append(f"   Archived: {_flag(repo.get('archived'))}")
            output.append(
                f"   Web Commit Signoff Required: {_flag(repo.get('web_commit_signoff_required'))}"
            )
            output.append("")

            # URLs
            output.append("🔗 URLs:")
            output.append(f"   HTML: {repo.get('html_url')}")
            output.append(f"   Clone: {repo.get('clone_url')}")

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error getting repo settings: {auth_error}")
        return fail(f"❌ {str(auth_error)}")
    except ConnectionError as conn_error:
        logger.error(f"Connection error getting repo settings: {conn_error}")
        return fail(f"❌ Network connection failed: {str(conn_error)}")
    except Exception as e:
        logger.error(f"Unexpected error getting repo settings: {e}", exc_info=True)
        return fail(f"❌ Error getting repository settings: {str(e)}")


async def github_update_repo_settings(
    repo_owner: str,
    repo_name: str,
    description: str | None = None,
    homepage: str | None = None,
    private: bool | None = None,
    visibility: str | None = None,
    default_branch: str | None = None,
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
            payload = provided_fields(
                description=description,
                homepage=homepage,
                private=private,
                visibility=visibility,
                default_branch=default_branch,
                has_issues=has_issues,
                has_projects=has_projects,
                has_wiki=has_wiki,
                has_discussions=has_discussions,
                allow_squash_merge=allow_squash_merge,
                allow_merge_commit=allow_merge_commit,
                allow_rebase_merge=allow_rebase_merge,
                allow_auto_merge=allow_auto_merge,
                delete_branch_on_merge=delete_branch_on_merge,
                allow_update_branch=allow_update_branch,
                squash_merge_commit_title=squash_merge_commit_title,
                squash_merge_commit_message=squash_merge_commit_message,
                merge_commit_title=merge_commit_title,
                merge_commit_message=merge_commit_message,
                archived=archived,
                web_commit_signoff_required=web_commit_signoff_required,
            )

            if not payload:
                return "⚠️ No update parameters provided"

            response = await client.patch(
                f"/repos/{repo_owner}/{repo_name}", json=payload
            )

            if response.status != 200:
                error_text = await response.text()
                return fail(
                    f"❌ Failed to update repository settings: {response.status} - {error_text}"
                )

            result = await response.json()
            updated_fields = list(payload.keys())
            logger.info(
                f"✅ Successfully updated repository settings: {updated_fields}"
            )
            return f"✅ Successfully updated repository settings for {result['full_name']}\nUpdated fields: {', '.join(updated_fields)}"

    except ValueError as auth_error:
        logger.error(f"Authentication error updating repo settings: {auth_error}")
        return fail(f"❌ {str(auth_error)}")
    except ConnectionError as conn_error:
        logger.error(f"Connection error updating repo settings: {conn_error}")
        return fail(f"❌ Network connection failed: {str(conn_error)}")
    except Exception as e:
        logger.error(f"Unexpected error updating repo settings: {e}", exc_info=True)
        return fail(f"❌ Error updating repository settings: {str(e)}")


def _format_created_repo(result: dict[str, Any], auto_init: bool) -> str:
    """Render the success message for a freshly created repository."""
    output = [
        f"Successfully created repository: {result['full_name']}",
        "",
        f"URL: {result['html_url']}",
        f"Clone (HTTPS): {result['clone_url']}",
        f"Clone (SSH): {result['ssh_url']}",
        "Visibility: Private" if result.get("private") else "Visibility: Public",
    ]
    if auto_init:
        output.append("Initialized with README")
    return "\n".join(output)


def _validation_error_message(error_data: dict[str, Any], target: str) -> str:
    """Render a 422 response: already-exists, or the API's own message."""
    errors = error_data.get("errors", [])
    if errors and any(
        e.get("message", "").startswith("name already exists") for e in errors
    ):
        return f"Error: Repository '{target}' already exists"
    return f"Validation error: {error_data.get('message', 'Unknown error')}"


async def _create_repo_error(response: Any, org: str | None, target: str) -> str:
    """Map a non-201 create-repository response to its error message."""
    if response.status == 422:
        return _validation_error_message(await response.json(), target)
    if response.status == 403:
        return "Error: Permission denied. Check your token has 'repo' scope."
    if response.status == 404:
        if org:
            return f"Error: Organization '{org}' not found or you don't have access."
        return f"Error: Not found - {await response.text()}"
    error_text = await response.text()
    return f"Error: Failed to create repository: {response.status} - {error_text}"


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
            payload: dict[str, Any] = {
                "name": name,
                "private": private,
                "auto_init": auto_init,
                "has_issues": has_issues,
                "has_projects": has_projects,
                "has_wiki": has_wiki,
                **provided_fields(
                    description=description,
                    gitignore_template=gitignore_template,
                    license_template=license_template,
                ),
            }

            # Use different endpoint for org vs personal repos
            endpoint = f"/orgs/{org}/repos" if org else "/user/repos"
            response = await client.post(endpoint, json=payload)

            if response.status == 201:
                result = await response.json()
                logger.info(f"Successfully created repository: {result['full_name']}")
                return _format_created_repo(result, auto_init)

            return await _create_repo_error(response, org, target)

    except ValueError as auth_error:
        logger.error(f"Authentication error creating repo: {auth_error}")
        return f"Error: {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error creating repo: {conn_error}")
        return f"Error: Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error creating repo: {e}", exc_info=True)
        return f"Error: Failed to create repository: {str(e)}"
