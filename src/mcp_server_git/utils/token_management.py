"""Token management utilities for LLM client optimization.

This module provides token estimation, content optimization, and intelligent truncation
capabilities for the MCP Git Server to prevent overwhelming LLM clients with excessive
response sizes while maintaining semantic meaning.
"""

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ClientType(Enum):
    """Types of clients that can connect to the server."""

    HUMAN = "human"
    LLM = "llm"
    UNKNOWN = "unknown"


class ContentType(Enum):
    """Types of content for different token estimation strategies."""

    TEXT = "text"
    CODE = "code"
    STRUCTURED = "structured"
    DIFF = "diff"
    LOG = "log"


class TokenizerType(Enum):
    """Different tokenizer types with varying accuracy characteristics."""

    GENERIC = "generic"  # Generic estimation (current approach)
    OPENAI = "openai"  # OpenAI GPT tokenizers (cl100k_base)
    ANTHROPIC = "anthropic"  # Anthropic Claude tokenizers
    HUGGINGFACE = "huggingface"  # HuggingFace transformers tokenizers


@dataclass
class TokenEstimate:
    """Token estimation result with metadata and confidence intervals."""

    estimated_tokens: int
    confidence: float
    content_type: ContentType
    char_count: int
    line_count: int
    tokenizer_type: TokenizerType = TokenizerType.GENERIC
    min_tokens: int = 0  # Lower bound of confidence interval
    max_tokens: int = 0  # Upper bound of confidence interval

    def __post_init__(self):
        """Calculate confidence intervals after initialization."""
        if self.min_tokens == 0 and self.max_tokens == 0:
            # Calculate confidence interval based on confidence level
            margin = int(self.estimated_tokens * (1 - self.confidence) * 0.5)
            self.min_tokens = max(0, self.estimated_tokens - margin)
            self.max_tokens = self.estimated_tokens + margin


@dataclass
class TruncationResult:
    """Result of content truncation operation."""

    content: str
    original_tokens: int
    final_tokens: int
    truncated: bool
    truncation_summary: str


class TokenEstimator:
    """Estimates token usage for different types of content with tokenizer-specific ratios."""

    # Token estimation ratios (characters per token) by tokenizer type
    RATIOS = {
        TokenizerType.GENERIC: {
            ContentType.TEXT: 4.0,  # Regular text ~4 chars/token
            ContentType.CODE: 3.0,  # Code is more dense ~3 chars/token
            ContentType.STRUCTURED: 5.0,  # JSON/structured ~5 chars/token
            ContentType.DIFF: 2.5,  # Diffs are very dense ~2.5 chars/token
            ContentType.LOG: 3.5,  # Git logs ~3.5 chars/token
        },
        TokenizerType.OPENAI: {
            ContentType.TEXT: 3.8,  # OpenAI tokenizers are slightly more efficient
            ContentType.CODE: 2.8,
            ContentType.STRUCTURED: 4.5,
            ContentType.DIFF: 2.2,
            ContentType.LOG: 3.2,
        },
        TokenizerType.ANTHROPIC: {
            ContentType.TEXT: 4.2,  # Claude tokenizers handle text well
            ContentType.CODE: 3.2,
            ContentType.STRUCTURED: 5.2,
            ContentType.DIFF: 2.7,
            ContentType.LOG: 3.7,
        },
        TokenizerType.HUGGINGFACE: {
            ContentType.TEXT: 4.1,  # HuggingFace varies by model
            ContentType.CODE: 3.1,
            ContentType.STRUCTURED: 4.8,
            ContentType.DIFF: 2.6,
            ContentType.LOG: 3.6,
        },
    }

    def __init__(self, tokenizer_type: TokenizerType = TokenizerType.GENERIC):
        self.logger = logging.getLogger(f"{__name__}.TokenEstimator")
        self.tokenizer_type = tokenizer_type

    def estimate_tokens(
        self, content: str, content_type: ContentType = ContentType.TEXT
    ) -> TokenEstimate:
        """Estimate token count for given content.

        Args:
            content: The text content to analyze
            content_type: Type of content for appropriate ratio

        Returns:
            TokenEstimate with metadata
        """
        if not content:
            return TokenEstimate(
                0, 1.0, content_type, 0, 0, tokenizer_type=self.tokenizer_type
            )

        char_count = len(content)
        line_count = content.count("\n") + 1

        # Base estimation using tokenizer-specific character ratio
        ratio = self.RATIOS[self.tokenizer_type][content_type]
        base_tokens = char_count / ratio

        # Confidence adjustment based on content characteristics
        confidence = self._calculate_confidence(content, content_type)

        # Apply content-specific adjustments
        adjusted_tokens = self._apply_content_adjustments(
            base_tokens, content, content_type
        )

        return TokenEstimate(
            estimated_tokens=int(adjusted_tokens),
            confidence=confidence,
            content_type=content_type,
            char_count=char_count,
            line_count=line_count,
            tokenizer_type=self.tokenizer_type,
        )

    def _calculate_confidence(self, content: str, content_type: ContentType) -> float:
        """Calculate confidence level for token estimate."""
        # Higher confidence for shorter content
        length_factor = min(1.0, 1000 / len(content)) if content else 1.0

        # Content type confidence factors
        type_confidence = {
            ContentType.TEXT: 0.9,
            ContentType.CODE: 0.85,
            ContentType.STRUCTURED: 0.95,
            ContentType.DIFF: 0.8,
            ContentType.LOG: 0.85,
        }

        return length_factor * type_confidence.get(content_type, 0.8)

    def _apply_content_adjustments(
        self, base_tokens: float, content: str, content_type: ContentType
    ) -> float:
        """Apply content-specific adjustments to base token estimate."""
        if content_type == ContentType.DIFF:
            # Diffs with lots of context lines are more token-dense
            context_lines = content.count("@@")
            if context_lines > 10:
                return base_tokens * 0.9  # More efficient for large diffs

        elif content_type == ContentType.CODE:
            # Code with lots of whitespace is less token-dense
            whitespace_ratio = len(re.findall(r"\s+", content)) / len(content)
            if whitespace_ratio > 0.3:
                return base_tokens * 1.1  # Account for whitespace tokens

        elif content_type == ContentType.STRUCTURED:
            # JSON/structured data efficiency
            if "{" in content and "}" in content:
                return base_tokens * 0.95  # JSON is typically efficient

        return base_tokens


