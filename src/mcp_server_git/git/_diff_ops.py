"""Diff operations for MCP Git Server."""

import logging
import re

from ..utils.git_import import GitCommandError, Repo
from .error_text import clean_git_error_text

logger = logging.getLogger(__name__)

__all__ = [
    "_validate_commit_range",
    "_validate_diff_parameters",
    "_apply_diff_size_limiting",
    "git_diff_unstaged",
    "git_diff_staged",
    "git_diff",
    "git_diff_branches",
]


def _validate_commit_range(commit_range: str) -> tuple[bool, str]:
    """Validate commit range format and return (is_valid, error_message)

    Supported formats:
    - commit1..commit2 (range between commits)
    - commit1...commit2 (symmetric difference)
    - HEAD~1..HEAD (relative references)
    - branch1..branch2 (branch ranges)
    """
    if not commit_range or not commit_range.strip():
        return False, "Commit range cannot be empty"

    # Patterns that should pass without warnings
    valid_patterns = [
        # Git commit hashes (6+ hex characters)
        r"^[a-fA-F0-9]{6,40}\.{2,3}[a-fA-F0-9]{6,40}$",
        # HEAD references with optional tilde notation
        r"^HEAD~?\d*\.{2,3}HEAD~?\d*$",
        # Branch name patterns (common patterns only - conservative)
        r"^[a-zA-Z][a-zA-Z0-9_]{1,}\.{2,3}[a-zA-Z][a-zA-Z0-9_]{1,}$",
        r"^(main|master|develop|dev|production|prod|staging|stage|test|release-v\d+\.\d+)\.{2,3}[a-zA-Z][a-zA-Z0-9_\-\.]{1,}$",
        r"^[a-zA-Z][a-zA-Z0-9_\-\.]{1,}\.{2,3}(main|master|develop|dev|production|prod|staging|stage|test)$",
        # Feature/release branch patterns with slashes
        r"^(feature|bugfix|hotfix|release)/[a-zA-Z0-9\-_\.]+\.{2,3}[a-zA-Z][a-zA-Z0-9_/\-\.]*$",
        r"^[a-zA-Z][a-zA-Z0-9_/\-\.]*\.{2,3}(feature|bugfix|hotfix|release)/[a-zA-Z0-9\-_\.]+$",
        # Mixed patterns - hash with branches (minimum reasonable lengths)
        r"^[a-fA-F0-9]{6,40}\.{2,3}[a-zA-Z][a-zA-Z0-9_/\-\.]{1,}$",
        r"^[a-zA-Z][a-zA-Z0-9_/\-\.]{1,}\.{2,3}[a-fA-F0-9]{6,40}$",
        # HEAD with branches/hashes (minimum reasonable lengths)
        r"^HEAD~?\d*\.{2,3}[a-zA-Z][a-zA-Z0-9_/\-\.]{1,}$",
        r"^[a-zA-Z][a-zA-Z0-9_/\-\.]{1,}\.{2,3}HEAD~?\d*$",
        r"^HEAD~?\d*\.{2,3}[a-fA-F0-9]{6,40}$",
        r"^[a-fA-F0-9]{6,40}\.{2,3}HEAD~?\d*$",
    ]

    range_patterns = valid_patterns

    commit_range = commit_range.strip()

    # Check against known patterns
    for pattern in range_patterns:
        if re.match(pattern, commit_range):
            return True, ""

    # Check for obvious injection attempts
    dangerous_chars = [";", "|", "&", "`", "$", "(", ")"]
    if any(char in commit_range for char in dangerous_chars):
        return False, f"Invalid characters detected in commit range: {commit_range}"

    # If no pattern matches, it might still be valid (git is flexible)
    # But warn about unusual format
    return (
        True,
        f"Warning: Unusual commit range format '{commit_range}' - proceed with caution",
    )


def _validate_diff_parameters(
    target: str | None = None,
    commit_range: str | None = None,
    base_commit: str | None = None,
    target_commit: str | None = None,
) -> tuple[bool, str]:
    """Validate that diff parameters are not conflicting or ambiguous"""
    provided_params = []
    if target:
        provided_params.append("target")
    if commit_range:
        provided_params.append("commit_range")
    if base_commit and target_commit:
        provided_params.append("base_commit + target_commit")
    elif base_commit or target_commit:
        return False, "Both base_commit and target_commit must be provided together"

    if len(provided_params) > 1:
        return (
            False,
            f"Conflicting diff parameters: {', '.join(provided_params)}. Use only one method to specify what to diff.",
        )

    # Validate commit_range format if provided
    if commit_range:
        is_valid, error_msg = _validate_commit_range(commit_range)
        if not is_valid:
            return False, f"Invalid commit_range: {error_msg}"
        elif error_msg:  # Warning case
            return True, error_msg

    return True, ""


