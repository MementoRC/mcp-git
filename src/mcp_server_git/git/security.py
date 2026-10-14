"""Git security validation and enforcement"""

import logging
import os
import subprocess
from collections.abc import Callable
from typing import Any

# Safe git import that handles ClaudeCode redirector conflicts
from ..utils.git_import import Repo
from ..utils.tool_failure import fail

logger = logging.getLogger(__name__)

# (section, key, default, is_ok, warning, recommendation)
_ConfigSpec = tuple[str, str, Any, Callable[[Any], bool], str, str]


def _gpgsign_enabled(value: Any) -> bool:
    return str(value).lower() == "true"


_GPG_SPECS: tuple[_ConfigSpec, ...] = (
    (
        "user",
        "signingkey",
        None,
        bool,
        "No GPG signing key configured (user.signingkey)",
        "Set up GPG signing: git config user.signingkey <key-id>",
    ),
    (
        "commit",
        "gpgsign",
        "false",
        _gpgsign_enabled,
        "GPG signing not enabled by default (commit.gpgsign)",
        "Enable GPG signing: git config commit.gpgsign true",
    ),
)

_USER_SPECS: tuple[_ConfigSpec, ...] = (
    (
        "user",
        "name",
        None,
        bool,
        "No user name configured (user.name)",
        "Set user name: git config user.name 'Your Name'",
    ),
    (
        "user",
        "email",
        None,
        bool,
        "No user email configured (user.email)",
        "Set user email: git config user.email 'your.email@example.com'",
    ),
)

# (config key under [user], env vars tried in order, strict-mode error)
_IDENTITY_SPECS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "name",
        ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"),
        fail(
            "❌ No user name configured. Set GIT_AUTHOR_NAME env var or git config user.name"
        ),
    ),
    (
        "email",
        ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"),
        fail(
            "❌ No user email configured. Set GIT_AUTHOR_EMAIL env var or git config user.email"
        ),
    ),
)

_ERR_NO_KEYS_FOUND = fail(
    "❌ No GPG keys found. Generate a GPG key or set GPG_SIGNING_KEY env var"
)
_ERR_NO_KEYS_AVAILABLE = fail(
    "❌ No GPG keys available. Install GPG and generate a key"
)


def _read_config(repo: Repo, section: str, key: str, default: Any) -> Any:
    try:
        return repo.config_reader().get_value(section, key)
    except Exception:
        return default


def _check_specs(
    repo: Repo,
    specs: tuple[_ConfigSpec, ...],
    label: str,
    warnings: list[str],
    recommendations: list[str],
) -> None:
    values = [_read_config(repo, s, k, default) for s, k, default, *_ in specs]
    try:
        for (_, _, _, is_ok, warning, recommendation), value in zip(
            specs, values, strict=True
        ):
            if not is_ok(value):
                warnings.append(warning)
                recommendations.append(recommendation)
    except Exception as e:
        warnings.append(f"Could not read {label} configuration: {e}")


def _check_latest_commit_signature(
    repo: Repo, warnings: list[str], recommendations: list[str]
) -> None:
    try:
        verify_result = subprocess.run(
            ["git", "log", "--show-signature", "-1", "--pretty=format:%G?"],
            cwd=repo.working_dir,
            capture_output=True,
            text=True,
        )
        if verify_result.returncode != 0:
            warnings.append("Could not verify commit signatures")
        elif verify_result.stdout.strip() not in ["G", "U"]:
            # G=good, U=good but untrusted
            warnings.append("Latest commit is not properly signed")
            recommendations.append("Ensure all commits are GPG signed")
    except Exception:
        warnings.append("Could not check commit signatures")


def _overall_status(warnings: list[str]) -> str:
    if not warnings:
        return "secure"
    return "warning" if len(warnings) <= 2 else "insecure"


def validate_git_security_config(repo: Repo) -> dict[str, Any]:
    """Validate Git security configuration for the repository"""

    warnings: list[str] = []
    recommendations: list[str] = []

    try:
        _check_specs(repo, _GPG_SPECS, "GPG", warnings, recommendations)
        _check_specs(repo, _USER_SPECS, "user", warnings, recommendations)
        _check_latest_commit_signature(repo, warnings, recommendations)

        return {
            "status": _overall_status(warnings),
            "warnings": warnings,
            "recommendations": recommendations,
        }

    except Exception as e:
        return {
            "status": "error",
            "warnings": [f"Security validation failed: {e}"],
            "recommendations": ["Check repository access and git configuration"],
        }


