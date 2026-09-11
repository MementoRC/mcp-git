"""GitHub security operations - vulnerability alerts, security fixes, analysis."""

from __future__ import annotations

import logging

from mcp_server_git.github.client import github_client_context

logger = logging.getLogger(__name__)


async def github_get_vulnerability_alerts(
    repo_owner: str,
    repo_name: str,
) -> str:
    """Check if vulnerability alerts (Dependabot alerts) are enabled."""
    logger.debug(f"🔍 Getting vulnerability alerts status for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/vulnerability-alerts"
            )

            if response.status == 204:
                return f"✅ Vulnerability alerts (Dependabot) are ENABLED for {repo_owner}/{repo_name}"
            elif response.status == 404:
                return f"❌ Vulnerability alerts (Dependabot) are DISABLED for {repo_owner}/{repo_name}"
            else:
                error_text = await response.text()
                return f"❌ Failed to check vulnerability alerts: {response.status} - {error_text}"

    except ValueError as auth_error:
        logger.error(
            f"Authentication error checking vulnerability alerts: {auth_error}"
        )
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error checking vulnerability alerts: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error checking vulnerability alerts: {e}", exc_info=True
        )
        return f"❌ Error checking vulnerability alerts: {str(e)}"


async def github_enable_vulnerability_alerts(
    repo_owner: str,
    repo_name: str,
) -> str:
    """Enable vulnerability alerts (Dependabot alerts) for a repository."""
    logger.debug(f"🚀 Enabling vulnerability alerts for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            response = await client.put(
                f"/repos/{repo_owner}/{repo_name}/vulnerability-alerts"
            )

            if response.status == 204:
                logger.info(
                    f"✅ Enabled vulnerability alerts for {repo_owner}/{repo_name}"
                )
                return f"✅ Successfully enabled vulnerability alerts (Dependabot) for {repo_owner}/{repo_name}"
            else:
                error_text = await response.text()
                return f"❌ Failed to enable vulnerability alerts: {response.status} - {error_text}"

    except ValueError as auth_error:
        logger.error(
            f"Authentication error enabling vulnerability alerts: {auth_error}"
        )
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error enabling vulnerability alerts: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error enabling vulnerability alerts: {e}", exc_info=True
        )
        return f"❌ Error enabling vulnerability alerts: {str(e)}"


async def github_disable_vulnerability_alerts(
    repo_owner: str,
    repo_name: str,
) -> str:
    """Disable vulnerability alerts (Dependabot alerts) for a repository."""
    logger.debug(f"🚀 Disabling vulnerability alerts for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            response = await client.delete(
                f"/repos/{repo_owner}/{repo_name}/vulnerability-alerts"
            )

            if response.status == 204:
                logger.info(
                    f"✅ Disabled vulnerability alerts for {repo_owner}/{repo_name}"
                )
                return f"✅ Successfully disabled vulnerability alerts (Dependabot) for {repo_owner}/{repo_name}"
            else:
                error_text = await response.text()
                return f"❌ Failed to disable vulnerability alerts: {response.status} - {error_text}"

    except ValueError as auth_error:
        logger.error(
            f"Authentication error disabling vulnerability alerts: {auth_error}"
        )
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error disabling vulnerability alerts: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error disabling vulnerability alerts: {e}", exc_info=True
        )
        return f"❌ Error disabling vulnerability alerts: {str(e)}"


async def github_get_required_signatures(
    repo_owner: str,
    repo_name: str,
    branch: str,
) -> str:
    """Check if required signatures are enabled on a protected branch."""
    logger.debug(
        f"🔍 Getting required signatures status for {repo_owner}/{repo_name}#{branch}"
    )

    try:
        async with github_client_context() as client:
            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/branches/{branch}/protection/required_signatures"
            )

            if response.status == 200:
                data = await response.json()
                enabled = data.get("enabled", False)
                return f"{'✅' if enabled else '❌'} Required signatures: {'enabled' if enabled else 'disabled'} on {repo_owner}/{repo_name}#{branch}"
            elif response.status == 404:
                return f"❌ Branch protection or branch not found: {repo_owner}/{repo_name}#{branch}"
            else:
                error_text = await response.text()
                return f"❌ Failed to check required signatures: {response.status} - {error_text}"

    except ValueError as auth_error:
        logger.error(f"Authentication error checking required signatures: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error checking required signatures: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error checking required signatures: {e}", exc_info=True
        )
        return f"❌ Error checking required signatures: {str(e)}"


async def github_enable_required_signatures(
    repo_owner: str,
    repo_name: str,
    branch: str,
) -> str:
    """Enable required signatures on a protected branch."""
    logger.debug(
        f"🚀 Enabling required signatures for {repo_owner}/{repo_name}#{branch}"
    )

    try:
        async with github_client_context() as client:
            response = await client.put(
                f"/repos/{repo_owner}/{repo_name}/branches/{branch}/protection/required_signatures"
            )

            if response.status == 200:
                logger.info(
                    f"✅ Enabled required signatures for {repo_owner}/{repo_name}#{branch}"
                )
                return f"✅ Enabled required signatures on {repo_owner}/{repo_name}#{branch}"
            else:
                error_text = await response.text()
                return f"❌ Failed to enable required signatures: {response.status} - {error_text}"

    except ValueError as auth_error:
        logger.error(f"Authentication error enabling required signatures: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error enabling required signatures: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error enabling required signatures: {e}", exc_info=True
        )
        return f"❌ Error enabling required signatures: {str(e)}"


