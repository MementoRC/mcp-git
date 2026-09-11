"""Remote operations (push, pull, fetch, remote management) for MCP Git Server."""

import logging
import os
import subprocess
from pathlib import Path

from ..utils.git_import import GitCommandError, Repo
from .error_text import clean_git_error_text

logger = logging.getLogger(__name__)

CLI_AUTH_TIMEOUT = 10  # seconds for GitHub CLI authentication
PUSH_OPERATION_TIMEOUT = 300  # seconds (5 minutes) for push operations
MIN_TOKEN_LENGTH = 10  # minimum length for a valid GitHub token

__all__ = [
    "_get_github_token_from_cli",
    "git_clone",
    "git_push",
    "git_pull",
    "git_remote_list",
    "git_remote_add",
    "git_remote_remove",
    "git_remote_rename",
    "git_remote_set_url",
    "git_remote_get_url",
    "git_fetch",
]


def _get_github_token_from_cli() -> str | None:
    """Extract token from GitHub CLI if available"""
    try:
        logger.debug("🔍 DEBUG: Running 'gh auth token' command...")
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=CLI_AUTH_TIMEOUT,
        )
        logger.debug(f"🔍 DEBUG: gh auth token return code: {result.returncode}")
        logger.debug(
            f"🔍 DEBUG: gh auth token stdout: {result.stdout[:50]}..."
            if result.stdout
            else "🔍 DEBUG: gh auth token stdout: EMPTY"
        )
        logger.debug(f"🔍 DEBUG: gh auth token stderr: {result.stderr}")

        if result.returncode == 0:
            token = result.stdout.strip()
            token_valid = token and len(token) >= MIN_TOKEN_LENGTH
            logger.debug(
                f"🔍 DEBUG: Token valid: {token_valid}, length: {len(token) if token else 0}"
            )
            return token if token_valid else None
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.debug(f"🔍 DEBUG: gh command failed: {e}")
        pass
    return None


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
        Mutually exclusive with ``branch``/``delete``.

    Dry-run control (issue #176):
      - ``dry_run``: maps to ``--dry-run``. Compatible with all push modes.
        When True, git reports what would be pushed without modifying remote state.
    """
    try:
        # Validate force-push parameter combinations (issue #161)
        if force and force_with_lease:
            return (
                "❌ force and force_with_lease are mutually exclusive. "
                "Prefer force_with_lease for safety."
            )
        if force_with_lease_expect is not None and not force_with_lease:
            return "❌ force_with_lease_expect requires force_with_lease=True"

        # Validate delete/refspec combinations (issue #173)
        if delete:
            if not branch:
                return "❌ delete=True requires branch to be set"
            if force or force_with_lease or force_if_includes:
                return "❌ delete=True cannot be combined with force/force_with_lease/force_if_includes"
            if set_upstream:
                return "❌ delete=True cannot be combined with set_upstream"
            if refspec is not None:
                return "❌ delete=True cannot be combined with refspec"
        if refspec is not None:
            if branch is not None:
                return "❌ refspec cannot be combined with branch"
            if set_upstream:
                return "❌ refspec cannot be combined with set_upstream"

        # Handle raw refspec push
        if refspec is not None:
            extra = ["--dry-run"] if dry_run else []
            repo.git.push(remote, refspec, *extra)
            suffix = " (dry-run; no remote state modified)" if dry_run else ""
            return f"✅ Successfully pushed refspec '{refspec}' to {remote}{suffix}"

        # Handle delete remote branch
        if delete:
            extra = ["--dry-run"] if dry_run else []
            repo.git.push(remote, "--delete", branch, *extra)
            suffix = " (dry-run; no remote state modified)" if dry_run else ""
            return f"✅ Successfully deleted remote branch '{branch}' from {remote}{suffix}"

        # Get current branch if not specified
        if not branch:
            try:
                branch = repo.active_branch.name
            except TypeError:  # Detached HEAD or no commits
                return "❌ No active branch found and no branch specified"

        # Build push arguments
        push_args = [remote]
        if branch:
            push_args.append(branch)

        if set_upstream:
            push_args.insert(0, "--set-upstream")
        if force:
            push_args.insert(0, "--force")
        elif force_with_lease:
            if force_with_lease_expect:
                # Accept "<refname>:<sha>" or "<sha>" (derive refname from branch)
                if ":" in force_with_lease_expect:
                    lease_arg = f"--force-with-lease={force_with_lease_expect}"
                else:
                    lease_arg = f"--force-with-lease={branch}:{force_with_lease_expect}"
            else:
                lease_arg = "--force-with-lease"
            push_args.insert(0, lease_arg)
        if force_if_includes:
            # Compatible with --force-with-lease; harmless without it on git 2.30+.
            push_args.insert(0, "--force-if-includes")
        if dry_run:
            push_args.append("--dry-run")

        # Get remote URL for GitHub authentication handling (cache for reuse)
        remote_url = ""
        is_github = False
        try:
            remote_url = repo.remote(remote).url
            is_github = "github.com" in remote_url
        except Exception:
            pass

        # GitHub HTTPS authentication handling
        if is_github and remote_url.startswith("https://"):
            # Try to load .env from current repository first
            from dotenv import load_dotenv

            repo_env = Path(repo.working_dir) / ".env"
            if repo_env.exists():
                logger.info(f"🔍 DEBUG: Loading .env from repository: {repo_env}")
                load_dotenv(repo_env, override=True)

            github_token = os.getenv("GITHUB_TOKEN")
            logger.info(
                f"🔍 DEBUG: GITHUB_TOKEN from env: {'SET' if github_token else 'NOT SET'}"
            )
            logger.info(f"🔍 DEBUG: Repository working dir: {repo.working_dir}")
            logger.info(f"🔍 DEBUG: .env file exists: {repo_env.exists()}")

            # If no GITHUB_TOKEN, try to get token from GitHub CLI
            if not github_token:
                logger.debug("🔍 DEBUG: Attempting GitHub CLI token extraction...")
                github_token = _get_github_token_from_cli()
                logger.debug(
                    f"🔍 DEBUG: GitHub CLI token: {'SET' if github_token else 'NOT SET'}"
                )

            if github_token:
                logger.debug(
                    "🔍 DEBUG: Token found, proceeding with authenticated push"
                )
                # Inject token into URL
                if "github.com" in remote_url:
                    # Format: https://token@github.com/user/repo.git
                    auth_url = remote_url.replace(
                        "https://", f"https://{github_token}@"
                    )

                    # Temporarily set remote URL with token
                    repo.remote(remote).set_url(auth_url)

                    try:
                        # Attempt push with authenticated URL
                        repo.git.push(*push_args)
                        success_msg = f"✅ Successfully pushed {branch} to {remote}"
                        if set_upstream:
                            success_msg += " (set upstream tracking)"
                        if dry_run:
                            success_msg += " (dry-run; no remote state modified)"

                        # Indicate which authentication method was used
                        if os.getenv("GITHUB_TOKEN"):
                            success_msg += "\n🔐 Used GITHUB_TOKEN authentication"
                        else:
                            success_msg += "\n🔐 Used GitHub CLI authentication"
                        return success_msg
                    finally:
                        # Restore original URL
                        repo.remote(remote).set_url(remote_url)
            else:
                # Fallback to system git with credential helpers
                logger.debug("🔍 DEBUG: NO TOKEN FOUND - falling back to system git")
                logger.info(
                    "No GitHub token available, falling back to system git authentication"
                )
                try:
                    # Use subprocess to call system git with credential helpers
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

                    logger.debug(
                        f"🔍 DEBUG: System git return code: {result.returncode}"
                    )
                    logger.debug(f"🔍 DEBUG: System git stdout: {result.stdout}")
                    logger.debug(f"🔍 DEBUG: System git stderr: {result.stderr}")

                    if result.returncode == 0:
                        success_msg = f"✅ Successfully pushed {branch} to {remote}"
                        if set_upstream:
                            success_msg += " (set upstream tracking)"
                        if dry_run:
                            success_msg += " (dry-run; no remote state modified)"
                        success_msg += "\n🔐 Used system git authentication"
                        return success_msg
                    else:
                        error_output = result.stderr.strip()
                        if (
                            "Authentication failed" in error_output
                            or "401" in error_output
                        ):
                            # Add debug info directly to error message
                            repo_env = Path(repo.working_dir) / ".env"
                            token_status = (
                                "SET" if os.getenv("GITHUB_TOKEN") else "NOT SET"
                            )
                            return (
                                f"❌ Authentication failed. Configure GITHUB_TOKEN environment variable "
                                f"or GitHub CLI authentication (gh auth login)\n"
                                f"🔍 DEBUG: GITHUB_TOKEN: {token_status}, "
                                f".env exists: {repo_env.exists()}, "
                                f"working_dir: {repo.working_dir}\n"
                                f"🔍 System git error: {error_output}"
                            )
                        elif (
                            "403" in error_output or "Permission denied" in error_output
                        ):
                            return "❌ Permission denied. Check repository access permissions"
                        elif "non-fast-forward" in error_output:
                            return "❌ Push rejected (non-fast-forward). Use force_with_lease=True (safe) or force=True (unconditional)"
                        else:
                            return f"❌ Push failed: {error_output}"

                except subprocess.TimeoutExpired:
                    return "❌ Push operation timed out. Check network connection and repository access"
                except Exception as e:
                    return f"❌ System git push failed: {str(e)}"

        # Regular push (SSH or authenticated HTTPS)
        try:
            repo.git.push(*push_args)
            success_msg = f"✅ Successfully pushed {branch} to {remote}"
            if set_upstream:
                success_msg += " (set upstream tracking)"
            if dry_run:
                success_msg += " (dry-run; no remote state modified)"
            return success_msg
        except GitCommandError as e:
            error_text = clean_git_error_text(e.stderr, "stderr")
            # If regular push fails and this is GitHub HTTPS, suggest auth options
            if is_github and remote_url.startswith("https://"):
                if "Authentication failed" in error_text or "401" in error_text:
                    # Add debug info directly to error message - REGULAR PUSH PATH
                    repo_env = Path(repo.working_dir) / ".env"
                    token_status = "SET" if os.getenv("GITHUB_TOKEN") else "NOT SET"
                    return (
                        f"❌ Authentication failed [DEBUG_VERSION_V3]. Configure GITHUB_TOKEN environment variable "
                        f"or GitHub CLI authentication (gh auth login)\n"
                        f"🔍 DEBUG [REGULAR_PUSH]: GITHUB_TOKEN: {token_status}, "
                        f".env exists: {repo_env.exists()}, "
                        f"working_dir: {repo.working_dir}\n"
                        f"🔍 GitPython error: {error_text}"
                    )
                elif "403" in error_text or "Permission denied" in error_text:
                    return "❌ Permission denied. Check repository access permissions"

            # Standard error handling for non-GitHub or non-auth issues
            if "non-fast-forward" in error_text:
                return "❌ Push rejected (non-fast-forward). Use force_with_lease=True (safe) or force=True (unconditional)"
            else:
                return f"❌ Push failed (exit {e.status}): {error_text}"

    except GitCommandError as e:
        error_text = clean_git_error_text(e.stderr, "stderr")
        if "Authentication failed" in error_text or "401" in error_text:
            # Add debug info directly to error message - OUTER EXCEPTION PATH
            repo_env = Path(repo.working_dir) / ".env"
            token = os.getenv("GITHUB_TOKEN", "")
            token_info = (
                f"length={len(token)}, starts_with={token[:4]}..."
                if token
                else "NOT SET"
            )
            return (
                f"❌ Authentication failed. Configure GITHUB_TOKEN environment variable "
                f"or GitHub CLI authentication (gh auth login)\n"
                f"🔍 DEBUG [OUTER_EXCEPTION]: GITHUB_TOKEN: {token_info}, "
                f".env exists: {repo_env.exists()}, "
                f"working_dir: {repo.working_dir}\n"
                f"🔍 Outer GitPython error: {error_text}"
            )
        elif "403" in error_text:
            return "❌ Permission denied. Check repository access permissions"
        elif "non-fast-forward" in error_text:
            return "❌ Push rejected (non-fast-forward). Use force_with_lease=True (safe) or force=True (unconditional)"
        else:
            return f"❌ Push failed (exit {e.status}): {error_text}"
    except Exception as e:
        return f"❌ Push error: {str(e)}"


def git_pull(repo: Repo, remote: str = "origin", branch: str | None = None) -> str:
    """Pull changes from remote repository"""
    try:
        # Get current branch if not specified
        if not branch:
            try:
                branch = repo.active_branch.name
            except TypeError:  # Detached HEAD or no commits
                return "❌ No active branch found and no branch specified"

        # Perform pull
        if branch:
            result = repo.git.pull(remote, branch)
        else:
            result = repo.git.pull(remote)

        return f"✅ Successfully pulled from {remote}/{branch}\n{result}"

    except GitCommandError as e:
        error_text = clean_git_error_text(e.stderr, "stderr")
        if "Authentication failed" in error_text:
            return f"❌ Authentication failed. Check credentials for {remote}"
        elif "merge conflict" in error_text.lower():
            return "❌ Pull failed due to merge conflicts. Resolve conflicts and retry"
        else:
            return f"❌ Pull failed (exit {e.status}): {error_text}"
    except Exception as e:
        return f"❌ Pull error: {str(e)}"


def git_remote_list(repo: Repo, verbose: bool = False) -> str:
    """List all remote repositories"""
    try:
        if verbose:
            return repo.git.remote("-v")
        else:
            return repo.git.remote()
    except GitCommandError as e:
        return f"❌ Remote list failed: {clean_git_error_text(e.stderr, 'stderr')}"
    except Exception as e:
        return f"❌ Remote list error: {str(e)}"


def git_remote_add(repo: Repo, name: str, url: str) -> str:
    """Add a new remote repository"""
    try:
        repo.git.remote("add", name, url)
        return f"✅ Successfully added remote '{name}' -> {url}"
    except GitCommandError as e:
        return f"❌ Remote add failed: {clean_git_error_text(e.stderr, 'stderr')}"
    except Exception as e:
        return f"❌ Remote add error: {str(e)}"


def git_remote_remove(repo: Repo, name: str) -> str:
    """Remove a remote repository"""
    try:
        repo.git.remote("remove", name)
        return f"✅ Successfully removed remote '{name}'"
    except GitCommandError as e:
        return f"❌ Remote remove failed: {clean_git_error_text(e.stderr, 'stderr')}"
    except Exception as e:
        return f"❌ Remote remove error: {str(e)}"


def git_remote_rename(repo: Repo, old_name: str, new_name: str) -> str:
    """Rename a remote repository"""
    try:
        repo.git.remote("rename", old_name, new_name)
        return f"✅ Successfully renamed remote '{old_name}' to '{new_name}'"
    except GitCommandError as e:
        return f"❌ Remote rename failed: {clean_git_error_text(e.stderr, 'stderr')}"
    except Exception as e:
        return f"❌ Remote rename error: {str(e)}"


def git_remote_set_url(repo: Repo, name: str, url: str) -> str:
    """Set URL for a remote repository"""
    try:
        repo.git.remote("set-url", name, url)
        return f"✅ Successfully set URL for remote '{name}' -> {url}"
    except GitCommandError as e:
        return f"❌ Remote set-url failed: {clean_git_error_text(e.stderr, 'stderr')}"
    except Exception as e:
        return f"❌ Remote set-url error: {str(e)}"


def git_remote_get_url(repo: Repo, name: str) -> str:
    """Get URL for a remote repository"""
    try:
        url = repo.git.remote("get-url", name)
        return f"Remote '{name}' URL: {url}"
    except GitCommandError as e:
        return f"❌ Remote get-url failed: {clean_git_error_text(e.stderr, 'stderr')}"
    except Exception as e:
        return f"❌ Remote get-url error: {str(e)}"


def git_clone(
    repo_url: str,
    target_path: str,
    branch: str | None = None,
    depth: int | None = None,
    single_branch: bool = False,
    recurse_submodules: bool = False,
) -> str:
    """Clone a remote repository to a local path"""
    try:
        target = Path(target_path)
        if not target.parent.exists():
            raise ValueError(f"Parent directory does not exist: {target.parent}")
        if target.exists() and any(target.iterdir()):
            raise ValueError(
                f"Target path already exists and is not empty: {target_path}"
            )

        multi_options = []
        if branch:
            multi_options.append(f"--branch={branch}")
        if depth is not None:
            multi_options.append(f"--depth={depth}")
        if single_branch:
            multi_options.append("--single-branch")
        if recurse_submodules:
            multi_options.append("--recurse-submodules")

        Repo.clone_from(repo_url, target_path, multi_options=multi_options)

        return f"✅ Cloned {repo_url} to {target_path}"
    except ValueError:
        raise
    except GitCommandError as e:
        return f"❌ Clone failed (exit {e.status}): {clean_git_error_text(e.stderr, 'stderr')}"
    except Exception as e:
        return f"❌ Clone error: {str(e)}"


def git_fetch(
    repo: Repo,
    remote: str = "origin",
    branch: str | None = None,
    prune: bool = False,
) -> str:
    """Fetch changes from remote repository"""
    try:
        args = [remote]
        if branch:
            args.append(branch)
        if prune:
            args.append("--prune")

        repo.git.fetch(*args)

        if branch:
            return f"✅ Successfully fetched {remote}/{branch}" + (
                " (with prune)" if prune else ""
            )
        else:
            return f"✅ Successfully fetched from {remote}" + (
                " (with prune)" if prune else ""
            )
    except GitCommandError as e:
        return f"❌ Fetch failed: {clean_git_error_text(e.stderr, 'stderr')}"
    except Exception as e:
        return f"❌ Fetch error: {str(e)}"
