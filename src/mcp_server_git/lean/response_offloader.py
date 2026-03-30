"""Response offloader — writes large responses to /tmp files with smart summaries."""

from __future__ import annotations

import glob
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime
from typing import Any

from mcp_server_git.lean.token_limiter import MCPTokenLimiter

logger = logging.getLogger(__name__)

_DEFAULT_OFFLOAD_DIR = os.environ.get("MCP_GIT_OFFLOAD_DIR", "/tmp")
_DEFAULT_MAX_AGE = 3600  # 1 hour


def _summarize_diff(result: Any) -> str:
    """Summarize unified diff: files changed, insertions, deletions."""
    if not isinstance(result, str):
        return _summarize_generic(result)
    files = len(re.findall(r"^diff --git", result, re.MULTILINE))
    insertions = len(re.findall(r"^\+[^+]", result, re.MULTILINE))
    deletions = len(re.findall(r"^-[^-]", result, re.MULTILINE))
    return f"{files} files changed, {insertions}(+), {deletions}(-)"


def _summarize_log(result: Any) -> str:
    """Summarize git log: commit count, authors, date range."""
    if not isinstance(result, str):
        return _summarize_generic(result)
    commits = len(re.findall(r"^commit [0-9a-f]+", result, re.MULTILINE))
    authors = set(re.findall(r"^Author:\s*(.+?)(?:\s*<.*>)?\s*$", result, re.MULTILINE))
    dates = re.findall(r"^Date:\s+(.+)$", result, re.MULTILINE)
    parts = [f"{commits} commits"]
    if authors:
        parts.append(f"{len(authors)} authors")
    if len(dates) >= 2:
        parts.append(f"{dates[-1].strip()} .. {dates[0].strip()}")
    return ", ".join(parts)


def _summarize_job_logs(result: Any) -> str:
    """Summarize CI job logs: line count, error/warning counts."""
    if not isinstance(result, str):
        return _summarize_generic(result)
    errors = len(re.findall(r"^.*\bERROR\b", result, re.MULTILINE | re.IGNORECASE))
    warnings = len(re.findall(r"^.*\bWARNING\b", result, re.MULTILINE | re.IGNORECASE))
    lines = result.count("\n") + 1
    return f"{lines} lines, {errors} errors, {warnings} warnings"


def _summarize_list(result: Any) -> str:
    """Summarize list output: line/item count."""
    if not isinstance(result, str):
        return _summarize_generic(result)
    items = [line for line in result.strip().splitlines() if line.strip()]
    return f"{len(items)} items"


_SUMMARY_GENERATORS: dict[str, Any] = {
    "git_diff": _summarize_diff,
    "git_diff_unstaged": _summarize_diff,
    "git_diff_staged": _summarize_diff,
    "git_diff_branches": _summarize_diff,
    "git_log": _summarize_log,
    "github_get_job_logs": _summarize_job_logs,
    "github_list_issues": _summarize_list,
    "github_list_pull_requests": _summarize_list,
    "github_list_workflow_runs": _summarize_list,
    "github_list_releases": _summarize_list,
    "github_list_release_assets": _summarize_list,
}


class ResponseOffloader:
    """Offloads large tool responses to /tmp files with smart summaries."""

    def __init__(
        self,
        token_limiter: MCPTokenLimiter,
        offload_dir: str | None = None,
    ):
        self.token_limiter = token_limiter
        self.offload_dir = offload_dir or _DEFAULT_OFFLOAD_DIR

    def should_offload(self, result: Any, tool_name: str) -> bool:
        """Check if a result should be offloaded to file."""
        if not isinstance(result, (dict, str, list)):
            return False
        data = result if isinstance(result, dict) else {"result": result}
        return self.token_limiter.would_truncate(data, tool_name)

    def offload(self, result: Any, tool_name: str) -> dict[str, Any]:
        """Write result to file and return summary dict."""
        if isinstance(result, (dict, list)):
            content = json.dumps(result, indent=2, default=str)
        else:
            content = str(result)

        path = self._write_to_tmp(content, tool_name)
        self._cleanup_old_files()
        summary = self._generate_summary(result, tool_name)

        return {
            "summary": summary,
            "full_output_path": path,
            "offloaded": True,
        }

    def _write_to_tmp(self, content: str, tool_name: str) -> str:
        """Write content to a temp file and return the path."""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        uid = uuid.uuid4().hex[:6]
        filename = f"mcp-git-{tool_name}-{timestamp}-{uid}.txt"
        path = os.path.join(self.offload_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Offloaded {tool_name} response ({len(content)} bytes) to {path}")
        return path

    def _cleanup_old_files(self, max_age_seconds: int = _DEFAULT_MAX_AGE) -> None:
        """Remove expired offload files. Best-effort, ignores errors."""
        pattern = os.path.join(self.offload_dir, "mcp-git-*")
        cutoff = time.time() - max_age_seconds
        for filepath in glob.glob(pattern):
            try:
                if os.path.getmtime(filepath) < cutoff:
                    os.remove(filepath)
                    logger.debug(f"Cleaned up expired offload file: {filepath}")
            except OSError:
                pass

    def _generate_summary(self, result: Any, tool_name: str) -> str:
        """Generate a smart summary for the offloaded result."""
        summarizer = _SUMMARY_GENERATORS.get(tool_name)
        if summarizer:
            try:
                return summarizer(result)
            except Exception:
                logger.warning(f"Summary generator failed for {tool_name}, using generic")
        return _summarize_generic(result)


def _summarize_generic(result: Any) -> str:
    """Fallback summary: response size and type."""
    if isinstance(result, str):
        size = len(result)
        content_type = "text"
    elif isinstance(result, dict):
        size = len(json.dumps(result, default=str))
        content_type = "json"
    elif isinstance(result, list):
        size = len(json.dumps(result, default=str))
        content_type = f"list ({len(result)} items)"
    else:
        size = len(str(result))
        content_type = type(result).__name__
    return f"Response offloaded ({size:,} bytes, {content_type})"
