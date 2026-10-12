"""Characterization tests for the PR ops (issue #264).

Pins the observable output of github_get_pr_details, github_update_pr,
github_get_pr_diff and gh_edit_pr so the C901 refactor can be proven
behaviour-preserving. Only the ``github_client_context`` boundary (or the
``_run_gh_command`` subprocess boundary for the CLI op) is faked.
"""

from unittest.mock import patch

import pytest

from mcp_server_git.github.cli import gh_edit_pr
from mcp_server_git.github.pr import github_get_pr_details
from mcp_server_git.github.pr_actions import github_update_pr
from mcp_server_git.github.pr_diff import github_get_pr_diff

PR_CTX = "mcp_server_git.github.pr.github_client_context"
ACT_CTX = "mcp_server_git.github.pr_actions.github_client_context"
DIFF_CTX = "mcp_server_git.github.pr_diff.github_client_context"
GH_RUN = "mcp_server_git.github.cli._run_gh_command"


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


# --------------------------------------------------------------------------
# github_get_pr_details
# --------------------------------------------------------------------------


async def _details(responses=(), exc=None, **kwargs):
    client = FakeClient(responses)
    with patch(PR_CTX, return_value=FakeContext(client, exc)):
        result = await github_get_pr_details("o", "r", 5, **kwargs)
    return result, client


class TestGetPrDetailsCore:
    @pytest.mark.asyncio
    async def test_get_pr_details_returns_status_error_when_pr_not_found(self):
        result, client = await _details([FakeResponse(404)])
        assert result == "❌ Failed to get PR #5: 404"
        assert client.calls == [("get", "/repos/o/r/pulls/5", {})]

    @pytest.mark.asyncio
    async def test_get_pr_details_returns_na_lines_when_payload_empty(self):
        result, _ = await _details([ok({})])
        assert result.split("\n") == [
            "Pull Request #5:",
            "",
            "Title: N/A",
            "State: N/A",
            "Author: N/A",
            "Base: N/A",
            "Head: N/A",
            "Created: N/A",
            "Updated: N/A",
        ]

    @pytest.mark.asyncio
    async def test_get_pr_details_returns_all_core_fields_when_payload_full(self):
        pr = {
            "title": "T",
            "state": "open",
            "user": {"login": "alice"},
            "base": {"ref": "main"},
            "head": {"ref": "feat"},
            "created_at": "c",
            "updated_at": "u",
            "body": "hello",
            "html_url": "https://x/pr/5",
        }
        result, client = await _details([ok(pr)])
        assert result.split("\n") == [
            "Pull Request #5:",
            "",
            "Title: T",
            "State: open",
            "Author: alice",
            "Base: main",
            "Head: feat",
            "Created: c",
            "Updated: u",
            "",
            "Description:",
            "hello",
            "",
            "URL: https://x/pr/5",
        ]
        assert len(client.calls) == 1

    @pytest.mark.asyncio
    async def test_get_pr_details_returns_merged_line_when_pr_closed_and_merged(self):
        pr = {
            "state": "closed",
            "merged_at": "2026-01-02",
            "merged_by": {"login": "bob"},
            "merge_commit_sha": "abcdef123456",
        }
        result, _ = await _details([ok(pr)])
        lines = result.split("\n")
        assert lines[3:5] == [
            "State: closed",
            "Merged: yes (2026-01-02, by bob, abcdef1)",
        ]

    @pytest.mark.asyncio
    async def test_get_pr_details_returns_merged_no_when_pr_closed_unmerged(self):
        result, _ = await _details([ok({"state": "closed"})])
        assert result.split("\n")[3:5] == ["State: closed", "Merged: no"]

    @pytest.mark.asyncio
    async def test_get_pr_details_keeps_500_char_body_whole_when_exactly_500(self):
        body = "b" * 500
        result, _ = await _details([ok({"body": body})])
        assert result.endswith(f"\nDescription:\n{body}")

    @pytest.mark.asyncio
    async def test_get_pr_details_truncates_body_with_ellipsis_when_over_500(self):
        result, _ = await _details([ok({"body": "b" * 501})])
        assert result.endswith(f"\nDescription:\n{'b' * 500}...")

    @pytest.mark.asyncio
    async def test_get_pr_details_skips_description_when_body_empty(self):
        result, _ = await _details([ok({"body": "", "html_url": ""})])
        assert "Description" not in result
        assert "URL:" not in result


