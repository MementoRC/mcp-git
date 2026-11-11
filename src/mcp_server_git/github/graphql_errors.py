"""Collapse repeated per-field GraphQL errors into a readable message.

GitHub reports a scope failure once per selected field, so one missing scope
yields many near-identical messages differing only in ``The '<field>' field``.
"""

import re
from typing import Any

MAX_GROUPS = 5
MAX_FIELDS = 5

_FIELD_RE = re.compile(r"The '([^']+)' field")
_PLACEHOLDER = "The field"


def _normalize(message: str) -> tuple[str, str | None]:
    """Return (message without the field fragment, field name or None)."""
    match = _FIELD_RE.search(message)
    if match is None:
        return message, None
    return _FIELD_RE.sub(_PLACEHOLDER, message, count=1), match.group(1)


def _render_group(text: str, fields: list[str], count: int) -> str:
    if count == 1 or not fields:
        return text
    shown = ", ".join(fields[:MAX_FIELDS])
    extra = len(fields) - MAX_FIELDS
    if extra > 0:
        shown += f", +{extra} more"
    return f"{text} ({count} fields: {shown})"


def summarize_graphql_errors(errors: list[dict[str, Any]]) -> str:
    """Join error messages, grouping those identical apart from the field."""
    groups: dict[str, tuple[list[str], list[int]]] = {}
    originals: dict[str, str] = {}
    for error in errors:
        message = error.get("message", str(error))
        text, field = _normalize(message)
        names, count = groups.setdefault(text, ([], [0]))
        originals.setdefault(text, message)
        count[0] += 1
        if field is not None and field not in names:
            names.append(field)

    rendered = [
        _render_group(text if count[0] > 1 else originals[text], names, count[0])
        for text, (names, count) in list(groups.items())[:MAX_GROUPS]
    ]
    hidden = len(groups) - MAX_GROUPS
    if hidden > 0:
        rendered.append(f"+{hidden} more errors")
    return "; ".join(rendered)