def _apply_diff_size_limiting(
    diff_output: str,
    operation_name: str,
    stat_only: bool = False,
    max_lines: int | None = None,
) -> str:
    """Apply size limiting to diff outputs with consistent formatting"""
    if not diff_output.strip():
        return f"No changes detected in {operation_name}"

    if stat_only:
        # This should be handled by the caller using --stat flag
        return diff_output

    # Apply line limit if specified
    if max_lines and max_lines > 0:
        lines = diff_output.split("\n")
        if len(lines) > max_lines:
            truncated_output = "\n".join(lines[:max_lines])
            truncated_output += (
                f"\n\n... [Truncated: showing {max_lines} of {len(lines)} lines]"
            )
            truncated_output += "\nUse stat_only=true for summary or increase max_lines for more content"
            return truncated_output

    # Check if output is extremely large and warn
    if len(diff_output) > 50000:  # 50KB threshold
        lines_count = len(diff_output.split("\n"))
        warning = f"⚠️  Large diff detected ({lines_count} lines, ~{len(diff_output) // 1000}KB)\n"
        warning += "Consider using stat_only=true for summary or max_lines parameter to limit output\n\n"
        return warning + diff_output

    return diff_output


def git_diff_unstaged(
    repo: Repo,
    stat_only: bool = False,
    max_lines: int | None = None,
    name_only: bool = False,
    paths: list[str] | None = None,
) -> str:
    """Get unstaged changes diff with file-specific and advanced options"""
    try:
        # Build git diff arguments
        diff_args = []

        # Add options based on parameters
        if name_only:
            diff_args.append("--name-only")
        elif stat_only:
            diff_args.append("--stat")

        # Add specific paths if provided
        if paths:
            diff_args.extend(["--"] + paths)

        # Execute git diff with arguments
        diff_output = repo.git.diff(*diff_args)

        # Handle name-only output
        if name_only:
            return (
                f"Files with unstaged changes:\n{diff_output}"
                if diff_output.strip()
                else "No unstaged changes"
            )

        # Handle stat-only output
        if stat_only:
            return (
                f"Unstaged changes summary:\n{diff_output}"
                if diff_output.strip()
                else "No unstaged changes"
            )

        # Apply size limiting for full diff output
        return _apply_diff_size_limiting(
            diff_output, "unstaged changes", stat_only, max_lines
        )

    except GitCommandError as e:
        return f"❌ Diff unstaged failed: {clean_git_error_text(e.stderr, 'stderr')}"
    except Exception as e:
        return f"❌ Diff unstaged error: {str(e)}"


def git_diff_staged(
    repo: Repo,
    stat_only: bool = False,
    max_lines: int | None = None,
    name_only: bool = False,
    paths: list[str] | None = None,
) -> str:
    """Get staged changes diff with file-specific and advanced options"""
    try:
        # Build git diff arguments
        diff_args = ["--cached"]

        # Add options based on parameters
        if name_only:
            diff_args.append("--name-only")
        elif stat_only:
            diff_args.append("--stat")

        # Add specific paths if provided
        if paths:
            diff_args.extend(["--"] + paths)

        # Execute git diff with arguments
        diff_output = repo.git.diff(*diff_args)

        # Handle name-only output
        if name_only:
            return (
                f"Files with staged changes:\n{diff_output}"
                if diff_output.strip()
                else "No staged changes"
            )

        # Handle stat-only output
        if stat_only:
            return (
                f"Staged changes summary:\n{diff_output}"
                if diff_output.strip()
                else "No staged changes"
            )

        # Apply size limiting for full diff output
        return _apply_diff_size_limiting(
            diff_output, "staged changes", stat_only, max_lines
        )

    except GitCommandError as e:
        return f"❌ Diff staged failed: {clean_git_error_text(e.stderr, 'stderr')}"
    except Exception as e:
        return f"❌ Diff staged error: {str(e)}"


