"""Rebase, merge, cherry-pick, abort, and continue operations for MCP Git Server."""

import logging
import os
import subprocess

from ..utils.git_import import GitCommandError, Repo
from ..utils.tool_failure import fail
from ._commit_ops import signing_enforced
from ._gpg import resolve_gpg_key
from ._merge_cmd import git_merge
from .error_text import clean_git_error_text

logger = logging.getLogger(__name__)

__all__ = [
    "git_rebase",
    "git_merge",
    "git_cherry_pick",
    "git_abort",
    "git_continue",
]


# Headless server: never let rebase (esp. --root/--rebase-merges) open an editor.
_NON_INTERACTIVE_ENV = {"GIT_SEQUENCE_EDITOR": "true", "GIT_EDITOR": "true"}


def _validate_rebase_params(
    onto: str | None,
    fork_point: str | None,
    branch: str | None,
    target_branch: str | None = None,
    root: bool = False,
) -> str | None:
    """Return an error message for invalid rebase ref parameters, else None."""
    dangerous_chars = [";", "|", "&", "`", "$", "(", ")"]
    for param_name, param_value in [
        ("target_branch", target_branch),
        ("onto", onto),
        ("fork_point", fork_point),
        ("branch", branch),
    ]:
        if param_value and param_value.startswith("-"):
            return fail(
                f"❌ {param_name} must not start with '-': '{param_value}' "
                "would be parsed as a git option"
            )
        if param_value and any(char in param_value for char in dangerous_chars):
            return fail(
                f"❌ Invalid characters detected in {param_name}: '{param_value}'"
            )

    if root:
        if target_branch or onto or fork_point:
            return fail(
                "❌ root cannot be combined with target_branch, onto or fork_point"
            )
        return None
    if not target_branch:
        return fail("❌ target_branch is required unless root=True")
    if onto and not fork_point:
        return fail("❌ --onto requires fork_point (the old base to rebase from)")
    if fork_point and not onto:
        return fail("❌ fork_point requires --onto (the new base to rebase onto)")
    return None


def _branch_exists(repo: Repo, name: str) -> bool:
    """Check local branches and remote refs (full and short names) for name."""
    all_branches = [b.name for b in repo.branches]
    try:
        if repo.remotes:
            for remote in repo.remotes:
                all_branches.extend([ref.name for ref in remote.refs])
                all_branches.extend([ref.name.split("/")[-1] for ref in remote.refs])
    except Exception:
        pass
    return name in all_branches


def _rebase_options(
    repo: Repo,
    root: bool,
    rebase_merges: bool,
    gpg_sign: bool,
    committer_date_is_author_date: bool,
) -> list[str] | str:
    """Option argv for ``git rebase``, or a failure string.

    Signing mirrors git_commit: when the server enforces it every rewritten
    commit is signed with the resolved key, whatever ``gpg_sign`` says.
    ``--root`` adds ``--force-rebase`` so the whole history is really replayed
    (and therefore re-signed) rather than fast-forwarded.
    """
    options: list[str] = []
    if root:
        options.extend(["--root", "--force-rebase"])
    if rebase_merges:
        options.append("--rebase-merges")
    if committer_date_is_author_date:
        options.append("--committer-date-is-author-date")
    if gpg_sign or signing_enforced():
        key, error = resolve_gpg_key(repo, None)
        if error:
            return error
        options.append(f"--gpg-sign={key}")
    return options


def _build_rebase_args(
    target_branch: str | None,
    onto: str | None,
    fork_point: str | None,
    branch: str | None,
    root: bool = False,
) -> list[str | None]:
    """Build the argument list for `git rebase` (after the options)."""
    if root or target_branch is None:
        return [branch] if branch else []
    if onto:
        args: list[str | None] = ["--onto", onto, fork_point]
        if branch:
            args.append(branch)
        return args
    if branch:
        return [target_branch, branch]
    return [target_branch]


def git_rebase(
    repo: Repo,
    target_branch: str | None = None,
    onto: str | None = None,
    fork_point: str | None = None,
    branch: str | None = None,
    root: bool = False,
    rebase_merges: bool = False,
    gpg_sign: bool = False,
    committer_date_is_author_date: bool = False,
) -> str:
    """Rebase current branch onto target branch (always non-interactive).

    Supports --onto for rebasing between bases:
        git rebase --onto <new_base> <old_fork_point> [<branch>]
    ``root=True`` replays the whole history (``--root``) and excludes
    target_branch/onto/fork_point. No ``--exec`` is exposed.
    """
    try:
        invalid = _validate_rebase_params(onto, fork_point, branch, target_branch, root)
        if invalid:
            return invalid

        # Get current branch for success message
        current_branch = repo.active_branch.name

        # Check if target branch exists (only when not using --onto/--root)
        if target_branch and not onto and not _branch_exists(repo, target_branch):
            return fail(f"❌ Target branch '{target_branch}' not found")

        options = _rebase_options(
            repo, root, rebase_merges, gpg_sign, committer_date_is_author_date
        )
        if isinstance(options, str):
            return options
        args = [
            *options,
            *_build_rebase_args(target_branch, onto, fork_point, branch, root),
        ]
        with repo.git.custom_environment(**_NON_INTERACTIVE_ENV):
            result = repo.git.rebase(*args)

        rebase_branch = branch or current_branch
        if root:
            return f"✅ Successfully rebased {rebase_branch} --root\n{result}"
        if onto:
            return f"✅ Successfully rebased {rebase_branch} --onto {onto} (from {fork_point})\n{result}"
        return f"✅ Successfully rebased {rebase_branch} onto {target_branch}\n{result}"

    except GitCommandError as e:
        error_text = clean_git_error_text(e.stderr, "stderr")
        if "conflict" in error_text.lower():
            return fail(
                "❌ Rebase failed due to conflicts. Resolve conflicts and run 'git rebase --continue'"
            )
        else:
            return fail(f"❌ Rebase failed: {error_text}")
    except Exception as e:
        return fail(f"❌ Rebase error: {str(e)}")


