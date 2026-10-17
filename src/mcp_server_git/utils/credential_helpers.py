"""Inspect configured git credential helpers (issue #303).

Used for the push failure hint and the informational health check. Helpers
are read with ``git config --show-origin`` (no shell) so each one is reported
with the file that defines it.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

__all__ = [
    "HelperEntry",
    "credential_helper_health",
    "credential_hint",
    "list_credential_helpers",
    "missing_executable",
]

_CONFIG_TIMEOUT = 10  # seconds
_HELPER_KEY_PATTERN = r"^credential\.(.+\.)?helper$"
_PROMPT_MARKERS = ("could not read Username", "terminal prompts disabled")
_FIX_ADVICE = (
    "Fix: run `gh auth setup-git`, remove the stale entry "
    "(`git config --unset-all <key>` in the file shown), or set GITHUB_TOKEN "
    "so the server's token path applies."
)


def missing_executable(value: str) -> str | None:
    """Return the helper's absolute executable when it does not exist.

    Only ``!/abs/path ...`` and ``/abs/path ...`` helpers name an executable
    that can be checked; built-in helpers (``store``, ``cache``) and shell
    snippets (``!f() { ...; }; f``) return None.
    """
    command = value.strip()
    if command.startswith("!"):
        command = command[1:].lstrip()
    if not command.startswith("/"):
        return None
    executable = command.split()[0]
    return None if Path(executable).exists() else executable


@dataclass(frozen=True)
class HelperEntry:
    """One ``credential[.<url>].helper`` value and the config file defining it."""

    origin: str
    key: str
    value: str

    @property
    def scope(self) -> str:
        """The URL subsection of the key; empty for the generic helper."""
        return self.key[len("credential.") : -len("helper")].rstrip(".")

    @property
    def missing_executable(self) -> str | None:
        return missing_executable(self.value)


def _parse_entries(output: str) -> list[HelperEntry]:
    """Parse ``--show-origin --null`` output: origin NUL key LF value NUL ..."""
    fields = output.split("\0")
    entries = []
    for origin, item in zip(fields[0::2], fields[1::2], strict=False):
        key, _, value = item.partition("\n")
        entries.append(HelperEntry(origin, key, value))
    return entries


def list_credential_helpers(cwd: str | None = None) -> list[HelperEntry]:
    """List every credential helper visible from ``cwd`` (all config scopes)."""
    result = subprocess.run(
        [
            "git",
            "config",
            "--show-origin",
            "--null",
            "--get-regexp",
            _HELPER_KEY_PATTERN,
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=_CONFIG_TIMEOUT,
        check=False,
    )
    return _parse_entries(result.stdout)


def _scope_matches(scope: str, url: str) -> bool:
    if not scope:
        return True
    wanted, actual = urlsplit(scope), urlsplit(url)
    if wanted.scheme and wanted.scheme != actual.scheme:
        return False
    return wanted.hostname == actual.hostname


def _display_url(url: str) -> str:
    """Drop any userinfo so embedded credentials are never echoed."""
    parts = urlsplit(url)
    if not parts.hostname:
        return url
    netloc = parts.hostname + (f":{parts.port}" if parts.port else "")
    return urlunsplit(parts._replace(netloc=netloc))


def _needs_hint(stderr: str) -> bool:
    if any(marker in stderr for marker in _PROMPT_MARKERS):
        return True
    return any(
        "credential" in line and "not found" in line for line in stderr.splitlines()
    )


def _describe(entry: HelperEntry) -> str:
    line = f"  - {entry.origin}: {entry.key} = {entry.value}"
    missing = entry.missing_executable
    return f"{line}  ⚠ missing executable: {missing}" if missing else line


def credential_hint(stderr: str, url: str, cwd: str | None = None) -> str:
    """Explain a credential failure by listing the helpers configured for ``url``.

    Returns "" unless ``stderr`` looks like a credential/prompt failure.
    """
    if not url or not _needs_hint(stderr):
        return ""
    try:
        entries = list_credential_helpers(cwd)
    except (OSError, subprocess.SubprocessError):
        entries = []
    lines = [f"\n💡 Credential helpers configured for {_display_url(url)}:"]
    matching = [e for e in entries if _scope_matches(e.scope, url)]
    lines += [_describe(e) for e in matching] or ["  (none configured)"]
    lines.append(_FIX_ADVICE)
    return "\n".join(lines)


def credential_helper_health(cwd: str | None = None) -> dict[str, Any]:
    """Report helpers whose executable is missing. Informational only."""
    try:
        entries = list_credential_helpers(cwd)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"status": "unknown", "error": str(exc), "missing_executables": []}
    missing = [
        {"origin": e.origin, "key": e.key, "executable": e.missing_executable}
        for e in entries
        if e.missing_executable
    ]
    return {
        "status": "warning" if missing else "ok",
        "helpers_checked": len(entries),
        "missing_executables": missing,
    }
