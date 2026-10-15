"""GitHub release asset management operations."""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Any

from mcp_server_git.github import _release_format as _fmt
from mcp_server_git.github._paging import clamp_paging
from mcp_server_git.github.client import github_client_context
from mcp_server_git.utils.tool_failure import fail

logger = logging.getLogger(__name__)


def _load_upload_file(path: Path, file_path: str) -> tuple[bytes, str | None]:
    """Return (content, error); content is empty when error is set."""
    if not path.exists():
        return b"", fail(f"❌ File not found: {file_path}")
    if not path.is_file():
        return b"", fail(f"❌ Path is not a file: {file_path}")
    try:
        with open(path, "rb") as f:
            return f.read(), None
    except Exception as read_error:
        return b"", fail(f"❌ Failed to read file {file_path}: {read_error}")


def _guess_content_type(asset_name: str) -> str:
    # Handle corrupt mimetypes database gracefully
    try:
        return mimetypes.guess_type(asset_name)[0] or "application/octet-stream"
    except Exception:
        return "application/octet-stream"


async def _fetch_upload_url(
    client: Any, repo_owner: str, repo_name: str, release_id: int
) -> tuple[str, str | None]:
    """Return (upload_url, error); url has the {?name,label} template removed."""
    response = await client.get(
        f"/repos/{repo_owner}/{repo_name}/releases/{release_id}"
    )

    if response.status == 404:
        return "", fail(
            f"❌ Release {release_id} not found in {repo_owner}/{repo_name}"
        )
    if response.status != 200:
        error_text = await response.text()
        return "", fail(f"❌ Failed to get release: {response.status} - {error_text}")

    release = await response.json()
    upload_url = release.get("upload_url", "")
    if not upload_url:
        return "", fail(f"❌ Release {release_id} has no upload URL")
    return upload_url.split("{")[0], None


async def _upload_error(response: Any) -> str | None:
    if response.status == 422:
        error_data = await response.json()
        error_msg = error_data.get("message", "Validation failed")
        return fail(f"❌ Failed to upload asset: {error_msg}")
    if response.status not in (200, 201):
        error_text = await response.text()
        return fail(f"❌ Failed to upload asset: {response.status} - {error_text}")
    return None


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
        path = Path(file_path)
        file_content, file_error = _load_upload_file(path, file_path)
        if file_error:
            return file_error

        asset_name = name or path.name
        content_type = _guess_content_type(asset_name)

        async with github_client_context() as client:
            # First get the release to get the upload_url
            upload_url, url_error = await _fetch_upload_url(
                client, repo_owner, repo_name, release_id
            )
            if url_error:
                return url_error

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

            upload_error = await _upload_error(response)
            if upload_error:
                return upload_error

            asset = await response.json()
            asset_url = asset.get("browser_download_url", "")
            asset_id = asset.get("id", "")
            asset_size = asset.get("size", 0)

            return f"✅ Asset '{asset_name}' uploaded successfully ({asset_size} bytes)\n🔗 URL: {asset_url}\n📋 Asset ID: {asset_id}"

    except ValueError as auth_error:
        logger.error(f"Authentication error uploading asset: {auth_error}")
        return fail(f"❌ {str(auth_error)}")
    except ConnectionError as conn_error:
        logger.error(f"Connection error uploading asset: {conn_error}")
        return fail(f"❌ Network connection failed: {str(conn_error)}")
    except Exception as e:
        logger.error(f"Unexpected error uploading asset: {e}", exc_info=True)
        return fail(f"❌ Error uploading asset: {str(e)}")


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
    per_page, page = clamp_paging(per_page, page)

    try:
        async with github_client_context() as client:
            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/releases/{release_id}/assets",
                params={"per_page": per_page, "page": page},
            )

            if response.status == 404:
                return fail(
                    f"❌ Release {release_id} not found in {repo_owner}/{repo_name}"
                )
            if response.status != 200:
                error_text = await response.text()
                return fail(
                    f"❌ Failed to list assets: {response.status} - {error_text}"
                )

            assets = await response.json()

            if not assets:
                return f"No assets found for release {release_id}"

            return _fmt.format_asset_list(
                repo_owner, repo_name, release_id, assets, response.headers, page
            )

    except ValueError as auth_error:
        logger.error(f"Authentication error listing assets: {auth_error}")
        return fail(f"❌ {str(auth_error)}")
    except ConnectionError as conn_error:
        logger.error(f"Connection error listing assets: {conn_error}")
        return fail(f"❌ Network connection failed: {str(conn_error)}")
    except Exception as e:
        logger.error(f"Unexpected error listing assets: {e}", exc_info=True)
        return fail(f"❌ Error listing assets: {str(e)}")


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
                return fail(
                    f"❌ Asset {asset_id} not found in {repo_owner}/{repo_name}"
                )
            if response.status != 204:
                error_text = await response.text()
                return fail(
                    f"❌ Failed to delete asset: {response.status} - {error_text}"
                )

            return f"✅ Asset {asset_id} deleted successfully from {repo_owner}/{repo_name}"

    except ValueError as auth_error:
        logger.error(f"Authentication error deleting asset: {auth_error}")
        return fail(f"❌ {str(auth_error)}")
    except ConnectionError as conn_error:
        logger.error(f"Connection error deleting asset: {conn_error}")
        return fail(f"❌ Network connection failed: {str(conn_error)}")
    except Exception as e:
        logger.error(f"Unexpected error deleting asset: {e}", exc_info=True)
        return fail(f"❌ Error deleting asset: {str(e)}")
