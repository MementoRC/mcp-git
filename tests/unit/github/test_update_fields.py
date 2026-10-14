"""Unit tests for the shared update-field helpers (issue #275)."""

import pytest

from mcp_server_git.github._update_fields import (
    first_required_error,
    required_text_error,
)
from mcp_server_git.github.models import GitHubUpdateIssue


@pytest.mark.parametrize(("milestone", "expected"), [(0, 0), (3, 3), (-1, None)])
def test_update_issue_model_keeps_zero_milestone_when_clearing(milestone, expected):
    model = GitHubUpdateIssue(
        repo_owner="o", repo_name="r", issue_number=1, milestone=milestone
    )
    assert model.milestone == expected


@pytest.mark.parametrize("value", [None, "x", " "])
def test_required_text_error_returns_none_when_value_not_empty(value):
    assert required_text_error("title", value) is None


def test_required_text_error_returns_message_when_value_empty():
    assert required_text_error("title", "") == (
        "❌ title cannot be empty. Pass None to leave it unchanged."
    )


def test_first_required_error_returns_first_empty_field_when_several_empty():
    error = first_required_error({"title": "T", "state": "", "base": ""})
    assert error == "❌ state cannot be empty. Pass None to leave it unchanged."


def test_first_required_error_returns_none_when_no_field_empty():
    assert first_required_error({"title": None, "base": "dev"}) is None
