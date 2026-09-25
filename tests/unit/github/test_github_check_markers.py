"""
Unit tests for check-run marker rendering (issue #246).

``github_get_pr_status`` and ``github_get_pr_checks`` both render a check
run as a marker plus its name, and both carried a *verbatim copy* of the
same mapping: ``{"completed": "✅" if conclusion == "success" else "❌", ...}``.
That collapsed every non-"success" conclusion onto ❌, so a ``skipped``
check -- routine anywhere jobs are conditional -- read as a failure.

The failure direction that matters is treating a non-failure conclusion
(skipped, neutral, cancelled, action_required, stale) as a failure: it
makes a healthy PR look broken and erodes trust in the status output.
Several tests below guard that direction specifically, and a companion
guard makes sure the fix doesn't over-correct by turning a real
``failure`` conclusion green.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp_server_git.github.check_markers import check_marker
from src.mcp_server_git.github.pr import github_get_pr_checks, github_get_pr_status

PATCH_TARGET = "src.mcp_server_git.github.pr.github_client_context"


def _pr_json(**overrides) -> dict:
    """A single-PR payload as the /pulls/{n} endpoint returns it."""
    base = {
        "number": 235,
        "title": "Some change",
        "state": "open",
        "user": {"login": "alice"},
        "base": {"ref": "development"},
        "head": {"ref": "feature-x", "sha": "abc1234"},
        "created_at": "2026-09-16T10:00:00Z",
        "updated_at": "2026-09-17T22:14:05Z",
        "merged": False,
        "merged_at": None,
        "merged_by": None,
        "merge_commit_sha": None,
        "mergeable": True,
        "mergeable_state": "clean",
        "html_url": "https://github.com/owner/repo/pull/235",
    }
    base.update(overrides)
    return base


def _check_run(**overrides) -> dict:
    """A single check-run entry as the check-runs endpoint returns it."""
    base = {
        "name": "build",
        "status": "completed",
        "conclusion": "success",
        "started_at": "2026-09-17T22:00:00Z",
        "completed_at": "2026-09-17T22:10:00Z",
        "html_url": "https://github.com/owner/repo/runs/1",
    }
    base.update(overrides)
    return base


def _status_client(pr_json: dict, check_runs: list[dict]) -> MagicMock:
    """github_get_pr_status GETs the PR, then its head sha's check-runs."""
    client = MagicMock()

    pr_response = AsyncMock()
    pr_response.status = 200
    pr_response.json = AsyncMock(return_value=pr_json)

    checks_response = AsyncMock()
    checks_response.status = 200
    checks_response.json = AsyncMock(return_value={"check_runs": check_runs})

    client.get = AsyncMock(side_effect=[pr_response, checks_response])
    return client


def _checks_client(pr_json: dict, check_runs: list[dict]) -> MagicMock:
    """github_get_pr_checks GETs the PR, then its head sha's check-runs."""
    client = MagicMock()

    pr_response = AsyncMock()
    pr_response.status = 200
    pr_response.json = AsyncMock(return_value=pr_json)

    checks_response = AsyncMock()
    checks_response.status = 200
    checks_response.json = AsyncMock(return_value={"check_runs": check_runs})

    client.get = AsyncMock(side_effect=[pr_response, checks_response])
    return client


def _patched(client: MagicMock):
    ctx = patch(PATCH_TARGET)
    mock_context = ctx.start()
    mock_context.return_value.__aenter__ = AsyncMock(return_value=client)
    mock_context.return_value.__aexit__ = AsyncMock(return_value=None)
    return ctx


class TestCheckMarkerConclusions:
    """Pure unit tests of check_marker's completed-run branch."""

    def test_success_conclusion_renders_check_mark(self) -> None:
        assert check_marker(_check_run(conclusion="success")) == "✅"

    def test_failure_conclusion_renders_cross_mark(self) -> None:
        assert check_marker(_check_run(conclusion="failure")) == "❌"

    def test_timed_out_conclusion_renders_cross_mark(self) -> None:
        assert check_marker(_check_run(conclusion="timed_out")) == "❌"

    def test_skipped_conclusion_renders_skip_marker(self) -> None:
        assert check_marker(_check_run(conclusion="skipped")) == "⏭️"

    def test_neutral_conclusion_renders_dash(self) -> None:
        assert check_marker(_check_run(conclusion="neutral")) == "➖"

    def test_cancelled_conclusion_renders_no_entry_marker(self) -> None:
        assert check_marker(_check_run(conclusion="cancelled")) == "🚫"

    def test_action_required_conclusion_renders_warning(self) -> None:
        assert check_marker(_check_run(conclusion="action_required")) == "⚠️"

    def test_stale_conclusion_renders_clock(self) -> None:
        assert check_marker(_check_run(conclusion="stale")) == "🕒"

    def test_completed_with_none_conclusion_renders_unknown(self) -> None:
        assert check_marker(_check_run(conclusion=None)) == "❓"

    def test_completed_with_unrecognised_conclusion_renders_unknown_not_failure(
        self,
    ) -> None:
        """An unrecognised conclusion must fall back to ❓, never ❌, so a
        future GitHub conclusion this table hasn't seen isn't painted red."""
        assert check_marker(_check_run(conclusion="some_new_conclusion")) == "❓"


