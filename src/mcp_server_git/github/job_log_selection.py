"""Line selection and filtering for large CI job logs.

``github_get_job_logs`` can only hand a small slice of a job log to an LLM.
These helpers decide *which* slice, so that the start of a log is reachable
(``head_lines``, ``start_line``/``end_line``) and so that a caller can pull
just the lines they care about out of a 64k-line log (``grep``).

Everything here is pure: it works on an already-fetched list of lines and
never touches the network or the filesystem.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_TAIL_LINES = 500
MAX_CHARS_FOR_LLM = 100 * 1024

_GREP_GROUP_SEPARATOR = "--"


class LogSelectionError(ValueError):
    """Raised when the requested selection parameters conflict or are invalid."""


@dataclass(frozen=True)
class LogSelection:
    """The slice of a log chosen for return, plus how it was chosen."""

    text: str
    label: str
    truncated: bool
    match_count: int | None = None
    char_truncated: bool = False
    windowed: bool = False


def _reject_conflicting_selectors(
    head_lines: int | None,
    tail_lines: int | None,
    start_line: int | None,
    end_line: int | None,
) -> None:
    """Reject more than one window selector, rather than silently picking one."""
    selectors = (
        head_lines,
        tail_lines,
        start_line if start_line is not None else end_line,
    )
    if sum(1 for selector in selectors if selector is not None) > 1:
        raise LogSelectionError(
            "Use only one of head_lines, tail_lines, or start_line/end_line."
        )


def _head_window(total_lines: int, count: int) -> tuple[int, int, str, bool]:
    if count <= 0:
        raise LogSelectionError("head_lines must be a positive integer.")
    end = min(count, total_lines)
    return 1, end, f"first {end} of {total_lines} lines", True


def _tail_window(total_lines: int, count: int) -> tuple[int, int, str, bool]:
    if count <= 0:
        raise LogSelectionError("tail_lines must be a positive integer.")
    start = max(1, total_lines - count + 1)
    kept = total_lines - start + 1
    return start, total_lines, f"last {kept} of {total_lines} lines", False


def _range_window(
    total_lines: int, start_line: int | None, end_line: int | None
) -> tuple[int, int, str, bool]:
    start = 1 if start_line is None else start_line
    end = total_lines if end_line is None else end_line
    if start < 1:
        raise LogSelectionError("start_line is 1-indexed and must be >= 1.")
    if end < start:
        raise LogSelectionError("end_line must be >= start_line.")
    if start > total_lines:
        raise LogSelectionError(
            f"start_line {start:,} is past the end of the log ({total_lines:,} lines)."
        )
    end = min(end, total_lines)
    return start, end, f"lines {start}-{end} of {total_lines}", True


def resolve_window(
    total_lines: int,
    *,
    head_lines: int | None = None,
    tail_lines: int | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
    full_log: bool = False,
    whole_log_default: bool = False,
) -> tuple[int, int, str, bool]:
    """Resolve the 1-indexed inclusive window of lines to return.

    Returns ``(start, end, label, anchored_at_head)``. ``anchored_at_head``
    records which end matters if the character cap bites later: a window taken
    from the start of the log must not then be trimmed from the front.

    ``whole_log_default`` selects the whole log when no explicit selector was
    given. It is used for ``grep``, where the filter already bounds the output
    and defaulting to the last 500 lines would silently hide earlier matches.
    """
    _reject_conflicting_selectors(head_lines, tail_lines, start_line, end_line)

    if start_line is not None or end_line is not None:
        return _range_window(total_lines, start_line, end_line)
    if head_lines is not None:
        return _head_window(total_lines, head_lines)
    if tail_lines is not None:
        return _tail_window(total_lines, tail_lines)
    if full_log or whole_log_default:
        return 1, total_lines, f"all {total_lines} lines", True
    return _tail_window(total_lines, DEFAULT_TAIL_LINES)


def _expand_context(
    match_indexes: list[int], context_lines: int, total: int
) -> list[int]:
    span = max(0, context_lines)
    keep: set[int] = set()
    for index in match_indexes:
        keep.update(range(max(0, index - span), min(total, index + span + 1)))
    return sorted(keep)


def _render_groups(
    numbered: list[tuple[int, str]], keep: list[int], matches: set[int]
) -> list[str]:
    """Render kept lines in grep's notation, separating discontiguous groups."""
    rendered: list[str] = []
    previous: int | None = None
    for index in keep:
        if previous is not None and index != previous + 1:
            rendered.append(_GREP_GROUP_SEPARATOR)
        number, text = numbered[index]
        rendered.append(f"{number}{':' if index in matches else '-'} {text}")
        previous = index
    return rendered