async def github_disable_required_signatures(
    repo_owner: str,
    repo_name: str,
    branch: str,
) -> str:
    """Disable required signatures on a protected branch."""
    logger.debug(
        f"🚀 Disabling required signatures for {repo_owner}/{repo_name}#{branch}"
    )

    try:
        async with github_client_context() as client:
            response = await client.delete(
                f"/repos/{repo_owner}/{repo_name}/branches/{branch}/protection/required_signatures"
            )

            if response.status == 204:
                logger.info(
                    f"✅ Disabled required signatures for {repo_owner}/{repo_name}#{branch}"
                )
                return f"✅ Disabled required signatures on {repo_owner}/{repo_name}#{branch}"
            else:
                error_text = await response.text()
                return f"❌ Failed to disable required signatures: {response.status} - {error_text}"

    except ValueError as auth_error:
        logger.error(
            f"Authentication error disabling required signatures: {auth_error}"
        )
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error disabling required signatures: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error disabling required signatures: {e}", exc_info=True
        )
        return f"❌ Error disabling required signatures: {str(e)}"


async def github_get_automated_security_fixes(
    repo_owner: str,
    repo_name: str,
) -> str:
    """Check if automated security fixes (Dependabot security updates) are enabled."""
    logger.debug(
        f"🔍 Getting automated security fixes status for {repo_owner}/{repo_name}"
    )

    try:
        async with github_client_context() as client:
            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/automated-security-fixes"
            )

            if response.status == 200:
                data = await response.json()
                enabled = data.get("enabled", False)
                paused = data.get("paused", False)

                status_parts = []
                if enabled:
                    status_parts.append("ENABLED")
                else:
                    status_parts.append("DISABLED")
                if paused:
                    status_parts.append("(PAUSED)")

                return f"{'✅' if enabled else '❌'} Automated security fixes (Dependabot security updates) are {' '.join(status_parts)} for {repo_owner}/{repo_name}"
            elif response.status == 404:
                return f"❌ Automated security fixes feature not available or disabled for {repo_owner}/{repo_name}"
            else:
                error_text = await response.text()
                return f"❌ Failed to check automated security fixes: {response.status} - {error_text}"

    except ValueError as auth_error:
        logger.error(
            f"Authentication error checking automated security fixes: {auth_error}"
        )
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(
            f"Connection error checking automated security fixes: {conn_error}"
        )
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error checking automated security fixes: {e}", exc_info=True
        )
        return f"❌ Error checking automated security fixes: {str(e)}"


async def github_enable_automated_security_fixes(
    repo_owner: str,
    repo_name: str,
) -> str:
    """Enable automated security fixes (Dependabot security updates) for a repository."""
    logger.debug(f"🚀 Enabling automated security fixes for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            response = await client.put(
                f"/repos/{repo_owner}/{repo_name}/automated-security-fixes"
            )

            if response.status == 204:
                logger.info(
                    f"✅ Enabled automated security fixes for {repo_owner}/{repo_name}"
                )
                return f"✅ Successfully enabled automated security fixes (Dependabot security updates) for {repo_owner}/{repo_name}"
            else:
                error_text = await response.text()
                return f"❌ Failed to enable automated security fixes: {response.status} - {error_text}"

    except ValueError as auth_error:
        logger.error(
            f"Authentication error enabling automated security fixes: {auth_error}"
        )
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(
            f"Connection error enabling automated security fixes: {conn_error}"
        )
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error enabling automated security fixes: {e}", exc_info=True
        )
        return f"❌ Error enabling automated security fixes: {str(e)}"


async def github_disable_automated_security_fixes(
    repo_owner: str,
    repo_name: str,
) -> str:
    """Disable automated security fixes (Dependabot security updates) for a repository."""
    logger.debug(f"🚀 Disabling automated security fixes for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            response = await client.delete(
                f"/repos/{repo_owner}/{repo_name}/automated-security-fixes"
            )

            if response.status == 204:
                logger.info(
                    f"✅ Disabled automated security fixes for {repo_owner}/{repo_name}"
                )
                return f"✅ Successfully disabled automated security fixes (Dependabot security updates) for {repo_owner}/{repo_name}"
            else:
                error_text = await response.text()
                return f"❌ Failed to disable automated security fixes: {response.status} - {error_text}"

    except ValueError as auth_error:
        logger.error(
            f"Authentication error disabling automated security fixes: {auth_error}"
        )
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(
            f"Connection error disabling automated security fixes: {conn_error}"
        )
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error disabling automated security fixes: {e}", exc_info=True
        )
        return f"❌ Error disabling automated security fixes: {str(e)}"


