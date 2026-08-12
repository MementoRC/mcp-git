"""
Pure unit tests for mcp_server_git.github.job_log_selection (issue #205).

No mocks, no network, no HTTP — every function under test is pure and
operates on already-fetched line lists / text.
"""

import re

import pytest

from src.mcp_server_git.github.job_log_selection import (
    LogSelectionError,
    build_log_response_lines,
    cap_characters,
    filter_lines,
    format_totals,
    resolve_window,
    select_log_text,
    write_full_log_response,
)


# ---------------------------------------------------------------------------
# resolve_window
# ---------------------------------------------------------------------------


class TestResolveWindow:
    def test_resolve_window_returns_last_500_lines_when_no_selectors_given(self):
        start, end, _label, anchored_at_head = resolve_window(1000)

        assert (start, end) == (501, 1000)
        assert anchored_at_head is False

    def test_resolve_window_returns_first_n_lines_when_head_lines_given(self):
        start, end, _label, anchored_at_head = resolve_window(1000, head_lines=200)

        assert (start, end) == (1, 200)
        assert anchored_at_head is True

    def test_resolve_window_returns_last_n_lines_when_tail_lines_given(self):
        start, end, _label, anchored_at_head = resolve_window(1000, tail_lines=50)

        assert (start, end) == (951, 1000)
        assert anchored_at_head is False

    def test_resolve_window_returns_exact_window_when_start_and_end_given(self):
        start, end, _label, anchored_at_head = resolve_window(
            1000, start_line=100, end_line=200
        )

        assert (start, end) == (100, 200)
        assert anchored_at_head is True

    def test_resolve_window_clamps_end_line_when_beyond_total(self):
        start, end, _label, _anchored = resolve_window(1000, end_line=2000)

        assert (start, end) == (1, 1000)

    def test_resolve_window_defaults_end_to_total_when_only_start_line_given(self):
        start, end, _label, _anchored = resolve_window(1000, start_line=100)

        assert (start, end) == (100, 1000)

    def test_resolve_window_defaults_start_to_one_when_only_end_line_given(self):
        start, end, _label, _anchored = resolve_window(1000, end_line=200)

        assert (start, end) == (1, 200)

    def test_resolve_window_returns_whole_log_when_full_log_true(self):
        start, end, _label, anchored_at_head = resolve_window(1000, full_log=True)

        assert (start, end) == (1, 1000)
        assert anchored_at_head is True

    def test_resolve_window_returns_whole_log_when_whole_log_default_and_no_selectors(
        self,
    ):
        start, end, _label, anchored_at_head = resolve_window(
            1000, whole_log_default=True
        )

        assert (start, end) == (1, 1000)
        assert anchored_at_head is True

    def test_resolve_window_raises_when_head_lines_and_tail_lines_combined(self):
        with pytest.raises(LogSelectionError):
            resolve_window(1000, head_lines=10, tail_lines=10)

    def test_resolve_window_raises_when_head_lines_and_start_line_combined(self):
        with pytest.raises(LogSelectionError):
            resolve_window(1000, head_lines=10, start_line=5)

    def test_resolve_window_raises_when_head_lines_is_zero(self):
        with pytest.raises(LogSelectionError):
            resolve_window(1000, head_lines=0)

    def test_resolve_window_raises_when_tail_lines_is_negative(self):
        with pytest.raises(LogSelectionError):
            resolve_window(1000, tail_lines=-1)

    def test_resolve_window_raises_when_start_line_is_zero(self):
        with pytest.raises(LogSelectionError):
            resolve_window(1000, start_line=0)

    def test_resolve_window_raises_when_end_line_less_than_start_line(self):
        with pytest.raises(LogSelectionError):
            resolve_window(1000, start_line=100, end_line=50)

    def test_resolve_window_raises_when_start_line_past_end_of_log(self):
        with pytest.raises(LogSelectionError):
            resolve_window(1000, start_line=1001)


# ---------------------------------------------------------------------------
# filter_lines
# ---------------------------------------------------------------------------