def filter_lines(
    numbered: list[tuple[int, str]],
    pattern: str,
    *,
    context_lines: int = 0,
    ignore_case: bool = False,
) -> tuple[list[str], int]:
    """Keep only lines matching *pattern*, with optional surrounding context.

    *numbered* is a list of ``(line_number, text)`` pairs. Returns
    ``(rendered_lines, match_count)`` using grep's own notation: ``n: text``
    for a match, ``n- text`` for context, ``--`` between separated groups.
    """
    try:
        regex = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
    except re.error as exc:
        raise LogSelectionError(f"Invalid grep pattern {pattern!r}: {exc}") from exc

    match_indexes = [i for i, (_, text) in enumerate(numbered) if regex.search(text)]
    if not match_indexes:
        return [], 0

    keep = _expand_context(match_indexes, context_lines, len(numbered))
    return _render_groups(numbered, keep, set(match_indexes)), len(match_indexes)


def cap_characters(
    text: str, *, keep_head: bool, limit: int = MAX_CHARS_FOR_LLM
) -> tuple[str, bool]:
    """Trim *text* to *limit* characters, keeping whichever end was asked for.

    Trimming stops at a line boundary so the result never starts or ends with
    half a line.
    """
    if len(text) <= limit:
        return text, False

    if keep_head:
        trimmed = text[:limit]
        boundary = trimmed.rfind("\n")
        if boundary > 0:
            trimmed = trimmed[:boundary]
    else:
        trimmed = text[-limit:]
        boundary = trimmed.find("\n")
        if boundary >= 0:
            trimmed = trimmed[boundary + 1 :]
    return trimmed, True


def select_log_text(
    lines: list[str],
    *,
    head_lines: int | None = None,
    tail_lines: int | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
    full_log: bool = False,
    grep: str | None = None,
    context_lines: int = 0,
    ignore_case: bool = False,
    limit: int = MAX_CHARS_FOR_LLM,
) -> LogSelection:
    """Choose the portion of *lines* to return, honouring the LLM char cap.

    A window is resolved first, then ``grep`` (when given) filters within it,
    so ``start_line``/``end_line`` and ``grep`` compose.
    """
    total_lines = len(lines)
    start, end, label, anchored_at_head = resolve_window(
        total_lines,
        head_lines=head_lines,
        tail_lines=tail_lines,
        start_line=start_line,
        end_line=end_line,
        full_log=full_log,
        whole_log_default=grep is not None,
    )

    window = list(enumerate(lines[start - 1 : end], start=start))
    match_count: int | None = None

    if grep is not None:
        rendered, match_count = filter_lines(
            window,
            grep,
            context_lines=context_lines,
            ignore_case=ignore_case,
        )
        label = f"{match_count:,} match(es) for {grep!r} within {label}"
        anchored_at_head = True
    else:
        rendered = [text for _, text in window]

    text, char_truncated = cap_characters(
        "\n".join(rendered), keep_head=anchored_at_head, limit=limit
    )
    windowed = (end - start + 1) < total_lines
    return LogSelection(
        text=text,
        label=label,
        truncated=char_truncated or windowed or grep is not None,
        match_count=match_count,
        char_truncated=char_truncated,
        windowed=windowed,
    )


