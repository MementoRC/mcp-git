#!/usr/bin/env python3
"""Atomic design line-count gate.

Fails if any passed Python file exceeds the configured maximum
(default 500 lines, matching the organism limit in CLAUDE.md).

Escape hatch: include `# atomic-exempt: <reason>` anywhere in the file
to grandfather it. Use sparingly and pair with a tracked decomposition
issue.
"""

from __future__ import annotations

import sys
from pathlib import Path

EXEMPT_MARKER = "# atomic-exempt"
DEFAULT_MAX = 500


def count_lines(text: str) -> int:
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def parse_args(argv: list[str]) -> tuple[int, list[str]]:
    max_lines = DEFAULT_MAX
    files: list[str] = []
    for arg in argv:
        if arg.startswith("--max="):
            max_lines = int(arg.split("=", 1)[1])
        elif arg in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        else:
            files.append(arg)
    return max_lines, files


def main(argv: list[str]) -> int:
    max_lines, files = parse_args(argv[1:])
    violations: list[tuple[int, str]] = []
    for path in files:
        p = Path(path)
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if EXEMPT_MARKER in text:
            continue
        lines = count_lines(text)
        if lines > max_lines:
            violations.append((lines, path))
    if not violations:
        return 0
    print(f"Atomic design violation: files exceed {max_lines} lines.")
    print(
        f"Decompose, or add `{EXEMPT_MARKER}: <reason>` "
        "anywhere in the file to grandfather (track decomposition in an issue):\n",
    )
    for lines, path in sorted(violations, reverse=True):
        print(f"  {lines:6d}  {path}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
