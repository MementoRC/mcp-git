"""Tolerant JSON repair for MCP clients that send bare control characters."""

import re


def _sanitize_json_string(s: str) -> str:
    """
    Escape bare control characters inside JSON string values.

    Some MCP clients produce JSON where string values contain literal
    newlines, carriage returns, or tabs rather than the escaped forms
    required by the JSON specification (\\n, \\r, \\t).  This causes
    json.loads() to raise JSONDecodeError even though the overall
    structure is otherwise valid JSON.

    Strategy: use a regex that matches the interior of JSON string
    literals (content between un-escaped double-quotes) and replace
    any bare control characters found there with their escape sequences.

    Args:
        s: A JSON-like string that may contain bare control characters.

    Returns:
        The string with bare control characters inside string values
        replaced by their JSON escape sequences.
    """

    def _escape_controls(m: re.Match) -> str:
        content = m.group(1)
        content = content.replace("\n", "\\n")
        content = content.replace("\r", "\\r")
        content = content.replace("\t", "\\t")
        # Cover remaining C0 controls that JSON forbids
        content = re.sub(
            r"[\x00-\x08\x0b\x0c\x0e-\x1f]",
            lambda c: f"\\u{ord(c.group()):04x}",
            content,
        )
        return f'"{content}"'

    # Match JSON string literals: opening quote, captured body, closing quote.
    # The body allows escaped sequences (\\.) or any char that is not a bare
    # quote or backslash.  We use a non-greedy match so we don't span across
    # multiple string values.
    return re.sub(r'"((?:[^"\\]|\\.)*?)"', _escape_controls, s, flags=re.DOTALL)