class TestGetPrDetailsFiles:
    @pytest.mark.asyncio
    async def test_get_pr_details_lists_files_when_include_files_set(self):
        files = [
            {"status": "added", "filename": "a.py", "additions": 3, "deletions": 0},
            {"status": "modified", "filename": "b.py", "additions": 1, "deletions": 2},
        ]
        result, client = await _details([ok({}), ok(files)], include_files=True)
        assert result.split("\n")[-4:] == [
            "",
            "Files (2):",
            "  A a.py (+3, -0)",
            "  M b.py (+1, -2)",
        ]
        assert client.calls[1] == ("get", "/repos/o/r/pulls/5/files", {})

    @pytest.mark.asyncio
    async def test_get_pr_details_caps_files_at_ten_when_more_returned(self):
        files = [
            {"status": "removed", "filename": f"f{i}", "additions": 0, "deletions": i}
            for i in range(12)
        ]
        result, _ = await _details([ok({}), ok(files)], include_files=True)
        lines = result.split("\n")
        assert "Files (12):" in lines
        assert "  R f9 (+0, -9)" in lines
        assert "  R f10 (+0, -10)" not in lines
        assert lines[-1] == "  ... and 2 more files"

    @pytest.mark.asyncio
    async def test_get_pr_details_omits_files_section_when_list_empty(self):
        result, _ = await _details([ok({}), ok([])], include_files=True)
        assert "Files" not in result

    @pytest.mark.asyncio
    async def test_get_pr_details_omits_files_section_when_files_status_not_200(self):
        result, _ = await _details([ok({}), FakeResponse(500)], include_files=True)
        assert result.endswith("Updated: N/A")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("error", [ConnectionError("down"), ValueError("bad")])
    async def test_get_pr_details_warns_about_files_when_connection_or_value_error(
        self, error
    ):
        result, _ = await _details([ok({}), error], include_files=True)
        assert result.endswith("\n\n⚠️ Could not retrieve files information")

    @pytest.mark.asyncio
    async def test_get_pr_details_returns_outer_error_when_files_raise_other(self):
        result, _ = await _details([ok({}), RuntimeError("boom")], include_files=True)
        assert result == "❌ Error getting PR details: boom"

    @pytest.mark.asyncio
    async def test_get_pr_details_returns_keyerror_text_when_file_missing_field(self):
        # Quirk: a file lacking additions/deletions escapes the inner handler.
        files = [{"status": "added", "filename": "a"}]
        result, _ = await _details([ok({}), ok(files)], include_files=True)
        assert result == "❌ Error getting PR details: 'additions'"


class TestGetPrDetailsReviews:
    @pytest.mark.asyncio
    async def test_get_pr_details_lists_reviews_with_state_markers_when_requested(self):
        reviews = [
            {"state": "APPROVED", "user": {"login": "a"}},
            {"state": "CHANGES_REQUESTED", "user": {"login": "b"}},
            {"state": "COMMENTED", "user": {"login": "c"}},
            {"state": "DISMISSED", "user": {"login": "d"}},
            {},
        ]
        result, client = await _details([ok({}), ok(reviews)], include_reviews=True)
        assert result.split("\n")[-7:] == [
            "",
            "Reviews (5):",
            "  ✅ a: APPROVED",
            "  ❌ b: CHANGES_REQUESTED",
            "  💬 c: COMMENTED",
            "  ❓ d: DISMISSED",
            "  ❓ N/A: N/A",
        ]
        assert client.calls[1] == ("get", "/repos/o/r/pulls/5/reviews", {})

    @pytest.mark.asyncio
    async def test_get_pr_details_shows_last_five_reviews_when_more_returned(self):
        reviews = [{"state": "APPROVED", "user": {"login": f"u{i}"}} for i in range(7)]
        result, _ = await _details([ok({}), ok(reviews)], include_reviews=True)
        lines = result.split("\n")
        assert "Reviews (7):" in lines
        assert "  ✅ u1: APPROVED" not in lines
        assert lines[-5:] == [f"  ✅ u{i}: APPROVED" for i in range(2, 7)]

    @pytest.mark.asyncio
    async def test_get_pr_details_omits_reviews_section_when_list_empty(self):
        result, _ = await _details([ok({}), ok([])], include_reviews=True)
        assert "Reviews" not in result

    @pytest.mark.asyncio
    async def test_get_pr_details_omits_reviews_when_reviews_status_not_200(self):
        result, _ = await _details([ok({}), FakeResponse(403)], include_reviews=True)
        assert result.endswith("Updated: N/A")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("error", [ConnectionError("down"), ValueError("bad")])
    async def test_get_pr_details_warns_about_reviews_when_connection_or_value_error(
        self, error
    ):
        result, _ = await _details([ok({}), error], include_reviews=True)
        assert result.endswith("\n\n⚠️ Could not retrieve reviews information")

    @pytest.mark.asyncio
    async def test_get_pr_details_orders_files_before_reviews_when_both_requested(self):
        files = [{"status": "added", "filename": "a", "additions": 1, "deletions": 0}]
        reviews = [{"state": "APPROVED", "user": {"login": "a"}}]
        result, client = await _details(
            [ok({}), ok(files), ok(reviews)], include_files=True, include_reviews=True
        )
        assert result.index("Files (1):") < result.index("Reviews (1):")
        assert [c[1] for c in client.calls] == [
            "/repos/o/r/pulls/5",
            "/repos/o/r/pulls/5/files",
            "/repos/o/r/pulls/5/reviews",
        ]


