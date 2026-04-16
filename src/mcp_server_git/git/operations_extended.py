"""Extended git operations for MCP Git Server.

New tools added to avoid bloating operations.py (2284 lines, tracked in #139/#140).
"""

import logging
import re

from ..utils.git_import import GitCommandError, Repo

logger = logging.getLogger(__name__)

DANGEROUS_CHARS = re.compile(r"[;&|`$()]")

__all__ = [
    "git_restore",
    "git_branch_update",
    "git_worktree_list",
    "git_worktree_remove",
    "git_merge_tree",
    "git_rm",
]


def _validate_ref(ref: str, param_name: str) -> str | None:
    """Validate a git ref for dangerous characters. Returns error string or None."""
    if DANGEROUS_CHARS.search(ref):
        return f"❌ Invalid characters detected in {param_name}: '{ref}'"
    return None


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
        return f"❌ Restore failed: {e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr}"
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
        stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr
        return f"❌ Branch update failed: {stderr}"
    except Exception as e:
        return f"❌ Error updating branch: {str(e)}"


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
        stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr
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
        stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr
        return f"❌ Failed to remove worktree: {stderr}"
    except Exception as e:
        return f"❌ Error removing worktree: {str(e)}"


def git_merge_tree(
    repo: Repo,
    branch1: str,
    branch2: str,
) -> str:
    """Simulate a merge without modifying working tree (dry-run conflict detection).

    Uses `git merge-tree --write-tree` (Git 2.38+) for three-way merge simulation.
    """
    error = _validate_ref(branch1, "branch1")
    if error:
        return error
    error = _validate_ref(branch2, "branch2")
    if error:
        return error

    try:
        output = repo.git.merge_tree("--write-tree", branch1, branch2)
        return f"✅ Clean merge: {branch1} + {branch2} → no conflicts\n{output}"

    except GitCommandError as e:
        stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")

        # Exit code 1 = conflicts detected (expected behavior, not an error)
        if e.status == 1:
            conflicts = [line for line in stdout.split("\n") if "CONFLICT" in line]
            if conflicts:
                conflict_list = "\n".join(f"  - {c}" for c in conflicts)
                return f"⚠️ Conflicts detected merging {branch1} + {branch2}:\n{conflict_list}"
            return f"⚠️ Conflicts detected merging {branch1} + {branch2}\n{stdout}"

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

    Safety: rejects wildcards, '.', '..', and directory separators ending in '/'.
    """
    if not file or not file.strip():
        return "❌ No file specified"

    file = file.strip()

    # Block directory-style paths and current/parent dir
    if file in (".", ".."):
        return "❌ Refusing to remove '.' or '..'. Specify an explicit file path."

    if file.endswith("/"):
        return "❌ Directory removal not supported. Specify an explicit file path."

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
        stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr
        return f"❌ git rm failed: {stderr}"
    except Exception as e:
        return f"❌ Error during git rm: {str(e)}"
