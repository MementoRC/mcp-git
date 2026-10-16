"""Metadata-preserving options for ``git commit`` (issue #283).

Validates ``author``, ``date`` and ``reuse_message_from`` and turns them into
argv fragments. Committer date is deliberately not exposed. GPG signing is
enforced elsewhere and is not influenced by anything here.
"""

import re
from datetime import datetime

from ..utils.tool_failure import fail
from ._ref_validation import validate_ref

__all__ = ["commit_option_args"]

_AUTHOR_RE = re.compile(r"^[^<>\n]+ <[^<>\n]+>$")


def _date_error(date: str) -> str | None:
    try:
        datetime.fromisoformat(date)
    except ValueError:
        return fail(
            f"❌ Invalid date '{date}': expected ISO 8601 (YYYY-MM-DDTHH:MM:SS)"
        )
    return None


def commit_option_args(
    message: str | None,
    author: str | None,
    date: str | None,
    reuse_message_from: str | None,
) -> tuple[list[str], str | None]:
    """Return ``(argv fragment, error)`` for the message and metadata options.

    Exactly one of *message* / *reuse_message_from* must be given (git forbids
    combining ``-m`` with ``-C``). *error* is a ToolFailure or None.
    """
    if bool(message) == bool(reuse_message_from):
        return [], fail("❌ Provide exactly one of message or reuse_message_from")
    args: list[str] = []
    if author:
        if not _AUTHOR_RE.match(author):
            return [], fail(f"❌ Invalid author '{author}': expected 'Name <email>'")
        args.append(f"--author={author}")
    if date:
        error = _date_error(date)
        if error:
            return [], error
        args.append(f"--date={date}")
    if reuse_message_from:
        error = validate_ref(reuse_message_from, "reuse_message_from")
        if error or reuse_message_from.startswith("-"):
            return [], error or fail("❌ Invalid reuse_message_from")
        args.extend(["-C", reuse_message_from])
    else:
        args.extend(["-m", str(message)])
    return args, None
