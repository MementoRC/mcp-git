"""Explicit failure type for string-returning tool operations."""

__all__ = ["ToolFailure", "fail"]


class ToolFailure(str):
    """An operation's failure message.

    The execute_tool envelope reports ``"status": "error"`` for it. It is
    still a ``str``, so callers and tests comparing the text are unaffected.
    """

    __slots__ = ()


def fail(message: str) -> ToolFailure:
    """Return *message* marked as a tool failure."""
    return ToolFailure(message)
