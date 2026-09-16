"""Shared error-envelope enrichment for the lean interface's two transports.

Issue #227 Part 2: the MCP path (``execute_tool`` -> ``_build_envelope`` in
``meta_tools.py``) and the HTTP direct-invocation path (``execute_tool_direct``
in ``interface.py``) both need to add a ``valid_parameters`` hint when a tool
implementation rejects an unknown/removed keyword argument. This module holds
that single piece of logic so neither transport re-implements (and risks
drifting from) the other.
"""

from typing import Any


def add_valid_parameters_hint(
    envelope: dict[str, Any], error_message: str, schema: dict[str, Any] | None
) -> dict[str, Any]:
    """Add a ``valid_parameters`` hint to an error envelope, in place.

    Every registered tool implementation is wrapped by
    ``GitLeanInterface._wrap_tool``, which catches exceptions -- including
    the ``TypeError`` raised for an unexpected/removed keyword argument
    (e.g. a deprecated alias) -- and converts them into an error-shaped
    dict rather than letting them propagate. When the resulting message
    matches that TypeError's wording and a JSON Schema is available, this
    appends the tool's accepted parameter names so callers can self-correct
    without a separate ``get_tool_spec`` round trip.

    Args:
        envelope: The error envelope dict to enrich and return.
        error_message: The error message to inspect for the unknown-kwarg
            phrasing ("unexpected keyword argument").
        schema: The tool's JSON Schema, or None if unavailable.

    Returns:
        The same envelope dict, with "valid_parameters" added when the
        error message matches and a schema was provided.
    """
    if schema is not None and "unexpected keyword argument" in error_message:
        envelope["valid_parameters"] = list(schema.get("properties", {}).keys())
    return envelope
