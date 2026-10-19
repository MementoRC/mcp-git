"""Lightweight GitHub read-by-ref tools.

Two read-only operations that avoid cloning a whole repository:

- ``github_get_content``: fetch a single file's decoded contents at a ref.
- ``github_resolve_ref``: resolve a branch/tag/short-SHA to its full commit SHA.

Both work on private repos with the server's existing GITHUB_TOKEN.
"""

import base64
import logging
from typing import Any

from ..text_limits import cap_characters
from ..utils.tool_failure import fail
from ._payload import obj_of
from .client import github_client_context
from .job_log_selection import LogSelectionError, resolve_window, select_log_text

logger = logging.getLogger(__name__)


def _format_directory(
    repo_owner: str, repo_name: str, path: str, ref: str | None, entries: list[Any]
) -> str:
    """Render a directory listing."""
    output = [
        f"Directory listing for {repo_owner}/{repo_name}/{path}"
        + (f" @ {ref}" if ref else "")
        + f" ({len(entries)} entries):\n"
    ]
    for entry in entries:
        output.append(
            f"  [{entry.get('type')}] {entry.get('name')} "
            f"({entry.get('size', 0)} bytes)"
        )
    return "\n".join(output)


def _decode_content(data: dict[str, Any], path: str) -> tuple[str | None, str | None]:
    """Return ``(text, None)``, or ``(None, failure_message)`` if unreadable."""
    encoding = data.get("encoding")
    raw = data.get("content", "")
    if encoding == "base64":
        try:
            return base64.b64decode(raw).decode("utf-8", errors="replace"), None
        except Exception as decode_error:  # pragma: no cover - defensive
            return None, fail(f"❌ Failed to decode content: {decode_error}")
    if encoding == "none" or not raw:
        # Files larger than 1MB are not returned by the contents API.
        return None, fail(
            f"❌ File '{path}' is too large for the contents API "
            f"({data.get('size', 0)} bytes). Use the Git blobs API or a raw download. "
            f"(sha: {data.get('sha')})"
        )
    # Unexpected encoding; return the raw payload as-is.
    return raw, None


def _trim_text(
    text: str,
    *,
    grep: str | None,
    start_line: int | None,
    end_line: int | None,
    context_lines: int,
    ignore_case: bool,
) -> str:
    """Select lines with the job-log helpers; output carries 1-based line numbers.

    Raises LogSelectionError on an invalid range or grep pattern.
    """
    lines = text.splitlines()
    total = len(lines)
    start, end, _, _ = resolve_window(
        total, start_line=start_line, end_line=end_line, whole_log_default=True
    )
    if grep is None:
        label = f"showing lines {start}-{end} of {total}"
        body = "\n".join(
            f"{n}: {line}" for n, line in enumerate(lines[start - 1 : end], start)
        )
        body, _ = cap_characters(body, keep_head=True)
        return f"{label}\n\n{body}"

    selection = select_log_text(
        lines,
        start_line=start_line,
        end_line=end_line,
        grep=grep,
        context_lines=context_lines,
        ignore_case=ignore_case,
    )
    if selection.match_count == 0:
        return f"🔍 No lines matched {grep!r} (searched lines {start}-{end} of {total})"
    label = (
        f"{selection.match_count} matching lines for {grep!r} "
        f"within lines {start}-{end} of {total}"
    )
    return f"{label}\n\n{selection.text}"


def _format_file(
    repo_owner: str,
    repo_name: str,
    path: str,
    ref: str | None,
    data: dict[str, Any],
    *,
    grep: str | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
    context_lines: int = 0,
    ignore_case: bool = False,
) -> str:
    """Render a single file's header and decoded text, or a failure."""
    entry_type = data.get("type")
    if entry_type != "file":
        return fail(
            f"❌ Path '{path}' is a {entry_type}, not a file (sha: {data.get('sha')})"
        )

    text, failure = _decode_content(data, path)
    if failure is not None:
        return failure

    header = (
        f"Content of {repo_owner}/{repo_name}/{path}"
        + (f" @ {ref}" if ref else "")
        + f"\nsha: {data.get('sha')} | size: {data.get('size', 0)} bytes\n"
    )
    if grep is None and start_line is None and end_line is None:
        return header + "\n" + str(text)
    try:
        body = _trim_text(
            str(text),
            grep=grep,
            start_line=start_line,
            end_line=end_line,
            context_lines=context_lines,
            ignore_case=ignore_case,
        )
    except LogSelectionError as exc:
        return fail(f"❌ {exc}")
    return header + body


async def github_get_content(
    repo_owner: str,
    repo_name: str,
    path: str,
    ref: str | None = None,
    grep: str | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
    context_lines: int = 0,
    ignore_case: bool = False,
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
        grep: Regex; return only matching lines (numbered), within any range
        start_line: 1-indexed first line to return
        end_line: 1-indexed last line to return (inclusive)
        context_lines: Lines of context either side of a grep match
        ignore_case: Case-insensitive grep
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
                return fail(
                    f"❌ Path '{path}' not found in {repo_owner}/{repo_name}{where}"
                )
            if response.status != 200:
                error_text = await response.text()
                return fail(
                    f"❌ Failed to get content: {response.status} - {error_text}"
                )

            data = await response.json()

            # A directory returns a JSON array of entries.
            if isinstance(data, list):
                return _format_directory(repo_owner, repo_name, path, ref, data)
            return _format_file(
                repo_owner,
                repo_name,
                path,
                ref,
                data,
                grep=grep,
                start_line=start_line,
                end_line=end_line,
                context_lines=context_lines,
                ignore_case=ignore_case,
            )

    except ValueError as auth_error:
        logger.error(f"Authentication error getting content: {auth_error}")
        return fail(f"❌ {str(auth_error)}")
    except ConnectionError as conn_error:
        logger.error(f"Connection error getting content: {conn_error}")
        return fail(f"❌ Network connection failed: {str(conn_error)}")
    except Exception as e:
        logger.error(f"Unexpected error getting content: {e}", exc_info=True)
        return fail(f"❌ Error getting content: {str(e)}")


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
                return fail(f"❌ Ref '{ref}' not found in {repo_owner}/{repo_name}")
            if response.status != 200:
                error_text = await response.text()
                return fail(
                    f"❌ Failed to resolve ref: {response.status} - {error_text}"
                )

            data = await response.json()
            sha = data.get("sha")
            commit = obj_of(data, "commit")
            author = obj_of(commit, "author")
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
        return fail(f"❌ {str(auth_error)}")
    except ConnectionError as conn_error:
        logger.error(f"Connection error resolving ref: {conn_error}")
        return fail(f"❌ Network connection failed: {str(conn_error)}")
    except Exception as e:
        logger.error(f"Unexpected error resolving ref: {e}", exc_info=True)
        return fail(f"❌ Error resolving ref: {str(e)}")
