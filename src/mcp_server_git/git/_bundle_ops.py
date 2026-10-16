"""Git bundle backup operations (issue #283).

Bundles are read-only with respect to the repository (they only read objects
and refs), so these tools do not touch the index.
"""

from pathlib import Path

from ..utils.git_import import GitCommandError, Repo
from ..utils.tool_failure import fail
from ._ref_validation import validate_ref
from .error_text import clean_git_error_text

__all__ = ["git_bundle_create", "git_bundle_verify"]

# Option-like rev-list arguments that may select what goes into a bundle.
_ALLOWED_OPTIONS = {"--all", "--branches", "--tags", "--remotes"}


def _invalid_ref_error(refs: list[str]) -> str | None:
    """Failure for the first ref that is an unknown option or has bad characters."""
    for ref in refs:
        if ref.startswith("-") and ref not in _ALLOWED_OPTIONS:
            return fail(f"❌ Invalid ref in refs: '{ref}'")
        error = validate_ref(ref, "refs")
        if error:
            return error
    return None


def git_bundle_create(
    repo: Repo,
    output_path: str,
    refs: list[str] | None = None,
    overwrite: bool = False,
) -> str:
    """Create a bundle file containing *refs* (default: ``--all``)."""
    out = Path(output_path)
    if out.is_dir():
        return fail(f"❌ output_path is a directory: {output_path}")
    if out.exists() and not overwrite:
        return fail(
            f"❌ Refusing to overwrite existing file: {output_path} "
            "(pass overwrite=True to replace it)"
        )
    if not out.parent.is_dir():
        return fail(f"❌ Output directory does not exist: {out.parent}")

    ref_args = refs or ["--all"]
    invalid = _invalid_ref_error(ref_args)
    if invalid:
        return invalid

    try:
        repo.git.bundle("create", str(out), *ref_args)
    except GitCommandError as e:
        return fail(
            f"❌ Bundle create failed: {clean_git_error_text(e.stderr, 'stderr')}"
        )
    except Exception as e:
        return fail(f"❌ Bundle create error: {str(e)}")
    return f"✅ Created bundle {output_path} ({out.stat().st_size} bytes) from {' '.join(ref_args)}"


def git_bundle_verify(repo: Repo, bundle_path: str) -> str:
    """Verify a bundle is valid and applicable to this repository."""
    if not Path(bundle_path).is_file():
        return fail(f"❌ Bundle not found: {bundle_path}")
    try:
        output = repo.git.bundle("verify", bundle_path)
    except GitCommandError as e:
        return fail(
            f"❌ Bundle verify failed: {clean_git_error_text(e.stderr, 'stderr')}"
        )
    except Exception as e:
        return fail(f"❌ Bundle verify error: {str(e)}")
    return f"✅ Bundle {bundle_path} is valid\n{output}".rstrip()
