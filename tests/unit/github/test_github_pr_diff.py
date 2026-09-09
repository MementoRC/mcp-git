"""
Unit tests for GitHub pull request diff retrieval (#211).

Tests the github_get_pr_diff function including:
- Whole-diff inline return
- file_filter selection
- grep line filtering
- output_path write-to-disk
- The oversize gate and full_diff override
- Error handling (404, empty diff, conflicting selectors)
- as_patch media type selection
- The pure diff_sections helpers it depends on
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp_server_git.github.api import github_get_pr_diff
from src.mcp_server_git.github.diff_sections import (
    filter_sections,
    parse_header_path,
    render_sections,
    split_sections,
)


def _pr_diff_lines() -> list[str]:
    """Lines of a realistic 3-file unified diff."""
    return [
        "diff --git a/src/a.py b/src/a.py",
        "index 1111111..2222222 100644",
        "--- a/src/a.py",
        "+++ b/src/a.py",
        "@@ -1,3 +1,3 @@",
        " def a():",
        "-    return 1",
        "+    return 2",
        "diff --git a/src/b.py b/src/b.py",
        "index 3333333..4444444 100644",
        "--- a/src/b.py",
        "+++ b/src/b.py",
        "@@ -1,2 +1,2 @@",
        "-b_old_marker",
        "+b_new_marker",
        "diff --git a/docs/readme.md b/docs/readme.md",
        "index 5555555..6666666 100644",
        "--- a/docs/readme.md",
        "+++ b/docs/readme.md",
        "@@ -1 +1 @@",
        "-old readme line",
        "+new readme content",
    ]


def _sample_diff() -> str:
    return "\n".join(_pr_diff_lines())


def _oversized_diff() -> str:
    """A diff whose a.py section is padded past the 100KB inline cap."""
    lines = _pr_diff_lines()
    padding = [f"+padding line {i} {'x' * 80}" for i in range(1400)]
    insert_at = lines.index("+    return 2") + 1
    lines = lines[:insert_at] + padding + lines[insert_at:]
    return "\n".join(lines)


def _pr_json(**overrides) -> dict:
    base = {
        "title": "Add feature X",
        "state": "open",
        "merged": False,
        "base": {"ref": "main"},
        "head": {"ref": "feature-x"},
        "changed_files": 3,
        "additions": 10,
        "deletions": 4,
        "html_url": "https://github.com/owner/repo/pull/182",
    }
    base.update(overrides)
    return base


def _mock_pr_client(
    diff_text: str | None, pr_status: int = 200, diff_status: int = 200
):
    """Build a mock client returning a PR response then a diff response."""
    mock_client = MagicMock()

    pr_response = AsyncMock()
    pr_response.status = pr_status
    pr_response.json = AsyncMock(return_value=_pr_json())

    if pr_status != 200:
        mock_client.get = AsyncMock(return_value=pr_response)
        return mock_client

    diff_response = AsyncMock()
    diff_response.status = diff_status
    diff_response.text = AsyncMock(return_value=diff_text or "")

    mock_client.get = AsyncMock(side_effect=[pr_response, diff_response])
    return mock_client


class TestGitHubGetPRDiff:
    """Test github_get_pr_diff function."""

    @pytest.mark.asyncio
    async def test_get_pr_diff_returns_whole_diff_inline_when_small(self):
        """A small diff is returned inline, with PR header and body."""
        mock_client = _mock_pr_client(_sample_diff())

        with patch(
            "src.mcp_server_git.github.pr_diff.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_context.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await github_get_pr_diff("owner", "repo", 182)

            assert "🔀 PR #182" in result
            assert "📋 Diff (" in result
            assert "return 2" in result
            assert "b_new_marker" in result
            assert "new readme content" in result

    @pytest.mark.asyncio
    async def test_get_pr_diff_with_file_filter_returns_only_matching_files(self):
        """file_filter='src/*' keeps src/a.py and src/b.py, drops docs/readme.md."""
        mock_client = _mock_pr_client(_sample_diff())

        with patch(
            "src.mcp_server_git.github.pr_diff.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_context.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await github_get_pr_diff("owner", "repo", 182, file_filter="src/*")

            assert "return 2" in result
            assert "b_new_marker" in result
            assert "new readme content" not in result
            assert "🔎 file_filter 'src/*': 2 of 3 file(s)" in result

    @pytest.mark.asyncio
    async def test_get_pr_diff_with_file_filter_returns_no_match_message_when_none_match(
        self,
    ):
        """A file_filter matching nothing returns the no-match message and no body."""
        mock_client = _mock_pr_client(_sample_diff())

        with patch(
            "src.mcp_server_git.github.pr_diff.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_context.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await github_get_pr_diff(
                "owner", "repo", 182, file_filter="nomatch/*"
            )

            assert "🔍 No files matched" in result
            assert "📋 Diff (" not in result

    @pytest.mark.asyncio
    async def test_get_pr_diff_with_grep_returns_only_matching_lines(self):
        """grep returns only matching lines, with non-matching lines excluded."""
        mock_client = _mock_pr_client(_sample_diff())

        with patch(
            "src.mcp_server_git.github.pr_diff.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_context.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await github_get_pr_diff("owner", "repo", 182, grep="b_new_marker")

            assert "b_new_marker" in result
            assert "new readme content" not in result

    @pytest.mark.asyncio
    async def test_get_pr_diff_with_output_path_writes_file_with_no_diff_body(
        self, tmp_path
    ):
        """output_path writes the whole diff to disk; the response has no body."""
        output_path = tmp_path / "pr182.diff"
        diff_text = _sample_diff()
        mock_client = _mock_pr_client(diff_text)

        with patch(
            "src.mcp_server_git.github.pr_diff.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_context.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await github_get_pr_diff(
                "owner", "repo", 182, output_path=str(output_path)
            )

            assert output_path.exists()
            assert output_path.read_text(encoding="utf-8") == diff_text
            assert "💾 Full diff written to" in result
            assert "@@" not in result

    @pytest.mark.asyncio
    async def test_get_pr_diff_with_relative_output_path_returns_error(self):
        """A relative output_path returns the absolute-path error."""
        mock_client = _mock_pr_client(_sample_diff())

        with patch(
            "src.mcp_server_git.github.pr_diff.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_context.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await github_get_pr_diff(
                "owner", "repo", 182, output_path="relative/pr.diff"
            )

            assert "❌ output_path must be an absolute path" in result

    @pytest.mark.asyncio
    async def test_get_pr_diff_returns_oversize_gate_when_too_large_and_no_selectors(
        self,
    ):
        """A diff over 100KB with no selectors is withheld behind a gate."""
        mock_client = _mock_pr_client(_oversized_diff())

        with patch(
            "src.mcp_server_git.github.pr_diff.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_context.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await github_get_pr_diff("owner", "repo", 182)

            assert "⚠️ Diff is" in result
            assert "output_path=" in result
            assert "📋 Diff (" not in result

    @pytest.mark.asyncio
    async def test_get_pr_diff_with_full_diff_true_returns_body_despite_oversize(self):
        """full_diff=True returns the body (still capped) instead of the gate."""
        mock_client = _mock_pr_client(_oversized_diff())

        with patch(
            "src.mcp_server_git.github.pr_diff.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_context.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await github_get_pr_diff("owner", "repo", 182, full_diff=True)

            assert "📋 Diff (" in result
            assert "⚠️ Truncated for LLM context" in result

    @pytest.mark.asyncio
    async def test_get_pr_diff_returns_not_found_when_pr_missing(self):
        """A 404 PR response surfaces as a not-found error message."""
        mock_client = _mock_pr_client(None, pr_status=404)

        with patch(
            "src.mcp_server_git.github.pr_diff.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_context.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await github_get_pr_diff("owner", "repo", 999)

            assert "❌ PR #999 not found" in result

    @pytest.mark.asyncio
    async def test_get_pr_diff_returns_empty_message_when_diff_is_empty(self):
        """An empty diff body returns the empty-diff message."""
        mock_client = _mock_pr_client("")

        with patch(
            "src.mcp_server_git.github.pr_diff.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_context.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await github_get_pr_diff("owner", "repo", 182)

            assert "📭 Diff is empty" in result

    @pytest.mark.asyncio
    async def test_get_pr_diff_with_conflicting_selectors_returns_error_message(self):
        """head_lines and tail_lines together surface the conflicting-selector error."""
        mock_client = _mock_pr_client(_sample_diff())

        with patch(
            "src.mcp_server_git.github.pr_diff.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_context.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await github_get_pr_diff(
                "owner", "repo", 182, head_lines=5, tail_lines=5
            )

            assert (
                "Use only one of head_lines, tail_lines, or start_line/end_line."
                in result
            )

    @pytest.mark.asyncio
    async def test_get_pr_diff_with_as_patch_requests_patch_media_type(self):
        """as_patch=True requests the .patch media type on the diff fetch."""
        mock_client = _mock_pr_client(_sample_diff())

        with patch(
            "src.mcp_server_git.github.pr_diff.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_context.return_value.__aexit__ = AsyncMock(return_value=None)

            await github_get_pr_diff("owner", "repo", 182, as_patch=True)

            second_call = mock_client.get.call_args_list[1]
            assert second_call.kwargs["accept"] == "application/vnd.github.v3.patch"


class TestDiffSections:
    """Pure tests for the diff_sections helpers."""

    def test_parse_header_path_returns_path_for_normal_header(self):
        header = "diff --git a/src/foo.py b/src/foo.py"
        assert parse_header_path(header) == "src/foo.py"

    def test_parse_header_path_returns_path_when_path_contains_space(self):
        header = "diff --git a/dir name/foo.py b/dir name/foo.py"
        assert parse_header_path(header) == "dir name/foo.py"

    def test_parse_header_path_returns_path_when_quoted_header_has_space(self):
        """git quotes both sides -- "a/<path>" "b/<path>" -- when path has a space."""
        header = 'diff --git "a/f oo.py" "b/f oo.py"'
        assert parse_header_path(header) == "f oo.py"

    def test_parse_header_path_decodes_octal_escapes_in_quoted_header(self):
        """Non-ASCII bytes are octal-escaped by git and must round-trip to UTF-8."""
        header = r'diff --git "a/caf\303\251.py" "b/caf\303\251.py"'
        assert parse_header_path(header) == "café.py"

    def test_parse_header_path_decodes_escaped_quotes_in_quoted_header(self):
        """Literal double quotes inside a quoted path are backslash-escaped."""
        header = r'diff --git "a/say \"hi\".py" "b/say \"hi\".py"'
        assert parse_header_path(header) == 'say "hi".py'

    def test_parse_header_path_returns_b_side_for_rename(self):
        """The b-side path wins so renames resolve to the post-image path."""
        header = "diff --git a/old/name.py b/new/name.py"
        assert parse_header_path(header) == "new/name.py"

    def test_parse_header_path_returns_path_for_unquoted_header_with_space(self):
        header = "diff --git a/f oo.py b/f oo.py"
        assert parse_header_path(header) == "f oo.py"

    def test_split_sections_returns_three_sections_and_round_trips(self):
        diff_text = _sample_diff()
        preamble, sections = split_sections(diff_text)

        assert preamble == ""
        assert [s.path for s in sections] == [
            "src/a.py",
            "src/b.py",
            "docs/readme.md",
        ]
        assert render_sections(sections) == diff_text

    def test_filter_sections_matches_by_basename(self):
        _preamble, sections = split_sections(_sample_diff())
        kept = filter_sections(sections, "readme.md")
        assert [s.path for s in kept] == ["docs/readme.md"]

    def test_filter_sections_matches_by_glob(self):
        _preamble, sections = split_sections(_sample_diff())
        kept = filter_sections(sections, "src/*")
        assert [s.path for s in kept] == ["src/a.py", "src/b.py"]

    def test_filter_sections_matches_quoted_header_path_with_space(self):
        """A quoted "a/.." "b/.." header must still resolve to a matchable path."""
        diff_text = "\n".join(
            [
                'diff --git "a/f oo.py" "b/f oo.py"',
                "index 1111111..2222222 100644",
                '--- "a/f oo.py"',
                '+++ "b/f oo.py"',
                "@@ -1 +1 @@",
                "-old",
                "+new",
                "diff --git a/other.py b/other.py",
                "index 3333333..4444444 100644",
                "--- a/other.py",
                "+++ b/other.py",
                "@@ -1 +1 @@",
                "-old2",
                "+new2",
            ]
        )
        _preamble, sections = split_sections(diff_text)
        kept = filter_sections(sections, "*.py")
        assert [s.path for s in kept] == ["f oo.py", "other.py"]

    def test_render_sections_rejoins_kept_sections(self):
        _preamble, sections = split_sections(_sample_diff())
        kept = filter_sections(sections, "src/*")
        rendered = render_sections(kept)
        assert "src/a.py" in rendered
        assert "src/b.py" in rendered
        assert "docs/readme.md" not in rendered