async def github_get_security_analysis(
    repo_owner: str,
    repo_name: str,
) -> str:
    """Get comprehensive security analysis status for a repository.

    Checks and reports on:
    - Vulnerability alerts (Dependabot alerts)
    - Automated security fixes (Dependabot security updates)
    - Secret scanning (if available)
    - Repository security settings

    Each check is performed independently with graceful error handling,
    so partial failures don't prevent other checks from completing.
    """
    logger.debug(f"🔍 Getting security analysis for {repo_owner}/{repo_name}")

    output = [f"Security Analysis for {repo_owner}/{repo_name}:\n"]
    checks_succeeded = 0
    checks_failed = 0

    try:
        async with github_client_context() as client:
            # Check vulnerability alerts
            try:
                vuln_response = await client.get(
                    f"/repos/{repo_owner}/{repo_name}/vulnerability-alerts"
                )
                if vuln_response.status == 204:
                    output.append("✅ Vulnerability Alerts (Dependabot): ENABLED")
                elif vuln_response.status == 404:
                    output.append("❌ Vulnerability Alerts (Dependabot): DISABLED")
                else:
                    output.append(
                        f"⚠️ Vulnerability Alerts: Unable to determine (HTTP {vuln_response.status})"
                    )
                checks_succeeded += 1
            except Exception as e:
                logger.warning(f"Failed to check vulnerability alerts: {e}")
                output.append(f"⚠️ Vulnerability Alerts: Check failed ({e})")
                checks_failed += 1

            # Check automated security fixes
            try:
                auto_response = await client.get(
                    f"/repos/{repo_owner}/{repo_name}/automated-security-fixes"
                )
                if auto_response.status == 200:
                    auto_data = await auto_response.json()
                    enabled = auto_data.get("enabled", False)
                    paused = auto_data.get("paused", False)
                    status = "ENABLED" if enabled else "DISABLED"
                    if paused:
                        status += " (PAUSED)"
                    output.append(
                        f"{'✅' if enabled else '❌'} Automated Security Fixes: {status}"
                    )
                else:
                    output.append(
                        "❌ Automated Security Fixes: DISABLED or unavailable"
                    )
                checks_succeeded += 1
            except Exception as e:
                logger.warning(f"Failed to check automated security fixes: {e}")
                output.append(f"⚠️ Automated Security Fixes: Check failed ({e})")
                checks_failed += 1

            # Get repository settings for additional security info
            try:
                repo_response = await client.get(f"/repos/{repo_owner}/{repo_name}")
                if repo_response.status == 200:
                    repo_data = await repo_response.json()

                    # Security-related repo settings
                    output.append("\n📋 Repository Security Settings:")
                    output.append(
                        f"   Visibility: {repo_data.get('visibility', 'unknown')}"
                    )
                    output.append(
                        f"   Private: {'✅' if repo_data.get('private') else '❌'}"
                    )
                    output.append(
                        f"   Archived: {'✅' if repo_data.get('archived') else '❌'}"
                    )

                    # Check for security policy
                    security_policy = repo_data.get("security_and_analysis", {})
                    if security_policy:
                        output.append("\n🔐 Security & Analysis Features:")

                        # Secret scanning
                        secret_scanning = security_policy.get("secret_scanning", {})
                        if secret_scanning.get("status") == "enabled":
                            output.append("   ✅ Secret Scanning: ENABLED")
                        else:
                            output.append("   ❌ Secret Scanning: DISABLED")

                        # Secret scanning push protection
                        push_protection = security_policy.get(
                            "secret_scanning_push_protection", {}
                        )
                        if push_protection.get("status") == "enabled":
                            output.append(
                                "   ✅ Secret Scanning Push Protection: ENABLED"
                            )
                        else:
                            output.append(
                                "   ❌ Secret Scanning Push Protection: DISABLED"
                            )

                        # Dependabot security updates
                        dependabot = security_policy.get(
                            "dependabot_security_updates", {}
                        )
                        if dependabot.get("status") == "enabled":
                            output.append("   ✅ Dependabot Security Updates: ENABLED")
                        else:
                            output.append("   ❌ Dependabot Security Updates: DISABLED")
                else:
                    output.append(
                        f"\n⚠️ Repository Settings: Unable to fetch (HTTP {repo_response.status})"
                    )
                checks_succeeded += 1
            except Exception as e:
                logger.warning(f"Failed to get repository settings: {e}")
                output.append(f"\n⚠️ Repository Settings: Check failed ({e})")
                checks_failed += 1

            # Add summary if there were any failures
            if checks_failed > 0:
                output.append(
                    f"\n⚠️ Note: {checks_failed} of {checks_succeeded + checks_failed} checks failed"
                )

            output.append(
                f"\n🔗 Security Settings: https://github.com/{repo_owner}/{repo_name}/settings/security_analysis"
            )

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error getting security analysis: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error getting security analysis: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error getting security analysis: {e}", exc_info=True)
        return f"❌ Error getting security analysis: {str(e)}"
