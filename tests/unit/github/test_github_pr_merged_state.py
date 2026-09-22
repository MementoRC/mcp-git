"""
Unit tests for merged-vs-closed PR rendering (issue #239).

A merged PR and one closed without merging were indistinguishable: both
rendered as "State: closed". github_list_pull_requests mapped a "merged"
key that GitHub REST never sets on `state`, so its purple marker was
unreachable and every closed PR showed the same red one.

The failure direction that matters is treating a closed-unmerged PR as
merged: branch-pruning acts on that answer and force-deletes work that
never landed. Several tests below guard that direction specifically.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp_server_git.github.pr import (
    github_get_pr_details,
    github_get_pr_status,
    github_list_pull_requests,
)

PATCH_TARGET = "src.mcp_server_git.github.pr.github_client_context"

MERGED_AT = "2026-09-17T22:14:05Z"


def _pr_json(**overrides) -> dict:
    """A single-PR payload as the /pulls/{n} endpoint returns it."""
    base = {
        "number": 235,
        "title": "Some change",
        "state": "closed",
        "user": {"login": "alice"},
        "base": {"ref": "development"},
        "head": {"ref": "feature-x", "sha": "abc1234"},
        "created_at": "2026-09-16T10:00:00Z",
        "updated_at": "2026-09-17T22:14:05Z",
        "merged": True,
        "merged_at": MERGED_AT,
        "merged_by": {"login": "bob"},
        "merge_commit_sha": "a1b2c3d4e5f6",
        "mergeable": None,
        "mergeable_state": "unknown",
        "html_url": "https://github.com/owner/repo/pull/235",
    }
    base.update(overrides)
    return base


def _closed_unmerged(**overrides) -> dict:
    """PR #190 in the issue: closed, never merged."""
    return _pr_json(
        state="closed",
        merged=False,
        merged_at=None,
        merged_by=None,
        merge_commit_sha=None,
        mergeable=False,
        mergeable_state="dirty",
        **overrides,
    )


def _open_pr(**overrides) -> dict:
    return _pr_json(
        state="open",
        merged=False,
        merged_at=None,
        merged_by=None,
        merge_commit_sha=None,
        mergeable=True,
        mergeable_state="clean",
        **overrides,
    )


def _details_client(pr_json: dict) -> MagicMock:
    """github_get_pr_details makes one GET when no files/reviews requested."""
    client = MagicMock()
    response = AsyncMock()
    response.status = 200
    response.json = AsyncMock(return_value=pr_json)
    client.get = AsyncMock(return_value=response)
    return client


def _status_client(pr_json: dict) -> MagicMock:
    """github_get_pr_status GETs the PR, then its head sha's check-runs."""
    client = MagicMock()

    pr_response = AsyncMock()
    pr_response.status = 200
    pr_response.json = AsyncMock(return_value=pr_json)

    checks_response = AsyncMock()
    checks_response.status = 200
    checks_response.json = AsyncMock(return_value={"check_runs": []})

    client.get = AsyncMock(side_effect=[pr_response, checks_response])
    return client


def _list_client(prs: list[dict]) -> MagicMock:
    client = MagicMock()
    response = AsyncMock()
    response.status = 200
    response.json = AsyncMock(return_value=prs)
    client.get = AsyncMock(return_value=response)
    return client


def _patched(client: MagicMock):
    ctx = patch(PATCH_TARGET)
    mock_context = ctx.start()
    mock_context.return_value.__aenter__ = AsyncMock(return_value=client)
    mock_context.return_value.__aexit__ = AsyncMock(return_value=None)
    return ctx


class TestPrDetailsMergedRendering:
    @pytest.mark.asyncio
    async def test_details_renders_merged_yes_with_date_and_author(self) -> None:
        ctx = _patched(_details_client(_pr_json()))
        try:
            result = await github_get_pr_details("owner", "repo", 235)
        finally:
            ctx.stop()

        assert "Merged: yes" in result
        assert MERGED_AT in result
        assert "bob" in result

    @pytest.mark.asyncio
    async def test_details_includes_merge_commit_sha_when_merged(self) -> None:
        ctx = _patched(_details_client(_pr_json()))
        try:
            result = await github_get_pr_details("owner", "repo", 235)
        finally:
            ctx.stop()

        assert "a1b2c3d" in result

    @pytest.mark.asyncio
    async def test_details_renders_merged_no_for_closed_unmerged(self) -> None:
        ctx = _patched(_details_client(_closed_unmerged()))
        try:
            result = await github_get_pr_details("owner", "repo", 190)
        finally:
            ctx.stop()

        assert "Merged: no" in result

    @pytest.mark.asyncio
    async def test_details_never_renders_closed_unmerged_as_merged(self) -> None:
        """The direction whose failure destroys work."""
        ctx = _patched(_details_client(_closed_unmerged()))
        try:
            result = await github_get_pr_details("owner", "repo", 190)
        finally:
            ctx.stop()

        assert "Merged: yes" not in result

    @pytest.mark.asyncio
    async def test_details_treats_missing_merge_keys_as_not_merged(self) -> None:
        """A payload lacking the keys entirely must not read as merged."""
        payload = _pr_json()
        for key in ("merged", "merged_at", "merged_by", "merge_commit_sha"):
            payload.pop(key)

        ctx = _patched(_details_client(payload))
        try:
            result = await github_get_pr_details("owner", "repo", 190)
        finally:
            ctx.stop()

        assert "Merged: yes" not in result
        assert "Merged: no" in result

    @pytest.mark.asyncio
    async def test_details_omits_merged_line_for_open_pr(self) -> None:
        """Merged-ness is not yet a question for an open PR."""
        ctx = _patched(_details_client(_open_pr()))
        try:
            result = await github_get_pr_details("owner", "repo", 300)
        finally:
            ctx.stop()

        assert "Merged:" not in result