class TestFilterLines:
    def _numbered(self, lines: list[str]) -> list[tuple[int, str]]:
        return list(enumerate(lines, start=1))

    def test_filter_lines_returns_matches_prefixed_with_original_line_numbers(self):
        numbered = self._numbered(["alpha", "beta NEEDLE", "gamma", "delta NEEDLE"])

        rendered, match_count = filter_lines(numbered, "NEEDLE")

        assert match_count == 2
        # Matches on non-adjacent lines are still separated groups even
        # without context, so "--" appears between them.
        assert rendered == ["2: beta NEEDLE", "--", "4: delta NEEDLE"]

    def test_filter_lines_includes_context_and_separates_discontiguous_groups(self):
        numbered = self._numbered(
            ["a", "b", "MATCH1", "d", "e", "f", "g", "h", "MATCH2", "j"]
        )

        rendered, match_count = filter_lines(numbered, "MATCH", context_lines=2)

        assert match_count == 2
        assert "--" in rendered
        assert "3: MATCH1" in rendered
        assert "9: MATCH2" in rendered
        assert "1- a" in rendered
        assert "5- e" in rendered

    def test_filter_lines_does_not_insert_separator_when_groups_are_adjacent(self):
        numbered = self._numbered(["a", "MATCH1", "b", "MATCH2", "c"])

        rendered, match_count = filter_lines(numbered, "MATCH", context_lines=1)

        assert match_count == 2
        assert "--" not in rendered

    def test_filter_lines_matches_case_insensitively_when_ignore_case_true(self):
        numbered = self._numbered(["Error: boom", "all good"])

        rendered, match_count = filter_lines(numbered, "error", ignore_case=True)

        assert match_count == 1
        assert rendered == ["1: Error: boom"]

    def test_filter_lines_is_case_sensitive_by_default(self):
        numbered = self._numbered(["Error: boom", "all good"])

        rendered, match_count = filter_lines(numbered, "error")

        assert rendered == []
        assert match_count == 0

    def test_filter_lines_returns_empty_when_no_matches(self):
        numbered = self._numbered(["alpha", "beta", "gamma"])

        rendered, match_count = filter_lines(numbered, "NEEDLE")

        assert (rendered, match_count) == ([], 0)

    def test_filter_lines_raises_on_invalid_regex(self):
        numbered = self._numbered(["alpha"])

        with pytest.raises(LogSelectionError):
            filter_lines(numbered, "[unclosed")


# ---------------------------------------------------------------------------
# cap_characters
# ---------------------------------------------------------------------------


class TestCapCharacters:
    def test_cap_characters_returns_unchanged_when_under_limit(self):
        text = "short text"

        result, truncated = cap_characters(text, keep_head=True, limit=1000)

        assert result == text
        assert truncated is False

    def test_cap_characters_keeps_beginning_when_keep_head_true(self):
        lines = [f"L{i:04d}" for i in range(2000)]
        text = "\n".join(lines)

        result, truncated = cap_characters(text, keep_head=True, limit=5000)

        assert truncated is True
        assert text.startswith(result)
        assert all(re.fullmatch(r"L\d{4}", line) for line in result.split("\n"))

    def test_cap_characters_keeps_end_when_keep_head_false(self):
        lines = [f"L{i:04d}" for i in range(2000)]
        text = "\n".join(lines)

        result, truncated = cap_characters(text, keep_head=False, limit=5000)

        assert truncated is True
        assert text.endswith(result)
        assert all(re.fullmatch(r"L\d{4}", line) for line in result.split("\n"))

    def test_cap_characters_result_never_starts_with_partial_line(self):
        lines = [f"LINE-{i:05d}" for i in range(3000)]
        text = "\n".join(lines)

        result, _truncated = cap_characters(text, keep_head=True, limit=7003)

        first_line = result.split("\n")[0]
        assert re.fullmatch(r"LINE-\d{5}", first_line)

    def test_cap_characters_result_never_ends_with_partial_line(self):
        lines = [f"LINE-{i:05d}" for i in range(3000)]
        text = "\n".join(lines)

        result, _truncated = cap_characters(text, keep_head=False, limit=7003)

        last_line = result.split("\n")[-1]
        assert re.fullmatch(r"LINE-\d{5}", last_line)

    def test_cap_characters_returns_truncated_true_when_it_bites(self):
        text = "x" * 100

        _result, truncated = cap_characters(text, keep_head=True, limit=10)

        assert truncated is True


