"""GitHub pull request unified diff retrieval (#211).

``github_get_pr_files`` reports which files a PR touches and by how much, but
never what changed. This module supplies the missing half: the unified diff
itself, fetched in a single request using GitHub's diff media type.

A PR diff carries the same context hazard as a CI job log, so it reuses the
``job_log_selection`` guardrails -- window/grep selection, a character cap,
and ``output_path=`` to keep the content out of the response entirely.
"""

from __future__ import annotations

import logging

from mcp_server_git.github.client import github_client_context
from mcp_server_git.github.diff_sections import (
    filter_sections,
    render_sections,
    split_sections,
)
from mcp_server_git.github.job_log_selection import (
    LogSelectionError,
    build_log_response_lines,
    write_full_log_response,
)

logger = logging.getLogger(__name__)

_PR_DIFF_MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB hard limit (memory protection)
_PR_DIFF_MAX_CHARS_FOR_LLM = 100 * 1024  # 100 KB soft limit (~25k tokens)
_PR_DIFF_SEPARATOR_LENGTH = 60
_DIFF_ACCEPT = "application/vnd.github.v3.diff"
_PATCH_ACCEPT = "application/vnd.github.v3.patch"


def _build_pr_header(
    repo_owner: str, repo_name: str, pr_number: int, pr_data: dict
) -> list[str]:
    """Render the PR identity lines shown before any diff content."""
    output = [
        f"🔀 PR #{pr_number} - {pr_data.get('title', '(no title)')}",
        f"Repository: {repo_owner}/{repo_name}",
    ]
    state = pr_data.get("state")
    if state:
        merged = " (merged)" if pr_data.get("merged") else ""
        output.append(f"State: {state}{merged}")
    base = (pr_data.get("base") or {}).get("ref")
    head = (pr_data.get("head") or {}).get("ref")
    if base and head:
        output.append(f"Branches: {head} → {base}")
    changed_files = pr_data.get("changed_files")
    if changed_files is not None:
        output.append(
            f"Files changed: {changed_files} "
            f"(+{pr_data.get('additions', 0)}, -{pr_data.get('deletions', 0)})"
        )
    if pr_data.get("html_url"):
        output.append(f"URL: {pr_data['html_url']}")
    return output


def _check_pr_response(
    response, pr_number: int, repo_owner: str, repo_name: str
) -> str | None:
    """Translate a bad PR HTTP response into a user-facing error."""
    if response.status == 404:
        return f"❌ PR #{pr_number} not found in {repo_owner}/{repo_name}"
    if response.status == 403:
        return (
            f"❌ Access denied for PR #{pr_number}. "
            "Check repository permissions or API rate limits."
        )
    if response.status == 429:
        return "❌ GitHub API rate limit exceeded. Please wait and try again."
    if response.status != 200:
        return f"❌ Failed to fetch PR #{pr_number}: HTTP {response.status}"
    return None


def _oversize_gate(diff_bytes: int, file_count: int) -> list[str]:
    """Explain why a large diff was withheld, and how to reach it anyway."""
    return [
        f"\n⚠️ Diff is {diff_bytes:,} bytes across {file_count} file(s), over the "
        f"{_PR_DIFF_MAX_CHARS_FOR_LLM:,}-byte inline limit. Nothing was returned "
        "inline to protect LLM context. Re-run with one of:",
        "  • output_path='/abs/path.diff' — write the whole diff to disk "
        "(no content enters context)",
        "  • file_filter='src/*' — limit to matching paths",
        "  • grep='pattern' — return only matching lines, searched diff-wide",
        "  • head_lines / tail_lines / start_line+end_line — an explicit window",
        "  • full_diff=True — return as much as fits under the 100KB cap",
    ]


