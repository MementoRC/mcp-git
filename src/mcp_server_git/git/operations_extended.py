"""Extended git operations for MCP Git Server.

New tools added to avoid bloating operations.py (2284 lines, tracked in #139/#140).
"""

import logging
import os
import re

from ..utils.git_import import GitCommandError, Repo
from .error_text import clean_git_error_text
from .merge_parse import (
    parse_merge_tree_output,
    render_conflict_paths,
    render_tree_hint,
)

logger = logging.getLogger(__name__)

DANGEROUS_CHARS = re.compile(r"[;&|`$()]")

__all__ = [
    "git_restore",
    "git_branch_update",
    "git_branch_delete",
    "git_worktree_list",
    "git_worktree_remove",
    "git_worktree_add",
    "git_merge_tree",
    "git_rm",
]


def _validate_ref(ref: str, param_name: str) -> str | None:
    """Validate a git ref for dangerous characters. Returns error string or None."""
    if DANGEROUS_CHARS.search(ref):
        return f"❌ Invalid characters detected in {param_name}: '{ref}'"
    return None


# Re-exported for backward compatibility: moved to error_text.py (issue #219)
# so modules other than operations_extended.py can import it without pulling
# in this module's unrelated tool functions. merge_ops.py imports the
# private alias directly; keep it resolvable.
_clean_git_error_text = clean_git_error_text


def git_restore(
    repo: Repo,
    files: list[str],
    staged: bool = False,
    source: str | None = None,
) -> str:
    """Restore working tree files or unstage files."""
    if not files:
        return "❌ No files specified to restore"

    if source:
        error = _validate_ref(source, "source")
        if error:
            return error

    try:
        args = []
        if staged:
            args.append("--staged")
        if source:
            args.extend(["--source", source])
        args.extend(files)

        repo.git.restore(*args)

        mode = "unstaged" if staged else "restored"
        file_list = ", ".join(files[:5])
        suffix = f" (+{len(files) - 5} more)" if len(files) > 5 else ""
        return f"✅ Restored {len(files)} file(s): {file_list}{suffix} ({mode})"

    except GitCommandError as e:
        stderr = _clean_git_error_text(e.stderr, "stderr")
        return f"❌ Restore failed: {stderr}"
    except Exception as e:
        return f"❌ Error during restore: {str(e)}"


def git_branch_update(
    repo: Repo,
    branch_name: str,
    target: str | None = None,
    delete: bool = False,
    force: bool = False,
) -> str:
    """Force-update a branch ref or delete a branch."""
    error = _validate_ref(branch_name, "branch_name")
    if error:
        return error

    if target and delete:
        return "❌ Cannot specify both target and delete"
    if not target and not delete:
        return "❌ Must specify either target (force-update) or delete"

    if target:
        error = _validate_ref(target, "target")
        if error:
            return error

    try:
        if delete:
            flag = "-D" if force else "-d"
            repo.git.branch(flag, branch_name)
            return f"✅ Deleted branch '{branch_name}'"
        else:
            repo.git.branch("-f", branch_name, target)
            return f"✅ Updated branch '{branch_name}' → {target}"

    except GitCommandError as e:
        stderr = _clean_git_error_text(e.stderr, "stderr")
        return f"❌ Branch update failed: {stderr}"
    except Exception as e:
        return f"❌ Error updating branch: {str(e)}"


def git_branch_delete(
    repo: Repo,
    branch_name: str,
    force: bool = False,
) -> str:
    """Delete a local git branch by delegating to git_branch_update.

    force=True uses -D (delete even if unmerged), else -d (safe delete).
    """
    return git_branch_update(repo, branch_name, delete=True, force=force)