def git_diff(
    repo: Repo,
    target: str | None = None,
    stat_only: bool = False,
    max_lines: int | None = None,
    name_only: bool = False,
    commit_range: str | None = None,
    base_commit: str | None = None,
    target_commit: str | None = None,
    paths: list[str] | None = None,
) -> str:
    """Get diff with advanced options including commit ranges and file filtering.

    Parameter Precedence (mutually exclusive - only one method should be used):
    1. commit_range: Use git range syntax like "HEAD~1..HEAD" or "main..develop"
    2. base_commit + target_commit: Compare two specific commits/branches
    3. target: Compare working tree against specific branch/commit (default behavior)
    4. None: Compare working tree against HEAD (fallback)

    Args:
        repo: Git repository object
        target: Branch/commit to diff against (conflicts with commit_range or base_commit/target_commit)
        stat_only: Show only file change statistics, not content
        max_lines: Limit output to specified number of lines (overridden by name_only/stat_only)
        name_only: Show only names of changed files
        commit_range: Git range syntax like "HEAD~1..HEAD" (conflicts with other diff methods)
        base_commit: Starting commit for comparison (requires target_commit)
        target_commit: Ending commit for comparison (requires base_commit)
        paths: Filter diff to specific files/directories

    Returns:
        Formatted diff output with validation warnings if applicable

    Raises:
        Returns error message if parameters are conflicting or invalid
    """
    # Validate parameters for conflicts and security
    is_valid, validation_msg = _validate_diff_parameters(
        target=target,
        commit_range=commit_range,
        base_commit=base_commit,
        target_commit=target_commit,
    )
    if not is_valid:
        return f"❌ Parameter validation failed: {validation_msg}"

    # If there's a warning, include it in the output
    validation_warning = validation_msg if validation_msg and is_valid else None
    try:
        # Build git diff arguments
        diff_args = []

        # Determine what we're diffing
        diff_description = ""

        if commit_range:
            # Use commit range syntax like "HEAD~1..HEAD"
            diff_args.append(commit_range)
            diff_description = f"commit range {commit_range}"
        elif base_commit and target_commit:
            # Compare two specific commits
            diff_args.extend([base_commit, target_commit])
            diff_description = f"{base_commit}...{target_commit}"
        elif target:
            # Compare against target branch/commit (original behavior)
            diff_args.append(target)
            diff_description = f"against {target}"
        else:
            # Default to comparing working tree against HEAD
            diff_args.append("HEAD")
            diff_description = "against HEAD"

        # Add options based on parameters
        if name_only:
            diff_args.append("--name-only")
        elif stat_only:
            diff_args.append("--stat")

        # Add specific paths if provided
        if paths:
            diff_args.extend(["--"] + paths)

        # Execute git diff with arguments
        diff_output = repo.git.diff(*diff_args)

        # Handle name-only output
        if name_only:
            result = (
                f"Changed files {diff_description}:\n{diff_output}"
                if diff_output.strip()
                else f"No changes {diff_description}"
            )
            if validation_warning:
                result = f"⚠️ {validation_warning}\n\n{result}"
            return result

        # Handle stat-only output
        if stat_only:
            result = (
                f"Diff {diff_description} summary:\n{diff_output}"
                if diff_output.strip()
                else f"No differences {diff_description}"
            )
            if validation_warning:
                result = f"⚠️ {validation_warning}\n\n{result}"
            return result

        # Apply size limiting for full diff output
        result = _apply_diff_size_limiting(
            diff_output, f"diff {diff_description}", stat_only, max_lines
        )
        if validation_warning:
            result = f"⚠️ {validation_warning}\n\n{result}"
        return result

    except GitCommandError as e:
        return f"❌ Diff failed: {clean_git_error_text(e.stderr, 'stderr')}"
    except Exception as e:
        return f"❌ Diff error: {str(e)}"


def git_diff_branches(
    repo: Repo,
    base_branch: str,
    compare_branch: str,
    stat_only: bool = False,
    max_lines: int | None = None,
) -> str:
    """Show differences between two branches with size limiting options"""
    try:
        # Verify branches exist - support both short names and full remote refs
        # Special refs like HEAD are always valid
        special_refs = ["HEAD", "FETCH_HEAD", "ORIG_HEAD", "MERGE_HEAD"]

        local_branches = [branch.name for branch in repo.branches]

        # Add remote branches if remotes exist (with error handling)
        try:
            remote_refs = repo.remote().refs
            # Include both full remote ref names (e.g., 'origin/development')
            # and short names (e.g., 'development') for compatibility
            remote_branch_names = [ref.name for ref in remote_refs]
            remote_branch_short_names = [ref.name.split("/")[-1] for ref in remote_refs]
            # Use set to avoid duplicates
            all_branches = set(
                local_branches
                + remote_branch_names
                + remote_branch_short_names
                + special_refs
            )
        except Exception:
            # Ignore remote access errors (e.g., no remotes configured)
            all_branches = set(local_branches + special_refs)

        if base_branch not in all_branches:
            return f"❌ Base branch '{base_branch}' not found"
        if compare_branch not in all_branches:
            return f"❌ Compare branch '{compare_branch}' not found"

        # Build diff command arguments
        diff_range = f"{base_branch}...{compare_branch}"

        if stat_only:
            # Return only file statistics
            diff_output = repo.git.diff("--stat", diff_range)
            if not diff_output.strip():
                return f"No differences between {base_branch} and {compare_branch}"
            return f"Diff statistics between {base_branch} and {compare_branch}:\n{diff_output}"

        # Get full diff
        diff_output = repo.git.diff(diff_range)

        if not diff_output.strip():
            return f"No differences between {base_branch} and {compare_branch}"

        # Apply line limit if specified
        if max_lines and max_lines > 0:
            lines = diff_output.split("\n")
            if len(lines) > max_lines:
                truncated_output = "\n".join(lines[:max_lines])
                truncated_output += (
                    f"\n\n... [Truncated: showing {max_lines} of {len(lines)} lines]"
                )
                truncated_output += "\nUse --stat flag for summary or increase max_lines for more content"
                return truncated_output

        # Check if output is extremely large and warn
        if len(diff_output) > 50000:  # 50KB threshold
            lines_count = len(diff_output.split("\n"))
            warning = f"⚠️  Large diff detected ({lines_count} lines, ~{len(diff_output) // 1000}KB)\n"
            warning += "Consider using stat_only=true for summary or max_lines parameter to limit output\n\n"
            return warning + diff_output

        return diff_output

    except GitCommandError as e:
        return f"❌ Diff failed: {clean_git_error_text(e.stderr, 'stderr')}"
    except Exception as e:
        return f"❌ Diff error: {str(e)}"
