"""Reporting helpers for git_add: describe the actual index state of requested paths."""

from ..utils.git_import import Repo
from ._lock_retry import READ_ONLY_ENV

__all__ = ["staged_status", "describe_add_result"]

_STATUS_LABELS = {"T": "typechange", "D": "deleted"}


def staged_status(repo: Repo, pathspecs: list[str]) -> dict[str, str]:
    """Return {path: status letter} for paths staged against HEAD under *pathspecs*.

    Status letters come from `git diff --cached --name-status` (A, M, D, T, R...).
    Falls back to the raw index (all "A") when there is no HEAD yet.
    """
    if not repo.head.is_valid():
        listing = repo.git.ls_files("--cached", "--", *pathspecs)
        return {line.strip(): "A" for line in listing.split("\n") if line.strip()}
    output = repo.git.diff(
        "--cached", "--name-status", "--", *pathspecs, env=READ_ONLY_ENV
    )
    result: dict[str, str] = {}
    for line in output.split("\n"):
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].strip():
            result[parts[-1].strip()] = parts[0][0]
    return result


def _label(path: str, status: dict[str, str]) -> str:
    suffix = _STATUS_LABELS.get(status.get(path, ""))
    return f"{path} ({suffix})" if suffix else path


def describe_add_result(
    newly_staged: list[str], staged_now: dict[str, str], format_list
) -> str:
    """Build the git_add report from the newly staged delta and the final state."""
    already = sorted(set(staged_now) - set(newly_staged))
    if newly_staged:
        message = (
            f"✅ Added {len(newly_staged)} file(s) to staging area: "
            f"{format_list([_label(p, staged_now) for p in newly_staged])}"
        )
        if already:
            message += (
                f"; {len(already)} already staged: "
                f"{format_list([_label(p, staged_now) for p in already])}"
            )
        return message
    if already:
        return (
            "✅ Already staged; index matches working tree "
            f"({len(already)} path(s)): "
            f"{format_list([_label(p, staged_now) for p in already])}"
        )
    return "⚠️ No changes detected in specified files"