def git_worktree_list(repo: Repo) -> str:
    """List all worktrees in the repository."""
    try:
        output = repo.git.worktree("list", "--porcelain")

        if not output.strip():
            return "No worktrees found"

        worktrees = []
        current = {}
        for line in output.split("\n"):
            if line.startswith("worktree "):
                if current:
                    worktrees.append(current)
                current = {"path": line[9:]}
            elif line.startswith("HEAD "):
                current["head"] = line[5:13]  # Short SHA (8 chars)
            elif line.startswith("branch "):
                current["branch"] = line[7:].replace("refs/heads/", "")
            elif line == "bare":
                current["bare"] = True
            elif line == "detached":
                current["detached"] = True

        if current:
            worktrees.append(current)

        lines = [f"Worktrees ({len(worktrees)}):"]
        for wt in worktrees:
            branch = wt.get("branch", "detached" if wt.get("detached") else "bare")
            head = wt.get("head", "???")
            lines.append(f"  {wt['path']} [{branch}] ({head})")

        return "\n".join(lines)

    except GitCommandError as e:
        stderr = _clean_git_error_text(e.stderr, "stderr")
        return f"❌ Failed to list worktrees: {stderr}"
    except Exception as e:
        return f"❌ Error listing worktrees: {str(e)}"


def git_worktree_remove(
    repo: Repo,
    worktree_path: str,
    force: bool = False,
) -> str:
    """Remove a worktree."""
    if DANGEROUS_CHARS.search(worktree_path):
        return f"❌ Invalid characters in worktree path: '{worktree_path}'"

    try:
        args = ["remove"]
        if force:
            args.append("--force")
        args.append(worktree_path)

        repo.git.worktree(*args)
        return f"✅ Removed worktree: {worktree_path}"

    except GitCommandError as e:
        stderr = _clean_git_error_text(e.stderr, "stderr")
        return f"❌ Failed to remove worktree: {stderr}"
    except Exception as e:
        return f"❌ Error removing worktree: {str(e)}"


def git_worktree_add(
    repo: Repo,
    worktree_path: str,
    branch: str | None = None,
    new_branch: str | None = None,
    commit_ish: str | None = None,
    force: bool = False,
) -> str:
    """Create a new linked worktree at `worktree_path`.

    Wraps `git worktree add`. Supported modes:
    - nothing set: detached HEAD at current HEAD
    - branch only: check out the existing branch
    - new_branch only: create new_branch from HEAD (uses -b, or -B with force)
    - new_branch + commit_ish: create new_branch from that start point
    - new_branch + branch: legacy form of the above (commit_ish wins if both)
    - commit_ish only: detached HEAD at that commit-ish
    """
    if DANGEROUS_CHARS.search(worktree_path):
        return f"❌ Invalid characters in worktree path: '{worktree_path}'"
    if branch and DANGEROUS_CHARS.search(branch):
        return f"❌ Invalid characters in branch: '{branch}'"
    if new_branch and DANGEROUS_CHARS.search(new_branch):
        return f"❌ Invalid characters in new_branch: '{new_branch}'"
    if commit_ish and DANGEROUS_CHARS.search(commit_ish):
        return f"❌ Invalid characters in commit_ish: '{commit_ish}'"

    if commit_ish and branch and not new_branch:
        return (
            "❌ commit_ish and branch are mutually exclusive unless new_branch "
            "is set: 'branch' checks out an existing branch, 'commit_ish' "
            "creates a detached worktree."
        )

    try:
        start_point = commit_ish if commit_ish is not None else branch

        args = ["add"]
        if force:
            args.append("--force")
        if new_branch:
            args.append("-B" if force else "-b")
            args.append(new_branch)
        args.append(worktree_path)
        if start_point:
            args.append(start_point)

        repo.git.worktree(*args)

        if new_branch:
            suffix = f" (new branch {new_branch}"
            suffix += f" from {start_point})" if start_point else ")"
        elif branch:
            suffix = f" (branch {branch})"
        elif commit_ish:
            suffix = f" (detached HEAD at {commit_ish})"
        else:
            suffix = " (detached HEAD)"
        return f"✅ Worktree added at {worktree_path}{suffix}"

    except GitCommandError as e:
        stderr = _clean_git_error_text(e.stderr, "stderr")
        return f"❌ Failed to add worktree: {stderr}"
    except Exception as e:
        return f"❌ Error adding worktree: {str(e)}"


