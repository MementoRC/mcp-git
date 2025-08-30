"""Content optimization utilities for LLM clients.

This module provides content transformation capabilities to convert human-friendly
git operation output into LLM-optimized format that reduces token usage while
preserving semantic meaning and technical accuracy.
"""

import logging
import re
from typing import Any

from .token_management import ClientType

logger = logging.getLogger(__name__)


class ContentOptimizer:
    """Optimizes content formatting for different client types."""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.ContentOptimizer")

        # Emoji patterns to remove for LLM clients
        self.emoji_patterns = [
            r"✅",
            r"❌",
            r"⚠️",
            r"🔄",
            r"🔒",
            r"🔐",
            r"🔑",
            r"🔗",
            r"📊",
            r"📝",
            r"🚨",
            r"💥",
            r"🧪",
            r"🌐",
            r"📡",
            r"📨",
            r"🟢",
            r"🔴",
            r"🟡",
            r"🟣",
            r"⏳",
            r"❓",
            r"💬",
            r"🎯",
            r"🚀",
            r"🛠️",
            r"⌨️",
            r"🔌",
            r"🔔",
        ]

        # Verbose phrase replacements for LLM optimization
        self.llm_replacements = {
            # Success messages
            r"✅ Successfully (.+)": r"\1 completed",
            r"✅ (.+) completed successfully": r"\1 completed",
            # Error messages
            r"❌ (.+) failed:": r"Error:",
            r"❌ (.+) error:": r"Error:",
            # Warning messages
            r"⚠️\s*(.+)": r"Warning: \1",
            # Status indicators
            r"🔄 (.+) in progress": r"\1 in progress",
            r"🔒 (.+)": r"Security: \1",
            r"🔑 (.+)": r"Auth: \1",
            # Remove redundant phrasing
            r"No changes detected in (.+)": r"No changes in \1",
            r"Successfully (.+) to (.+)": r"\1 to \2",
            r"(.+) was (.+) successfully": r"\1 \2",
            # Simplify git output
            r"Git command failed": r"Command failed",
            r"Repository (.+)": r"Repo \1",
        }

        # Patterns for removing human-friendly but LLM-unnecessary content
        self.removal_patterns = [
            r"\n⚡ .+",  # Lightning bolt status updates
            r"\n🎯 .+",  # Target/goal indicators
            r"\n🚀 .+",  # Rocket launch indicators
            r"\n\s*Generated with \[Claude Code\].+",  # Attribution footer
            r"\n\s*Co-Authored-By: Claude.+",  # Co-author lines for LLMs
        ]

    def optimize_for_client(
        self, content: str, client_type: ClientType, operation: str = ""
    ) -> str:
        """Optimize content formatting based on client type.

        Args:
            content: Original content to optimize
            client_type: Type of client (LLM, human, unknown)
            operation: Git operation that generated the content

        Returns:
            Optimized content string
        """
        if client_type == ClientType.HUMAN:
            # Keep human-friendly formatting
            return content

        if client_type == ClientType.LLM:
            # Apply LLM optimizations
            return self._optimize_for_llm(content, operation)

        # ClientType.UNKNOWN
        # Apply conservative optimizations
        return self._optimize_conservatively(content, operation)

    def _optimize_for_llm(self, content: str, operation: str) -> str:
        """Apply aggressive optimizations for LLM clients."""
        optimized = content

        # Remove emojis
        for emoji in self.emoji_patterns:
            optimized = re.sub(emoji, "", optimized)

        # Apply phrase replacements
        for pattern, replacement in self.llm_replacements.items():
            optimized = re.sub(pattern, replacement, optimized, flags=re.IGNORECASE)

        # Remove LLM-unnecessary content
        for pattern in self.removal_patterns:
            optimized = re.sub(pattern, "", optimized, flags=re.MULTILINE)

        # Operation-specific optimizations
        optimized = self._apply_operation_specific_optimization(optimized, operation)

        # Clean up extra whitespace
        optimized = re.sub(
            r"\n\s*\n\s*\n", "\n\n", optimized
        )  # Max 2 consecutive newlines
        optimized = re.sub(
            r"^\s+|\s+$", "", optimized
        )  # Strip leading/trailing whitespace

        return optimized

    def _optimize_conservatively(self, content: str, operation: str) -> str:
        """Apply conservative optimizations for unknown clients."""
        optimized = content

        # Only remove obviously LLM-unnecessary content
        for pattern in self.removal_patterns:
            optimized = re.sub(pattern, "", optimized, flags=re.MULTILINE)

        # Clean up extra whitespace
        optimized = re.sub(r"\n\s*\n\s*\n", "\n\n", optimized)
        optimized = re.sub(r"^\s+|\s+$", "", optimized)

        return optimized

    def _apply_operation_specific_optimization(
        self, content: str, operation: str
    ) -> str:
        """Apply operation-specific optimizations."""
        if operation.startswith("git_diff"):
            return self._optimize_diff_output(content)
        if operation == "git_status":
            return self._optimize_status_output(content)
        if operation == "git_log":
            return self._optimize_log_output(content)
        if operation.startswith("github_"):
            return self._optimize_github_output(content)

        return content

    def _optimize_diff_output(self, content: str) -> str:
        """Optimize git diff output for LLM consumption."""
        lines = content.split("\n")
        optimized_lines = []

        for line in lines:
            # Preserve essential diff structure
            if line.startswith(("diff --git", "+++", "---", "@@")):
                optimized_lines.append(line)
            # Preserve actual diff content
            elif line.startswith(("+", "-", " ")):
                optimized_lines.append(line)
            # Optimize metadata lines
            elif line.startswith("index "):
                # Shorten index lines
                optimized_lines.append(line[:50] + "..." if len(line) > 50 else line)
            else:
                optimized_lines.append(line)

        return "\n".join(optimized_lines)

    def _optimize_status_output(self, content: str) -> str:
        """Optimize git status output for LLM consumption."""
        # Simplify common status phrases
        replacements = {
            r"On branch (.+)": r"Branch: \1",
            r"Your branch is (.+)": r"Branch \1",
            r"Changes to be committed:": r"Staged:",
            r"Changes not staged for commit:": r"Unstaged:",
            r"Untracked files:": r"Untracked:",
            r'\s+\(use "git [^"]*" to [^)]*\)': "",  # Remove git command hints
        }

        optimized = content
        for pattern, replacement in replacements.items():
            optimized = re.sub(pattern, replacement, optimized, flags=re.MULTILINE)

        return optimized

    def _optimize_log_output(self, content: str) -> str:
        """Optimize git log output for LLM consumption."""
        # Simplify commit formatting
        replacements = {
            r"commit ([a-f0-9]{40})": r"commit \1[:8]",  # Shorten commit hashes
            r"Author:\s*(.+) <([^>]+)>": r"Author: \1",  # Remove email addresses
            r"Date:\s*(.+)": r"Date: \1",
            r"Merge: ([a-f0-9]{7}) ([a-f0-9]{7})": r"Merge: \1..\2",  # Shorten merge info
        }

        optimized = content
        for pattern, replacement in replacements.items():
            optimized = re.sub(pattern, replacement, optimized)

        return optimized

    def _optimize_github_output(self, content: str) -> str:
        """Optimize GitHub API output for LLM consumption."""
        # Remove GitHub-specific decorative elements
        replacements = {
            r"Pull Request #(\d+):": r"PR #\1:",
            r"Check runs for PR #(\d+)": r"PR #\1 checks:",
            r"Files changed in PR #(\d+)": r"PR #\1 files:",
            r"Failing jobs for PR #(\d+)": r"PR #\1 failures:",
        }

        optimized = content
        for pattern, replacement in replacements.items():
            optimized = re.sub(pattern, replacement, optimized)

        return optimized