class ContentTruncator(ABC):
    """Abstract base class for content truncation strategies."""

    @abstractmethod
    def truncate(
        self, content: str, max_tokens: int, estimator: TokenEstimator
    ) -> TruncationResult:
        """Truncate content to fit within token limit."""
        pass


class GenericTruncator(ContentTruncator):
    """Generic truncation strategy for unknown content types."""

    def truncate(
        self, content: str, max_tokens: int, estimator: TokenEstimator
    ) -> TruncationResult:
        """Simple truncation keeping first portion of content."""
        original_estimate = estimator.estimate_tokens(content)

        if original_estimate.estimated_tokens <= max_tokens:
            return TruncationResult(
                content=content,
                original_tokens=original_estimate.estimated_tokens,
                final_tokens=original_estimate.estimated_tokens,
                truncated=False,
                truncation_summary="",
            )

        # Binary search for the right content size
        min_chars = 0
        max_chars = len(content)
        truncated_content = ""

        while min_chars <= max_chars:
            mid_chars = (min_chars + max_chars) // 2

            # Find good breaking point (prefer line boundaries)
            test_content = content[:mid_chars]
            lines = test_content.split("\n")
            if len(lines) > 1 and mid_chars < len(content):
                test_content = "\n".join(lines[:-1])  # Remove incomplete line

            # Test with the truncation message included
            remaining_lines = content[len(test_content) :].count("\n")
            test_msg = (
                f"\n\n[Truncated: {remaining_lines} lines omitted to fit token limit]"
            )
            full_test_content = test_content + test_msg
            test_tokens = estimator.estimate_tokens(full_test_content).estimated_tokens

            if test_tokens <= max_tokens:
                truncated_content = test_content
                min_chars = mid_chars + 1
            else:
                max_chars = mid_chars - 1

        # Add truncation message
        remaining_lines = content[len(truncated_content) :].count("\n")
        truncation_msg = (
            f"\n\n[Truncated: {remaining_lines} lines omitted to fit token limit]"
        )
        final_content = truncated_content + truncation_msg

        final_estimate = estimator.estimate_tokens(final_content)

        return TruncationResult(
            content=final_content,
            original_tokens=original_estimate.estimated_tokens,
            final_tokens=final_estimate.estimated_tokens,
            truncated=True,
            truncation_summary=f"Truncated {remaining_lines} lines",
        )


