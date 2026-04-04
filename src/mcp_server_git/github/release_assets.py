"""GitHub release asset management operations."""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path

from mcp_server_git.github.client import github_client_context

logger = logging.getLogger(__name__)


async def github_upload_release_asset(
    repo_owner: str,
    repo_name: str,
    release_id: int,
    file_path: str,
    name: str | None = None,
    label: str | None = None,
) -> str:
    """Upload a file as a release asset.

    Args:
        repo_owner: Repository owner
        repo_name: Repository name
        release_id: Release ID to upload asset to
        file_path: Local path to file to upload
        name: Asset name (defaults to filename)
        label: Asset label/description
    """
    logger.debug(
        f"📤 Uploading asset {file_path} to release {release_id} for {repo_owner}/{repo_name}"
    )

    try:
        # Validate file exists
        path = Path(file_path)
        if not path.exists():
            return f"❌ File not found: {file_path}"
        if not path.is_file():
            return f"❌ Path is not a file: {file_path}"

        # Read file content
        try:
            with open(path, "rb") as f:
                file_content = f.read()
        except Exception as read_error:
            return f"❌ Failed to read file {file_path}: {read_error}"

        # Determine asset name
        asset_name = name or path.name

        # Determine content type (handle corrupt mimetypes database gracefully)
        try:
            content_type = (
                mimetypes.guess_type(asset_name)[0] or "application/octet-stream"
            )
        except Exception:
            content_type = "application/octet-stream"

        async with github_client_context() as client:
            # First get the release to get the upload_url
            release_response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/releases/{release_id}"
            )

            if release_response.status == 404:
                return f"❌ Release {release_id} not found in {repo_owner}/{repo_name}"
            if release_response.status != 200:
                error_text = await release_response.text()
                return f"❌ Failed to get release: {release_response.status} - {error_text}"

            release = await release_response.json()
            upload_url = release.get("upload_url", "")

            if not upload_url:
                return f"❌ Release {release_id} has no upload URL"

            # Remove the {?name,label} template from upload_url
            upload_url = upload_url.split("{")[0]

            # Build query params
            params = {"name": asset_name}
            if label:
                params["label"] = label

            # Upload the asset
            response = await client.post(
                upload_url,
                params=params,
                data=file_content,
                headers={"Content-Type": content_type},
            )

            if response.status == 422:
                error_data = await response.json()
                error_msg = error_data.get("message", "Validation failed")
                return f"❌ Failed to upload asset: {error_msg}"
            if response.status not in (200, 201):
                error_text = await response.text()
                return f"❌ Failed to upload asset: {response.status} - {error_text}"

            asset = await response.json()
            asset_url = asset.get("browser_download_url", "")
            asset_id = asset.get("id", "")
            asset_size = asset.get("size", 0)

            return f"✅ Asset '{asset_name}' uploaded successfully ({asset_size} bytes)\n🔗 URL: {asset_url}\n📋 Asset ID: {asset_id}"

    except ValueError as auth_error:
        logger.error(f"Authentication error uploading asset: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error uploading asset: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error uploading asset: {e}", exc_info=True)
        return f"❌ Error uploading asset: {str(e)}"


async def github_list_release_assets(
    repo_owner: str,
    repo_name: str,
    release_id: int,
    per_page: int = 30,
    page: int = 1,
) -> str:
    """List assets for a release.

    Args:
        repo_owner: Repository owner
        repo_name: Repository name
        release_id: Release ID
        per_page: Number of assets per page (max 100)
        page: Page number to retrieve
    """
    logger.debug(
        f"🔍 Listing assets for release {release_id} in {repo_owner}/{repo_name}"
    )

    try:
        async with github_client_context() as client:
            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/releases/{release_id}/assets",
                params={"per_page": per_page, "page": page},
            )

            if response.status == 404:
                return f"❌ Release {release_id} not found in {repo_owner}/{repo_name}"
            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to list assets: {response.status} - {error_text}"

            assets = await response.json()

            if not assets:
                return f"No assets found for release {release_id}"

            output = [f"Assets for Release {release_id} in {repo_owner}/{repo_name}:\n"]

            for asset in assets:
                name = asset.get("name")
                size = asset.get("size", 0)
                downloads = asset.get("download_count", 0)
                content_type = asset.get("content_type", "unknown")
                asset_id = asset.get("id")

                # Format size nicely
                if size < 1024:
                    size_str = f"{size} B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.1f} KB"
                else:
                    size_str = f"{size / (1024 * 1024):.1f} MB"

                output.append(f"📎 {name}")
                output.append(f"   ID: {asset_id}")
                output.append(f"   Size: {size_str}")
                output.append(f"   Type: {content_type}")
                output.append(f"   Downloads: {downloads}")
                output.append(f"   URL: {asset.get('browser_download_url')}")
                output.append("")

            # Add pagination info
            link_header = response.headers.get("Link", "")
            if "next" in link_header or page > 1:
                output.append(f"📄 Page {page} (use page parameter to see more)")

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error listing assets: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error listing assets: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error listing assets: {e}", exc_info=True)
        return f"❌ Error listing assets: {str(e)}"


async def github_delete_release_asset(
    repo_owner: str,
    repo_name: str,
    asset_id: int,
) -> str:
    """Delete a release asset.

    Args:
        repo_owner: Repository owner
        repo_name: Repository name
        asset_id: Asset ID to delete
    """
    logger.debug(f"🗑️  Deleting asset {asset_id} for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            response = await client.delete(
                f"/repos/{repo_owner}/{repo_name}/releases/assets/{asset_id}"
            )

            if response.status == 404:
                return f"❌ Asset {asset_id} not found in {repo_owner}/{repo_name}"
            if response.status != 204:
                error_text = await response.text()
                return f"❌ Failed to delete asset: {response.status} - {error_text}"

            return f"✅ Asset {asset_id} deleted successfully from {repo_owner}/{repo_name}"

    except ValueError as auth_error:
        logger.error(f"Authentication error deleting asset: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error deleting asset: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error deleting asset: {e}", exc_info=True)
        return f"❌ Error deleting asset: {str(e)}"
