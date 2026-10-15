"""Characterization tests for DiffTruncator.truncate outcomes (issue #255)."""

from mcp_server_git.utils.token_management import DiffTruncator, TokenEstimator


def _file_diff(name: str, body_lines: int) -> list[str]:
    header = [
        f"diff --git a/{name} b/{name}",
        "index 1111111..2222222 100644",
        f"--- a/{name}",
        f"+++ b/{name}",
        f"@@ -1,{body_lines} +1,{body_lines} @@",
    ]
    return header + [f"+added line {i}" for i in range(body_lines)]


def _truncate(content: str, max_tokens: int):
    return DiffTruncator().truncate(content, max_tokens, TokenEstimator())


def test_truncate_returns_content_unchanged_when_under_limit():
    content = "\n".join(_file_diff("a.py", 2))
    result = _truncate(content, 10_000)
    assert result.content == content
    assert result.truncated is False
    assert result.truncation_summary == ""
    assert result.original_tokens == result.final_tokens


def test_truncate_returns_only_summary_when_no_header_fits():
    content = "\n".join(
        _file_diff("a.py", 30) + _file_diff("b.py", 30) + _file_diff("c.py", 30)
    )
    result = _truncate(content, 30)
    assert result.content == (
        "\n\n[Diff truncated: showing 0 files, 3 files omitted to fit token limit]"
    )
    assert result.truncated is True
    assert result.truncation_summary == "Truncated 3 of 3 files"


def test_truncate_omits_file_count_suffix_when_single_file_shown():
    content = "\n".join(_file_diff("a.py", 200))
    result = _truncate(content, 120)
    assert result.content.endswith(
        "\n\n[Diff truncated: showing 1 files to fit token limit]"
    )
    assert result.truncation_summary == "Truncated 0 of 1 files"
    assert result.truncated is True


def test_truncate_keeps_first_file_headers_and_counts_omitted_files_when_budget_allows():
    content = "\n".join(
        _file_diff("a.py", 30) + _file_diff("b.py", 30) + _file_diff("c.py", 30)
    )
    result = _truncate(content, 200)
    header = "\n".join(_file_diff("a.py", 30)[:5])
    assert result.content.startswith(header)
    assert "b.py" not in result.content
    assert result.content.endswith(
        "\n\n[Diff truncated: showing 1 files, 2 files omitted to fit token limit]"
    )
    assert result.truncation_summary == "Truncated 2 of 3 files"
    assert result.final_tokens > 0


def test_truncate_reports_zero_files_when_content_has_no_diff_headers():
    content = "\n".join(f"plain line number {i}" for i in range(300))
    result = _truncate(content, 100)
    assert result.content.endswith(
        "\n\n[Diff truncated: showing 0 files to fit token limit]"
    )
    assert result.truncation_summary == "Truncated 0 of 0 files"
    assert result.content.startswith("plain line number 0\nplain line number 1\n")
