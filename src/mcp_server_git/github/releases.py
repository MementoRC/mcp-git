"""GitHub release CRUD operations."""

from __future__ import annotations

import logging
from typing import Any

from mcp_server_git.github.client import github_client_context

logger = logging.getLogger(__name__)


async def github_create_release(
    repo_owner: str,
    repo_name: str,
    tag_name: str,
    name: str | None = None,
    body: str | None = None,
    draft: bool = False,
    prerelease: bool = False,
    target_commitish: str | None = None,
    generate_release_notes: bool = False,
) -> str:
    """Create a new GitHub release.

    Args:
        repo_owner: Repository owner
        repo_name: Repository name
        tag_name: Git tag name for the release
        name: Release title (defaults to tag_name if not provided)
        body: Release description/notes
        draft: If true, creates a draft (unpublished) release
        prerelease: If true, marks as pre-release
        target_commitish: Branch or commit SHA for the release (defaults to default branch)
        generate_release_notes: Auto-generate release notes from commits
    """
    logger.debug(f"🚀 Creating release {tag_name} for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            payload: dict[str, Any] = {
                "tag_name": tag_name,
                "draft": draft,
                "prerelease": prerelease,
            }

            if name:
                payload["name"] = name
            if body:
                payload["body"] = body
            if target_commitish:
                payload["target_commitish"] = target_commitish
            if generate_release_notes:
                payload["generate_release_notes"] = generate_release_notes

            response = await client.post(
                f"/repos/{repo_owner}/{repo_name}/releases",
                json=payload,
            )

            if response.status == 404:
                return f"❌ Repository {repo_owner}/{repo_name} not found"
            if response.status == 422:
                error_data = await response.json()
                error_msg = error_data.get("message", "Validation failed")
                return f"❌ Failed to create release: {error_msg}"
            if response.status not in (200, 201):
                error_text = await response.text()
                return f"❌ Failed to create release: {response.status} - {error_text}"

            release = await response.json()
            release_url = release.get("html_url", "")
            release_id = release.get("id", "")

            status = []
            if draft:
                status.append("draft")
            if prerelease:
                status.append("pre-release")
            status_str = f" ({', '.join(status)})" if status else ""

            return f"✅ Release {tag_name} created successfully{status_str}\n🔗 URL: {release_url}\n📋 Release ID: {release_id}"

    except ValueError as auth_error:
        logger.error(f"Authentication error creating release: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error creating release: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error creating release: {e}", exc_info=True)
        return f"❌ Error creating release: {str(e)}"


async def github_get_release(
    repo_owner: str,
    repo_name: str,
    release_id: int | None = None,
    tag: str | None = None,
) -> str:
    """Get a GitHub release by ID or tag.

    Args:
        repo_owner: Repository owner
        repo_name: Repository name
        release_id: Release ID (mutually exclusive with tag)
        tag: Tag name (mutually exclusive with release_id)
    """
    if not release_id and not tag:
        return "❌ Either release_id or tag must be provided"
    if release_id and tag:
        return "❌ Only one of release_id or tag can be provided"

    identifier = f"ID: {release_id}" if release_id else f"tag: {tag}"
    logger.debug(f"🔍 Getting release for {repo_owner}/{repo_name} ({identifier})")

    try:
        async with github_client_context() as client:
            if release_id:
                endpoint = f"/repos/{repo_owner}/{repo_name}/releases/{release_id}"
            else:
                endpoint = f"/repos/{repo_owner}/{repo_name}/releases/tags/{tag}"

            response = await client.get(endpoint)

            if response.status == 404:
                identifier = f"ID {release_id}" if release_id else f"tag '{tag}'"
                return f"❌ Release {identifier} not found in {repo_owner}/{repo_name}"
            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to get release: {response.status} - {error_text}"

            release = await response.json()

            output = [f"Release Information for {repo_owner}/{repo_name}:\n"]
            output.append(f"📦 Tag: {release.get('tag_name')}")
            output.append(f"📋 Name: {release.get('name') or '(none)'}")

            status = []
            if release.get("draft"):
                status.append("draft")
            if release.get("prerelease"):
                status.append("pre-release")
            if status:
                output.append(f"🏷️  Status: {', '.join(status)}")

            output.append(f"🔗 URL: {release.get('html_url')}")
            output.append(f"📅 Created: {release.get('created_at')}")
            output.append(
                f"📅 Published: {release.get('published_at') or 'Not published'}"
            )

            author = release.get("author", {})
            if author:
                output.append(f"👤 Author: {author.get('login')}")

            body = release.get("body")
            if body:
                output.append(f"\n📝 Description:\n{body}")

            assets = release.get("assets", [])
            if assets:
                output.append(f"\n📎 Assets ({len(assets)}):")
                for asset in assets:
                    output.append(
                        f"   • {asset.get('name')} ({asset.get('size')} bytes)"
                    )
            else:
                output.append("\n📎 Assets: None")

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error getting release: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error getting release: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error getting release: {e}", exc_info=True)
        return f"❌ Error getting release: {str(e)}"