def format_totals(
    *,
    total_lines: int,
    total_bytes: int,
    label: str,
    truncated: bool,
    was_size_truncated: bool,
    clamp_noun: str = "log",
) -> str:
    """Render the one-line totals summary shown before every log body."""
    truncated_text = "yes" if truncated else "no"
    line = (
        f"📊 Total: {total_lines:,} lines / {total_bytes:,} bytes | "
        f"Returned: {label} | Truncated: {truncated_text}"
    )
    if was_size_truncated:
        line += f" ({clamp_noun} clamped to 10MB before selection)"
    return line


def _truncation_notes(
    *,
    was_size_truncated: bool,
    total_bytes: int,
    windowed: bool,
    total_lines: int,
    char_truncated: bool,
) -> list[str]:
    """Build the comma-joined notes shown on the ⚠️ truncation line."""
    notes: list[str] = []
    if was_size_truncated:
        notes.append(f"size: {total_bytes:,} bytes")
    if windowed:
        notes.append(f"lines: {total_lines} total")
    if char_truncated:
        notes.append("chars: exceeded 100KB limit")
    return notes


def write_full_log_response(
    output: list[str], output_path: str, logs_text: str, noun: str = "log"
) -> str:
    """Write the complete log/diff to disk and return metadata only (#205).

    No log content enters the response — only the caller-supplied header
    lines, the write confirmation, and the totals line.
    """
    path = Path(output_path)
    if not path.is_absolute():
        return f"❌ output_path must be an absolute path, got: {output_path}"

    total_lines = len(logs_text.splitlines())
    total_bytes = len(logs_text)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(logs_text, encoding="utf-8")
    except OSError as exc:
        return f"❌ Failed to write {noun} to {output_path}: {exc}"

    output.append(f"💾 Full {noun} written to {output_path}")
    output.append(
        format_totals(
            total_lines=total_lines,
            total_bytes=total_bytes,
            label="written to disk",
            truncated=False,
            was_size_truncated=False,
        )
    )
    return "\n".join(output)


def build_log_response_lines(
    logs_text: str,
    *,
    tail_lines: int | None,
    full_log: bool,
    head_lines: int | None,
    start_line: int | None,
    end_line: int | None,
    grep: str | None,
    context_lines: int,
    ignore_case: bool,
    size_limit: int,
    char_limit: int,
    separator_length: int = 60,
    body_label: str = "Logs",
    clamp_noun: str = "log",
) -> list[str]:
    """Clamp, window, and render a fetched log for the LLM response.

    Raises LogSelectionError if the requested selectors conflict or are
    out of range.
    """
    total_bytes = len(logs_text)
    wants_head = (
        grep is not None
        or head_lines is not None
        or start_line is not None
        or end_line is not None
    )

    logs_text, was_size_truncated = cap_characters(
        logs_text, keep_head=wants_head, limit=size_limit
    )
    if was_size_truncated:
        logger.warning(f"Job logs clamped to {size_limit} bytes before selection")

    lines = logs_text.splitlines()
    total_lines = len(lines)
    selection = select_log_text(
        lines,
        head_lines=head_lines,
        tail_lines=tail_lines,
        start_line=start_line,
        end_line=end_line,
        full_log=full_log,
        grep=grep,
        context_lines=context_lines,
        ignore_case=ignore_case,
        limit=char_limit,
    )

    result = [
        format_totals(
            total_lines=total_lines,
            total_bytes=total_bytes,
            label=selection.label,
            truncated=selection.truncated,
            was_size_truncated=was_size_truncated,
            clamp_noun=clamp_noun,
        )
    ]

    notes = _truncation_notes(
        was_size_truncated=was_size_truncated,
        total_bytes=total_bytes,
        windowed=selection.windowed,
        total_lines=total_lines,
        char_truncated=selection.char_truncated,
    )
    if notes:
        result.append(f"⚠️ Truncated for LLM context ({', '.join(notes)})")

    if grep is not None and selection.match_count == 0:
        result.append(f"🔍 No lines matched {grep!r}")
        return result

    separator = "-" * separator_length
    result.append(f"\n📋 {body_label} ({selection.label}):")
    result.append(separator)
    result.append(selection.text)
    result.append(separator)
    return result
