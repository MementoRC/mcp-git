"""Independent checks that make up ``github_get_security_analysis``.

Each check takes an open GitHub client, appends its report lines to
``output`` and returns whether it succeeded. A check never raises, so one
failing check cannot hide the others.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp_server_git.github._payload import obj_of
from mcp_server_git.github.check_markers import bool_marker, enabled_line

logger = logging.getLogger(__name__)

_ANALYSIS_FEATURES = (
    ("Secret Scanning", "secret_scanning"),
    ("Secret Scanning Push Protection", "secret_scanning_push_protection"),
    ("Dependabot Security Updates", "dependabot_security_updates"),
)


async def check_vulnerability_alerts(
    client: Any, repo_owner: str, repo_name: str, output: list[str]
) -> bool:
    """Report whether Dependabot vulnerability alerts are enabled."""
    try:
        response = await client.get(
            f"/repos/{repo_owner}/{repo_name}/vulnerability-alerts"
        )
        if response.status == 204:
            output.append("✅ Vulnerability Alerts (Dependabot): ENABLED")
        elif response.status == 404:
            output.append(enabled_line("Vulnerability Alerts (Dependabot)", False))
        else:
            output.append(
                f"⚠️ Vulnerability Alerts: Unable to determine (HTTP {response.status})"
            )
        return True
    except Exception as e:
        logger.warning(f"Failed to check vulnerability alerts: {e}")
        output.append(f"⚠️ Vulnerability Alerts: Check failed ({e})")
        return False


async def check_automated_security_fixes(
    client: Any, repo_owner: str, repo_name: str, output: list[str]
) -> bool:
    """Report whether Dependabot security updates are enabled or paused."""
    try:
        response = await client.get(
            f"/repos/{repo_owner}/{repo_name}/automated-security-fixes"
        )
        if response.status != 200:
            output.append(
                f"{bool_marker(False)} Automated Security Fixes: DISABLED or unavailable"
            )
            return True
        data = await response.json()
        enabled = data.get("enabled", False)
        status = "ENABLED" if enabled else "DISABLED"
        if data.get("paused", False):
            status += " (PAUSED)"
        output.append(f"{bool_marker(enabled)} Automated Security Fixes: {status}")
        return True
    except Exception as e:
        logger.warning(f"Failed to check automated security fixes: {e}")
        output.append(f"⚠️ Automated Security Fixes: Check failed ({e})")
        return False


def _append_repo_security(repo_data: dict[str, Any], output: list[str]) -> None:
    """Append the repository's security-related settings to ``output``."""
    output.append("\n📋 Repository Security Settings:")
    output.append(f"   Visibility: {repo_data.get('visibility', 'unknown')}")
    output.append(f"   Private: {bool_marker(repo_data.get('private'))}")
    output.append(f"   Archived: {bool_marker(repo_data.get('archived'))}")

    security_policy = obj_of(repo_data, "security_and_analysis")
    if not security_policy:
        return
    output.append("\n🔐 Security & Analysis Features:")
    for label, key in _ANALYSIS_FEATURES:
        feature = obj_of(security_policy, key)
        output.append(enabled_line(label, feature.get("status") == "enabled", "   "))


async def check_repo_security_settings(
    client: Any, repo_owner: str, repo_name: str, output: list[str]
) -> bool:
    """Report security settings from the repository metadata."""
    try:
        response = await client.get(f"/repos/{repo_owner}/{repo_name}")
        if response.status == 200:
            _append_repo_security(await response.json(), output)
        else:
            output.append(
                f"\n⚠️ Repository Settings: Unable to fetch (HTTP {response.status})"
            )
        return True
    except Exception as e:
        logger.warning(f"Failed to get repository settings: {e}")
        output.append(f"\n⚠️ Repository Settings: Check failed ({e})")
        return False


_CHECKS = (
    check_vulnerability_alerts,
    check_automated_security_fixes,
    check_repo_security_settings,
)


async def run_security_checks(
    client: Any, repo_owner: str, repo_name: str, output: list[str]
) -> None:
    """Run every check in order, appending to ``output`` plus a failure note."""
    failed = 0
    for check in _CHECKS:
        if not await check(client, repo_owner, repo_name, output):
            failed += 1

    if failed > 0:
        output.append(f"\n⚠️ Note: {failed} of {len(_CHECKS)} checks failed")