# ---------------------------------------------------------------------------
# select_log_text
# ---------------------------------------------------------------------------


class TestSelectLogTextRegressions:
    """Regression tests for the default-500-line-hides-grep-matches bug (#205)."""

    def test_grep_with_no_window_selector_searches_the_whole_log(self):
        lines = ["filler line" for _ in range(10_000)]
        lines[2] = "NEEDLE found here"  # line number 3 (1-indexed)

        selection = select_log_text(lines, grep="NEEDLE")

        assert selection.match_count == 1
        assert "3: NEEDLE found here" in selection.text

    def test_head_lines_on_large_log_reaches_start_of_log_not_end(self):
        lines = [f"line {i}" for i in range(64_000)]

        selection = select_log_text(lines, head_lines=200)

        assert "line 0" in selection.text
        assert "line 63999" not in selection.text

    def test_start_end_window_composes_with_grep(self):
        lines = ["filler" for _ in range(1000)]
        lines[149] = "NEEDLE inside window"  # line 150, inside [100, 200]
        lines[499] = "NEEDLE outside window"  # line 500, outside [100, 200]

        selection = select_log_text(lines, start_line=100, end_line=200, grep="NEEDLE")

        assert "150: NEEDLE inside window" in selection.text
        assert "NEEDLE outside window" not in selection.text

    def test_truncated_false_only_when_whole_log_returned_uncapped(self):
        lines = [f"line {i}" for i in range(10)]

        selection = select_log_text(lines, full_log=True)

        assert selection.truncated is False

    def test_truncated_true_for_windowed_selection(self):
        lines = [f"line {i}" for i in range(1000)]

        selection = select_log_text(lines, head_lines=10)

        assert selection.truncated is True

    def test_truncated_true_whenever_grep_was_used(self):
        lines = [f"line {i}" for i in range(10)]
        lines[0] = "NEEDLE"

        selection = select_log_text(lines, full_log=True, grep="NEEDLE")

        assert selection.truncated is True

    def test_match_count_is_none_when_grep_not_used(self):
        lines = [f"line {i}" for i in range(10)]

        selection = select_log_text(lines)

        assert selection.match_count is None

    def test_match_count_is_int_when_grep_used(self):
        lines = [f"line {i}" for i in range(10)]
        lines[0] = "NEEDLE"

        selection = select_log_text(lines, full_log=True, grep="NEEDLE")

        assert selection.match_count == 1


# ---------------------------------------------------------------------------
# format_totals
# ---------------------------------------------------------------------------


class TestFormatTotals:
    def test_format_totals_includes_lines_bytes_label_and_truncated_yes(self):
        line = format_totals(
            total_lines=1234,
            total_bytes=5678,
            label="last 500 of 1234 lines",
            truncated=True,
            was_size_truncated=False,
        )

        assert "1,234" in line
        assert "5,678" in line
        assert "last 500 of 1234 lines" in line
        assert "Truncated: yes" in line

    def test_format_totals_reports_truncated_no_when_not_truncated(self):
        line = format_totals(
            total_lines=10,
            total_bytes=20,
            label="all 10 lines",
            truncated=False,
            was_size_truncated=False,
        )

        assert "Truncated: no" in line

    def test_format_totals_appends_clamp_note_when_size_truncated(self):
        line = format_totals(
            total_lines=10,
            total_bytes=20,
            label="all 10 lines",
            truncated=False,
            was_size_truncated=True,
        )

        assert "10MB" in line

    def test_format_totals_omits_clamp_note_when_not_size_truncated(self):
        line = format_totals(
            total_lines=10,
            total_bytes=20,
            label="all 10 lines",
            truncated=False,
            was_size_truncated=False,
        )

        assert "10MB" not in line


