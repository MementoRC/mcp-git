"""Fail-closed read-only guard for GraphQL documents (#355).

A small lexer per the GraphQL spec (no parser dependency): whitespace, commas,
``#`` comments, strings and block strings are skipped, brackets are tracked, and
the first token of each top-level definition is classified. Only shorthand
queries, ``query`` and ``fragment`` definitions pass; anything unclassifiable
is rejected.
"""

from collections.abc import Iterator

_BOM = "﻿"
_LINE_END = frozenset("\r\n")
_IGNORED = frozenset(" \t\r\n,")
_PUNCT = frozenset("!$&()=:@[]{|}.")
_NUMBER_CHARS = frozenset("-+0123456789")
_CLOSERS = {"{": "}", "(": ")", "[": "]"}
_CLOSING = frozenset(_CLOSERS.values())
_ALLOWED = frozenset({"query", "fragment"})
_FORBIDDEN = frozenset({"mutation", "subscription"})
_STRING = '"'


class _Reject(Exception):
    """The document cannot be proven read-only."""


def _end_block_string(text: str, i: int) -> int:
    while i < len(text):
        if text.startswith('\\"""', i):
            i += 4
        elif text.startswith('"""', i):
            return i + 3
        else:
            i += 1
    raise _Reject("unterminated block string")


def _end_string(text: str, i: int) -> int:
    while i < len(text):
        ch = text[i]
        if ch == "\\" and text[i + 1 : i + 2] not in _LINE_END:
            i += 2
        elif ch == '"':
            return i + 1
        elif ch in _LINE_END:
            break
        else:
            i += 1
    raise _Reject("unterminated string")


def _end_comment(text: str, i: int) -> int:
    """A comment runs to the first LF or CR (the spec's LineTerminator) or EOF."""
    while i < len(text) and text[i] not in _LINE_END:
        i += 1
    return i


def _unexpected(ch: str) -> _Reject:
    if ch == _BOM:
        return _Reject(
            "byte order mark (U+FEFF) is only allowed at the start of the document"
        )
    return _Reject(f"unexpected character {ch!r}")


def _end_name(text: str, i: int) -> int:
    while i < len(text) and text[i].isascii() and (text[i].isalnum() or text[i] == "_"):
        i += 1
    return i


def _tokens(text: str) -> Iterator[str]:
    """Yield names, punctuators and a ``"`` marker per string literal."""
    i, n = (1 if text.startswith(_BOM) else 0), len(text)
    while i < n:
        ch = text[i]
        if ch in _IGNORED:
            i += 1
        elif ch == "#":
            i = _end_comment(text, i)
        elif text.startswith('"""', i):
            i = _end_block_string(text, i + 3)
            yield _STRING
        elif ch == _STRING:
            i = _end_string(text, i + 1)
            yield _STRING
        elif ch.isascii() and (ch.isalpha() or ch == "_"):
            end = _end_name(text, i)
            yield text[i:end]
            i = end
        elif ch in _PUNCT:
            yield ch
            i += 1
        elif ch in _NUMBER_CHARS:
            i += 1
        else:
            raise _unexpected(ch)


def _check_top_level(tok: str, in_definition: bool) -> None:
    if tok in _FORBIDDEN:
        raise _Reject(f"{tok} operations are not allowed (read-only tool)")
    if in_definition:
        return
    if tok != "{" and tok not in _ALLOWED:
        raise _Reject(f"unexpected top-level token {tok!r}; expected a query")


def _step(stack: list[str], tok: str) -> None:
    if tok in _CLOSERS:
        stack.append(_CLOSERS[tok])
    elif tok in _CLOSING and (not stack or stack.pop() != tok):
        raise _Reject("unbalanced brackets")


def _check(document: str) -> None:
    stack: list[str] = []
    in_definition = False
    definitions = 0
    for tok in _tokens(document):
        if not stack:
            _check_top_level(tok, in_definition)
            if not in_definition:
                definitions += 1
                in_definition = True
        _step(stack, tok)
        if in_definition and not stack and tok == "}":
            in_definition = False
    if stack:
        raise _Reject("unbalanced brackets")
    if in_definition:
        raise _Reject("incomplete definition (missing selection set)")
    if definitions == 0:
        raise _Reject("empty document")


def read_only_violation(document: str) -> str | None:
    """Return why *document* is not a provably read-only query, else ``None``."""
    try:
        _check(document)
    except _Reject as exc:
        return str(exc)
    return None
