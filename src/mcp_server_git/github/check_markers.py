"""Markers for GitHub check-run status and conclusion.

``github_get_pr_status`` and ``github_get_pr_checks`` both render a check
run as a marker plus its name, and both carried a *verbatim copy* of the
mapping. Both collapsed every non-"success" conclusion onto ❌ (issue #246),
so a ``skipped`` check -- routine anywhere jobs are conditional -- read as a
failure.

Only ``failure`` and ``timed_out`` are failures. Everything else is merely
*not success*, and painting it red makes a green PR look broken: on this
repo five of fifteen checks are normally skipped, so every healthy PR
reported five false failures.

An unrecognised conclusion renders ❓ rather than ❌ on purpose. The defect
being fixed is over-reporting failure, so the fallback must not reintroduce
it when GitHub adds a conclusion this table has not seen.

Pure: no network, no I/O.
"""

from __future__ import annotations

UNKNOWN_MARKER = "❓"

CONCLUSION_MARKERS = {
    "success": "✅",
    "failure": "❌",
    "timed_out": "❌",
    "skipped": "⏭️",
    "neutral": "➖",
    "cancelled": "🚫",
    "action_required": "⚠️",
    "stale": "🕒",
}

STATUS_MARKERS = {
    "in_progress": "🔄",
    "queued": "⏳",
    "waiting": "⏳",
    "pending": "⏳",
    "requested": "⏳",
}


def check_marker(run: dict) -> str:
    """Render one check run's marker from its status and conclusion.

    A completed run is described by its ``conclusion``; one still running is
    described by its ``status``. Unknown values in either position fall back
    to ❓, never to a failure marker (see module docstring).
    """
    if run.get("status") == "completed":
        conclusion = run.get("conclusion")
        if conclusion is None:
            return UNKNOWN_MARKER
        return CONCLUSION_MARKERS.get(str(conclusion), UNKNOWN_MARKER)
    return STATUS_MARKERS.get(str(run.get("status")), UNKNOWN_MARKER)