class TestGetPrDetailsErrors:
    @pytest.mark.asyncio
    async def test_get_pr_details_returns_message_when_value_error_on_enter(self):
        result, _ = await _details(exc=ValueError("no token"))
        assert result == "❌ no token"

    @pytest.mark.asyncio
    async def test_get_pr_details_returns_network_error_when_connection_error(self):
        result, _ = await _details(exc=ConnectionError("down"))
        assert result == "❌ Network connection failed: down"

    @pytest.mark.asyncio
    async def test_get_pr_details_returns_generic_error_when_unexpected_exception(self):
        result, _ = await _details(exc=RuntimeError("boom"))
        assert result == "❌ Error getting PR details: boom"

    @pytest.mark.asyncio
    async def test_get_pr_details_returns_attribute_error_text_when_user_is_null(self):
        # Quirk: .get("user", {}) does not guard against an explicit null.
        result, _ = await _details([ok({"user": None})])
        assert result == (
            "❌ Error getting PR details: 'NoneType' object has no attribute 'get'"
        )


# --------------------------------------------------------------------------
# github_update_pr
# --------------------------------------------------------------------------


async def _update(responses=(), exc=None, **kwargs):
    client = FakeClient(responses)
    with patch(ACT_CTX, return_value=FakeContext(client, exc)):
        result = await github_update_pr("o", "r", 7, **kwargs)
    return result, client


class TestUpdatePr:
    @pytest.mark.asyncio
    async def test_update_pr_returns_warning_when_no_params_given(self):
        result, client = await _update()
        assert result == (
            "⚠️ No update parameters provided. Please specify title, body, state, or base."
        )
        assert client.calls == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("kwargs", "payload"),
        [
            ({"title": "T"}, {"title": "T"}),
            ({"body": "B"}, {"body": "B"}),
            ({"body": ""}, {"body": ""}),
            ({"title": ""}, {"title": ""}),
            ({"state": "open"}, {"state": "open"}),
            ({"state": "closed"}, {"state": "closed"}),
            ({"base": "dev"}, {"base": "dev"}),
            (
                {"title": "T", "body": "B", "state": "closed", "base": "dev"},
                {"title": "T", "body": "B", "state": "closed", "base": "dev"},
            ),
        ],
    )
    async def test_update_pr_sends_only_given_fields_when_params_set(
        self, kwargs, payload
    ):
        resp = ok({"number": 7, "html_url": "https://x/7"})
        result, client = await _update([resp], **kwargs)
        assert result == "✅ Successfully updated PR #7: https://x/7"
        assert client.calls == [("patch", "/repos/o/r/pulls/7", {"json": payload})]

    @pytest.mark.asyncio
    async def test_update_pr_returns_state_error_when_state_invalid(self):
        result, client = await _update(title="T", state="merged")
        assert result == "❌ State must be 'open' or 'closed'"
        assert client.calls == []

    @pytest.mark.asyncio
    async def test_update_pr_returns_status_and_text_when_patch_fails(self):
        result, _ = await _update(
            [FakeResponse(422, text="Validation Failed")], base="x"
        )
        assert result == "❌ Failed to update PR #7: 422 - Validation Failed"

    @pytest.mark.asyncio
    async def test_update_pr_returns_message_when_value_error_on_enter(self):
        result, _ = await _update(exc=ValueError("no token"), title="T")
        assert result == "❌ no token"

    @pytest.mark.asyncio
    async def test_update_pr_returns_network_error_when_connection_error(self):
        result, _ = await _update([ConnectionError("down")], title="T")
        assert result == "❌ Network connection failed: down"

    @pytest.mark.asyncio
    async def test_update_pr_returns_generic_error_when_unexpected_exception(self):
        result, _ = await _update([RuntimeError("boom")], title="T")
        assert result == "❌ Error updating PR: boom"

    @pytest.mark.asyncio
    async def test_update_pr_returns_keyerror_text_when_response_lacks_number(self):
        result, _ = await _update([ok({})], title="T")
        assert result == "❌ Error updating PR: 'number'"


