"""Pure output formatting for the GitHub PR ops (issue #264).

Everything here turns already-fetched payloads into output lines; nothing
performs I/O, so none of it is a patch target. The ops modules (``pr``,
``pr_actions``) own the client calls and error handling.
"""

from __future__ import annotations

from typing import Any

from mcp_server_git.github._payload import body_preview, login_of, obj_of
from mcp_server_git.github.check_markers import check_marker

_BOT_TEMPLATE_MARKER = "${{"
_MAX_FILES_SHOWN = 10
_MAX_REVIEWS_SHOWN = 5
_REVIEW_MARKERS: dict[str | None, str] = {
    "APPROVED": "✅",
    "CHANGES_REQUESTED": "❌",
    "COMMENTED": "💬",
}


def merged_line(pr_data: dict) -> str | None:
    """Render merged-ness for a closed PR; None while it is still open.

    GitHub's ``state`` is only ever "open" or "closed", so whether a PR was
    merged has to come from ``merged`` / ``merged_at`` (issue #239). For an
    open PR the question is premature, so nothing is rendered.
    """
    if pr_data.get("state") != "closed":
        return None
    if not (pr_data.get("merged") or pr_data.get("merged_at")):
        return "Merged: no"
    parts: list[str] = []
    if pr_data.get("merged_at"):
        parts.append(str(pr_data["merged_at"]))
    login = (pr_data.get("merged_by") or {}).get("login")
    if login:
        parts.append(f"by {login}")
    sha = pr_data.get("merge_commit_sha")
    if sha:
        parts.append(str(sha)[:7])
    detail = f" ({', '.join(parts)})" if parts else ""
    return f"Merged: yes{detail}"


def pr_state_marker(pr: dict) -> str:
    """Per-PR marker distinguishing merged from closed-but-unmerged (#239).

    The list endpoint carries ``merged_at`` but no ``merged`` bool, and REST
    never reports ``state == "merged"`` — so the old three-key state map could
    never emit its purple marker and every closed PR rendered red.
    """
    state = pr.get("state")
    if state == "open":
        return "🟢"
    if pr.get("merged") or pr.get("merged_at"):
        return "🟣"
    if state == "closed":
        return "🔴"
    return "❓"


def format_check_run(run: dict) -> list[str]:
    """Render one check run as output lines, ending with a blank line."""
    lines = [
        f"{check_marker(run)} {run['name']}",
        f"   Status: {run['status']}",
    ]
    if run.get("conclusion"):
        lines.append(f"   Conclusion: {run['conclusion']}")
    lines.append(f"   Started: {run.get('started_at', 'N/A')}")
    if run.get("completed_at"):
        lines.append(f"   Completed: {run['completed_at']}")
    if run.get("html_url"):
        lines.append(f"   URL: {run['html_url']}")
    lines.append("")
    return lines


def failing_run_header(run: dict) -> list[str]:
    """Name, conclusion and timing lines for a failing check run."""
    return [
        f"❌ {run['name']}",
        f"   Conclusion: {run['conclusion']}",
        f"   Started: {run.get('started_at', 'N/A')}",
        f"   Completed: {run.get('completed_at', 'N/A')}",
    ]


def annotation_lines(annotations: list[dict]) -> list[str]:
    """Render up to the first five annotations; empty when there are none."""
    if not annotations:
        return []
    lines = ["   Annotations:"]
    for annotation in annotations[:5]:
        lines.append(
            f"     • {annotation.get('title', 'Error')}: {annotation.get('message', 'No message')}"
        )
        if annotation.get("path"):
            lines.append(
                f"       File: {annotation['path']} (line {annotation.get('start_line', 'unknown')})"
            )
    return lines


