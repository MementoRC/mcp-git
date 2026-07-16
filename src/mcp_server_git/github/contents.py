"""Lightweight GitHub read-by-ref tools.

Two read-only operations that avoid cloning a whole repository:

- ``github_get_content``: fetch a single file's decoded contents at a ref.
- ``github_resolve_ref``: resolve a branch/tag/short-SHA to its full commit SHA.

Both work on private repos with the server's existing GITHUB_TOKEN.
"""

import base64
import logging

from .client import github_client_context

logger = logging.getLogger(__name__)


async def github_get_content(
    repo_owner: str,
    repo_name: str,
    path: str,
    ref: str | None = None,
) -> str:
    """Get a single file's contents from a GitHub repo at an optional ref.

    Wraps GET /repos/{owner}/{repo}/contents/{path}?ref={ref}. Decodes
    base64-encoded file content and reports the blob sha and size. For a
    directory path, lists the entries instead.

    Args:
        repo_owner: Repository owner
        repo_name: Repository name
        path: File path within the repo (no leading slash required)
        ref: Optional branch, tag, or commit SHA (defaults to the repo's
            default branch)
    """
    logger.debug(
        f"🔍 Getting content for {repo_owner}/{repo_name}/{path}"
        + (f" @ {ref}" if ref else "")
    )
    try:
        async with github_client_context() as client:
            endpoint = f"/repos/{repo_owner}/{repo_name}/contents/{path.lstrip('/')}"
            if ref:
                endpoint += f"?ref={ref}"

            response = await client.get(endpoint)

            if response.status == 404:
                where = f" at ref '{ref}'" if ref else ""
                return (
                    f"❌ Path '{path}' not found in "
                    f"{repo_owner}/{repo_name}{where}"
                )
            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to get content: {response.status} - {error_text}"

            data = await response.json()

            # A directory returns a JSON array of entries.
            if isinstance(data, list):
                output = [
                    f"Directory listing for {repo_owner}/{repo_name}/{path}"
                    + (f" @ {ref}" if ref else "")
                    + f" ({len(data)} entries):\n"
                ]
                for entry in data:
                    output.append(
                        f"  [{entry.get('type')}] {entry.get('name')} "
                        f"({entry.get('size', 0)} bytes)"
                    )
                return "\n".join(output)

            entry_type = data.get("type")
            if entry_type != "file":
                return (
                    f"❌ Path '{path}' is a {entry_type}, not a file "
                    f"(sha: {data.get('sha')})"
                )

            sha = data.get("sha")
            size = data.get("size", 0)
            encoding = data.get("encoding")
            raw = data.get("content", "")

            if encoding == "base64":
                try:
                    text = base64.b64decode(raw).decode("utf-8", errors="replace")
                except Exception as decode_error:  # pragma: no cover - defensive
                    return f"❌ Failed to decode content: {decode_error}"
            elif encoding == "none" or not raw:
                # Files larger than 1MB are not returned by the contents API.
                return (
                    f"❌ File '{path}' is too large for the contents API "
                    f"({size} bytes). Use the Git blobs API or a raw download. "
                    f"(sha: {sha})"
                )
            else:
                # Unexpected encoding; return the raw payload as-is.
                text = raw

            header = (
                f"Content of {repo_owner}/{repo_name}/{path}"
                + (f" @ {ref}" if ref else "")
                + f"\nsha: {sha} | size: {size} bytes\n"
            )
            return header + "\n" + text

    except ValueError as auth_error:
        logger.error(f"Authentication error getting content: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error getting content: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error getting content: {e}", exc_info=True)
        return f"❌ Error getting content: {str(e)}"


async def github_resolve_ref(
    repo_owner: str,
    repo_name: str,
    ref: str,
) -> str:
    """Resolve a branch, tag, or short SHA to its full commit SHA.

    Wraps GET /repos/{owner}/{repo}/commits/{ref}, which resolves branches,
    tags (including annotated tags), and short SHAs to the full commit SHA.

    Args:
        repo_owner: Repository owner
        repo_name: Repository name
        ref: Branch name, tag name, or (short/full) commit SHA
    """
    logger.debug(f"🔍 Resolving ref '{ref}' for {repo_owner}/{repo_name}")
    try:
        async with github_client_context() as client:
            endpoint = f"/repos/{repo_owner}/{repo_name}/commits/{ref}"
            response = await client.get(endpoint)

            if response.status in (404, 422):
                return f"❌ Ref '{ref}' not found in {repo_owner}/{repo_name}"
            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to resolve ref: {response.status} - {error_text}"

            data = await response.json()
            sha = data.get("sha")
            commit = data.get("commit", {})
            author = commit.get("author", {})
            message = (commit.get("message") or "").split("\n", 1)[0]

            output = [
                f"Ref '{ref}' in {repo_owner}/{repo_name}:",
                f"🔑 Commit SHA: {sha}",
            ]
            if author:
                output.append(
                    f"👤 Author: {author.get('name')} <{author.get('email')}>"
                )
                output.append(f"📅 Date: {author.get('date')}")
            if message:
                output.append(f"📝 Message: {message}")
            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error resolving ref: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error resolving ref: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error resolving ref: {e}", exc_info=True)
        return f"❌ Error resolving ref: {str(e)}"