def _cherry_pick_options(
    repo: Repo, no_commit: bool, gpg_sign: bool, mainline: int | None
) -> list[str] | str:
    """Option argv for ``git cherry-pick``, or a failure string.

    Mirrors git_commit: when the server enforces signing every created commit
    is signed with the resolved key, whatever ``gpg_sign`` says. ``--no-commit``
    creates no commit, so nothing is signed then.
    """
    if mainline is not None and mainline < 1:
        return fail("❌ mainline must be a positive parent number (>= 1)")
    options: list[str] = []
    if no_commit:
        options.append("--no-commit")
    elif gpg_sign or signing_enforced():
        key, error = resolve_gpg_key(repo, None)
        if error:
            return error
        options.append(f"--gpg-sign={key}")
    if mainline is not None:
        options.extend(["--mainline", str(mainline)])
    return options


def git_cherry_pick(
    repo: Repo,
    commit_hash: str,
    no_commit: bool = False,
    gpg_sign: bool = False,
    mainline: int | None = None,
) -> str:
    """Cherry-pick commits (signed when signing is enforced; ``mainline`` = ``-m``)."""
    try:
        options = _cherry_pick_options(repo, no_commit, gpg_sign, mainline)
        if isinstance(options, str):
            return options
        cp_args = [*options, commit_hash]

        # Perform cherry-pick
        result = repo.git.cherry_pick(*cp_args)

        action = "staged" if no_commit else "cherry-picked"
        return f"✅ Successfully {action} commit {commit_hash[:8]}\n{result}"

    except GitCommandError as e:
        error_text = clean_git_error_text(e.stderr, "stderr")
        if "conflict" in error_text.lower():
            return fail(
                "❌ Cherry-pick failed due to conflicts. Resolve conflicts and continue"
            )
        else:
            return fail(f"❌ Cherry-pick failed: {error_text}")
    except Exception as e:
        return fail(f"❌ Cherry-pick error: {str(e)}")


def git_abort(repo: Repo, operation: str) -> str:
    """Abort ongoing operations (rebase, merge, cherry-pick)"""
    try:
        valid_operations = ["rebase", "merge", "cherry-pick"]
        if operation not in valid_operations:
            return fail(
                f"❌ Invalid operation '{operation}'. Valid operations: {', '.join(valid_operations)}"
            )

        # Perform abort using the same pattern as other operations
        if operation == "rebase":
            repo.git.rebase("--abort")
        elif operation == "merge":
            repo.git.merge("--abort")
        elif operation == "cherry-pick":
            repo.git.cherry_pick("--abort")

        return f"✅ Successfully aborted {operation}"

    except GitCommandError as e:
        return fail(
            f"❌ Abort {operation} failed: {clean_git_error_text(e.stderr, 'stderr')}"
        )
    except Exception as e:
        return fail(f"❌ Abort error: {str(e)}")


def _describe_continue_failure(
    result: subprocess.CompletedProcess[str], operation: str
) -> str:
    """Translate a failed `git <operation> --continue` into a helpful message."""
    # Failed - return stderr which contains the error message
    error_output = result.stderr.strip()
    if not error_output:
        error_output = result.stdout.strip()

    # Provide helpful error messages based on common scenarios
    if (
        "No rebase in progress" in error_output
        or "no merge in progress" in error_output
        or "no cherry-pick in progress" in error_output
    ):
        return fail(f"❌ No {operation} in progress to continue")
    elif "conflicts" in error_output.lower():
        return fail(
            f"❌ Unresolved conflicts remain. Resolve conflicts before continuing {operation}"
        )
    elif "nothing to commit" in error_output.lower():
        return fail(
            f"❌ No changes to commit. Add changes before continuing {operation}"
        )
    else:
        return fail(f"❌ Continue {operation} failed: {error_output}")


def git_continue(repo: Repo, operation: str) -> str:
    """Continue operations after resolving conflicts

    Uses subprocess instead of GitPython for interactive operations to avoid
    MCP client timeout issues (issue #97). GitPython's handling of interactive
    git operations can trigger client-side AbortError (-32001).
    """
    try:
        valid_operations = ["rebase", "merge", "cherry-pick"]
        if operation not in valid_operations:
            return fail(
                f"❌ Invalid operation '{operation}'. Valid operations: {', '.join(valid_operations)}"
            )

        # Use subprocess for all continue operations to ensure reliable execution
        # This avoids GitPython's interactive operation handling issues
        result = subprocess.run(
            ["git", operation, "--continue"],
            cwd=repo.working_dir,
            capture_output=True,
            text=True,
            timeout=60,  # 60 second timeout for continue operations
            # Headless server has no editor; "true" accepts the prepared message as-is
            env={**os.environ, "GIT_EDITOR": "true"},
        )

        if result.returncode == 0:
            # Success - combine stdout and stderr for complete output
            output = (result.stdout + result.stderr).strip()
            success_msg = f"✅ Successfully continued {operation}"
            if output:
                success_msg += f"\n{output}"
            return success_msg
        return _describe_continue_failure(result, operation)

    except subprocess.TimeoutExpired:
        return fail(f"❌ {operation} continue operation timed out after 60 seconds")
    except GitCommandError as e:
        return fail(
            f"❌ Continue {operation} failed: {clean_git_error_text(e.stderr, 'stderr')}"
        )
    except Exception as e:
        return fail(f"❌ Continue error: {str(e)}")