class DiffTruncator(ContentTruncator):
    """Intelligent truncation for git diff output."""

    def truncate(
        self, content: str, max_tokens: int, estimator: TokenEstimator
    ) -> TruncationResult:
        """Truncate diff content while preserving file headers and important context."""
        original_estimate = estimator.estimate_tokens(content, ContentType.DIFF)

        if original_estimate.estimated_tokens <= max_tokens:
            return TruncationResult(
                content=content,
                original_tokens=original_estimate.estimated_tokens,
                final_tokens=original_estimate.estimated_tokens,
                truncated=False,
                truncation_summary="",
            )

        lines = content.split("\n")
        result_lines = []
        files_processed = 0
        files_truncated = 0
        total_files = len([line for line in lines if line.startswith("diff --git")])

        # Reserve tokens for truncation summary
        sample_summary = "\n\n[Diff truncated: showing 99 files, 99 files omitted to fit token limit]"
        summary_tokens = estimator.estimate_tokens(
            sample_summary, ContentType.DIFF
        ).estimated_tokens
        available_tokens = max_tokens - summary_tokens

        # First pass: collect all file headers to ensure we can show at least basic structure
        file_headers = []
        i = 0
        current_file_lines = []

        while i < len(lines):
            line = lines[i]

            if line.startswith("diff --git"):
                # Save previous file if exists
                if current_file_lines:
                    file_headers.append(current_file_lines)
                current_file_lines = [line]
                files_processed += 1

            elif line.startswith(("index ", "---", "+++")) and current_file_lines:
                current_file_lines.append(line)
            else:
                # This is content - if we have headers, save the file structure
                if current_file_lines and line.startswith("@@"):
                    current_file_lines.append(line)
                break  # Stop collecting headers once we hit content
            i += 1

        # Save last file headers
        if current_file_lines:
            file_headers.append(current_file_lines)

        # Build result prioritizing file structure
        for file_header in file_headers:
            test_content = "\n".join(result_lines + file_header)
            if (
                estimator.estimate_tokens(
                    test_content, ContentType.DIFF
                ).estimated_tokens
                <= available_tokens
            ):
                result_lines.extend(file_header)
            else:
                files_truncated += 1
                break

        # Add some content if there's room
        remaining_budget = (
            available_tokens
            - estimator.estimate_tokens(
                "\n".join(result_lines), ContentType.DIFF
            ).estimated_tokens
        )

        if remaining_budget > 50:  # Only add content if we have reasonable room
            i = 0
            while i < len(lines):
                line = lines[i]

                if not any(
                    line.startswith(prefix)
                    for prefix in ["diff --git", "index ", "---", "+++"]
                ):
                    test_content = "\n".join(result_lines + [line])
                    if (
                        estimator.estimate_tokens(
                            test_content, ContentType.DIFF
                        ).estimated_tokens
                        <= available_tokens
                    ):
                        result_lines.append(line)
                    else:
                        break
                i += 1

        # Calculate files shown vs omitted
        files_shown = len(file_headers) - files_truncated
        files_omitted = total_files - files_shown

        # Add truncation summary
        truncation_msg = f"\n\n[Diff truncated: showing {files_shown} files"
        if files_omitted > 0:
            truncation_msg += f", {files_omitted} files omitted"
        truncation_msg += " to fit token limit]"

        final_content = "\n".join(result_lines) + truncation_msg
        final_estimate = estimator.estimate_tokens(final_content, ContentType.DIFF)

        return TruncationResult(
            content=final_content,
            original_tokens=original_estimate.estimated_tokens,
            final_tokens=final_estimate.estimated_tokens,
            truncated=True,
            truncation_summary=f"Truncated {files_omitted} of {total_files} files",
        )


