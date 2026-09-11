"""Shared helper for unwrapping GitPython's decorated error text.

Extracted from ``operations_extended.py`` (issue #219) once more than one
module needed it. Mirrors the precedent set in #213, where
``cap_characters``/``MAX_CHARS_FOR_LLM`` moved to ``text_limits.py``.
"""


def clean_git_error_text(raw: bytes | str | None, label: str) -> str:
    """Unwrap GitPython's decorated ``GitCommandError`` stdout/stderr text.

    GitPython's ``CommandError.__init__`` never exposes the raw stdout/stderr
    it was given: it re-formats it as ``"\\n  <label>: '<text>'"`` (see
    ``git.exc.CommandError``). Any code that wants to parse the actual git
    output -- not GitPython's decorated wrapper -- needs to undo that first.
    """
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        raw = raw.decode()
    prefix = f"\n  {label}: '"
    if raw.startswith(prefix) and raw.endswith("'"):
        return raw[len(prefix) : -1]
    return raw
