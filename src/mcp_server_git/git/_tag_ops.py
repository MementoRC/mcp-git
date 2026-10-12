"""Tag operations for MCP Git Server."""

import logging

from ..utils.git_import import GitCommandError, Repo
from ..utils.tool_failure import fail
from ._gpg import resolve_gpg_key
from ._ref_validation import validate_ref
from .error_text import clean_git_error_text

logger = logging.getLogger(__name__)

__all__ = [
    "git_tag_list",
    "git_tag_create",
    "git_tag_delete",
]


def git_tag_list(
    repo: Repo,
    pattern: str | None = None,
    points_at: str | None = None,
) -> str:
    """List tags, optionally filtered by glob pattern or --points-at commit."""
    if pattern is not None:
        error = validate_ref(pattern, "pattern")
        if error:
            return fail(error)
    if points_at is not None:
        error = validate_ref(points_at, "points_at")
        if error:
            return fail(error)

    try:
        args = ["-l"]
        if points_at:
            args.append(f"--points-at={points_at}")
        if pattern:
            args.append(pattern)

        tag_list = repo.git.tag(*args)
        if not tag_list.strip():
            return "No tags found"
        return f"Tags:\n{tag_list}"
    except GitCommandError as e:
        return fail(f"❌ Tag list failed: {clean_git_error_text(e.stderr, 'stderr')}")
    except Exception as e:
        return fail(f"❌ Tag list error: {str(e)}")


def _validate_tag_refs(tag_name: str, target: str | None) -> str | None:
    """Validate the tag name, then the target if given. Returns a failure or None."""
    error = validate_ref(tag_name, "tag_name")
    if error:
        return fail(error)
    if target is not None:
        error = validate_ref(target, "commit_ish")
        if error:
            return fail(error)
    return None


def _build_tag_args(
    repo: Repo,
    tag_name: str,
    target: str | None,
    message: str | None,
    *,
    sign: bool,
    annotate: bool,
    force: bool,
    gpg_key_id: str | None,
) -> tuple[list[str], str | None]:
    """Build the ``git tag`` argv. Returns ``(args, key_error)``."""
    args: list[str] = []
    if force:
        args.append("-f")

    if sign:
        key_id, key_error = resolve_gpg_key(repo, gpg_key_id)
        if key_error:
            return args, fail(key_error)
        args.extend(["-u", str(key_id)])
    elif annotate or message:
        args.append("-a")

    if message:
        args.extend(["-m", message])

    args.append(tag_name)
    if target:
        args.append(target)
    return args, None


def git_tag_create(
    repo: Repo,
    tag_name: str,
    commit_ish: str | None = None,
    message: str | None = None,
    sign: bool = False,
    annotate: bool = False,
    force: bool = False,
    gpg_key_id: str | None = None,
    commit: str | None = None,  # Deprecated back-compat alias for commit_ish.
) -> str:
    """Create a local git tag (lightweight, annotated, or GPG-signed).

    Args:
        repo: Git repository object
        tag_name: Name of the tag to create
        commit_ish: Commit-ish to tag (default: HEAD)
        message: Tag message. Required for annotated/signed tags; if omitted
            while sign or annotate is True, defaults to tag_name to avoid
            git opening $EDITOR (which would hang a non-interactive caller).
        sign: Create a GPG-signed tag (git tag -u <key>); implies annotated.
        annotate: Create an annotated tag (git tag -a).
        force: Replace an existing tag of the same name (git tag -f).
        gpg_key_id: Explicit GPG key id for signing. Falls back to
            GPG_SIGNING_KEY env var, then the repo's user.signingkey config.
        commit: Deprecated. Use commit_ish instead.

    Returns:
        Success or error message string.
    """
    target = commit_ish if commit_ish is not None else commit

    error = _validate_tag_refs(tag_name, target)
    if error:
        return error

    # An annotated or signed tag with no message would make git open
    # $EDITOR and hang a non-interactive caller — default to tag_name.
    effective_message = message
    if (sign or annotate) and not effective_message:
        effective_message = tag_name

    try:
        args, key_error = _build_tag_args(
            repo,
            tag_name,
            target,
            effective_message,
            sign=sign,
            annotate=annotate,
            force=force,
            gpg_key_id=gpg_key_id,
        )
        if key_error:
            return key_error

        repo.git.tag(*args)
        return f"✅ Successfully created tag '{tag_name}'" + (
            f" on {target}" if target else ""
        )
    except GitCommandError as e:
        return fail(f"❌ Tag create failed: {clean_git_error_text(e.stderr, 'stderr')}")
    except Exception as e:
        return fail(f"❌ Tag create error: {str(e)}")


def git_tag_delete(repo: Repo, tag_name: str) -> str:
    """Delete a local git tag."""
    error = validate_ref(tag_name, "tag_name")
    if error:
        return fail(error)

    try:
        repo.git.tag("-d", tag_name)
        return f"✅ Successfully deleted tag '{tag_name}'"
    except GitCommandError as e:
        return fail(f"❌ Tag delete failed: {clean_git_error_text(e.stderr, 'stderr')}")
    except Exception as e:
        return fail(f"❌ Tag delete error: {str(e)}")
