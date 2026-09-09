"""Character limits shared by every tool that returns bulk text to an LLM.

Lives outside the ``github`` package because the git domain needs the same
cap: a merged file with conflict markers floods a context exactly as a CI log
does.
"""

from __future__ import annotations

MAX_CHARS_FOR_LLM = 100 * 1024


def cap_characters(
    text: str, *, keep_head: bool, limit: int = MAX_CHARS_FOR_LLM
) -> tuple[str, bool]:
    """Trim *text* to *limit* characters, keeping whichever end was asked for.

    Trimming stops at a line boundary so the result never starts or ends with
    half a line.
    """
    if len(text) <= limit:
        return text, False

    if keep_head:
        trimmed = text[:limit]
        boundary = trimmed.rfind("\n")
        if boundary > 0:
            trimmed = trimmed[:boundary]
    else:
        trimmed = text[-limit:]
        boundary = trimmed.find("\n")
        if boundary >= 0:
            trimmed = trimmed[boundary + 1 :]
    return trimmed, True
