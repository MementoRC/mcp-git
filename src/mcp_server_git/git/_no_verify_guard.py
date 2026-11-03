"""Optional branch allowlist for ``git_commit(no_verify=True)`` (issue #330)."""

import fnmatch
import os
import subprocess

from ..utils.git_import import Repo
from ..utils.tool_failure import fail

__all__ = ["no_verify_refusal"]

_ENV_VAR = "MCP_GIT_NO_VERIFY_BRANCHES"


def _allowed_patterns() -> list[str]:
    """Patterns from the env var; empty when unset or blank."""
    raw = os.environ.get(_ENV_VAR, "")
    return [p.strip() for p in raw.split(",") if p.strip()]


def _current_branch(repo: Repo) -> str:
    """Short branch name, or '' on detached HEAD."""
    result = subprocess.run(
        ["git", "symbolic-ref", "--short", "-q", "HEAD"],
        cwd=repo.working_dir,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def no_verify_refusal(repo: Repo) -> str | None:
    """Failure message when no_verify is not allowed on this branch, else None."""
    patterns = _allowed_patterns()
    if not patterns:
        return None
    branch = _current_branch(repo)
    if branch and any(fnmatch.fnmatchcase(branch, p) for p in patterns):
        return None
    shown = branch or "(detached HEAD)"
    return fail(
        f"❌ no_verify refused on branch '{shown}': allowed only on branches "
        f"matching {', '.join(patterns)} ({_ENV_VAR})"
    )
