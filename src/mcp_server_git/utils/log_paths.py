"""Default on-disk locations for downloaded CI logs (``save_to_disk``)."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

LOG_DIR_ENV = "MCP_GIT_LOG_DIR"
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def sanitize_component(value: object) -> str:
    """Reduce a name part to ``[A-Za-z0-9._-]`` so it is safe in a filename."""
    return _UNSAFE_CHARS.sub("_", str(value))


def log_dir() -> Path:
    """Directory for saved logs: ``$MCP_GIT_LOG_DIR`` or ``<tmp>/mcp-git-logs``."""
    configured = os.environ.get(LOG_DIR_ENV)
    if configured:
        return Path(configured)
    return Path(tempfile.gettempdir()) / "mcp-git-logs"


def resolve_output_path(
    output_path: str | None, save_to_disk: bool, *name_parts: object
) -> str | None:
    """Pick where to write a full log, or None to keep it inline.

    An explicit ``output_path`` always wins. Otherwise ``save_to_disk`` yields
    ``<log dir>/<name parts joined by '-'>.log`` (components sanitized; the
    directory is created; an existing file is overwritten on write).
    """
    if output_path is not None:
        return output_path
    if not save_to_disk:
        return None
    directory = log_dir()
    directory.mkdir(parents=True, exist_ok=True)
    stem = "-".join(sanitize_component(part) for part in name_parts)
    return str(directory.resolve() / f"{stem}.log")
