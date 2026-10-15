"""Workflow job/run markers distinguish skipped from failed (issue #293)."""

from unittest.mock import patch

import pytest

from mcp_server_git.github.api import github_get_workflow_run
from mcp_server_git.github.check_markers import conclusion_marker
from tests.unit.github.test_workflow_run_job_ids import (
    WF_CTX,
    FakeClient,
    _job,
    _routes,
)


@pytest.mark.parametrize(
    ("conclusion", "expected"),
    [
        ("success", "✅"),
        ("failure", "❌"),
        ("timed_out", "❌"),
        ("startup_failure", "❌"),
        ("action_required", "⚠️"),
        ("cancelled", "🚫"),
        ("skipped", "⏭️"),
        ("neutral", "➖"),
        ("stale", "🕒"),
        (None, "⏳"),
        ("", "⏳"),
        ("brand_new_value", "❓"),
    ],
)
def test_conclusion_marker_returns_expected_marker_when_conclusion_given(
    conclusion, expected
):
    assert conclusion_marker(conclusion) == expected


def test_conclusion_marker_returns_in_progress_marker_when_no_conclusion_and_running():
    assert conclusion_marker(None, "in_progress") == "🔄"


@pytest.mark.asyncio
async def test_github_get_workflow_run_marks_skipped_job_distinctly_when_job_skipped():
    client = FakeClient(
        _routes([_job(1, "deploy", "skipped"), _job(2, "build", "failure")])
    )

    with patch(WF_CTX) as wf:
        wf.return_value.__aenter__.return_value = client
        result = await github_get_workflow_run("o", "r", 9)

    assert "⏭️ deploy" in result
    assert "❌ build" in result
    assert "❌ deploy" not in result