# --------------------------------------------------------------------------
# github_get_pr_diff
# --------------------------------------------------------------------------

DIFF_LINES = [
    "diff --git a/src/a.py b/src/a.py",
    "--- a/src/a.py",
    "+++ b/src/a.py",
    "@@ -1 +1 @@",
    "-a_old",
    "+a_new",
    "diff --git a/src/b.py b/src/b.py",
    "--- a/src/b.py",
    "+++ b/src/b.py",
    "@@ -1 +1 @@",
    "-b_old",
    "+b_new",
    "diff --git a/docs/r.md b/docs/r.md",
    "--- a/docs/r.md",
    "+++ b/docs/r.md",
    "@@ -1 +1 @@",
    "-r_old",
    "+r_new",
]
DIFF = "\n".join(DIFF_LINES)
SEP = "-" * 60
FULL_PR = {
    "title": "Add X",
    "state": "open",
    "merged": False,
    "base": {"ref": "main"},
    "head": {"ref": "feat"},
    "changed_files": 3,
    "additions": 10,
    "deletions": 4,
    "html_url": "https://x/pr/9",
}
FULL_HEADER = [
    "🔀 PR #9 - Add X",
    "Repository: o/r",
    "State: open",
    "Branches: feat → main",
    "Files changed: 3 (+10, -4)",
    "URL: https://x/pr/9",
]


def _oversized() -> str:
    padding = [f"+pad {i} {'x' * 80}" for i in range(1400)]
    return "\n".join(DIFF_LINES[:6] + padding + DIFF_LINES[6:])


async def _diff(responses=(), exc=None, **kwargs):
    client = FakeClient(responses)
    with patch(DIFF_CTX, return_value=FakeContext(client, exc)):
        result = await github_get_pr_diff("o", "r", 9, **kwargs)
    return result, client


def _ok_diff(text=DIFF, pr=None):
    return [ok(FULL_PR if pr is None else pr), FakeResponse(200, text=text)]


