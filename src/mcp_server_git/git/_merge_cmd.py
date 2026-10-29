"""``git_merge``: merge any commit-ish into the current branch."""

from ..utils.git_import import GitCommandError, Repo
from ..utils.tool_failure import fail
from ._ignored_guard import ignored_overwrite_failure
from .error_text import clean_git_error_text

__all__ = ["git_merge"]

# %G? codes: G good, U good/unknown validity, X/Y expired, R revoked-key,
# B bad, E cannot check, N none.
_GOOD_SIGNATURE_CODES = {"G", "U", "X", "Y"}


def _resolve_source(
    source_branch: str | None, source: str | None
) -> tuple[str | None, str | None]:
    """Reconcile the ``source_branch`` / ``source`` aliases. Returns ``(ref, error)``."""
    if source_branch and source and source_branch != source:
        return None, fail(
            f"❌ source_branch ('{source_branch}') and source ('{source}') differ; "
            "give only one"
        )
    ref = source_branch or source
    if not ref:
        return None, fail("❌ source (or source_branch) is required")
    if ref.startswith("-"):
        return None, fail(
            f"❌ source must not start with '-': '{ref}' would be parsed as a git option"
        )
    return ref, None


def _check_flags(no_commit: bool, no_ff: bool, ff_only: bool) -> str | None:
    if ff_only and no_ff:
        return fail("❌ ff_only and no_ff are mutually exclusive")
    if ff_only and no_commit:
        return fail("❌ ff_only and no_commit are mutually exclusive")
    return None


def _commit_ish_exists(repo: Repo, ref: str) -> bool:
    """True when ``ref`` (SHA, tag, branch, remote ref) resolves to a commit."""
    status, _out, _err = repo.git.rev_parse(
        "--verify",
        "--quiet",
        f"{ref}^{{commit}}",
        with_extended_output=True,
        with_exceptions=False,
    )
    return status == 0


def _head_sha(repo: Repo) -> str:
    return repo.git.rev_parse("HEAD").strip()


def _signature_report(repo: Repo, head_before: str) -> str:
    """Signing status line for a merge commit created by this call, else ''."""
    head = _head_sha(repo)
    if head == head_before or len(repo.commit(head).parents) < 2:
        return ""
    code = repo.git.log("-1", "--format=%G?", head).strip()
    short = head[:8]
    if code in _GOOD_SIGNATURE_CODES:
        return f"\n🔒 Merge commit {short} has a VERIFIED GPG signature"
    if code == "N":
        return (
            f"\n⚠️ Merge commit {short} is UNSIGNED "
            "(set commit.gpgsign or sign it with git_commit --amend)"
        )
    return f"\n⚠️ Merge commit {short} GPG signature status: {code} (not verified)"


def _merge_argv(
    ref: str, message: str | None, no_commit: bool, no_ff: bool, ff_only: bool
) -> list[str]:
    args = []
    if no_commit:
        args.append("--no-commit")
    if no_ff or no_commit:
        # --no-commit alone would silently fast-forward and stage nothing.
        args.append("--no-ff")
    if ff_only:
        args.append("--ff-only")
    args.append(ref)
    if message:
        args.extend(["-m", message])
    return args


def git_merge(
    repo: Repo,
    source_branch: str | None = None,
    strategy: str = "merge",
    message: str | None = None,
    allow_overwrite_ignored: bool = False,
    source: str | None = None,
    no_commit: bool = False,
    no_ff: bool = False,
    ff_only: bool = False,
) -> str:
    """Merge a commit-ish (SHA, tag, branch, remote ref) into the current branch.

    ``source`` is an alias of ``source_branch``. ``no_commit`` leaves the merge
    staged; ``no_ff`` forces a merge commit; ``ff_only`` refuses a non-fast-forward.
    Refused when the merge would overwrite ignored files unless
    ``allow_overwrite_ignored=True`` (issue #283). A created merge commit's GPG
    signature status is reported.
    """
    ref, error = _resolve_source(source_branch, source)
    if error or ref is None:
        return error or fail("❌ source is required")
    flag_error = _check_flags(no_commit, no_ff, ff_only)
    if flag_error:
        return flag_error
    try:
        current_branch = repo.active_branch.name
        if not _commit_ish_exists(repo, ref):
            return fail(f"❌ Source '{ref}' not found (not a commit-ish)")

        blocked = ignored_overwrite_failure(
            repo, ref, "merge", allow=allow_overwrite_ignored, only_changed=True
        )
        if blocked:
            return blocked

        head_before = _head_sha(repo)
        result = repo.git.merge(*_merge_argv(ref, message, no_commit, no_ff, ff_only))
        if no_commit:
            return (
                f"✅ Merged {ref} into {current_branch}: changes are staged and "
                f"uncommitted (no_commit); run git_commit to conclude\n{result}"
            )
        report = _signature_report(repo, head_before)
        return f"✅ Successfully merged {ref} into {current_branch}\n{result}{report}"

    except GitCommandError as e:
        error_text = clean_git_error_text(e.stderr, "stderr")
        if "conflict" in error_text.lower():
            return fail(
                "❌ Merge failed due to conflicts. Resolve conflicts and commit"
            )
        return fail(f"❌ Merge failed: {error_text}")
    except Exception as e:
        return fail(f"❌ Merge error: {str(e)}")
