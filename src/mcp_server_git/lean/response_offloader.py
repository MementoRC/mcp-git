"""Response offloader — writes large responses to /tmp files with smart summaries."""

from __future__ import annotations

import glob
import json
import logging
import os
import time
import uuid
from datetime import datetime
from typing import Any

from mcp_server_git.lean.token_limiter import MCPTokenLimiter

logger = logging.getLogger(__name__)

_DEFAULT_OFFLOAD_DIR = os.environ.get("MCP_GIT_OFFLOAD_DIR", "/tmp")
_DEFAULT_MAX_AGE = 3600  # 1 hour


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