class TestGetPrDiffHeaderAndErrors:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("status", "message"),
        [
            (404, "❌ PR #9 not found in o/r"),
            (
                403,
                "❌ Access denied for PR #9. "
                "Check repository permissions or API rate limits.",
            ),
            (429, "❌ GitHub API rate limit exceeded. Please wait and try again."),
            (500, "❌ Failed to fetch PR #9: HTTP 500"),
        ],
    )
    async def test_get_pr_diff_returns_error_when_pr_response_not_ok(
        self, status, message
    ):
        result, client = await _diff([FakeResponse(status)])
        assert result == message
        assert len(client.calls) == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("status", "message"),
        [
            (404, "❌ PR #9 not found in o/r"),
            (429, "❌ GitHub API rate limit exceeded. Please wait and try again."),
            (502, "❌ Failed to fetch PR #9: HTTP 502"),
        ],
    )
    async def test_get_pr_diff_appends_error_to_header_when_diff_response_not_ok(
        self, status, message
    ):
        result, _ = await _diff([ok(FULL_PR), FakeResponse(status)])
        assert result == "\n".join([*FULL_HEADER, message])

    @pytest.mark.asyncio
    async def test_get_pr_diff_returns_minimal_header_when_pr_payload_empty(self):
        result, _ = await _diff(_ok_diff("  \n", pr={}))
        assert result.split("\n") == [
            "🔀 PR #9 - (no title)",
            "Repository: o/r",
            "",
            "📭 Diff is empty (no file changes)",
        ]

    @pytest.mark.asyncio
    async def test_get_pr_diff_marks_merged_and_defaults_counts_when_partial(self):
        pr = {"title": "T", "state": "closed", "merged": True, "changed_files": 0}
        result, _ = await _diff(_ok_diff("", pr=pr))
        assert result.split("\n")[:4] == [
            "🔀 PR #9 - T",
            "Repository: o/r",
            "State: closed (merged)",
            "Files changed: 0 (+0, -0)",
        ]

    @pytest.mark.asyncio
    async def test_get_pr_diff_omits_branches_when_head_missing_or_null(self):
        pr = {"base": {"ref": "main"}, "head": None}
        result, _ = await _diff(_ok_diff("", pr=pr))
        assert "Branches" not in result

    @pytest.mark.asyncio
    async def test_get_pr_diff_requests_diff_media_type_when_not_patch(self):
        _, client = await _diff(_ok_diff())
        assert client.calls == [
            ("get", "/repos/o/r/pulls/9", {}),
            (
                "get",
                "/repos/o/r/pulls/9",
                {"accept": "application/vnd.github.v3.diff"},
            ),
        ]

    @pytest.mark.asyncio
    async def test_get_pr_diff_requests_patch_media_type_when_as_patch_set(self):
        _, client = await _diff(_ok_diff(), as_patch=True)
        assert client.calls[1][2] == {"accept": "application/vnd.github.v3.patch"}

    @pytest.mark.asyncio
    async def test_get_pr_diff_returns_message_when_value_error_on_enter(self):
        result, _ = await _diff(exc=ValueError("no token"))
        assert result == "❌ no token"

    @pytest.mark.asyncio
    async def test_get_pr_diff_returns_network_error_when_connection_error(self):
        result, _ = await _diff(exc=ConnectionError("down"))
        assert result == "❌ Network connection failed: down"

    @pytest.mark.asyncio
    async def test_get_pr_diff_returns_generic_error_when_unexpected_exception(self):
        result, _ = await _diff(exc=RuntimeError("boom"))
        assert result == "❌ Error getting PR diff: boom"


