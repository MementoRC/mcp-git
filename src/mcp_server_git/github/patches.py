"""GitHub patch content management utilities."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class PatchMemoryManager:
    """Memory-aware patch content manager with configurable limits and streaming support."""

    def __init__(self, max_patch_size: int = 1000, max_total_memory: int = 50000):
        self.max_patch_size = max_patch_size
        self.max_total_memory = max_total_memory
        self.current_memory_usage = 0
        self.patches_processed = 0

    def can_include_patch(self, patch_size: int) -> bool:
        """Check if patch can be included within memory constraints."""
        return (self.current_memory_usage + patch_size) <= self.max_total_memory

    def process_patch(self, patch_content: str) -> tuple[str, bool]:
        """Process patch content with memory management and truncation.

        Returns:
            tuple[str, bool]: (processed_content, was_truncated)
        """
        patch_size = len(patch_content)
        self.patches_processed += 1

        # Check memory budget first
        if not self.can_include_patch(patch_size):
            logger.warning(
                f"Patch #{self.patches_processed} skipped: exceeds memory budget ({patch_size} bytes, {self.current_memory_usage}/{self.max_total_memory} used)"
            )
            return (
                f"[Patch skipped - memory limit reached ({self.current_memory_usage}/{self.max_total_memory} bytes used)]",
                True,
            )

        # Apply individual patch size limit
        if patch_size > self.max_patch_size:
            truncated_patch = patch_content[: self.max_patch_size]
            self.current_memory_usage += self.max_patch_size
            logger.info(
                f"Patch #{self.patches_processed} truncated: {patch_size} -> {self.max_patch_size} bytes"
            )
            return (
                f"```diff\n{truncated_patch}\n... [truncated {patch_size - self.max_patch_size} chars]\n```",
                True,
            )
        else:
            self.current_memory_usage += patch_size
            return f"```diff\n{patch_content}\n```", False