class TestCheckMarkerStatuses:
    """Pure unit tests of check_marker's non-completed branch."""

    def test_in_progress_status_renders_spinner(self) -> None:
        assert check_marker(_check_run(status="in_progress", conclusion=None)) == "🔄"

    def test_queued_status_renders_hourglass(self) -> None:
        assert check_marker(_check_run(status="queued", conclusion=None)) == "⏳"

    def test_unrecognised_status_renders_unknown(self) -> None:
        assert (
            check_marker(_check_run(status="some_new_status", conclusion=None)) == "❓"
        )


class TestCheckMarkerGuardsAgainstFailureMisrendering:
    """The whole defect: a non-failure conclusion must never render ❌."""

    @pytest.mark.parametrize(
        "conclusion",
        ["skipped", "neutral", "cancelled", "action_required", "stale"],
    )
    def test_non_failure_conclusion_never_renders_cross_mark(
        self, conclusion: str
    ) -> None:
        assert check_marker(_check_run(conclusion=conclusion)) != "❌"

    def test_failure_conclusion_still_renders_cross_mark(self) -> None:
        """Guards over-correction: the fix must not turn real failures
        green (or any other non-❌ marker) while fixing skipped/neutral/etc."""
        assert check_marker(_check_run(conclusion="failure")) == "❌"


class TestPrStatusSkippedCheckRendering:
    """Integration: github_get_pr_status must not render skipped as failed."""

    @pytest.mark.asyncio
    async def test_status_skipped_check_does_not_render_cross_mark(self) -> None:
        runs = [
            _check_run(name="build", conclusion="success"),
            _check_run(name="e2e", conclusion="skipped"),
        ]
        ctx = _patched(_status_client(_pr_json(), runs))
        try:
            result = await github_get_pr_status("owner", "repo", 235)
        finally:
            ctx.stop()

        skipped_line = next(ln for ln in result.splitlines() if "e2e" in ln)
        assert "❌" not in skipped_line

    @pytest.mark.asyncio
    async def test_status_skipped_check_renders_skip_marker(self) -> None:
        runs = [
            _check_run(name="build", conclusion="success"),
            _check_run(name="e2e", conclusion="skipped"),
        ]
        ctx = _patched(_status_client(_pr_json(), runs))
        try:
            result = await github_get_pr_status("owner", "repo", 235)
        finally:
            ctx.stop()

        skipped_line = next(ln for ln in result.splitlines() if "e2e" in ln)
        assert "⏭️" in skipped_line


class TestPrChecksSkippedCheckRendering:
    """Integration: github_get_pr_checks must not render skipped as failed."""

    @pytest.mark.asyncio
    async def test_checks_skipped_check_does_not_render_cross_mark(self) -> None:
        runs = [
            _check_run(name="build", conclusion="success"),
            _check_run(name="e2e", conclusion="skipped"),
        ]
        ctx = _patched(_checks_client(_pr_json(), runs))
        try:
            result = await github_get_pr_checks("owner", "repo", 235)
        finally:
            ctx.stop()

        skipped_line = next(ln for ln in result.splitlines() if "e2e" in ln)
        assert "❌" not in skipped_line

    @pytest.mark.asyncio
    async def test_checks_skipped_check_renders_skip_marker(self) -> None:
        runs = [
            _check_run(name="build", conclusion="success"),
            _check_run(name="e2e", conclusion="skipped"),
        ]
        ctx = _patched(_checks_client(_pr_json(), runs))
        try:
            result = await github_get_pr_checks("owner", "repo", 235)
        finally:
            ctx.stop()

        skipped_line = next(ln for ln in result.splitlines() if "e2e" in ln)
        assert "⏭️" in skipped_line


class TestAntiDriftBothToolsAgree:
    """The bug was a verbatim duplicated mapping across two call sites.

    This asserts both tools render the identical marker for the identical
    check run, so the two sites cannot silently drift apart again.
    """

    @pytest.mark.asyncio
    async def test_status_and_checks_render_same_marker_for_skipped_run(
        self,
    ) -> None:
        runs = [_check_run(name="e2e", conclusion="skipped")]

        status_ctx = _patched(_status_client(_pr_json(), runs))
        try:
            status_result = await github_get_pr_status("owner", "repo", 235)
        finally:
            status_ctx.stop()

        checks_ctx = _patched(_checks_client(_pr_json(), runs))
        try:
            checks_result = await github_get_pr_checks("owner", "repo", 235)
        finally:
            checks_ctx.stop()

        status_line = next(ln for ln in status_result.splitlines() if "e2e" in ln)
        checks_line = next(ln for ln in checks_result.splitlines() if "e2e" in ln)

        assert "⏭️" in status_line
        assert "⏭️" in checks_line
