"""Shared execute_tool response envelope builder for both lean transports.

Issue #232: the MCP path (``execute_tool`` -> ``_build_envelope`` in
``meta_tools.py``) promoted *every* error-shaped tool result to a
``"status": "error"`` envelope (the issue #196 defect-2 fix), but the HTTP
direct-invocation path (``execute_tool_direct`` in ``interface.py``) only
ever re-implemented a narrow slice of that logic -- promoting just the
unexpected-keyword-argument case (issue #227 Part 2) -- so every other
error-shaped result fell through to a ``"status": "success"`` envelope with
the error buried in ``"result"``. This module holds the single envelope-
construction rule so the two transports cannot diverge a fourth time.
"""

from typing import Any

from ._error_hints import add_valid_parameters_hint


def _is_error_result(result: Any) -> bool:
    """
    Detect whether a tool implementation's return value is error-shaped.

    Issue #196 defect 2: ``_wrap_tool`` in interface.py catches exceptions
    raised by tool implementations and converts them into a dict of the
    form ``{"error": str(e), "tool": tool_name, "success": False}`` rather
    than re-raising. Previously, ``execute_tool`` unconditionally wrapped
    *any* returned value (including this error dict) in a
    ``{"status": "success", "result": ...}`` envelope, producing a
    contradictory response where the outer envelope claims success while
    the inner payload reports failure.

    This check is intentionally strict to avoid false positives on tools
    that legitimately carry an ``"error"`` key as *data* (e.g. a CI-log
    payload describing someone else's error): a result is only considered
    error-shaped when it is a dict, contains an ``"error"`` key, AND its
    ``"success"`` key is precisely the value ``False`` (identity
    comparison, not truthiness) as emitted by ``_wrap_tool``.

    Args:
        result: The raw value returned by a tool implementation.

    Returns:
        True if the result matches the ``_wrap_tool`` error shape.
    """
    if not isinstance(result, dict):
        return False
    if "error" not in result:
        return False
    return result.get("success") is False


def build_tool_envelope(
    tool_name: str,
    result: Any,
    schema: dict[str, Any] | None = None,
    execution_mode: str | None = None,
) -> dict[str, Any]:
    """Build the execute_tool response envelope shared by both transports.

    The top-level status must never contradict an error payload (issue
    #196 defect 2, and its HTTP-transport recurrence, issue #232).

    Every registered tool implementation is wrapped by
    ``GitLeanInterface._wrap_tool`` (see ``register_tool``), which catches
    exceptions -- including the ``TypeError`` raised for an unexpected/
    removed keyword argument (e.g. a deprecated alias) -- and converts them
    into an error-shaped dict rather than letting them propagate. This is
    the chokepoint, shared by every git/github/azure tool and both
    transports, where an unknown-kwarg error is enriched with the accepted
    parameter names via ``add_valid_parameters_hint`` (issue #227 Part 2),
    mirroring the "valid_parameters" hint already returned for JSON Schema
    validation failures.

    Args:
        tool_name: Name of the tool that was executed.
        result: The raw value returned by the tool implementation.
        schema: The tool's JSON Schema, used for the ``valid_parameters``
            hint when applicable. Optional.
        execution_mode: When provided, added to the envelope verbatim
            (the MCP path sets this to ``"lean_mcp_dynamic"``; the HTTP
            direct path omits it entirely -- that difference is
            intentional and must be preserved by callers).

    Returns:
        A ``{"tool", "status", "result", ...}`` envelope, with ``"error"``
        (and possibly ``"valid_parameters"``) added when *result* is
        error-shaped.
    """
    if _is_error_result(result):
        envelope: dict[str, Any] = {
            "tool": tool_name,
            "status": "error",
            "error": result.get("error"),
            "result": result,
        }
        if execution_mode is not None:
            envelope["execution_mode"] = execution_mode
        return add_valid_parameters_hint(
            envelope, str(result.get("error") or ""), schema
        )

    envelope = {
        "tool": tool_name,
        "status": "success",
        "result": result,
    }
    if execution_mode is not None:
        envelope["execution_mode"] = execution_mode
    return envelope