# ---------------------------------------------------------------------------
# build_log_response_lines
# ---------------------------------------------------------------------------


class TestBuildLogResponseLines:
    def _logs_text(self, n: int = 50) -> str:
        return "\n".join(f"line {i}" for i in range(n))

    def test_totals_line_is_first_element_for_default_selection(self):
        result = build_log_response_lines(
            self._logs_text(),
            tail_lines=None,
            full_log=False,
            head_lines=None,
            start_line=None,
            end_line=None,
            grep=None,
            context_lines=0,
            ignore_case=False,
            size_limit=10_000_000,
            char_limit=100_000,
        )

        assert result[0].startswith("📊 Total:")

    def test_totals_line_is_first_element_for_head_selection(self):
        result = build_log_response_lines(
            self._logs_text(),
            tail_lines=None,
            full_log=False,
            head_lines=5,
            start_line=None,
            end_line=None,
            grep=None,
            context_lines=0,
            ignore_case=False,
            size_limit=10_000_000,
            char_limit=100_000,
        )

        assert result[0].startswith("📊 Total:")

    def test_totals_line_is_first_element_for_range_selection(self):
        result = build_log_response_lines(
            self._logs_text(),
            tail_lines=None,
            full_log=False,
            head_lines=None,
            start_line=5,
            end_line=10,
            grep=None,
            context_lines=0,
            ignore_case=False,
            size_limit=10_000_000,
            char_limit=100_000,
        )

        assert result[0].startswith("📊 Total:")

    def test_totals_line_is_first_element_for_grep_selection(self):
        result = build_log_response_lines(
            self._logs_text(),
            tail_lines=None,
            full_log=False,
            head_lines=None,
            start_line=None,
            end_line=None,
            grep="line 3",
            context_lines=0,
            ignore_case=False,
            size_limit=10_000_000,
            char_limit=100_000,
        )

        assert result[0].startswith("📊 Total:")

    def test_grep_with_zero_matches_returns_totals_and_no_matches_message_only(self):
        result = build_log_response_lines(
            self._logs_text(),
            tail_lines=None,
            full_log=False,
            head_lines=None,
            start_line=None,
            end_line=None,
            grep="NOPE_NO_MATCH",
            context_lines=0,
            ignore_case=False,
            size_limit=10_000_000,
            char_limit=100_000,
        )

        assert result[0].startswith("📊 Total:")
        assert any("No lines matched" in entry for entry in result)
        assert len(result) == 2
        assert not any(entry.strip() == "" for entry in result)


# ---------------------------------------------------------------------------
# write_full_log_response
# ---------------------------------------------------------------------------


class TestWriteFullLogResponse:
    def test_relative_output_path_returns_error_and_writes_nothing(self, tmp_path):
        relative_path = "relative/nested/out.txt"

        result = write_full_log_response([], relative_path, "some log text")

        assert result.startswith("❌ output_path must be an absolute path")
        from pathlib import Path

        assert not Path(relative_path).exists()

    def test_writes_complete_log_text_creating_missing_parent_dirs(self, tmp_path):
        output_path = tmp_path / "sub" / "dir" / "log.txt"
        logs_text = "line one\nline two\nline three\n"

        write_full_log_response([], str(output_path), logs_text)

        assert output_path.exists()
        assert output_path.read_text(encoding="utf-8") == logs_text

    def test_response_contains_write_confirmation_and_totals_but_not_log_body(
        self, tmp_path
    ):
        output_path = tmp_path / "log.txt"
        logs_text = "UNIQUE_MARKER_XYZ\nsecond line\n"

        result = write_full_log_response([], str(output_path), logs_text)

        assert "written to" in result
        assert "📊 Total:" in result
        assert "UNIQUE_MARKER_XYZ" not in result

    def test_returns_error_when_write_fails(self, tmp_path):
        blocker = tmp_path / "blocker"
        blocker.write_text("i am a file, not a directory")
        output_path = blocker / "log.txt"

        result = write_full_log_response([], str(output_path), "some log text")

        assert result.startswith("❌ Failed to write log to ")