class LogTruncator(ContentTruncator):
    """Intelligent truncation for git log output."""

    def truncate(
        self, content: str, max_tokens: int, estimator: TokenEstimator
    ) -> TruncationResult:
        """Truncate log content while preserving recent commits."""
        original_estimate = estimator.estimate_tokens(content, ContentType.LOG)

        if original_estimate.estimated_tokens <= max_tokens:
            return TruncationResult(
                content=content,
                original_tokens=original_estimate.estimated_tokens,
                final_tokens=original_estimate.estimated_tokens,
                truncated=False,
                truncation_summary="",
            )

        # Split by commits (looking for commit hashes - flexible format)
        commit_pattern = r"^commit [a-f0-9]+$"  # Accept any length hex hash
        lines = content.split("\n")
        commits = []
        current_commit = []

        for line in lines:
            if re.match(commit_pattern, line):
                if current_commit:  # Save previous commit if it exists
                    commits.append("\n".join(current_commit))
                current_commit = [line]  # Start new commit
            else:
                current_commit.append(line)

        if current_commit:
            commits.append("\n".join(current_commit))

        # Reserve tokens for truncation message
        sample_summary = "\n\n[Log truncated: showing 99 most recent commits, 99 older commits omitted]"
        summary_tokens = estimator.estimate_tokens(
            sample_summary, ContentType.LOG
        ).estimated_tokens
        available_tokens = max_tokens - summary_tokens

        # Keep recent commits that fit within token limit
        result_commits = []

        for commit in commits:
            test_content = "\n".join(result_commits + [commit])
            test_tokens = estimator.estimate_tokens(
                test_content, ContentType.LOG
            ).estimated_tokens
            if test_tokens <= available_tokens:
                result_commits.append(commit)
            else:
                break

        # Add truncation summary
        commits_shown = len(result_commits)
        commits_omitted = len(commits) - commits_shown

        final_content = "\n".join(result_commits)
        if commits_omitted > 0:
            final_content += f"\n\n[Log truncated: showing {commits_shown} most recent commits, {commits_omitted} older commits omitted]"

        final_estimate = estimator.estimate_tokens(final_content, ContentType.LOG)

        return TruncationResult(
            content=final_content,
            original_tokens=original_estimate.estimated_tokens,
            final_tokens=final_estimate.estimated_tokens,
            truncated=commits_omitted > 0,
            truncation_summary=f"Truncated {commits_omitted} of {len(commits)} commits",
        )


class IntelligentTruncationManager:
    """Manages intelligent truncation strategies for different content types."""

    def __init__(self):
        self.estimator = TokenEstimator()
        self.truncators = {
            "git_diff": DiffTruncator(),
            "git_diff_unstaged": DiffTruncator(),
            "git_diff_staged": DiffTruncator(),
            "git_diff_branches": DiffTruncator(),
            "git_show": DiffTruncator(),
            "git_log": LogTruncator(),
            # Add more operation-specific truncators as needed
        }
        self.default_truncator = GenericTruncator()
        self.logger = logging.getLogger(f"{__name__}.IntelligentTruncationManager")

    def truncate_for_operation(
        self, content: str, operation: str, max_tokens: int
    ) -> TruncationResult:
        """Truncate content using operation-specific strategy.

        Args:
            content: The content to truncate
            operation: The git operation that generated the content
            max_tokens: Maximum allowed tokens

        Returns:
            TruncationResult with optimized content
        """
        truncator = self.truncators.get(operation, self.default_truncator)

        try:
            result = truncator.truncate(content, max_tokens, self.estimator)

            if result.truncated:
                self.logger.info(
                    f"Truncated {operation} output: {result.original_tokens} -> {result.final_tokens} tokens"
                )

            return result

        except Exception as e:
            self.logger.error(f"Error truncating content for {operation}: {e}")
            # Fallback to generic truncation
            return self.default_truncator.truncate(content, max_tokens, self.estimator)


class ClientDetector:
    """Detects client types to apply appropriate optimizations."""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.ClientDetector")

        # Common LLM client identifiers
        self.llm_indicators = [
            "claude",
            "gpt",
            "openai",
            "anthropic",
            "llm",
            "ai-assistant",
            "chatgpt",
            "api-client",
        ]

    def detect_client_type(
        self, user_agent: str = "", request_metadata: dict = None
    ) -> ClientType:
        """Detect client type based on available metadata.

        Args:
            user_agent: User-Agent header value
            request_metadata: Additional request metadata

        Returns:
            Detected client type
        """
        if not user_agent and not request_metadata:
            return ClientType.UNKNOWN

        # Check user agent for LLM indicators
        user_agent_lower = user_agent.lower()
        for indicator in self.llm_indicators:
            if indicator in user_agent_lower:
                self.logger.debug(f"Detected LLM client from user agent: {indicator}")
                return ClientType.LLM

        # Check for human browser indicators
        human_indicators = ["mozilla", "browser", "chrome", "firefox", "safari", "edge"]
        for indicator in human_indicators:
            if indicator in user_agent_lower:
                self.logger.debug(f"Detected human client from user agent: {indicator}")
                return ClientType.HUMAN

        # Check request metadata for additional clues
        if request_metadata:
            # Look for API client patterns
            if request_metadata.get("api_client"):
                return ClientType.LLM

            # Look for interactive session patterns
            if request_metadata.get("interactive"):
                return ClientType.HUMAN

        return ClientType.UNKNOWN
