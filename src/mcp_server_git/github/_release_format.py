"""Pure formatters for GitHub release and release-asset output (no I/O)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

PAGE_FOOTER = "📄 Page {page} (use page parameter to see more)"


def flag_labels(draft: Any, prerelease: Any) -> list[str]:
    """Return the status labels for the draft / pre-release flags."""
    labels = []
    if draft:
        labels.append("draft")
    if prerelease:
        labels.append("pre-release")
    return labels


def page_footer(headers: Mapping[str, str], page: int) -> list[str]:
    """Return the pagination footer lines, empty when there is no more to see."""
    link_header = headers.get("Link", "")
    if "next" in link_header or page > 1:
        return [PAGE_FOOTER.format(page=page)]
    return []


def _release_header_lines(release: dict[str, Any]) -> list[str]:
    lines = [
        f"📦 Tag: {release.get('tag_name')}",
        f"📋 Name: {release.get('name') or '(none)'}",
    ]
    status = flag_labels(release.get("draft"), release.get("prerelease"))
    if status:
        lines.append(f"🏷️  Status: {', '.join(status)}")
    lines.append(f"🔗 URL: {release.get('html_url')}")
    lines.append(f"📅 Created: {release.get('created_at')}")
    lines.append(f"📅 Published: {release.get('published_at') or 'Not published'}")
    return lines


def _release_asset_lines(assets: list[dict[str, Any]]) -> list[str]:
    if not assets:
        return ["\n📎 Assets: None"]
    lines = [f"\n📎 Assets ({len(assets)}):"]
    for asset in assets:
        lines.append(f"   • {asset.get('name')} ({asset.get('size')} bytes)")
    return lines


def format_release_details(
    repo_owner: str, repo_name: str, release: dict[str, Any]
) -> str:
    """Format a single release for ``github_get_release``."""
    output = [f"Release Information for {repo_owner}/{repo_name}:\n"]
    output.extend(_release_header_lines(release))

    author = release.get("author", {})
    if author:
        output.append(f"👤 Author: {author.get('login')}")

    body = release.get("body")
    if body:
        output.append(f"\n📝 Description:\n{body}")

    output.extend(_release_asset_lines(release.get("assets", [])))
    return "\n".join(output)


def format_release_entry(release: dict[str, Any]) -> list[str]:
    """Format one release block for ``github_list_releases``."""
    tag = release.get("tag_name")
    name = release.get("name") or tag
    created = release.get("created_at", "")[:10]  # Just the date

    status = flag_labels(release.get("draft"), release.get("prerelease"))
    status_str = f" [{', '.join(status)}]" if status else ""

    return [
        f"📦 {tag}: {name}{status_str}",
        f"   📅 Created: {created}",
        f"   🔗 {release.get('html_url')}",
        "",
    ]


def format_release_list(
    repo_owner: str,
    repo_name: str,
    releases: list[dict[str, Any]],
    headers: Mapping[str, str],
    page: int,
) -> str:
    """Format the release listing including the pagination footer."""
    output = [f"Releases for {repo_owner}/{repo_name}:\n"]
    for release in releases:
        output.extend(format_release_entry(release))
    output.extend(page_footer(headers, page))
    return "\n".join(output)


def format_asset_size(size: int) -> str:
    """Format a byte count as B / KB / MB."""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def format_asset_entry(asset: dict[str, Any]) -> list[str]:
    """Format one asset block for ``github_list_release_assets``."""
    size_str = format_asset_size(asset.get("size", 0))
    return [
        f"📎 {asset.get('name')}",
        f"   ID: {asset.get('id')}",
        f"   Size: {size_str}",
        f"   Type: {asset.get('content_type', 'unknown')}",
        f"   Downloads: {asset.get('download_count', 0)}",
        f"   URL: {asset.get('browser_download_url')}",
        "",
    ]


def format_asset_list(
    repo_owner: str,
    repo_name: str,
    release_id: int,
    assets: list[dict[str, Any]],
    headers: Mapping[str, str],
    page: int,
) -> str:
    """Format the asset listing including the pagination footer."""
    output = [f"Assets for Release {release_id} in {repo_owner}/{repo_name}:\n"]
    for asset in assets:
        output.extend(format_asset_entry(asset))
    output.extend(page_footer(headers, page))
    return "\n".join(output)
