"""Tests for grep / line-range trimming in github_get_content (#314)."""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_server_git.github.api import github_get_content
from mcp_server_git.lean.interface import GitLeanInterface
from mcp_server_git.utils.tool_failure import ToolFailure

FILE_TEXT = "\n".join(
    f"line {i}{' NEEDLE' if i % 4 == 0 else ''}" for i in range(1, 13)
)


async def _get(**kwargs):
    response = AsyncMock()
    response.status = 200
    response.json = AsyncMock(
        return_value={
            "type": "file",
            "encoding": "base64",
            "content": base64.b64encode(FILE_TEXT.encode()).decode("ascii"),
            "sha": "abc123",
            "size": len(FILE_TEXT),
        }
    )
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    with patch("mcp_server_git.github.contents.github_client_context") as ctx:
        ctx.return_value.__aenter__.return_value = client
        return await github_get_content("o", "r", "f.ml", ref="5.5.1", **kwargs)


@pytest.mark.asyncio
async def test_get_content_returns_numbered_matches_when_grep_given():
    result = await _get(grep="NEEDLE")
    assert "3 matching lines" in result
    assert "4: line 4 NEEDLE" in result
    assert "12: line 12 NEEDLE" in result
    assert "line 5" not in result
    assert "sha: abc123" in result and "@ 5.5.1" in result


@pytest.mark.asyncio
async def test_get_content_returns_exact_lines_when_range_given():
    result = await _get(start_line=2, end_line=4)
    assert "showing lines 2-4 of 12" in result
    assert "2: line 2\n3: line 3\n4: line 4 NEEDLE" in result
    assert "1: line 1" not in result and "5: line 5" not in result


@pytest.mark.asyncio
async def test_get_content_returns_matches_in_range_when_grep_and_range_given():
    result = await _get(grep="NEEDLE", start_line=5, end_line=9)
    assert "1 matching lines" in result
    assert "8: line 8 NEEDLE" in result
    assert "4: line 4" not in result and "12: line 12" not in result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs", [{"start_line": 5, "end_line": 2}, {"start_line": 0}, {"grep": "("}]
)
async def test_get_content_returns_failure_when_selection_invalid(kwargs):
    result = await _get(**kwargs)
    assert isinstance(result, ToolFailure)
    assert "❌" in result


@pytest.mark.asyncio
async def test_get_content_returns_notice_when_grep_has_no_matches():
    result = await _get(grep="ZZZ")
    assert not isinstance(result, ToolFailure)
    assert "No lines matched 'ZZZ'" in result
    assert "sha: abc123" in result


@pytest.mark.asyncio
async def test_get_content_returns_full_unnumbered_text_when_no_trim_params():
    result = await _get()
    assert result.endswith("\n\n" + FILE_TEXT)
    assert "matching" not in result and "showing lines" not in result


def test_discover_tools_returns_get_content_when_pattern_is_file():
    iface = GitLeanInterface(MagicMock(), MagicMock(), MagicMock())
    found = iface.discover_tools("file")
    assert "github_get_file_contents" in str(found)