def _enforce_identity(
    config_writer: Any,
    current: dict[str, Any],
    strict_mode: bool,
    changes_made: list[str],
) -> str | None:
    """Fill missing user.name/user.email from env; return strict-mode error."""
    for key, env_vars, strict_error in _IDENTITY_SPECS:
        if current[key]:
            continue
        env_value = next((v for v in map(os.getenv, env_vars) if v), None)
        if env_value:
            config_writer.set_value("user", key, env_value)
            changes_made.append(f"Set user.{key} to '{env_value}' from environment")
        elif strict_mode:
            return strict_error
    return None


def _parse_signing_key_id(gpg_output: str) -> str | None:
    for line in gpg_output.split("\n"):
        if line.strip().startswith("sec"):
            # Extract key ID from line like "sec   4096R/ABCD1234 2023-01-01"
            parts = line.split()
            if len(parts) >= 2 and "/" in parts[1]:
                return parts[1].split("/")[1].split()[0]
    return None


def _autodetect_signing_key(
    config_writer: Any, strict_mode: bool, changes_made: list[str]
) -> str | None:
    """Set user.signingkey from the first gpg secret key; return strict error."""
    try:
        gpg_result = subprocess.run(
            ["gpg", "--list-secret-keys", "--keyid-format", "LONG"],
            capture_output=True,
            text=True,
        )
        if gpg_result.returncode != 0 or "sec" not in gpg_result.stdout:
            return _ERR_NO_KEYS_AVAILABLE if strict_mode else None
        key_id = _parse_signing_key_id(gpg_result.stdout)
        if key_id is None:
            return _ERR_NO_KEYS_FOUND if strict_mode else None
        config_writer.set_value("user", "signingkey", key_id)
        changes_made.append(f"Auto-detected and set GPG signing key: {key_id}")
    except Exception as e:
        if strict_mode:
            return fail(
                f"❌ Could not detect GPG keys: {e}. Set GPG_SIGNING_KEY env var"
            )
    return None


def _enforce_signing_key(
    config_writer: Any, strict_mode: bool, changes_made: list[str]
) -> str | None:
    env_key = os.getenv("GPG_SIGNING_KEY")
    if env_key:
        config_writer.set_value("user", "signingkey", env_key)
        changes_made.append(f"Set GPG signing key to '{env_key}' from environment")
        return None
    return _autodetect_signing_key(config_writer, strict_mode, changes_made)


def _write_config(config_writer: Any) -> str | None:
    try:
        config_writer.write()
        config_writer.release()
    except Exception as e:
        return fail(f"❌ Could not write git configuration: {e}")
    return None


def _format_changes(changes_made: list[str]) -> str:
    if not changes_made:
        return "✅ Git security configuration already optimal"
    result = "✅ Git security configuration enforced:\n"
    for change in changes_made:
        result += f"  • {change}\n"
    result += "🔒 Repository is now configured for secure commits"
    return result


def enforce_secure_git_config(repo: Repo, strict_mode: bool = True) -> str:
    """Enforce secure Git configuration (GPG signing, proper user config)"""

    try:
        config_writer = repo.config_writer()
        changes_made: list[str] = []

        current = {
            key: _read_config(repo, "user", key, None) for key, _, _ in _IDENTITY_SPECS
        }
        signing_key = _read_config(repo, "user", "signingkey", None)
        gpg_sign = _read_config(repo, "commit", "gpgsign", "false")

        error = _enforce_identity(config_writer, current, strict_mode, changes_made)
        if error:
            return error

        if not _gpgsign_enabled(gpg_sign):
            config_writer.set_value("commit", "gpgsign", "true")
            changes_made.append("Enabled GPG signing for commits (commit.gpgsign=true)")

        if not signing_key:
            error = _enforce_signing_key(config_writer, strict_mode, changes_made)
            if error:
                return error

        error = _write_config(config_writer)
        if error:
            return error

        return _format_changes(changes_made)

    except Exception as e:
        return fail(f"❌ Security enforcement failed: {e}")