class TestGetPrDiffSelection:
    @pytest.mark.asyncio
    async def test_get_pr_diff_returns_whole_diff_when_no_selectors(self):
        result, _ = await _diff(_ok_diff())
        lines = result.split("\n")
        assert lines[:6] == FULL_HEADER
        assert lines[6].startswith(f"📊 Total: 18 lines / {len(DIFF)} bytes | ")
        assert lines[6].endswith("| Truncated: no")
        assert lines[7] == ""
        assert lines[8].startswith("📋 Diff (")
        assert result.endswith(f"{SEP}\n{DIFF}\n{SEP}")

    @pytest.mark.asyncio
    async def test_get_pr_diff_reports_counts_when_file_filter_matches(self):
        result, _ = await _diff(_ok_diff(), file_filter="src/*")
        assert "🔎 file_filter 'src/*': 2 of 3 file(s)" in result.split("\n")
        assert "+b_new" in result
        assert "r_new" not in result

    @pytest.mark.asyncio
    async def test_get_pr_diff_stops_after_filter_line_when_no_file_matches(self):
        result, _ = await _diff(_ok_diff(), file_filter="zzz*")
        assert result.split("\n")[-2:] == [
            "🔎 file_filter 'zzz*': 0 of 3 file(s)",
            "🔍 No files matched 'zzz*'",
        ]

    @pytest.mark.asyncio
    async def test_get_pr_diff_writes_whole_diff_to_disk_when_output_path_given(
        self, tmp_path
    ):
        target = tmp_path / "sub" / "out.diff"
        result, _ = await _diff(_ok_diff(), output_path=str(target))
        lines = result.split("\n")
        assert lines[6] == f"💾 Full diff written to {target}"
        assert lines[7].startswith(
            f"📊 Total: 18 lines / {len(DIFF)} bytes | Returned:"
        )
        assert "written to disk" in lines[7]
        assert target.read_text() == DIFF
        assert "a_new" not in result

    @pytest.mark.asyncio
    async def test_get_pr_diff_writes_only_filtered_sections_when_filter_and_path(
        self, tmp_path
    ):
        target = tmp_path / "out.diff"
        await _diff(_ok_diff(), output_path=str(target), file_filter="docs/*")
        assert target.read_text() == "\n".join(DIFF_LINES[12:])

    @pytest.mark.asyncio
    async def test_get_pr_diff_returns_error_when_output_path_relative(self):
        result, _ = await _diff(_ok_diff(), output_path="rel.diff")
        assert result == "❌ output_path must be an absolute path, got: rel.diff"

    @pytest.mark.asyncio
    async def test_get_pr_diff_returns_gate_when_oversize_and_no_selectors(self):
        text = _oversized()
        result, _ = await _diff(_ok_diff(text))
        assert result.split("\n")[6:] == [
            "",
            f"⚠️ Diff is {len(text):,} bytes across 3 file(s), over the "
            "102,400-byte inline limit. Nothing was returned inline to protect "
            "LLM context. Re-run with one of:",
            "  • output_path='/abs/path.diff' — write the whole diff to disk "
            "(no content enters context)",
            "  • file_filter='src/*' — limit to matching paths",
            "  • grep='pattern' — return only matching lines, searched diff-wide",
            "  • head_lines / tail_lines / start_line+end_line — an explicit window",
            "  • full_diff=True — return as much as fits under the 100KB cap",
        ]

    @pytest.mark.asyncio
    async def test_get_pr_diff_truncates_to_cap_when_oversize_and_full_diff(self):
        result, _ = await _diff(_ok_diff(_oversized()), full_diff=True)
        assert "⚠️ Truncated for LLM context (chars: exceeded 100KB limit)" in result
        assert "Nothing was returned inline" not in result

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"head_lines": 3},
            {"tail_lines": 3},
            {"start_line": 1},
            {"end_line": 3},
            {"grep": "a_new"},
            {"file_filter": "docs/*"},
        ],
    )
    async def test_get_pr_diff_skips_gate_when_oversize_and_selector_given(
        self, kwargs
    ):
        result, _ = await _diff(_ok_diff(_oversized()), **kwargs)
        assert "Nothing was returned inline" not in result
        assert "📋 Diff (" in result

    @pytest.mark.asyncio
    async def test_get_pr_diff_returns_head_window_when_head_lines_given(self):
        result, _ = await _diff(_ok_diff(), head_lines=2)
        assert "| Truncated: yes" in result
        assert result.endswith(f"{SEP}\n{DIFF_LINES[0]}\n{DIFF_LINES[1]}\n{SEP}")
        assert "⚠️ Truncated for LLM context (lines: 18 total)" in result

    @pytest.mark.asyncio
    async def test_get_pr_diff_returns_tail_window_when_tail_lines_given(self):
        result, _ = await _diff(_ok_diff(), tail_lines=2)
        assert result.endswith(f"{SEP}\n{DIFF_LINES[-2]}\n{DIFF_LINES[-1]}\n{SEP}")

    @pytest.mark.asyncio
    async def test_get_pr_diff_returns_explicit_window_when_start_and_end_given(self):
        result, _ = await _diff(_ok_diff(), start_line=5, end_line=6)
        assert result.endswith(f"{SEP}\n{DIFF_LINES[4]}\n{DIFF_LINES[5]}\n{SEP}")

    @pytest.mark.asyncio
    async def test_get_pr_diff_returns_matching_lines_when_grep_given(self):
        result, _ = await _diff(_ok_diff(), grep="B_NEW", ignore_case=True)
        assert "1 match(es) for 'B_NEW' within" in result
        assert result.endswith(f"{SEP}\n12: +b_new\n{SEP}")

    @pytest.mark.asyncio
    async def test_get_pr_diff_keeps_context_lines_when_grep_with_context(self):
        result, _ = await _diff(_ok_diff(), grep="b_new", context_lines=1)
        body = result.split(SEP)[-2]
        assert "-b_old" in body
        assert "-a_old" not in body

    @pytest.mark.asyncio
    async def test_get_pr_diff_reports_no_match_when_grep_matches_nothing(self):
        result, _ = await _diff(_ok_diff(), grep="zzz")
        assert result.split("\n")[-1] == "🔍 No lines matched 'zzz'"
        assert "📋 Diff" not in result

    @pytest.mark.asyncio
    async def test_get_pr_diff_returns_error_when_selectors_conflict(self):
        result, _ = await _diff(_ok_diff(), head_lines=1, tail_lines=1)
        assert result.startswith("❌ ")
        assert "🔀 PR" not in result


