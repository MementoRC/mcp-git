"""Pure formatters for GitHub issue operations (no I/O)."""

from __future__ import annotations

from typing import Any

from mcp_server_git.github._payload import login_of

_STATE_MARKERS = {"open": "🟢", "closed": "🔴"}


def state_marker(state: Any) -> str:
    """Return the emoji marker for an issue state ('❓' when unknown)."""
    return _STATE_MARKERS.get(state, "❓")


def _label_assignee_lines(issue: dict[str, Any], indent: str) -> list[str]:
    lines: list[str] = []
    if issue.get("labels"):
        names = [label["name"] for label in issue["labels"]]
        lines.append(f"{indent}Labels: {', '.join(names)}")
    if issue.get("assignees"):
        logins = [assignee["login"] for assignee in issue["assignees"]]
        lines.append(f"{indent}Assignees: {', '.join(logins)}")
    return lines


def _summary_head_lines(issue: dict[str, Any]) -> list[str]:
    marker = state_marker(issue.get("state"))
    return [
        f"{marker} #{issue['number']}: {issue['title']}",
        f"   Author: {login_of(issue)}",
    ]


def format_issue_list(
    state: str, repo_owner: str, repo_name: str, issues: list[dict[str, Any]]
) -> str:
    """Format list_issues results, skipping pull requests."""
    output = [f"{state.title()} Issues for {repo_owner}/{repo_name}:\n"]
    for issue in issues:
        if issue.get("pull_request"):
            continue
        output.extend(_summary_head_lines(issue))
        output.extend(_label_assignee_lines(issue, "   "))
        output.append(f"   Created: {issue.get('created_at', 'N/A')}")
        output.append("")
    return "\n".join(output)


def _search_issue_lines(issue: dict[str, Any]) -> list[str]:
    lines = _summary_head_lines(issue)
    lines.extend(_label_assignee_lines(issue, "   "))
    if issue.get("milestone"):
        lines.append(f"   Milestone: {issue['milestone'].get('title', 'N/A')}")
    lines.append(f"   Created: {issue.get('created_at', 'N/A')}")
    lines.append(f"   Score: {issue.get('score', 'N/A')}")
    lines.append("")
    return lines


def format_search_results(
    query: str,
    repo_owner: str,
    repo_name: str,
    page: int,
    per_page: int,
    issues: list[dict[str, Any]],
    total_count: int,
) -> str:
    """Format search_issues results with pagination info."""
    output = [f"Search Results for '{query}' in {repo_owner}/{repo_name}:\n"]
    output.append(f"Found {total_count} total issues (showing page {page})\n")
    for issue in issues:
        if issue.get("pull_request"):
            continue
        output.extend(_search_issue_lines(issue))

    max_results = min(1000, total_count)  # GitHub limits search to 1000 results
    if total_count > len(issues):
        max_page = (max_results + per_page - 1) // per_page
        output.append(
            f"📄 Page {page} of {max_page} (max {max_results} results from GitHub)"
        )
    return "\n".join(output)


def _issue_meta_lines(issue: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if issue.get("closed_at"):
        lines.append(f"Closed: {issue['closed_at']}")
    lines.extend(_label_assignee_lines(issue, ""))
    if issue.get("milestone"):
        lines.append(f"Milestone: {issue['milestone'].get('title', 'N/A')}")
    lines.append(f"Comments: {issue.get('comments', 0)}")
    lines.append(f"URL: {issue.get('html_url', 'N/A')}")
    return lines


def _issue_body_lines(issue: dict[str, Any], max_body_chars: int | None) -> list[str]:
    body = issue.get("body") or "(No description provided)"
    lines = ["", "Description:", "-" * 40]
    if max_body_chars and max_body_chars > 0 and len(body) > max_body_chars:
        lines.append(
            body[:max_body_chars] + f"\n\n... (truncated: showing {max_body_chars} "
            f"of {len(body)} chars)"
        )
    else:
        lines.append(body)
    return lines


def format_issue_detail(issue: dict[str, Any], max_body_chars: int | None) -> str:
    """Format a single issue for get_issue (body truncated only on request)."""
    marker = state_marker(issue.get("state"))
    output = [
        f"Issue #{issue['number']}: {issue['title']}",
        f"State: {marker} {issue.get('state', 'unknown')}",
        f"Author: {login_of(issue)}",
        f"Created: {issue.get('created_at', 'N/A')}",
        f"Updated: {issue.get('updated_at', 'N/A')}",
    ]
    output.extend(_issue_meta_lines(issue))
    output.extend(_issue_body_lines(issue, max_body_chars))
    return "\n".join(output)