def git_merge_tree(
    repo: Repo,
    branch1: str,
    branch2: str,
) -> str:
    """Simulate a merge without modifying working tree (dry-run conflict detection).

    Uses `git merge-tree --write-tree` (Git 2.38+) for three-way merge simulation.
    `branch2` accepts a raw SHA (unlike `git_diff_branches`). On success, the
    merged tree's OID is returned so any file -- conflict markers included --
    can be read via `git_show(revision="<oid>:<path>")` with no checkout.
    """
    error = _validate_ref(branch1, "branch1")
    if error:
        return error
    error = _validate_ref(branch2, "branch2")
    if error:
        return error

    try:
        output = repo.git.merge_tree("--write-tree", branch1, branch2)
        result = parse_merge_tree_output(output)
        lines = [f"✅ Clean merge: {branch1} + {branch2} → no conflicts"]
        if result.tree_oid:
            lines.extend(render_tree_hint(result.tree_oid))
        else:
            lines.append(output)
        return "\n".join(lines)

    except GitCommandError as e:
        stdout = _clean_git_error_text(e.stdout, "stdout")
        stderr = _clean_git_error_text(e.stderr, "stderr")

        # Exit code 1 = conflicts detected (expected behavior, not an error)
        if e.status == 1:
            result = parse_merge_tree_output(stdout)
            if not result.messages:
                return f"⚠️ Conflicts detected merging {branch1} + {branch2}\n{stdout}"

            lines = [f"⚠️ Conflicts detected merging {branch1} + {branch2}:"]
            lines.extend(f"  - {message}" for message in result.messages)
            if result.tree_oid:
                lines.extend(render_tree_hint(result.tree_oid))
            lines.extend(render_conflict_paths(result))
            return "\n".join(lines)

        return f"❌ Merge-tree failed: {stderr or stdout}"

    except Exception as e:
        return f"❌ Error during merge-tree: {str(e)}"


# Dangerous-path blocklist for git_rm: reject wildcards, directories, bare '.'
_UNSAFE_PATH = re.compile(r"[*?\[\]{}]")


def git_rm(
    repo: Repo,
    file: str,
    cached: bool = False,
    dry_run: bool = False,
) -> str:
    """Remove a single, explicitly-named file from the working tree and index.

    Safety: rejects wildcards, '.', '..', absolute paths, and trailing '/'.

    Examples::

        git_rm(repo, "old_module.py")           # remove from tree + index
        git_rm(repo, "old_module.py", cached=True)  # untrack, keep on disk
        git_rm(repo, "old_module.py", dry_run=True)  # preview only
    """
    if not file or not file.strip():
        return "❌ No file specified"

    file = file.strip()

    # Check trailing slash before normpath strips it
    if file.endswith("/"):
        return "❌ Directory removal not supported. Specify an explicit file path."

    # Normalize path to collapse ./, ../, and redundant separators
    file = os.path.normpath(file)

    # Block current/parent dir (also catches paths that normalize to . or ..)
    if file in (".", ".."):
        return "❌ Refusing to remove '.' or '..'. Specify an explicit file path."

    # Block absolute paths to prevent accidental system file removal
    if os.path.isabs(file):
        return (
            "❌ Absolute paths not allowed. Use a path relative to the repository root."
        )

    if _UNSAFE_PATH.search(file):
        return "❌ Wildcards/globs not allowed. Specify an explicit file path."

    if DANGEROUS_CHARS.search(file):
        return f"❌ Invalid characters detected in file path: '{file}'"

    try:
        args = []
        if cached:
            args.append("--cached")
        if dry_run:
            args.append("--dry-run")
        args.append("--")
        args.append(file)

        output = repo.git.rm(*args)

        if dry_run:
            return f"🔍 Dry-run: would remove '{file}'\n{output}"

        mode = "from index (kept on disk)" if cached else "from working tree and index"
        return f"✅ Removed '{file}' {mode}"

    except GitCommandError as e:
        stderr = _clean_git_error_text(e.stderr, "stderr")
        if "did not match any files" in stderr:
            return f"❌ File not found: '{file}' is not tracked by git"
        if "has local modifications" in stderr or "has changes staged" in stderr:
            return f"❌ File '{file}' has uncommitted changes. Stage or stash first, or use force."
        return f"❌ git rm failed: {stderr}"
    except Exception as e:
        return f"❌ Error during git rm: {str(e)}"
