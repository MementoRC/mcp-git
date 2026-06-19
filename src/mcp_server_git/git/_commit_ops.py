"""Commit, status, log, show, and blame operations for MCP Git Server."""

import logging
import os
import re
import subprocess

from ..utils.git_import import GitCommandError, Repo

logger = logging.getLogger(__name__)

__all__ = [
    "git_status",
    "git_commit",
    "git_log",
    "git_show",
    "git_blame",
    "git_reflog",
]


def git_status(repo: Repo, porcelain: bool = False) -> str:
    """Get repository status in either human-readable or machine-readable format.

    Args:
        repo: Git repository object
        porcelain: If True, return porcelain (machine-readable) format

    Returns:
        Status output string
    """
    if porcelain:
        return repo.git.status("--porcelain")
    else:
        return repo.git.status()


def git_commit(
    repo: Repo,
    message: str,
    amend: bool = False,  # If True, amend the most recent commit instead of creating new one
    gpg_sign: bool = False,
    gpg_key_id: str | None = None,
    allow_empty: bool = False,
) -> str:
    """Commit staged changes with optional amend, GPG signing and automatic security enforcement"""
    try:
        # Import security functions locally to avoid circular imports
        from .security import enforce_secure_git_config

        # 🔒 SECURITY: Enforce secure configuration before committing
        security_result = enforce_secure_git_config(repo, strict_mode=True)
        security_messages = []
        if "✅" in security_result:
            security_messages.append("🔒 Security configuration enforced")

        # Force GPG signing for all commits (SECURITY REQUIREMENT)
        force_gpg = True

        # Get GPG key from parameters, environment, or git config
        if gpg_key_id:
            force_key_id = gpg_key_id
        else:
            # Try environment variable first
            env_key = os.getenv("GPG_SIGNING_KEY")
            if env_key:
                force_key_id = env_key
            else:
                # Fall back to git config
                try:
                    config_key = repo.config_reader().get_value("user", "signingkey")
                    force_key_id = str(config_key)
                except Exception:
                    return "❌ Could not determine GPG signing key. Please configure GPG_SIGNING_KEY env var"

        if force_gpg:
            # Use git command directly for GPG signing
            cmd = ["git", "commit"]
            if amend:
                cmd.append("--amend")
            if allow_empty:
                cmd.append("--allow-empty")
            cmd.append(f"--gpg-sign={force_key_id}")
            cmd.extend(["-m", message])

            result = subprocess.run(
                cmd, cwd=repo.working_dir, capture_output=True, text=True
            )
            if result.returncode == 0:
                # Get the commit hash from git log
                hash_result = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=repo.working_dir,
                    capture_output=True,
                    text=True,
                )
                commit_hash = (
                    hash_result.stdout.strip()[:8]
                    if hash_result.returncode == 0
                    else "unknown"
                )

                action = "amended" if amend else "created"
                success_msg = (
                    f"✅ Commit {commit_hash} {action} with VERIFIED GPG signature"
                )
                if security_messages:
                    success_msg += f"\n{chr(10).join(security_messages)}"

                # Add security reminder
                success_msg += f"\n🔒 Enforced GPG signing with key {force_key_id}"
                success_msg += (
                    "\n⚠️  MCP Git Server used - no fallback to system git commands"
                )

                return success_msg
            else:
                return f"❌ Commit failed: {result.stderr}\n🔒 GPG signing was enforced but failed"
        else:
            # This path should never be reached due to force_gpg=True
            return "❌ SECURITY VIOLATION: Unsigned commits are not allowed by MCP Git Server"

    except GitCommandError as e:
        return f"❌ Commit failed: {str(e)}\n🔒 Security enforcement may have prevented insecure operation"
    except Exception as e:
        return f"❌ Commit error: {str(e)}\n🔒 Verify repository security configuration"


