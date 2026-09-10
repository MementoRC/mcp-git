"""Per-file splitting and filtering of a unified diff.

``github_get_pr_diff`` needs to answer "show me only the files I care about"
without the caller paying for the whole patch. A unified diff is already
self-delimiting -- every file starts a new ``diff --git a/<path> b/<path>``
header -- so the split is exact rather than heuristic.

Everything here is pure: it works on already-fetched diff text and never
touches the network or the filesystem.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass

DIFF_FILE_HEADER = "diff --git "

# git quotes a header path when it holds spaces, quotes, or non-ASCII bytes.
_QUOTED_HEADER = re.compile(r'^"a/(?P<pre>.*)" "b/(?P<post>.*)"$')
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "f": "\f", "v": "\v"}


@dataclass(frozen=True)
class DiffSection:
    """One file's portion of a unified diff."""

    path: str
    text: str


def _unquote(path: str) -> str:
    """Decode git's C-style path quoting.

    git quotes a path when it contains spaces, quotes, or (by default)
    non-ASCII bytes, escaping them as ``\\"``, ``\\\\``, ``\\t`` and friends,
    and non-ASCII bytes as three-digit octal. Octal escapes are decoded back
    to bytes before the whole path is read as UTF-8, so a quoted "café.py"
    round-trips rather than turning into digits.
    """
    raw = bytearray()
    index = 0
    while index < len(path):
        char = path[index]
        if char != "\\" or index + 1 >= len(path):
            raw.extend(char.encode("utf-8"))
            index += 1
            continue

        octal = path[index + 1 : index + 4]
        if len(octal) == 3 and all(digit in "01234567" for digit in octal):
            raw.append(int(octal, 8))
            index += 4
            continue

        escape = path[index + 1]
        raw.extend(_ESCAPES.get(escape, escape).encode("utf-8"))
        index += 2

    return raw.decode("utf-8", errors="replace")


def parse_header_path(header: str) -> str:
    """Extract the post-image path from a ``diff --git`` header line.

    The b-side is used because it is the path the change results in, and it
    survives renames.

    Two header forms exist. When the path needs quoting, git emits
    ``"a/<path>" "b/<path>"`` and the path is C-quoted. Otherwise it emits
    ``a/<path> b/<path>``, where a path containing spaces makes the split
    ambiguous from the left -- so that form is split from the right on
    ``" b/"``.
    """
    remainder = header[len(DIFF_FILE_HEADER) :].strip()

    quoted = _QUOTED_HEADER.match(remainder)
    if quoted:
        return _unquote(quoted.group("post"))

    if " b/" in remainder:
        return remainder.rsplit(" b/", 1)[-1].strip()
    return remainder


def split_sections(diff_text: str) -> tuple[str, list[DiffSection]]:
    """Split *diff_text* into ``(preamble, sections)``.

    *preamble* is any content before the first file header -- empty for a
    plain ``.diff``, but non-empty for the ``.patch`` mbox form. Each section
    keeps its own header line, so re-joining the parts reproduces the input.
    """
    preamble: list[str] = []
    sections: list[DiffSection] = []
    current_path: str | None = None
    current: list[str] = []

    for line in diff_text.splitlines():
        if line.startswith(DIFF_FILE_HEADER):
            if current_path is not None:
                sections.append(DiffSection(current_path, "\n".join(current)))
            current_path = parse_header_path(line)
            current = [line]
        elif current_path is None:
            preamble.append(line)
        else:
            current.append(line)

    if current_path is not None:
        sections.append(DiffSection(current_path, "\n".join(current)))

    return "\n".join(preamble), sections


def filter_sections(sections: list[DiffSection], pattern: str) -> list[DiffSection]:
    """Keep the sections whose path matches the glob *pattern*.

    ``fnmatch`` semantics apply, in which ``*`` also matches ``/`` -- so
    ``recipe/*`` reaches nested paths and ``*.yaml`` reaches any depth. The
    basename is tried as well, so ``meta.yaml`` finds ``recipe/meta.yaml``.
    """
    return [
        section
        for section in sections
        if fnmatch.fnmatch(section.path, pattern)
        or fnmatch.fnmatch(section.path.rsplit("/", 1)[-1], pattern)
    ]


def render_sections(sections: list[DiffSection]) -> str:
    """Re-join sections into a single diff body."""
    return "\n".join(section.text for section in sections)
