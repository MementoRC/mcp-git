"""Helpers for DiffTruncator (token_management.py).

Each helper takes an ``estimate`` callable (text -> estimated diff tokens) so
this module does not import ``token_management`` (which imports it).
"""

from collections.abc import Callable

_HEADER_PREFIXES = ("diff --git", "index ", "---", "+++")


def collect_file_headers(lines: list[str]) -> list[list[str]]:
    """Collect leading file-header blocks, stopping at the first content line.

    A content line is kept only when it is a hunk header (``@@``) following a
    file header; collection stops there either way.
    """
    file_headers: list[list[str]] = []
    current_file_lines: list[str] = []

    for line in lines:
        if line.startswith("diff --git"):
            # Save previous file if exists
            if current_file_lines:
                file_headers.append(current_file_lines)
            current_file_lines = [line]
        elif line.startswith(("index ", "---", "+++")) and current_file_lines:
            current_file_lines.append(line)
        else:
            # This is content - if we have headers, save the file structure
            if current_file_lines and line.startswith("@@"):
                current_file_lines.append(line)
            break  # Stop collecting headers once we hit content

    # Save last file headers
    if current_file_lines:
        file_headers.append(current_file_lines)
    return file_headers


def fit_file_headers(
    file_headers: list[list[str]],
    available_tokens: int,
    estimate: Callable[[str], int],
) -> tuple[list[str], int]:
    """Add whole header blocks while they fit; returns (lines, files_truncated)."""
    result_lines: list[str] = []
    for file_header in file_headers:
        if estimate("\n".join(result_lines + file_header)) <= available_tokens:
            result_lines.extend(file_header)
        else:
            return result_lines, 1
    return result_lines, 0


def append_content_lines(
    result_lines: list[str],
    lines: list[str],
    available_tokens: int,
    estimate: Callable[[str], int],
) -> None:
    """Append non-header lines to *result_lines* until the budget runs out."""
    for line in lines:
        if line.startswith(_HEADER_PREFIXES):
            continue
        if estimate("\n".join(result_lines + [line])) > available_tokens:
            break
        result_lines.append(line)