# --------------------------------------------------------------------------
# gh_edit_pr
# --------------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path):
    (tmp_path / ".git").mkdir()
    return str(tmp_path)


class TestGhEditPr:
    def test_gh_edit_pr_returns_error_when_repo_path_missing(self, tmp_path):
        missing = str(tmp_path / "nope")
        assert gh_edit_pr(missing, 3) == (
            f"❌ Repository path does not exist: {missing}"
        )

    def test_gh_edit_pr_returns_error_when_path_not_git_repo(self, tmp_path):
        assert gh_edit_pr(str(tmp_path), 3) == (f"❌ Not a git repository: {tmp_path}")

    def test_gh_edit_pr_runs_bare_edit_when_no_options(self, repo):
        with patch(GH_RUN, return_value=("", "", 0)) as run:
            result = gh_edit_pr(repo, 3)
        assert result == "✅ Pull request #3 edited successfully"
        run.assert_called_once_with(["pr", "edit", "3"], repo)

    @pytest.mark.parametrize(
        ("kwargs", "argv"),
        [
            ({"title": "T"}, ["--title", "T"]),
            ({"body": "B"}, ["--body", "B"]),
            ({"base": "dev"}, ["--base", "dev"]),
            ({"add_assignee": ["a", "b"]}, ["--add-assignee", "a,b"]),
            ({"remove_assignee": ["a"]}, ["--remove-assignee", "a"]),
            ({"add_label": ["x", "y"]}, ["--add-label", "x,y"]),
            ({"remove_label": ["x"]}, ["--remove-label", "x"]),
            ({"add_reviewer": ["r1", "r2"]}, ["--add-reviewer", "r1,r2"]),
            ({"remove_reviewer": ["r1"]}, ["--remove-reviewer", "r1"]),
        ],
    )
    def test_gh_edit_pr_adds_one_flag_when_single_option_given(
        self, repo, kwargs, argv
    ):
        with patch(GH_RUN, return_value=("", "", 0)) as run:
            gh_edit_pr(repo, 3, **kwargs)
        run.assert_called_once_with(["pr", "edit", "3", *argv], repo)

    def test_gh_edit_pr_orders_flags_when_all_options_given(self, repo):
        with patch(GH_RUN, return_value=("", "", 0)) as run:
            gh_edit_pr(
                repo,
                12,
                remove_reviewer=["rr"],
                add_reviewer=["ar"],
                remove_label=["rl"],
                add_label=["al"],
                remove_assignee=["ra"],
                add_assignee=["aa"],
                base="dev",
                body="B",
                title="T",
            )
        run.assert_called_once_with(
            [
                "pr",
                "edit",
                "12",
                "--title",
                "T",
                "--body",
                "B",
                "--base",
                "dev",
                "--add-assignee",
                "aa",
                "--remove-assignee",
                "ra",
                "--add-label",
                "al",
                "--remove-label",
                "rl",
                "--add-reviewer",
                "ar",
                "--remove-reviewer",
                "rr",
            ],
            repo,
        )

    def test_gh_edit_pr_skips_flags_when_values_empty(self, repo):
        with patch(GH_RUN, return_value=("", "", 0)) as run:
            gh_edit_pr(
                repo,
                3,
                title="",
                body="",
                base="",
                add_assignee=[],
                remove_assignee=[],
                add_label=[],
                remove_label=[],
                add_reviewer=[],
                remove_reviewer=[],
            )
        run.assert_called_once_with(["pr", "edit", "3"], repo)

    def test_gh_edit_pr_returns_stderr_when_command_fails(self, repo):
        with patch(GH_RUN, return_value=("out", "no such label", 1)):
            result = gh_edit_pr(repo, 3, add_label=["x"])
        assert result == "❌ Failed to edit PR: no such label"

    def test_gh_edit_pr_returns_error_text_when_runner_raises(self, repo):
        with patch(GH_RUN, side_effect=RuntimeError("boom")):
            assert gh_edit_pr(repo, 3) == "❌ Edit PR error: boom"