def git_log(
    repo: Repo,
    max_count: int = 10,
    oneline: bool = False,
    graph: bool = False,
    format_str: str | None = None,  # Renamed from 'format'
    since: str | None = None,
    until: str | None = None,
    author: str | None = None,
    grep: str | None = None,
    files: list[str] | None = None,
    branch: str | None = None,
    reverse: bool = False,
    merges: bool | None = None,
) -> str:
    """Get commit history with advanced filtering and formatting options

    Args:
        repo: Git repository object
        max_count: Maximum number of commits to show (default: 10)
        oneline: Compact "hash message" format (equivalent to --oneline)
        graph: Show merge graph (--graph)
        format_str: Custom format string (e.g., "%h - %s (%an)")
        since: Date filter - commits after this date (e.g., "2024-01-01", "1 week ago")
        until: Date filter - commits before this date (e.g., "yesterday", "2024-12-31")
        author: Filter by commit author (email or name)
        grep: Search commit messages (regex pattern)
        files: Commits affecting specific files (list of file paths)
        branch: Specific branch to show log for (default: current branch)
        reverse: Reverse chronological order (oldest first)
        merges: Filter merge commits (None=all, True=only merges, False=no merges)

    Returns:
        Formatted commit log output
    """
    try:
        args = []

        # Add branch if specified
        if branch:
            args.append(branch)

        # Add count limit
        if max_count is not None and max_count > 0:
            args.extend(["-n", str(max_count)])

        # Add formatting options
        if oneline:
            args.append("--oneline")
        elif format_str:  # Use format_str
            args.extend(["--pretty=format:" + format_str])

        if graph:
            args.append("--graph")

        # Add date filters
        if since:
            args.extend(["--since", since])
        if until:
            args.extend(["--until", until])

        # Add author filter
        if author:
            args.extend(["--author", author])

        # Add message search
        if grep:
            args.extend(["--grep", grep])

        # Add merge commit filter
        if merges is True:
            args.append("--merges")
        elif merges is False:
            args.append("--no-merges")

        # Add reverse order
        if reverse:
            args.append("--reverse")

        # Add file paths if specified (must come after --)
        if files:
            args.append("--")
            args.extend(files)

        # Get commit log
        log_output = repo.git.log(*args)

        if not log_output.strip():
            return "No commits found matching the specified criteria"

        return log_output

    except GitCommandError as e:
        return f"❌ Log failed: {str(e)}"
    except Exception as e:
        return f"❌ Log error: {str(e)}"


def git_show(
    repo: Repo, revision: str, stat_only: bool = False, max_lines: int | None = None
) -> str:
    """Show commit details with diff and size limiting options"""
    try:
        if stat_only:
            # Return only commit info and file statistics
            show_output = repo.git.show("--stat", revision)
            return f"Commit details for {revision}:\n{show_output}"

        # Get full commit details
        show_output = repo.git.show(revision)

        # Apply line limit if specified
        if max_lines and max_lines > 0:
            lines = show_output.split("\n")
            if len(lines) > max_lines:
                truncated_output = "\n".join(lines[:max_lines])
                truncated_output += (
                    f"\n\n... [Truncated: showing {max_lines} of {len(lines)} lines]"
                )
                truncated_output += "\nUse stat_only=true for summary or increase max_lines for more content"
                return truncated_output

        # Check if output is extremely large and warn
        if len(show_output) > 50000:  # 50KB threshold
            lines_count = len(show_output.split("\n"))
            warning = f"⚠️  Large commit detected ({lines_count} lines, ~{len(show_output) // 1000}KB)\n"
            warning += "Consider using stat_only=true for summary or max_lines parameter to limit output\n\n"
            return warning + show_output

        return show_output

    except GitCommandError as e:
        return f"❌ Show failed: {str(e)}"
    except Exception as e:
        return f"❌ Show error: {str(e)}"


def git_blame(
    repo: Repo,
    file_path: str,
    line_start: int | None = None,
    line_end: int | None = None,
) -> str:
    """Show blame information for a file"""
    try:
        args = [file_path]
        if line_start and line_end:
            args.extend(["-L", f"{line_start},{line_end}"])
        elif line_start:
            args.extend(["-L", f"{line_start},+1"])

        blame_output = repo.git.blame(*args)
        return f"Blame for {file_path}:\n{blame_output}"
    except GitCommandError as e:
        return f"❌ Blame failed: {str(e)}"
    except Exception as e:
        return f"❌ Blame error: {str(e)}"