async def github_list_releases(
    repo_owner: str,
    repo_name: str,
    per_page: int = 30,
    page: int = 1,
) -> str:
    """List releases for a repository.

    Args:
        repo_owner: Repository owner
        repo_name: Repository name
        per_page: Number of releases per page (max 100)
        page: Page number to retrieve
    """
    logger.debug(f"🔍 Listing releases for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/releases",
                params={"per_page": per_page, "page": page},
            )

            if response.status == 404:
                return f"❌ Repository {repo_owner}/{repo_name} not found"
            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to list releases: {response.status} - {error_text}"

            releases = await response.json()

            if not releases:
                return f"No releases found for {repo_owner}/{repo_name}"

            output = [f"Releases for {repo_owner}/{repo_name}:\n"]

            for release in releases:
                tag = release.get("tag_name")
                name = release.get("name") or tag
                created = release.get("created_at", "")[:10]  # Just the date

                status = []
                if release.get("draft"):
                    status.append("draft")
                if release.get("prerelease"):
                    status.append("pre-release")
                status_str = f" [{', '.join(status)}]" if status else ""

                output.append(f"📦 {tag}: {name}{status_str}")
                output.append(f"   📅 Created: {created}")
                output.append(f"   🔗 {release.get('html_url')}")
                output.append("")

            # Add pagination info
            link_header = response.headers.get("Link", "")
            if "next" in link_header or page > 1:
                output.append(f"📄 Page {page} (use page parameter to see more)")

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error listing releases: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error listing releases: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error listing releases: {e}", exc_info=True)
        return f"❌ Error listing releases: {str(e)}"


async def github_update_release(
    repo_owner: str,
    repo_name: str,
    release_id: int,
    tag_name: str | None = None,
    name: str | None = None,
    body: str | None = None,
    draft: bool | None = None,
    prerelease: bool | None = None,
    target_commitish: str | None = None,
) -> str:
    """Update a GitHub release.

    Args:
        repo_owner: Repository owner
        repo_name: Repository name
        release_id: Release ID to update
        tag_name: New tag name
        name: New release title
        body: New release description
        draft: Update draft status
        prerelease: Update pre-release status
        target_commitish: Update target commitish
    """
    logger.debug(f"🚀 Updating release {release_id} for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            # Build payload with only provided fields
            payload: dict[str, Any] = {}
            if tag_name is not None:
                payload["tag_name"] = tag_name
            if name is not None:
                payload["name"] = name
            if body is not None:
                payload["body"] = body
            if draft is not None:
                payload["draft"] = draft
            if prerelease is not None:
                payload["prerelease"] = prerelease
            if target_commitish is not None:
                payload["target_commitish"] = target_commitish

            if not payload:
                return "❌ No fields provided to update"

            response = await client.patch(
                f"/repos/{repo_owner}/{repo_name}/releases/{release_id}",
                json=payload,
            )

            if response.status == 404:
                return f"❌ Release {release_id} not found in {repo_owner}/{repo_name}"
            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to update release: {response.status} - {error_text}"

            release = await response.json()
            release_url = release.get("html_url", "")
            tag = release.get("tag_name", "")

            return f"✅ Release {tag} (ID: {release_id}) updated successfully\n🔗 URL: {release_url}"

    except ValueError as auth_error:
        logger.error(f"Authentication error updating release: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error updating release: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error updating release: {e}", exc_info=True)
        return f"❌ Error updating release: {str(e)}"


async def github_delete_release(
    repo_owner: str,
    repo_name: str,
    release_id: int,
) -> str:
    """Delete a GitHub release.

    Args:
        repo_owner: Repository owner
        repo_name: Repository name
        release_id: Release ID to delete
    """
    logger.debug(f"🗑️  Deleting release {release_id} for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            response = await client.delete(
                f"/repos/{repo_owner}/{repo_name}/releases/{release_id}"
            )

            if response.status == 404:
                return f"❌ Release {release_id} not found in {repo_owner}/{repo_name}"
            if response.status != 204:
                error_text = await response.text()
                return f"❌ Failed to delete release: {response.status} - {error_text}"

            return f"✅ Release {release_id} deleted successfully from {repo_owner}/{repo_name}"

    except ValueError as auth_error:
        logger.error(f"Authentication error deleting release: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error deleting release: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error deleting release: {e}", exc_info=True)
        return f"❌ Error deleting release: {str(e)}"


from .release_assets import *  # noqa: F401,F403
