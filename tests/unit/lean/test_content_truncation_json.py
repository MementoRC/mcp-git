"""Characterization tests for ContentTruncator._truncate_json (issue #255)."""

import json

import pytest

from mcp_server_git.lean.content_truncation import ContentTruncator
from mcp_server_git.lean.token_types import TruncationConfig

_INDICATOR = "[TRUNC]"


def _truncator(preserve_keys: list[str] | None = None) -> ContentTruncator:
    return ContentTruncator(
        TruncationConfig(
            preserve_keys=preserve_keys or [],
            truncation_indicator=_INDICATOR,
            max_preserve_ratio=0.5,
            min_content_tokens=1,
        )
    )


def test_truncate_json_returns_meta_when_dict_exceeds_limit():
    data = {"status": "ok", "a": "x" * 10, "b": "y" * 400}
    result = _truncator(["status"])._truncate_json(json.dumps(data), 50)
    assert result == json.dumps(
        {
            "status": "ok",
            "a": "x" * 10,
            "_meta": {
                "truncated": True,
                "original_keys": 3,
                "preserved_keys": 2,
                "truncation_indicator": _INDICATOR,
            },
        },
        indent=2,
    )


def test_truncate_json_returns_all_keys_without_meta_when_dict_fits():
    data = {"a": 1, "b": [1, 2]}
    result = _truncator()._truncate_json(json.dumps(data), 1000)
    assert result == json.dumps(data, indent=2)


def test_truncate_json_puts_preserved_keys_first_when_declared_after_others():
    data = {"a": 1, "z": 2}
    result = _truncator(["z"])._truncate_json(json.dumps(data), 1000)
    assert list(json.loads(result)) == ["z", "a"]


def test_truncate_json_skips_preserved_key_when_absent_from_dict():
    result = _truncator(["missing"])._truncate_json('{"a": 1}', 1000)
    assert result == json.dumps({"a": 1}, indent=2)


def test_truncate_json_returns_only_meta_when_first_key_exceeds_limit():
    data = {"a": "x" * 1000, "b": 1}
    result = _truncator()._truncate_json(json.dumps(data), 10)
    assert result == json.dumps(
        {
            "_meta": {
                "truncated": True,
                "original_keys": 2,
                "preserved_keys": 0,
                "truncation_indicator": _INDICATOR,
            }
        },
        indent=2,
    )


def test_truncate_json_keeps_leading_items_and_marker_when_list_exceeds_limit():
    data = ["x" * 20] * 10
    result = _truncator()._truncate_json(json.dumps(data), 30)
    assert result == json.dumps(
        ["x" * 20] * 4
        + [
            {
                "_truncated": True,
                "original_length": 10,
                "preserved_length": 4,
                "indicator": _INDICATOR,
            }
        ],
        indent=2,
    )


def test_truncate_json_returns_list_unchanged_when_list_fits():
    data = [1, 2, 3]
    assert _truncator()._truncate_json("[1, 2, 3]", 1000) == json.dumps(data, indent=2)


@pytest.mark.parametrize(("content", "expected"), [("{}", "{}"), ("[]", "[]")])
def test_truncate_json_returns_empty_container_when_content_empty(content, expected):
    assert _truncator()._truncate_json(content, 0) == expected


def test_truncate_json_keeps_nested_value_whole_when_key_fits():
    data = {"outer": {"inner": [1, {"deep": True}]}}
    result = _truncator()._truncate_json(json.dumps(data), 1000)
    assert json.loads(result) == data


def test_truncate_json_falls_back_to_text_when_scalar_json():
    content = json.dumps("a" * 100)
    result = _truncator()._truncate_json(content, 10)
    assert result == content[:23] + f"\n\n{_INDICATOR}"


def test_truncate_json_falls_back_to_text_when_content_not_json():
    content = "not json " * 20
    result = _truncator()._truncate_json(content, 10)
    assert result == content[:23] + f"\n\n{_INDICATOR}"