def git_reflog(
    repo: Repo,
    ref: str = "HEAD",
    max_count: int | None = None,
    all: bool = False,  # noqa: A002
) -> list[dict] | str:
    """Read git reflog (HEAD/ref movement history including non-commit operations).

    Args:
        repo: Git repository object
        ref: Ref to show reflog for (default: HEAD)
        max_count: Maximum number of entries to return
        all: If True, show reflog for all refs (--all)

    Returns:
        List of dicts with keys: new_sha, label, action, message, and
        old_sha (the SHA before this operation, derived from the next entry's
        new_sha since reflog is newest-first; absent for the oldest entry).
        Returns a string starting with '❌' on error.

    Note on old_sha:
        %gP (reflog parent selector) yields a reflog selector like 'HEAD@{1}',
        not a commit SHA. old_sha is instead taken from entry[i+1].new_sha,
        which is always the commit HEAD pointed to before entry[i]'s operation.

        old_sha is provided only for single-ref reflogs (all=False). Under
        all=True, entries from different refs are interleaved so the adjacent
        entry may belong to another ref, making derivation unreliable. old_sha
        is therefore omitted entirely when all=True.
    """
    try:
        # %H = new (post-move) full SHA, %gD = reflog selector (HEAD@{0}),
        # %gs = reflog subject (e.g. "checkout: moving from main to feature")
        # Note: %gP gives a reflog selector (HEAD@{N}), not a commit SHA,
        # so old_sha is derived from the next entry's new_sha instead.
        sep = "\x00"
        fmt = f"%H{sep}%gD{sep}%gs"

        args = ["show", f"--format={fmt}", "--no-abbrev", "--no-patch"]

        # max_count <= 0 (or None) means no limit; only positive values constrain.
        if max_count is not None and max_count > 0:
            args.extend(["-n", str(max_count)])

        if all:  # noqa: A002
            args.append("--all")
        else:
            args.append(ref)

        raw_output = repo.git.reflog(*args)

        if not raw_output.strip():
            return []

        entries = []
        for line in raw_output.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(sep)
            if len(parts) < 3:
                continue
            new_sha, label, subject = parts[0], parts[1], parts[2]

            # Derive action from subject: verb before ':', keeping any
            # parenthetical qualifier that immediately follows the verb.
            # Examples:
            #   "checkout: moving from A to B"    -> "checkout"
            #   "merge origin/main: Fast-forward" -> "merge"
            #   "commit (amend): fixup msg"        -> "commit (amend)"
            #   "rebase (start): checkout main"    -> "rebase (start)"
            #   "commit (initial import): msg"     -> "commit (initial import)"
            pre_colon = subject.split(":", 1)[0].strip() if subject else ""
            m = re.match(r'^(\w[\w-]*(?:\s+\([^)]*\))?)', pre_colon)
            action = m.group(1) if m else (pre_colon.split()[0] if pre_colon.split() else "unknown")

            entries.append({
                "new_sha": new_sha,
                "label": label,
                "action": action,
                "message": subject,
            })

        # old_sha for entry[i] = entry[i+1].new_sha (reflog is newest-first).
        # Only valid for single-ref reflogs; under all=True entries from different
        # refs are interleaved so skip derivation entirely.
        if not all:  # noqa: A002
            for i in range(len(entries) - 1):
                entries[i]["old_sha"] = entries[i + 1]["new_sha"]

        # Warn on large output, mirroring git_show's 50KB threshold.
        serialized_size = len(str(entries))
        if serialized_size > 50000:  # 50KB threshold
            entries.append({
                "warning": (
                    f"⚠️  Large reflog detected ({len(entries) - 1} entries, "
                    f"~{serialized_size // 1000}KB). "
                    "Consider using max_count to limit output."
                )
            })

        return entries

    except GitCommandError as e:
        return f"❌ Reflog failed: {str(e)}"
    except Exception as e:
        return f"❌ Reflog error: {str(e)}"
