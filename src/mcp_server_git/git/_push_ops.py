"""Push operation (authentication, force controls, delete/refspec) for MCP Git Server."""

import logging
import os
import subprocess
from pathlib import Path

from ..utils.git_import import GitCommandError, Repo
from ..utils.tool_failure import fail
from ._github_token import _resolve_github_token
from .error_text import clean_git_error_text

logger = logging.getLogger(__name__)

PUSH_OPERATION_TIMEOUT = 300  # seconds (5 minutes) for push operations

__all__ = ["git_push"]

_DRY_RUN_SUFFIX = " (dry-run; no remote state modified)"
_AUTH_HELP = (
    "Authentication failed. Configure GITHUB_TOKEN environment variable "
    "or GitHub CLI authentication (gh auth login)\n"
)
_PERMISSION_DENIED = fail("❌ Permission denied. Check repository access permissions")


def _lease_flag(expect: str | None, refname: str | None) -> str:
    """Build the --force-with-lease flag.

    ``expect`` is "<refname>:<sha>" or a bare "<sha>"; a bare SHA takes its
    refname from ``refname`` (the branch, or the refspec destination).
    """
    if not expect:
        return "--force-with-lease"
    if ":" in expect:
        return f"--force-with-lease={expect}"
    return f"--force-with-lease={refname}:{expect}"


def _push_rejected_message(force: bool, force_with_lease: bool) -> str:
    """Explain a non-fast-forward rejection in terms of what was requested.

    Recommending the force flags only helps when none were supplied. When they
    were, repeating them reads as caller error and hides the real cause (#237).
    """
    if force_with_lease:
        return fail(
            "❌ Push rejected (non-fast-forward) even though force_with_lease=True. "
            "The lease was refused because the remote ref moved since your last "
            "fetch. Fetch and re-inspect the remote tip, then retry — passing "
            "force_with_lease_expect='<refname>:<sha>' to name the commit you "
            "intend to replace."
        )
    if force:
        return fail(
            "❌ Push rejected (non-fast-forward) even though force=True. "
            "The remote refused the forced update; this is usually branch "
            "protection or receive.denyNonFastForwards on the server, not a "
            "local problem."
        )
    return fail(
        "❌ Push rejected (non-fast-forward). "
        "Use force_with_lease=True (safe) or force=True (unconditional)"
    )


def _validate_force_args(
    force: bool, force_with_lease: bool, force_with_lease_expect: str | None
) -> str | None:
    """Validate force-push parameter combinations (issue #161)."""
    if force and force_with_lease:
        return fail(
            "❌ force and force_with_lease are mutually exclusive. "
            "Prefer force_with_lease for safety."
        )
    if force_with_lease_expect is not None and not force_with_lease:
        return fail("❌ force_with_lease_expect requires force_with_lease=True")
    return None


def _validate_delete_args(
    branch: str | None,
    force: bool,
    force_with_lease: bool,
    force_if_includes: bool,
    set_upstream: bool,
    refspec: str | None,
) -> str | None:
    """Validate delete combinations (issue #173)."""
    if not branch:
        return fail("❌ delete=True requires branch to be set")
    if force or force_with_lease or force_if_includes:
        return fail(
            "❌ delete=True cannot be combined with force/force_with_lease/force_if_includes"
        )
    if set_upstream:
        return fail("❌ delete=True cannot be combined with set_upstream")
    if refspec is not None:
        return fail("❌ delete=True cannot be combined with refspec")
    return None


def _validate_refspec_args(branch: str | None, set_upstream: bool) -> str | None:
    """Validate refspec combinations (issue #173)."""
    if branch is not None:
        return fail("❌ refspec cannot be combined with branch")
    if set_upstream:
        return fail("❌ refspec cannot be combined with set_upstream")
    return None