async def github_get_pr_diff(
    repo_owner: str,
    repo_name: str,
    pr_number: int,
    output_path: str | None = None,
    grep: str | None = None,
    context_lines: int = 0,
    ignore_case: bool = False,
    file_filter: str | None = None,
    head_lines: int | None = None,
    tail_lines: int | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
    full_diff: bool = False,
    as_patch: bool = False,
) -> str:
    """Get the unified diff of a pull request.

    Returns what actually changed, which ``github_get_pr_files`` cannot: that
    tool reports only per-file status and ``(+N, -M)`` counts.

    The complete diff is returned inline when it fits under the 100KB LLM cap.
    Past that cap nothing is returned inline; pass ``output_path``,
    ``file_filter``, ``grep``, a window, or ``full_diff=True`` to say how much
    you want and where it should go.

    Args:
        repo_owner: Repository owner/organization
        repo_name: Repository name
        pr_number: Pull request number
        output_path: Absolute path to write the complete diff to disk instead
            of returning it inline; the response then carries only metadata
        grep: Regex; return only matching lines. Searches the whole diff by
            default, not just a window
        context_lines: Lines of context to keep either side of a grep match
        ignore_case: Case-insensitive grep
        file_filter: Glob; keep only files whose path matches (``*`` also
            matches ``/``, and the basename is tried too)
        head_lines: Return only the first N lines
        tail_lines: Return only the last N lines
        start_line: 1-indexed inclusive start of an explicit window
        end_line: 1-indexed inclusive end of an explicit window
        full_diff: Return the diff despite the inline cap (still trimmed to
            100KB, with the truncation reported)
        as_patch: Fetch the ``.patch`` mbox form, which additionally carries
            commit messages and authorship

    Returns:
        Formatted string with PR information and diff content (or, when
        output_path is given, PR information and write metadata only).
        Every response reports total lines, total bytes, and whether the
        returned content was truncated. Only one of head_lines, tail_lines,
        or start_line/end_line may be given; grep composes with any of them.
    """
    logger.debug(f"🔍 Fetching diff for PR #{pr_number} in {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            pr_response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}"
            )
            pr_error = _check_pr_response(pr_response, pr_number, repo_owner, repo_name)
            if pr_error is not None:
                return pr_error

            pr_data = await pr_response.json()
            output = _build_pr_header(repo_owner, repo_name, pr_number, pr_data)

            diff_response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}",
                accept=_PATCH_ACCEPT if as_patch else _DIFF_ACCEPT,
            )
            diff_error = _check_pr_response(
                diff_response, pr_number, repo_owner, repo_name
            )
            if diff_error is not None:
                output.append(diff_error)
                return "\n".join(output)

            diff_text = await diff_response.text()
            if not diff_text.strip():
                output.append("\n📭 Diff is empty (no file changes)")
                return "\n".join(output)

            _preamble, sections = split_sections(diff_text)
            file_count = len(sections)

            if file_filter is not None:
                kept = filter_sections(sections, file_filter)
                output.append(
                    f"🔎 file_filter {file_filter!r}: "
                    f"{len(kept)} of {file_count} file(s)"
                )
                if not kept:
                    output.append(f"🔍 No files matched {file_filter!r}")
                    return "\n".join(output)
                diff_text = render_sections(kept)

            if output_path is not None:
                return write_full_log_response(
                    output, output_path, diff_text, noun="diff"
                )

            windowed = any(
                selector is not None
                for selector in (head_lines, tail_lines, start_line, end_line)
            )
            asked_for_less = (
                windowed or grep is not None or file_filter is not None or full_diff
            )
            if not asked_for_less and len(diff_text) > _PR_DIFF_MAX_CHARS_FOR_LLM:
                output.extend(_oversize_gate(len(diff_text), file_count))
                return "\n".join(output)

            try:
                output.extend(
                    build_log_response_lines(
                        diff_text,
                        tail_lines=tail_lines,
                        full_log=not windowed,
                        head_lines=head_lines,
                        start_line=start_line,
                        end_line=end_line,
                        grep=grep,
                        context_lines=context_lines,
                        ignore_case=ignore_case,
                        size_limit=_PR_DIFF_MAX_SIZE_BYTES,
                        char_limit=_PR_DIFF_MAX_CHARS_FOR_LLM,
                        separator_length=_PR_DIFF_SEPARATOR_LENGTH,
                        body_label="Diff",
                        clamp_noun="diff",
                    )
                )
            except LogSelectionError as exc:
                return f"❌ {exc}"

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error getting PR diff: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error getting PR diff: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error getting PR diff: {e}", exc_info=True)
        return f"❌ Error getting PR diff: {str(e)}"
