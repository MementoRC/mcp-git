"""Shared None/empty semantics for the GitHub update ops (issue #275).

For update operations ``None`` means "leave unchanged" (the field is omitted),
and an explicit empty value (``""``, ``[]``, or ``0`` for an unsettable id)
means "clear the field". A field that can never be empty must be rejected up
front, before any request is made.
"""

from __future__ import annotations

from collections.abc import Mapping


def required_text_error(name: str, value: str | None) -> str | None:
    """Return an error message when a required text field is explicitly empty."""
    if value != "":
        return None
    return f"❌ {name} cannot be empty. Pass None to leave it unchanged."


def first_required_error(fields: Mapping[str, str | None]) -> str | None:
    """First ``required_text_error`` across ``fields`` (in order), or None."""
    for name, value in fields.items():
        error = required_text_error(name, value)
        if error:
            return error
    return None