def _validate_push_args(
    branch: str | None,
    set_upstream: bool,
    force: bool,
    force_with_lease: bool,
    force_with_lease_expect: str | None,
    force_if_includes: bool,
    delete: bool,
    refspec: str | None,
) -> str | None:
    """Return the first validation error for the option combination, if any."""
    error = _validate_force_args(force, force_with_lease, force_with_lease_expect)
    if error is None and delete:
        error = _validate_delete_args(
            branch, force, force_with_lease, force_if_includes, set_upstream, refspec
        )
    if error is None and refspec is not None:
        error = _validate_refspec_args(branch, set_upstream)
    return error


def _push_refspec(
    repo: Repo,
    remote: str,
    refspec: str,
    force: bool,
    force_with_lease: bool,
    force_with_lease_expect: str | None,
    force_if_includes: bool,
    dry_run: bool,
) -> str:
    """Push a raw refspec."""
    # branch is None here, so a bare-SHA lease takes its refname from
    # the refspec destination ("src:dst" -> "dst"; "dst" -> "dst").
    dst = refspec.split(":", 1)[1] if ":" in refspec else refspec
    force_args: list[str] = []
    if force:
        force_args.append("--force")
    elif force_with_lease:
        force_args.append(_lease_flag(force_with_lease_expect, dst))
    if force_if_includes:
        force_args.append("--force-if-includes")
    extra = ["--dry-run"] if dry_run else []
    repo.git.push(*force_args, remote, refspec, *extra)
    suffix = _DRY_RUN_SUFFIX if dry_run else ""
    return f"✅ Successfully pushed refspec '{refspec}' to {remote}{suffix}"


def _push_delete(repo: Repo, remote: str, branch: str | None, dry_run: bool) -> str:
    """Delete a remote branch."""
    extra = ["--dry-run"] if dry_run else []
    repo.git.push(remote, "--delete", branch, *extra)
    suffix = _DRY_RUN_SUFFIX if dry_run else ""
    return f"✅ Successfully deleted remote branch '{branch}' from {remote}{suffix}"


def _build_push_args(
    remote: str,
    branch: str | None,
    set_upstream: bool,
    force: bool,
    force_with_lease: bool,
    force_with_lease_expect: str | None,
    force_if_includes: bool,
    dry_run: bool,
) -> list[str]:
    """Build the git push argument list for a plain branch push."""
    push_args = [remote]
    if branch:
        push_args.append(branch)

    if set_upstream:
        push_args.insert(0, "--set-upstream")
    if force:
        push_args.insert(0, "--force")
    elif force_with_lease:
        push_args.insert(0, _lease_flag(force_with_lease_expect, branch))
    if force_if_includes:
        # Compatible with --force-with-lease; harmless without it on git 2.30+.
        push_args.insert(0, "--force-if-includes")
    if dry_run:
        push_args.append("--dry-run")
    return push_args


def _remote_url_info(repo: Repo, remote: str) -> tuple[str, bool]:
    """Return (remote URL, is_github) for GitHub authentication handling."""
    remote_url = ""
    is_github = False
    try:
        remote_url = repo.remote(remote).url
        is_github = "github.com" in remote_url
    except Exception:
        pass
    return remote_url, is_github


def _success_message(
    branch: str | None, remote: str, set_upstream: bool, dry_run: bool
) -> str:
    """Build the success message for a plain branch push."""
    success_msg = f"✅ Successfully pushed {branch} to {remote}"
    if set_upstream:
        success_msg += " (set upstream tracking)"
    if dry_run:
        success_msg += _DRY_RUN_SUFFIX
    return success_msg


def _push_with_token(
    repo: Repo,
    remote: str,
    remote_url: str,
    github_token: str,
    push_args: list[str],
    success_msg: str,
) -> str:
    """Push using a token injected into the remote URL, restoring it after."""
    logger.debug("🔍 DEBUG: Token found, proceeding with authenticated push")
    # Format: https://token@github.com/user/repo.git
    auth_url = remote_url.replace("https://", f"https://{github_token}@")

    # Temporarily set remote URL with token
    repo.remote(remote).set_url(auth_url)

    try:
        repo.git.push(*push_args)
        # Indicate which authentication method was used
        if os.getenv("GITHUB_TOKEN"):
            return success_msg + "\n🔐 Used GITHUB_TOKEN authentication"
        return success_msg + "\n🔐 Used GitHub CLI authentication"
    finally:
        repo.remote(remote).set_url(remote_url)


