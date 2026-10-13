"""Characterization tests for the issue ops (issue #265).

Pins the observable output of github_list_issues, github_get_issue,
github_update_issue and github_search_issues so the C901 refactor can be
proven behaviour-preserving. Only the ``github_client_context`` boundary is
faked.
"""

from unittest.mock import patch

import pytest

from mcp_server_git.github.issue_search import github_search_issues
from mcp_server_git.github.issues import (
    github_get_issue,
    github_list_issues,
    github_update_issue,
)

ISS_CTX = "mcp_server_git.github.issues.github_client_context"
SEARCH_CTX = "mcp_server_git.github.issue_search.github_client_context"


class FakeResponse:
    def __init__(self, status=200, payload=None, text=""):
        self.status = status
        self._payload = payload
        self._text = text

    async def json(self):
        return self._payload

    async def text(self):
        return self._text


class FakeClient:
    """Serves queued responses in call order and records every call."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def _next(self, method, endpoint, kwargs):
        self.calls.append((method, endpoint, kwargs))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def get(self, endpoint, **kwargs):
        return await self._next("get", endpoint, kwargs)

    async def patch(self, endpoint, **kwargs):
        return await self._next("patch", endpoint, kwargs)


class FakeContext:
    def __init__(self, client=None, exc=None):
        self.client = client
        self.exc = exc

    async def __aenter__(self):
        if self.exc is not None:
            raise self.exc
        return self.client

    async def __aexit__(self, *args):
        return None


def ok(payload):
    return FakeResponse(200, payload)


async def _run(func, ctx, args, responses=(), exc=None, **kwargs):
    client = FakeClient(responses)
    with patch(ctx, return_value=FakeContext(client, exc)):
        result = await func(*args, **kwargs)
    return result, client


async def _list(responses=(), exc=None, **kwargs):
    return await _run(github_list_issues, ISS_CTX, ("o", "r"), responses, exc, **kwargs)


async def _get(responses=(), exc=None, **kwargs):
    return await _run(
        github_get_issue, ISS_CTX, ("o", "r", 7), responses, exc, **kwargs
    )


async def _update(responses=(), exc=None, **kwargs):
    return await _run(
        github_update_issue, ISS_CTX, ("o", "r", 7), responses, exc, **kwargs
    )


async def _search(responses=(), exc=None, **kwargs):
    return await _run(
        github_search_issues, SEARCH_CTX, ("o", "r", "bug"), responses, exc, **kwargs
    )


# --------------------------------------------------------------------------
# github_list_issues
# --------------------------------------------------------------------------

BASE_PARAMS = {
    "state": "open",
    "sort": "created",
    "direction": "desc",
    "per_page": 30,
    "page": 1,
}


class TestListIssuesParams:
    @pytest.mark.asyncio
    async def test_list_issues_sends_default_params_when_no_filters(self):
        _, client = await _list([ok([])])
        assert client.calls == [("get", "/repos/o/r/issues", {"params": BASE_PARAMS})]

    @pytest.mark.asyncio
    async def test_list_issues_sends_all_filters_when_all_provided(self):
        _, client = await _list(
            [ok([])],
            state="closed",
            labels=["a", "b"],
            assignee="al",
            creator="cr",
            mentioned="me",
            milestone="3",
            sort="updated",
            direction="asc",
            since="2024-01-01T00:00:00Z",
            per_page=5,
            page=2,
        )
        assert client.calls[0][2]["params"] == {
            "state": "closed",
            "sort": "updated",
            "direction": "asc",
            "per_page": 5,
            "page": 2,
            "labels": "a,b",
            "assignee": "al",
            "creator": "cr",
            "mentioned": "me",
            "milestone": "3",
            "since": "2024-01-01T00:00:00Z",
        }

    @pytest.mark.asyncio
    async def test_list_issues_drops_filters_when_empty_values(self):
        _, client = await _list(
            [ok([])],
            labels=[],
            assignee="",
            creator="",
            mentioned="",
            milestone="",
            since="",
        )
        assert client.calls[0][2]["params"] == BASE_PARAMS

    @pytest.mark.asyncio
    async def test_list_issues_passes_through_when_invalid_values(self):
        _, client = await _list(
            [ok([])],
            state="bogus",
            sort="nope",
            direction="sideways",
            per_page=500,
            page=0,
        )
        assert client.calls[0][2]["params"] == {
            "state": "bogus",
            "sort": "nope",
            "direction": "sideways",
            "per_page": 500,
            "page": 0,
        }


class TestListIssuesOutput:
    @pytest.mark.asyncio
    async def test_list_issues_returns_status_error_when_not_200(self):
        result, _ = await _list([FakeResponse(500, text="boom")])
        assert result == "❌ Failed to list issues: 500 - boom"

    @pytest.mark.asyncio
    async def test_list_issues_returns_none_found_when_empty(self):
        result, _ = await _list([ok([])], state="closed")
        assert result == "No closed issues found"

    @pytest.mark.asyncio
    async def test_list_issues_formats_minimal_issue_when_fields_missing(self):
        result, _ = await _list([ok([{"number": 1, "title": "T"}])])
        assert result.split("\n") == [
            "Open Issues for o/r:",
            "",
            "❓ #1: T",
            "   Author: N/A",
            "   Created: N/A",
            "",
        ]

    @pytest.mark.asyncio
    async def test_list_issues_formats_full_issue_when_all_fields_present(self):
        issue = {
            "number": 2,
            "title": "Two",
            "state": "closed",
            "user": {"login": "bob"},
            "labels": [{"name": "x"}, {"name": "y"}],
            "assignees": [{"login": "a1"}, {"login": "a2"}],
            "created_at": "2024-01-01",
        }
        result, _ = await _list([ok([issue])], state="closed")
        assert result.split("\n") == [
            "Closed Issues for o/r:",
            "",
            "🔴 #2: Two",
            "   Author: bob",
            "   Labels: x, y",
            "   Assignees: a1, a2",
            "   Created: 2024-01-01",
            "",
        ]

    @pytest.mark.asyncio
    async def test_list_issues_skips_pull_requests_when_pull_request_key_set(self):
        issues = [
            {"number": 1, "title": "PR", "pull_request": {"url": "u"}},
            {"number": 2, "title": "Real", "state": "open"},
        ]
        result, _ = await _list([ok(issues)])
        assert result.split("\n") == [
            "Open Issues for o/r:",
            "",
            "🟢 #2: Real",
            "   Author: N/A",
            "   Created: N/A",
            "",
        ]

    @pytest.mark.asyncio
    async def test_list_issues_returns_header_only_when_all_are_pull_requests(self):
        issues = [{"number": 1, "title": "PR", "pull_request": {"url": "u"}}]
        result, _ = await _list([ok(issues)])
        assert result == "Open Issues for o/r:\n"

    @pytest.mark.asyncio
    async def test_list_issues_omits_empty_labels_and_assignees_when_empty_lists(self):
        issue = {
            "number": 3,
            "title": "E",
            "state": "open",
            "labels": [],
            "assignees": [],
            "created_at": "d",
        }
        result, _ = await _list([ok([issue])])
        assert result.split("\n")[2:] == [
            "🟢 #3: E",
            "   Author: N/A",
            "   Created: d",
            "",
        ]

    @pytest.mark.asyncio
    async def test_list_issues_shows_na_author_when_user_is_null(self):
        issue = {"number": 1, "title": "T", "user": None}
        result, _ = await _list([ok([issue])])
        assert "   Author: N/A" in result.split("\n")


class TestListIssuesErrors:
    @pytest.mark.asyncio
    async def test_list_issues_returns_auth_message_when_value_error(self):
        result, _ = await _list(exc=ValueError("no token"))
        assert result == "❌ no token"

    @pytest.mark.asyncio
    async def test_list_issues_returns_network_message_when_connection_error(self):
        result, _ = await _list(exc=ConnectionError("down"))
        assert result == "❌ Network connection failed: down"

    @pytest.mark.asyncio
    async def test_list_issues_returns_generic_message_when_unexpected_error(self):
        result, _ = await _list(exc=RuntimeError("kaboom"))
        assert result == "❌ Error listing issues: kaboom"


# --------------------------------------------------------------------------
# github_get_issue
# --------------------------------------------------------------------------

FULL_ISSUE = {
    "number": 7,
    "title": "Seven",
    "state": "closed",
    "user": {"login": "bob"},
    "created_at": "c",
    "updated_at": "u",
    "closed_at": "x",
    "labels": [{"name": "l1"}, {"name": "l2"}],
    "assignees": [{"login": "a1"}, {"login": "a2"}],
    "milestone": {"title": "v1"},
    "comments": 4,
    "html_url": "http://h",
    "body": "hello",
}


class TestGetIssue:
    @pytest.mark.asyncio
    async def test_get_issue_returns_not_found_when_404(self):
        result, client = await _get([FakeResponse(404)])
        assert result == (
            "❌ Issue #7 not found in o/r. Check issue number and repository access."
        )
        assert client.calls == [("get", "/repos/o/r/issues/7", {})]

    @pytest.mark.asyncio
    async def test_get_issue_returns_status_error_when_not_200(self):
        result, _ = await _get([FakeResponse(500, text="boom")])
        assert result == "❌ Failed to get issue: 500 - boom"

    @pytest.mark.asyncio
    async def test_get_issue_rejects_pull_request_when_pull_request_key_set(self):
        result, _ = await _get([ok({"pull_request": {"url": "u"}})])
        assert result == "❌ #7 is a pull request, not an issue"

    @pytest.mark.asyncio
    async def test_get_issue_formats_full_issue_when_all_fields_present(self):
        result, _ = await _get([ok(FULL_ISSUE)])
        assert result.split("\n") == [
            "Issue #7: Seven",
            "State: 🔴 closed",
            "Author: bob",
            "Created: c",
            "Updated: u",
            "Closed: x",
            "Labels: l1, l2",
            "Assignees: a1, a2",
            "Milestone: v1",
            "Comments: 4",
            "URL: http://h",
            "",
            "Description:",
            "-" * 40,
            "hello",
        ]

    @pytest.mark.asyncio
    async def test_get_issue_formats_defaults_when_optional_fields_missing(self):
        result, _ = await _get([ok({"number": 7, "title": "T"})])
        assert result.split("\n") == [
            "Issue #7: T",
            "State: ❓ unknown",
            "Author: N/A",
            "Created: N/A",
            "Updated: N/A",
            "Comments: 0",
            "URL: N/A",
            "",
            "Description:",
            "-" * 40,
            "(No description provided)",
        ]

    @pytest.mark.asyncio
    async def test_get_issue_shows_open_marker_when_state_open(self):
        result, _ = await _get([ok({"number": 7, "title": "T", "state": "open"})])
        assert result.split("\n")[1] == "State: 🟢 open"

    @pytest.mark.asyncio
    async def test_get_issue_shows_na_author_when_user_null(self):
        result, _ = await _get([ok({"number": 7, "title": "T", "user": None})])
        assert result.split("\n")[2] == "Author: N/A"

    @pytest.mark.asyncio
    async def test_get_issue_shows_na_milestone_when_title_missing(self):
        result, _ = await _get(
            [ok({"number": 7, "title": "T", "milestone": {"number": 1}})]
        )
        assert "Milestone: N/A" in result.split("\n")

    @pytest.mark.asyncio
    async def test_get_issue_omits_empty_labels_assignees_when_empty_lists(self):
        issue = {"number": 7, "title": "T", "labels": [], "assignees": []}
        result, _ = await _get([ok(issue)])
        lines = result.split("\n")
        assert not any(ln.startswith(("Labels:", "Assignees:")) for ln in lines)

    @pytest.mark.asyncio
    async def test_get_issue_uses_placeholder_when_body_empty_string(self):
        result, _ = await _get([ok({"number": 7, "title": "T", "body": ""})])
        assert result.endswith("(No description provided)")

    @pytest.mark.asyncio
    async def test_get_issue_truncates_body_when_over_max_body_chars(self):
        result, _ = await _get(
            [ok({"number": 7, "title": "T", "body": "abcdefghij"})],
            max_body_chars=4,
        )
        assert result.split("\n")[-3:] == [
            "abcd",
            "",
            "... (truncated: showing 4 of 10 chars)",
        ]

    @pytest.mark.asyncio
    async def test_get_issue_keeps_body_when_within_max_body_chars(self):
        result, _ = await _get(
            [ok({"number": 7, "title": "T", "body": "abcd"})], max_body_chars=4
        )
        assert result.endswith("\nabcd")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("cap", [0, -5, None])
    async def test_get_issue_keeps_full_body_when_cap_non_positive_or_none(self, cap):
        result, _ = await _get(
            [ok({"number": 7, "title": "T", "body": "abcdefghij"})],
            max_body_chars=cap,
        )
        assert result.endswith("\nabcdefghij")

    @pytest.mark.asyncio
    async def test_get_issue_returns_auth_message_when_value_error(self):
        result, _ = await _get(exc=ValueError("no token"))
        assert result == "❌ no token"

    @pytest.mark.asyncio
    async def test_get_issue_returns_network_message_when_connection_error(self):
        result, _ = await _get(exc=ConnectionError("down"))
        assert result == "❌ Network connection failed: down"

    @pytest.mark.asyncio
    async def test_get_issue_returns_generic_message_when_unexpected_error(self):
        result, _ = await _get(exc=RuntimeError("kaboom"))
        assert result == "❌ Error getting issue: kaboom"


# --------------------------------------------------------------------------
# github_update_issue
# --------------------------------------------------------------------------


class TestUpdateIssue:
    @pytest.mark.asyncio
    async def test_update_issue_returns_warning_when_no_params(self):
        result, client = await _update()
        assert result == (
            "⚠️ No update parameters provided. Please specify title, body, "
            "state, labels, assignees, or milestone."
        )
        assert client.calls == []

    @pytest.mark.asyncio
    async def test_update_issue_rejects_state_when_invalid(self):
        result, client = await _update(state="merged", title="T")
        assert result == "❌ State must be 'open' or 'closed'"
        assert client.calls == []

    @pytest.mark.asyncio
    async def test_update_issue_rejects_state_when_empty_string(self):
        result, _ = await _update(state="")
        assert result == "❌ State must be 'open' or 'closed'"

    @pytest.mark.asyncio
    async def test_update_issue_sends_all_fields_when_all_provided(self):
        result, client = await _update(
            [ok({"number": 7, "html_url": "http://h"})],
            title="T",
            body="B",
            state="closed",
            labels=["x"],
            assignees=["a"],
            milestone=2,
        )
        assert result == "✅ Successfully updated issue #7: http://h"
        assert client.calls == [
            (
                "patch",
                "/repos/o/r/issues/7",
                {
                    "json": {
                        "title": "T",
                        "body": "B",
                        "state": "closed",
                        "labels": ["x"],
                        "assignees": ["a"],
                        "milestone": 2,
                    }
                },
            )
        ]

    @pytest.mark.asyncio
    async def test_update_issue_sends_falsy_values_when_not_none(self):
        _, client = await _update(
            [ok({"number": 7, "html_url": "h"})],
            title="",
            body="",
            labels=[],
            assignees=[],
            milestone=0,
        )
        assert client.calls[0][2]["json"] == {
            "title": "",
            "body": "",
            "labels": [],
            "assignees": [],
            "milestone": 0,
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("kwargs", "expected"),
        [
            ({"title": "T"}, {"title": "T"}),
            ({"body": "B"}, {"body": "B"}),
            ({"state": "open"}, {"state": "open"}),
            ({"labels": ["l"]}, {"labels": ["l"]}),
            ({"assignees": ["a"]}, {"assignees": ["a"]}),
            ({"milestone": 5}, {"milestone": 5}),
        ],
    )
    async def test_update_issue_sends_single_field_when_only_one_given(
        self, kwargs, expected
    ):
        _, client = await _update([ok({"number": 7, "html_url": "h"})], **kwargs)
        assert client.calls[0][2]["json"] == expected

    @pytest.mark.asyncio
    async def test_update_issue_returns_status_error_when_not_200(self):
        result, _ = await _update([FakeResponse(422, text="bad")], title="T")
        assert result == "❌ Failed to update issue #7: 422 - bad"

    @pytest.mark.asyncio
    async def test_update_issue_returns_auth_message_when_value_error(self):
        result, _ = await _update(exc=ValueError("no token"), title="T")
        assert result == "❌ no token"

    @pytest.mark.asyncio
    async def test_update_issue_returns_network_message_when_connection_error(self):
        result, _ = await _update(exc=ConnectionError("down"), title="T")
        assert result == "❌ Network connection failed: down"

    @pytest.mark.asyncio
    async def test_update_issue_returns_generic_message_when_unexpected_error(self):
        result, _ = await _update(exc=RuntimeError("kaboom"), title="T")
        assert result == "❌ Error updating issue: kaboom"


# --------------------------------------------------------------------------
# github_search_issues
# --------------------------------------------------------------------------


def _search_payload(items, total=None):
    return {"items": items, "total_count": len(items) if total is None else total}


class TestSearchIssues:
    @pytest.mark.asyncio
    async def test_search_issues_builds_query_params_when_defaults(self):
        _, client = await _search([ok({})])
        assert client.calls == [
            (
                "get",
                "/search/issues",
                {
                    "params": {
                        "q": "repo:o/r is:issue bug",
                        "sort": "created",
                        "order": "desc",
                        "per_page": 30,
                        "page": 1,
                    }
                },
            )
        ]

    @pytest.mark.asyncio
    async def test_search_issues_passes_custom_params_when_provided(self):
        _, client = await _search(
            [ok({})], sort="updated", order="asc", per_page=5, page=3
        )
        params = client.calls[0][2]["params"]
        assert (params["sort"], params["order"]) == ("updated", "asc")
        assert (params["per_page"], params["page"]) == (5, 3)

    @pytest.mark.asyncio
    async def test_search_issues_returns_status_error_when_not_200(self):
        result, _ = await _search([FakeResponse(403, text="rate")])
        assert result == "❌ Failed to search issues: 403 - rate"

    @pytest.mark.asyncio
    async def test_search_issues_returns_none_found_when_no_items(self):
        result, _ = await _search([ok({"items": [], "total_count": 0})])
        assert result == "No issues found matching query: bug"

    @pytest.mark.asyncio
    async def test_search_issues_formats_minimal_issue_when_fields_missing(self):
        result, _ = await _search([ok(_search_payload([{"number": 1, "title": "T"}]))])
        assert result.split("\n") == [
            "Search Results for 'bug' in o/r:",
            "",
            "Found 1 total issues (showing page 1)",
            "",
            "❓ #1: T",
            "   Author: N/A",
            "   Created: N/A",
            "   Score: N/A",
            "",
        ]

    @pytest.mark.asyncio
    async def test_search_issues_formats_full_issue_when_all_fields_present(self):
        issue = {
            "number": 2,
            "title": "Two",
            "state": "open",
            "user": {"login": "bob"},
            "labels": [{"name": "x"}],
            "assignees": [{"login": "a1"}, {"login": "a2"}],
            "milestone": {"title": "v1"},
            "created_at": "d",
            "score": 1.5,
        }
        result, _ = await _search([ok(_search_payload([issue]))])
        assert result.split("\n")[4:] == [
            "🟢 #2: Two",
            "   Author: bob",
            "   Labels: x",
            "   Assignees: a1, a2",
            "   Milestone: v1",
            "   Created: d",
            "   Score: 1.5",
            "",
        ]

    @pytest.mark.asyncio
    async def test_search_issues_skips_pull_requests_when_pull_request_key_set(self):
        items = [
            {"number": 1, "title": "PR", "pull_request": {"url": "u"}, "state": "open"},
            {"number": 2, "title": "Real", "state": "closed"},
        ]
        result, _ = await _search([ok(_search_payload(items))])
        lines = result.split("\n")
        assert "🔴 #2: Real" in lines
        assert not any("#1" in ln for ln in lines)

    @pytest.mark.asyncio
    async def test_search_issues_adds_pagination_when_total_exceeds_items(self):
        items = [{"number": 1, "title": "T"}]
        result, _ = await _search(
            [ok(_search_payload(items, total=95))], per_page=10, page=2
        )
        assert result.split("\n")[-1] == (
            "📄 Page 2 of 10 (max 95 results from GitHub)"
        )

    @pytest.mark.asyncio
    async def test_search_issues_caps_pagination_at_1000_when_total_large(self):
        items = [{"number": 1, "title": "T"}]
        result, _ = await _search([ok(_search_payload(items, total=5000))], per_page=30)
        assert result.split("\n")[-1] == (
            "📄 Page 1 of 34 (max 1000 results from GitHub)"
        )

    @pytest.mark.asyncio
    async def test_search_issues_omits_pagination_when_total_equals_items(self):
        items = [{"number": 1, "title": "T"}]
        result, _ = await _search([ok(_search_payload(items))])
        assert result.endswith("   Score: N/A\n")

    @pytest.mark.asyncio
    async def test_search_issues_shows_na_author_when_user_is_null(self):
        items = [{"number": 1, "title": "T", "user": None}]
        result, _ = await _search([ok(_search_payload(items))])
        assert "   Author: N/A" in result.split("\n")

    @pytest.mark.asyncio
    async def test_search_issues_shows_na_milestone_when_title_missing(self):
        items = [{"number": 1, "title": "T", "milestone": {"number": 1}}]
        result, _ = await _search([ok(_search_payload(items))])
        assert "   Milestone: N/A" in result.split("\n")

    @pytest.mark.asyncio
    async def test_search_issues_returns_auth_message_when_value_error(self):
        result, _ = await _search(exc=ValueError("no token"))
        assert result == "❌ no token"

    @pytest.mark.asyncio
    async def test_search_issues_returns_network_message_when_connection_error(self):
        result, _ = await _search(exc=ConnectionError("down"))
        assert result == "❌ Network connection failed: down"

    @pytest.mark.asyncio
    async def test_search_issues_returns_generic_message_when_unexpected_error(self):
        result, _ = await _search(exc=RuntimeError("kaboom"))
        assert result == "❌ Error searching issues: kaboom"
