"""Unit tests for the shared paging/filter helpers (issue #274)."""

import pytest

from mcp_server_git.github._paging import clamp_paging, invalid_choice
from mcp_server_git.github._payload import body_preview


@pytest.mark.parametrize(
    ("per_page", "page", "expected"),
    [
        (30, 1, (30, 1)),
        (500, 0, (100, 1)),
        (0, -4, (1, 1)),
        (-7, 9, (1, 9)),
        (100, 2, (100, 2)),
        (1, 1, (1, 1)),
    ],
)
def test_clamp_paging_returns_bounded_values_when_out_of_range(
    per_page, page, expected
):
    assert clamp_paging(per_page, page) == expected


def test_invalid_choice_returns_message_when_value_not_allowed():
    assert invalid_choice("state", "bogus", ("open", "closed")) == (
        "❌ Invalid state 'bogus'. Must be one of: open, closed"
    )


@pytest.mark.parametrize("value", [None, "open"])
def test_invalid_choice_returns_none_when_value_none_or_allowed(value):
    assert invalid_choice("state", value, ("open", "closed")) is None


def test_body_preview_returns_text_unchanged_when_at_limit():
    assert body_preview("x" * 500) == "x" * 500


def test_body_preview_truncates_with_ellipsis_when_over_limit():
    assert body_preview("x" * 501) == "x" * 500 + "..."