def _system_git_failure(
    repo: Repo, error_output: str, force: bool, force_with_lease: bool
) -> str:
    """Render a failed system-git push."""
    if "Authentication failed" in error_output or "401" in error_output:
        repo_env = Path(repo.working_dir) / ".env"
        token_status = "SET" if os.getenv("GITHUB_TOKEN") else "NOT SET"
        return fail(
            f"❌ {_AUTH_HELP}"
            f"🔍 DEBUG: GITHUB_TOKEN: {token_status}, "
            f".env exists: {repo_env.exists()}, "
            f"working_dir: {repo.working_dir}\n"
            f"🔍 System git error: {error_output}"
        )
    if "403" in error_output or "Permission denied" in error_output:
        return _PERMISSION_DENIED
    if "non-fast-forward" in error_output:
        return _push_rejected_message(force, force_with_lease)
    return fail(f"❌ Push failed: {error_output}")


def _push_with_system_git(
    repo: Repo,
    push_args: list[str],
    success_msg: str,
    force: bool,
    force_with_lease: bool,
) -> str:
    """Fallback to system git with credential helpers."""
    logger.debug("🔍 DEBUG: NO TOKEN FOUND - falling back to system git")
    logger.info("No GitHub token available, falling back to system git authentication")
    try:
        cmd = ["git", "push"]
        cmd.extend(push_args)
        logger.debug(f"🔍 DEBUG: System git command: {' '.join(cmd)}")
        logger.debug(f"🔍 DEBUG: Working directory: {repo.working_dir}")

        result = subprocess.run(
            cmd,
            cwd=repo.working_dir,
            capture_output=True,
            text=True,
            timeout=PUSH_OPERATION_TIMEOUT,
        )

        logger.debug(f"🔍 DEBUG: System git return code: {result.returncode}")
        logger.debug(f"🔍 DEBUG: System git stdout: {result.stdout}")
        logger.debug(f"🔍 DEBUG: System git stderr: {result.stderr}")

        if result.returncode == 0:
            return success_msg + "\n🔐 Used system git authentication"
        return _system_git_failure(repo, result.stderr.strip(), force, force_with_lease)
    except subprocess.TimeoutExpired:
        return fail(
            "❌ Push operation timed out. Check network connection and repository access"
        )
    except Exception as e:
        return fail(f"❌ System git push failed: {str(e)}")


def _push_github_https(
    repo: Repo,
    remote: str,
    remote_url: str,
    push_args: list[str],
    success_msg: str,
    force: bool,
    force_with_lease: bool,
) -> str:
    """Push to a GitHub HTTPS remote: token auth, else system git."""
    github_token = _resolve_github_token(repo)
    if github_token:
        return _push_with_token(
            repo, remote, remote_url, github_token, push_args, success_msg
        )
    return _push_with_system_git(repo, push_args, success_msg, force, force_with_lease)


def _push_regular(
    repo: Repo,
    push_args: list[str],
    success_msg: str,
    force: bool,
    force_with_lease: bool,
) -> str:
    """Regular push (SSH or non-GitHub remotes)."""
    try:
        repo.git.push(*push_args)
        return success_msg
    except GitCommandError as e:
        error_text = clean_git_error_text(e.stderr, "stderr")
        if "non-fast-forward" in error_text:
            return _push_rejected_message(force, force_with_lease)
        return fail(f"❌ Push failed (exit {e.status}): {error_text}")