def format_pr_summary(
    pr_number: int, pr_data: dict, full_body: bool = False
) -> list[str]:
    """Header, identity, description and URL lines for ``github_get_pr_details``.

    ``full_body`` returns the description verbatim instead of the shared
    preview, so callers can safely round-trip it through a PR body edit (#320).
    """
    output = [f"Pull Request #{pr_number}:\n"]
    output.append(f"Title: {pr_data.get('title', 'N/A')}")
    output.append(f"State: {pr_data.get('state', 'N/A')}")
    merged = merged_line(pr_data)
    if merged:
        output.append(merged)
    output.append(f"Author: {login_of(pr_data)}")
    output.append(f"Base: {obj_of(pr_data, 'base').get('ref', 'N/A')}")
    head = obj_of(pr_data, "head")
    output.append(f"Head: {head.get('ref', 'N/A')}")
    if head.get("sha"):
        output.append(f"Head SHA: {head['sha']}")
    output.append(f"Created: {pr_data.get('created_at', 'N/A')}")
    output.append(f"Updated: {pr_data.get('updated_at', 'N/A')}")

    body = pr_data.get("body")
    if body:
        output.append(f"\nDescription:\n{body if full_body else body_preview(body)}")
    if pr_data.get("html_url"):
        output.append(f"\nURL: {pr_data['html_url']}")
    return output


def format_files_section(files_data: list[dict]) -> list[str]:
    """Render the first ten changed files; empty when there are none."""
    if not files_data:
        return []
    lines = [f"\nFiles ({len(files_data)}):"]
    for file in files_data[:_MAX_FILES_SHOWN]:
        status = file.get("status") or "N/A"
        lines.append(
            f"  {status[0].upper()} {file.get('filename') or 'N/A'} "
            f"(+{file.get('additions') or 0}, -{file.get('deletions') or 0})"
        )
    if len(files_data) > _MAX_FILES_SHOWN:
        lines.append(f"  ... and {len(files_data) - _MAX_FILES_SHOWN} more files")
    return lines


def format_reviews_section(reviews_data: list[dict]) -> list[str]:
    """Render the last five reviews; empty when there are none."""
    if not reviews_data:
        return []
    lines = [f"\nReviews ({len(reviews_data)}):"]
    for review in reviews_data[-_MAX_REVIEWS_SHOWN:]:
        marker = _REVIEW_MARKERS.get(review.get("state"), "❓")
        lines.append(f"  {marker} {login_of(review)}: {review.get('state', 'N/A')}")
    return lines


def select_rendered_body(comment: dict[str, Any]) -> str:
    """Pick the most useful body field from a GitHub comment object.

    GitHub renders bot template placeholders (e.g. ``${{ metadata.patch }}``)
    server-side only when the response includes ``body_html`` / ``body_text``
    (requested via ``application/vnd.github.full+json``). When the markdown
    ``body`` contains template syntax we fall back to the rendered ``body_text``;
    otherwise we keep the markdown ``body`` to preserve links and formatting.
    """
    body = (comment.get("body") or "").strip()
    if _BOT_TEMPLATE_MARKER in body:
        body_text = (comment.get("body_text") or "").strip()
        if body_text:
            return body_text
    return body


def format_issue_comment(comment: dict[str, Any]) -> list[str]:
    """Render one top-level PR conversation comment."""
    author = login_of(comment, default="unknown")
    created = comment.get("created_at", "")
    body = select_rendered_body(comment)
    comment_id = comment.get("id", "")
    return [f"  #{comment_id} by {author} ({created}):", f"    {body}\n"]


def format_review_comment(comment: dict[str, Any]) -> list[str]:
    """Render one inline review comment, ending with a blank line."""
    author = login_of(comment, default="unknown")
    created = comment.get("created_at", "")
    body = select_rendered_body(comment)
    path = comment.get("path", "")
    line = comment.get("line") or comment.get("original_line", "")
    comment_id = comment.get("id", "")
    in_reply_to = comment.get("in_reply_to_id", "")
    reply_info = f" (reply to #{in_reply_to})" if in_reply_to else ""
    diff_hunk = (comment.get("diff_hunk") or "").strip()

    lines = [
        f"  #{comment_id} by {author} ({created}){reply_info}:",
        f"    File: {path}:{line}",
        f"    {body}",
    ]
    if diff_hunk:
        lines.extend(["    Diff hunk:", "    ```diff", diff_hunk, "    ```"])
    lines.append("")
    return lines