class TestPrStatusMergedRendering:
    @pytest.mark.asyncio
    async def test_status_renders_merged_yes_for_merged_pr(self) -> None:
        ctx = _patched(_status_client(_pr_json()))
        try:
            result = await github_get_pr_status("owner", "repo", 235)
        finally:
            ctx.stop()

        assert "Merged: yes" in result
        assert MERGED_AT in result

    @pytest.mark.asyncio
    async def test_status_renders_merged_no_for_closed_unmerged(self) -> None:
        ctx = _patched(_status_client(_closed_unmerged()))
        try:
            result = await github_get_pr_status("owner", "repo", 190)
        finally:
            ctx.stop()

        assert "Merged: no" in result

    @pytest.mark.asyncio
    async def test_status_never_renders_closed_unmerged_as_merged(self) -> None:
        ctx = _patched(_status_client(_closed_unmerged()))
        try:
            result = await github_get_pr_status("owner", "repo", 190)
        finally:
            ctx.stop()

        assert "Merged: yes" not in result

    @pytest.mark.asyncio
    async def test_status_omits_mergeable_lines_for_closed_pr(self) -> None:
        """'Can this merge now' is noise once the PR is closed; rendering
        'Mergeable: None / Merge State: unknown' is what made a merged PR
        and an abandoned one look alike."""
        ctx = _patched(_status_client(_pr_json()))
        try:
            result = await github_get_pr_status("owner", "repo", 235)
        finally:
            ctx.stop()

        assert "Mergeable:" not in result
        assert "Merge State:" not in result

    @pytest.mark.asyncio
    async def test_status_keeps_mergeable_lines_for_open_pr(self) -> None:
        """Regression guard: mergeable_state is meaningful while open."""
        ctx = _patched(_status_client(_open_pr()))
        try:
            result = await github_get_pr_status("owner", "repo", 300)
        finally:
            ctx.stop()

        assert "Mergeable:" in result
        assert "Merge State:" in result


class TestListPullRequestsMarker:
    @pytest.mark.asyncio
    async def test_list_marks_open_pr_green(self) -> None:
        ctx = _patched(_list_client([_open_pr()]))
        try:
            result = await github_list_pull_requests("owner", "repo", state="open")
        finally:
            ctx.stop()

        assert "🟢" in result

    @pytest.mark.asyncio
    async def test_list_marks_merged_pr_purple(self) -> None:
        """The list endpoint carries merged_at but no 'merged' bool."""
        merged = _pr_json()
        merged.pop("merged")
        ctx = _patched(_list_client([merged]))
        try:
            result = await github_list_pull_requests("owner", "repo", state="closed")
        finally:
            ctx.stop()

        assert "🟣" in result

    @pytest.mark.asyncio
    async def test_list_marks_closed_unmerged_red(self) -> None:
        ctx = _patched(_list_client([_closed_unmerged()]))
        try:
            result = await github_list_pull_requests("owner", "repo", state="closed")
        finally:
            ctx.stop()

        assert "🔴" in result

    @pytest.mark.asyncio
    async def test_list_never_marks_closed_unmerged_as_merged(self) -> None:
        """10 of 149 closed PRs were never merged; marking them merged is
        what force-deletes branches holding unlanded work."""
        ctx = _patched(_list_client([_closed_unmerged()]))
        try:
            result = await github_list_pull_requests("owner", "repo", state="closed")
        finally:
            ctx.stop()

        assert "🟣" not in result

    @pytest.mark.asyncio
    async def test_list_distinguishes_merged_from_unmerged_in_one_page(self) -> None:
        """The pruning case: both kinds in a single listing."""
        merged = _pr_json(number=235)
        merged.pop("merged")
        unmerged = _closed_unmerged(number=190)

        ctx = _patched(_list_client([merged, unmerged]))
        try:
            result = await github_list_pull_requests("owner", "repo", state="closed")
        finally:
            ctx.stop()

        assert "🟣" in result
        assert "🔴" in result
        merged_line = next(ln for ln in result.splitlines() if "#235" in ln)
        unmerged_line = next(ln for ln in result.splitlines() if "#190" in ln)
        assert "🟣" in merged_line
        assert "🔴" in unmerged_line