class ResponseFormatter:
    """Formats responses based on client requirements and token constraints."""

    def __init__(self):
        self.optimizer = ContentOptimizer()
        self.logger = logging.getLogger(f"{__name__}.ResponseFormatter")

    def format_response(
        self,
        content: str,
        client_type: ClientType,
        operation: str = "",
        metadata: dict[str, Any] = None,
    ) -> str:
        """Format response content for the client.

        Args:
            content: Original response content
            client_type: Type of client
            operation: Git operation that generated the content
            metadata: Additional formatting metadata

        Returns:
            Formatted response content
        """
        metadata = metadata or {}

        try:
            # Apply client-specific optimizations
            optimized_content = self.optimizer.optimize_for_client(
                content, client_type, operation
            )

            # Apply any additional formatting based on metadata
            if metadata.get("structured_output"):
                optimized_content = self._add_structure_markers(
                    optimized_content, operation
                )

            if metadata.get("include_summary") and len(optimized_content) > 1000:
                optimized_content = self._add_content_summary(
                    optimized_content, operation
                )

            return optimized_content

        except Exception as e:
            self.logger.error(f"Error formatting response for {operation}: {e}")
            # Return original content on error
            return content

    def _add_structure_markers(self, content: str, operation: str) -> str:
        """Add structure markers for better LLM parsing."""
        if operation.startswith("git_diff"):
            return f"DIFF_START\n{content}\nDIFF_END"
        if operation == "git_status":
            return f"STATUS_START\n{content}\nSTATUS_END"
        if operation == "git_log":
            return f"LOG_START\n{content}\nLOG_END"

        return content

    def _add_content_summary(self, content: str, operation: str) -> str:
        """Add a brief summary for long content."""
        lines = content.split("\n")

        if operation.startswith("git_diff"):
            files_changed = len([l for l in lines if l.startswith("diff --git")])
            summary = f"SUMMARY: {files_changed} files changed\n\n"
        elif operation == "git_log":
            commits = len([l for l in lines if l.startswith("commit ")])
            summary = f"SUMMARY: {commits} commits shown\n\n"
        elif operation == "git_status":
            staged = len(
                [
                    l
                    for l in lines
                    if l.strip().startswith("modified:")
                    or l.strip().startswith("new file:")
                ]
            )
            summary = f"SUMMARY: {staged} files with changes\n\n"
        else:
            summary = f"SUMMARY: {len(lines)} lines, {len(content)} characters\n\n"

        return summary + content