def _outer_git_error(
    repo: Repo,
    error_text: str,
    status: int | str | None,
    force: bool,
    force_with_lease: bool,
) -> str:
    """Render a GitCommandError that escaped the inner push paths."""
    if "Authentication failed" in error_text or "401" in error_text:
        repo_env = Path(repo.working_dir) / ".env"
        token = os.getenv("GITHUB_TOKEN", "")
        token_info = (
            f"length={len(token)}, starts_with={token[:4]}..." if token else "NOT SET"
        )
        return fail(
            f"❌ {_AUTH_HELP}"
            f"🔍 DEBUG [OUTER_EXCEPTION]: GITHUB_TOKEN: {token_info}, "
            f".env exists: {repo_env.exists()}, "
            f"working_dir: {repo.working_dir}\n"
            f"🔍 Outer GitPython error: {error_text}"
        )
    if "403" in error_text:
        return _PERMISSION_DENIED
    if "non-fast-forward" in error_text:
        return _push_rejected_message(force, force_with_lease)
    return fail(f"❌ Push failed (exit {status}): {error_text}")


def git_push(
    repo: Repo,
    remote: str = "origin",
    branch: str | None = None,
    set_upstream: bool = False,
    force: bool = False,
    force_with_lease: bool = False,
    force_with_lease_expect: str | None = None,
    force_if_includes: bool = False,
    delete: bool = False,
    refspec: str | None = None,
    dry_run: bool = False,
) -> str:
    """Push with comprehensive authentication including fallback to system git credentials.

    Force-push controls (issue #161):
      - ``force``: maps to ``--force`` (unconditional overwrite — dangerous).
      - ``force_with_lease``: maps to ``--force-with-lease`` (refuses if remote
        ref moved since last fetch — the safe force-push).
      - ``force_with_lease_expect``: ``<refname>:<sha>`` or ``<sha>``. When only
        a SHA is given, the refname is derived from ``branch``. Requires
        ``force_with_lease=True``.
      - ``force_if_includes``: maps to ``--force-if-includes`` (git 2.30+).
        Composes with ``--force-with-lease`` to also detect rebase-on-stale-base.

    ``force`` and ``force_with_lease`` are mutually exclusive.

    Delete / refspec controls (issue #173):
      - ``delete``: maps to ``--delete <branch>`` (delete remote branch).
        Requires ``branch``; mutually exclusive with force/refspec.
      - ``refspec``: raw push refspec (e.g. ``src:dst`` or ``:branch``).
        Mutually exclusive with ``branch``/``delete``. The force controls
        above (``force``, ``force_with_lease``, ``force_if_includes``) DO
        apply to the refspec form; a bare-SHA ``force_with_lease_expect``
        derives its refname from the refspec destination (``src:dst`` -> the
        ``dst`` side; a bare ``dst`` refspec -> itself).

    Dry-run control (issue #176):
      - ``dry_run``: maps to ``--dry-run``. Compatible with all push modes.
        When True, git reports what would be pushed without modifying remote state.
    """
    try:
        error = _validate_push_args(
            branch,
            set_upstream,
            force,
            force_with_lease,
            force_with_lease_expect,
            force_if_includes,
            delete,
            refspec,
        )
        if error is not None:
            return error

        if refspec is not None:
            return _push_refspec(
                repo,
                remote,
                refspec,
                force,
                force_with_lease,
                force_with_lease_expect,
                force_if_includes,
                dry_run,
            )
        if delete:
            return _push_delete(repo, remote, branch, dry_run)

        # Get current branch if not specified
        if not branch:
            try:
                branch = repo.active_branch.name
            except TypeError:  # Detached HEAD or no commits
                return fail("❌ No active branch found and no branch specified")

        push_args = _build_push_args(
            remote,
            branch,
            set_upstream,
            force,
            force_with_lease,
            force_with_lease_expect,
            force_if_includes,
            dry_run,
        )
        success_msg = _success_message(branch, remote, set_upstream, dry_run)

        remote_url, is_github = _remote_url_info(repo, remote)
        if is_github and remote_url.startswith("https://"):
            return _push_github_https(
                repo,
                remote,
                remote_url,
                push_args,
                success_msg,
                force,
                force_with_lease,
            )
        return _push_regular(repo, push_args, success_msg, force, force_with_lease)

    except GitCommandError as e:
        error_text = clean_git_error_text(e.stderr, "stderr")
        return _outer_git_error(repo, error_text, e.status, force, force_with_lease)
    except Exception as e:
        return fail(f"❌ Push error: {str(e)}")
