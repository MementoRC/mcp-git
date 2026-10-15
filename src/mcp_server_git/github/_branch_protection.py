"""Branch protection payload building and report formatting (pure, no I/O)."""

from __future__ import annotations

from typing import Any

from mcp_server_git.github._payload import obj_of, provided_fields
from mcp_server_git.github.check_markers import bool_marker

_OTHER_SETTINGS = (
    ("Required Linear History", "required_linear_history"),
    ("Allow Force Pushes", "allow_force_pushes"),
    ("Allow Deletions", "allow_deletions"),
    ("Required Conversation Resolution", "required_conversation_resolution"),
    ("Lock Branch", "lock_branch"),
)


def status_checks_payload(
    strict: bool | None, contexts: list[str] | None
) -> dict[str, Any] | None:
    """Required status checks rule, or ``None`` when neither input is given."""
    if strict is None and contexts is None:
        return None
    return {"strict": strict or False, "contexts": contexts or []}


def pr_reviews_payload(required: bool | None, **options: Any) -> dict[str, Any] | None:
    """Required PR reviews rule; ``None`` unless required and non-empty."""
    if not required:
        return None
    return provided_fields(**options) or None


def restrictions_payload(
    restrict: bool | None, users: list[str] | None, teams: list[str] | None
) -> dict[str, Any] | None:
    """Push restrictions rule, or ``None`` when pushes are not restricted."""
    if not restrict:
        return None
    return {"users": users or [], "teams": teams or []}


def format_status_checks(data: dict[str, Any]) -> list[str]:
    """Report lines for the required status checks rule."""
    checks = data.get("required_status_checks")
    if not checks:
        return [f"{bool_marker(False)} Required Status Checks: Not configured"]
    contexts = checks.get("contexts", [])
    return [
        "✅ Required Status Checks:",
        f"   Strict: {bool_marker(checks.get('strict'))}",
        f"   Contexts: {', '.join(contexts)}" if contexts else "   Contexts: (none)",
    ]


def format_pr_reviews(data: dict[str, Any]) -> list[str]:
    """Report lines for the required pull request reviews rule."""
    reviews = data.get("required_pull_request_reviews")
    if not reviews:
        return [f"\n{bool_marker(False)} Required Pull Request Reviews: Not configured"]
    return [
        "\n✅ Required Pull Request Reviews:",
        f"   Dismiss Stale Reviews: {bool_marker(reviews.get('dismiss_stale_reviews'))}",
        f"   Require Code Owner Reviews: {bool_marker(reviews.get('require_code_owner_reviews'))}",
        f"   Required Approving Review Count: {reviews.get('required_approving_review_count', 0)}",
        f"   Require Last Push Approval: {bool_marker(reviews.get('require_last_push_approval'))}",
    ]


def format_restrictions(data: dict[str, Any]) -> list[str]:
    """Report lines for the push restrictions rule."""
    restrictions = data.get("restrictions")
    if not restrictions:
        return ["\n🔓 Push Restrictions: Not configured"]
    lines = ["\n🔒 Push Restrictions: Enabled"]
    if restrictions.get("users"):
        lines.append(
            f"   Users: {', '.join(u['login'] for u in restrictions['users'])}"
        )
    if restrictions.get("teams"):
        lines.append(f"   Teams: {', '.join(t['slug'] for t in restrictions['teams'])}")
    return lines


def format_branch_protection(
    repo_owner: str, repo_name: str, branch: str, data: dict[str, Any]
) -> str:
    """Render the full branch protection report."""
    output = [f"Branch Protection for {repo_owner}/{repo_name}:{branch}\n"]
    output.extend(format_status_checks(data))
    output.extend(format_pr_reviews(data))
    if data.get("enforce_admins"):
        output.append(
            f"\n👮 Enforce Admins: {bool_marker(data['enforce_admins'].get('enabled'))}"
        )
    output.extend(format_restrictions(data))
    output.append("\n📋 Other Settings:")
    output.extend(
        f"   {label}: {bool_marker(obj_of(data, key).get('enabled'))}"
        for label, key in _OTHER_SETTINGS
    )
    return "\n".join(output)
