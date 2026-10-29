"""git_verify_commit: signature status, key id and signer of a commit (#321).

Reads ``%G?``/``%GK``/``%GS`` through ``git log -1`` rather than parsing the
output of ``git verify-commit``: the placeholders are stable, and an unsigned
commit yields ``N`` instead of a failing exit status.
"""

from ..utils.git_import import GitCommandError, Repo
from ..utils.tool_failure import fail
from ._lock_retry import READ_ONLY_ENV
from ._ref_validation import validate_ref
from .error_text import clean_git_error_text

__all__ = ["SIGNATURE_STATUS_WORDS", "format_verification", "git_verify_commit"]

SIGNATURE_STATUS_WORDS = {
    "G": "good signature",
    "B": "bad signature",
    "U": "good signature, unknown validity",
    "X": "good signature, expired",
    "Y": "good signature, made by an expired key",
    "R": "good signature, made by a revoked key",
    "E": "cannot be checked (missing key or gpg error)",
    "N": "not signed",
}

_FORMAT = "%G?%n%GK%n%GS"


def format_verification(code: str, key: str, signer: str) -> str:
    """Render a decoded verification result; ``code`` is a ``%G?`` letter."""
    if code == "N":
        return "Not signed: commit has no signature (status N)"
    words = SIGNATURE_STATUS_WORDS.get(code, "unknown status")
    return (
        f"Signature status: {code} ({words})\n"
        f"Key: {key or '(none)'}\n"
        f"Signer: {signer or '(none)'}"
    )


def git_verify_commit(repo: Repo, commit: str = "HEAD") -> str:
    """Verify the signature of ``commit`` (default HEAD)."""
    if commit.startswith("-"):
        return fail(f"❌ Invalid commit: '{commit}'")
    invalid = validate_ref(commit, "commit")
    if invalid:
        return invalid
    try:
        out = repo.git.log("-1", f"--format={_FORMAT}", commit, env=READ_ONLY_ENV)
    except GitCommandError as e:
        return fail(f"❌ Verify failed: {clean_git_error_text(e.stderr, 'stderr')}")
    code, key, signer = (out.split("\n") + ["", "", ""])[:3]
    return f"Commit {commit}\n" + format_verification(
        code.strip(), key.strip(), signer.strip()
    )
