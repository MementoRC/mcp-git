"""Turn a user-supplied value into a ProjectV2FieldValue input (#345)."""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import date
from typing import Any

from .projects_gql import ProjectError

__all__ = ["build_value"]


def _pick(kind: str, raw: str, choices: dict[str, str]) -> str:
    """Id of the choice whose name matches *raw*; error lists valid names."""
    for name, ident in choices.items():
        if name.lower() == raw.strip().lower():
            return ident
    valid = ", ".join(choices)
    raise ProjectError(f"Unknown {kind} '{raw}'. Valid {kind}s: {valid}")


def _single_select(field: dict[str, Any], raw: str) -> dict[str, Any]:
    options = {o["name"]: o["id"] for o in field.get("options") or []}
    return {"singleSelectOptionId": _pick("option", raw, options)}


def _iteration(field: dict[str, Any], raw: str) -> dict[str, Any]:
    config = field.get("configuration") or {}
    found = [*config.get("iterations", []), *config.get("completedIterations", [])]
    return {
        "iterationId": _pick("iteration", raw, {i["title"]: i["id"] for i in found})
    }


def _number(_field: dict[str, Any], raw: str) -> dict[str, Any]:
    try:
        number = float(raw)
    except ValueError:
        raise ProjectError(f"'{raw}' is not a number.") from None
    if not math.isfinite(number):
        raise ProjectError(f"'{raw}' is not a finite number (NaN/inf rejected).")
    return {"number": number}


def _date(_field: dict[str, Any], raw: str) -> dict[str, Any]:
    try:
        return {"date": date.fromisoformat(raw.strip()).isoformat()}
    except ValueError:
        raise ProjectError(f"'{raw}' is not an ISO date (YYYY-MM-DD).") from None


_BUILDERS: dict[str, Callable[[dict[str, Any], str], dict[str, Any]]] = {
    "SINGLE_SELECT": _single_select,
    "ITERATION": _iteration,
    "NUMBER": _number,
    "DATE": _date,
    "TEXT": lambda _field, raw: {"text": raw},
}


def build_value(field: dict[str, Any], raw: str) -> dict[str, Any]:
    """ProjectV2FieldValue input for *field*; value resolved by name/parse."""
    builder = _BUILDERS.get(field.get("dataType", ""))
    if builder is None:
        raise ProjectError(
            f"Field '{field['name']}' has unsupported type {field.get('dataType')}; "
            "supported: SINGLE_SELECT, TEXT, NUMBER, DATE, ITERATION."
        )
    return builder(field, raw)
