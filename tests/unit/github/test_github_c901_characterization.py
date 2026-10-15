"""Characterization tests locking behaviour ahead of the C901 refactor (#267).

Exact return strings and, for write operations, the exact JSON payload sent to
the HTTP client, for the six functions whose complexity is being reduced.
"""

import base64
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_server_git.github.contents import github_get_content
from mcp_server_git.github.permissions import (
    github_get_branch_protection,
    github_update_branch_protection,
)
from mcp_server_git.github.repos import github_create_repo, github_update_repo_settings
from mcp_server_git.github.security import github_get_security_analysis
from mcp_server_git.utils.tool_failure import ToolFailure


def _resp(status: int, data=None, text: str = "") -> AsyncMock:
    response = AsyncMock()
    response.status = status
    response.json = AsyncMock(return_value=data)
    response.text = AsyncMock(return_value=text)
    return response


@contextmanager
def _client(module: str, **methods):
    client = MagicMock()
    for name, value in methods.items():
        if isinstance(value, list):
            setattr(client, name, AsyncMock(side_effect=value))
        else:
            setattr(client, name, AsyncMock(return_value=value))
    with patch(f"mcp_server_git.github.{module}.github_client_context") as ctx:
        ctx.return_value.__aenter__.return_value = client
        yield client


@contextmanager
def _raising(module: str, error: Exception):
    with patch(f"mcp_server_git.github.{module}.github_client_context") as ctx:
        ctx.return_value.__aenter__.side_effect = error
        yield


# ---------------------------------------------------------------- update_repo_settings

ALL_REPO_FIELDS = {
    "description": "d",
    "homepage": "h",
    "private": True,
    "visibility": "private",
    "default_branch": "main",
    "has_issues": False,
    "has_projects": True,
    "has_wiki": False,
    "has_discussions": True,
    "allow_squash_merge": True,
    "allow_merge_commit": False,
    "allow_rebase_merge": True,
    "allow_auto_merge": False,
    "delete_branch_on_merge": True,
    "allow_update_branch": False,
    "squash_merge_commit_title": "PR_TITLE",
    "squash_merge_commit_message": "BLANK",
    "merge_commit_title": "MERGE_MESSAGE",
    "merge_commit_message": "PR_BODY",
    "archived": False,
    "web_commit_signoff_required": True,
}


@pytest.mark.asyncio
async def test_update_repo_settings_sends_all_fields_when_all_provided():
    with _client("repos", patch=_resp(200, {"full_name": "o/r"})) as client:
        result = await github_update_repo_settings("o", "r", **ALL_REPO_FIELDS)

    client.patch.assert_called_once_with("/repos/o/r", json=ALL_REPO_FIELDS)
    assert list(client.patch.call_args.kwargs["json"]) == list(ALL_REPO_FIELDS)
    assert result == (
        "✅ Successfully updated repository settings for o/r\n"
        f"Updated fields: {', '.join(ALL_REPO_FIELDS)}"
    )


@pytest.mark.asyncio
async def test_update_repo_settings_keeps_falsy_values_when_provided():
    with _client("repos", patch=_resp(200, {"full_name": "o/r"})) as client:
        await github_update_repo_settings("o", "r", description="", has_wiki=False)

    client.patch.assert_called_once_with(
        "/repos/o/r", json={"description": "", "has_wiki": False}
    )


@pytest.mark.asyncio
async def test_update_repo_settings_returns_warning_when_nothing_provided():
    with _client("repos", patch=_resp(200)) as client:
        result = await github_update_repo_settings("o", "r")

    assert result == "⚠️ No update parameters provided"
    assert not isinstance(result, ToolFailure)
    client.patch.assert_not_called()


@pytest.mark.asyncio
async def test_update_repo_settings_returns_failure_when_status_not_200():
    with _client("repos", patch=_resp(422, text="bad")):
        result = await github_update_repo_settings("o", "r", archived=True)

    assert result == "❌ Failed to update repository settings: 422 - bad"
    assert isinstance(result, ToolFailure)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ValueError("no token"), "❌ no token"),
        (ConnectionError("down"), "❌ Network connection failed: down"),
        (RuntimeError("boom"), "❌ Error updating repository settings: boom"),
    ],
)
@pytest.mark.asyncio
async def test_update_repo_settings_returns_failure_when_client_raises(error, expected):
    with _raising("repos", error):
        result = await github_update_repo_settings("o", "r", archived=True)

    assert result == expected
    assert isinstance(result, ToolFailure)


# ---------------------------------------------------------------- create_repo

REPO_BODY = {
    "full_name": "my-org/new",
    "html_url": "https://github.com/my-org/new",
    "clone_url": "https://github.com/my-org/new.git",
    "ssh_url": "git@github.com:my-org/new.git",
    "private": True,
}


@pytest.mark.asyncio
async def test_create_repo_returns_full_output_when_org_repo_created():
    with _client("repos", post=_resp(201, REPO_BODY)) as client:
        result = await github_create_repo(
            "new",
            org="my-org",
            description="desc",
            private=True,
            auto_init=True,
            gitignore_template="Python",
            license_template="mit",
            has_issues=False,
            has_projects=False,
            has_wiki=False,
        )

    client.post.assert_called_once_with(
        "/orgs/my-org/repos",
        json={
            "name": "new",
            "private": True,
            "auto_init": True,
            "has_issues": False,
            "has_projects": False,
            "has_wiki": False,
            "description": "desc",
            "gitignore_template": "Python",
            "license_template": "mit",
        },
    )
    assert result == (
        "Successfully created repository: my-org/new\n"
        "\n"
        "URL: https://github.com/my-org/new\n"
        "Clone (HTTPS): https://github.com/my-org/new.git\n"
        "Clone (SSH): git@github.com:my-org/new.git\n"
        "Visibility: Private\n"
        "Initialized with README"
    )


@pytest.mark.asyncio
async def test_create_repo_returns_public_output_when_personal_repo_created():
    body = {**REPO_BODY, "private": False}
    with _client("repos", post=_resp(201, body)):
        result = await github_create_repo("new")

    assert result.endswith("Visibility: Public")
    assert "Initialized" not in result


@pytest.mark.parametrize(
    ("status", "data", "text", "org", "expected"),
    [
        (
            422,
            {"errors": [{"message": "name already exists on this account"}]},
            "",
            None,
            "Error: Repository 'new' already exists",
        ),
        (
            422,
            {"errors": [{"message": "name already exists"}]},
            "",
            "o",
            "Error: Repository 'o/new' already exists",
        ),
        (
            422,
            {"message": "Nope", "errors": [{"message": "other"}]},
            "",
            None,
            "Validation error: Nope",
        ),
        (422, {}, "", None, "Validation error: Unknown error"),
        (
            403,
            None,
            "",
            None,
            "Error: Permission denied. Check your token has 'repo' scope.",
        ),
        (
            404,
            None,
            "",
            "o",
            "Error: Organization 'o' not found or you don't have access.",
        ),
        (404, None, "gone", None, "Error: Not found - gone"),
        (500, None, "oops", None, "Error: Failed to create repository: 500 - oops"),
    ],
)
@pytest.mark.asyncio
async def test_create_repo_returns_error_string_when_status_not_201(
    status, data, text, org, expected
):
    with _client("repos", post=_resp(status, data, text)):
        result = await github_create_repo("new", org=org)

    assert result == expected
    assert not isinstance(result, ToolFailure)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ValueError("no token"), "Error: no token"),
        (ConnectionError("down"), "Error: Network connection failed: down"),
        (RuntimeError("boom"), "Error: Failed to create repository: boom"),
    ],
)
@pytest.mark.asyncio
async def test_create_repo_returns_error_string_when_client_raises(error, expected):
    with _raising("repos", error):
        result = await github_create_repo("new")

    assert result == expected


# ------------------------------------------------------- update_branch_protection

BP_URL = "/repos/o/r/branches/main/protection"
BP_OK = "✅ Successfully updated branch protection for o/r:main"


@pytest.mark.asyncio
async def test_update_branch_protection_sends_defaults_when_nothing_provided():
    with _client("permissions", put=_resp(200)) as client:
        result = await github_update_branch_protection("o", "r", "main")

    client.put.assert_called_once_with(
        BP_URL,
        json={
            "required_status_checks": None,
            "required_pull_request_reviews": None,
            "enforce_admins": False,
            "restrictions": None,
        },
    )
    assert result == BP_OK


@pytest.mark.asyncio
async def test_update_branch_protection_sends_every_rule_when_all_provided():
    with _client("permissions", put=_resp(201)) as client:
        result = await github_update_branch_protection(
            "o",
            "r",
            "main",
            required_status_checks_strict=True,
            required_status_checks_contexts=["ci"],
            require_pull_request_reviews=True,
            dismiss_stale_reviews=True,
            require_code_owner_reviews=False,
            required_approving_review_count=0,
            require_last_push_approval=True,
            enforce_admins=True,
            restrict_pushes=True,
            push_allowances_users=["u"],
            push_allowances_teams=["t"],
            required_linear_history=True,
            allow_force_pushes=False,
            allow_deletions=False,
            block_creations=True,
            required_conversation_resolution=True,
            lock_branch=False,
            allow_fork_syncing=True,
        )

    expected = {
        "required_status_checks": {"strict": True, "contexts": ["ci"]},
        "required_pull_request_reviews": {
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": False,
            "required_approving_review_count": 0,
            "require_last_push_approval": True,
        },
        "enforce_admins": True,
        "restrictions": {"users": ["u"], "teams": ["t"]},
        "required_linear_history": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "block_creations": True,
        "required_conversation_resolution": True,
        "lock_branch": False,
        "allow_fork_syncing": True,
    }
    client.put.assert_called_once_with(BP_URL, json=expected)
    assert list(client.put.call_args.kwargs["json"]) == list(expected)
    assert result == BP_OK


@pytest.mark.asyncio
async def test_update_branch_protection_defaults_status_checks_when_only_contexts():
    with _client("permissions", put=_resp(200)) as client:
        await github_update_branch_protection(
            "o", "r", "main", required_status_checks_strict=False
        )

    sent = client.put.call_args.kwargs["json"]
    assert sent["required_status_checks"] == {"strict": False, "contexts": []}


@pytest.mark.asyncio
async def test_update_branch_protection_sends_null_reviews_when_required_but_empty():
    with _client("permissions", put=_resp(200)) as client:
        await github_update_branch_protection(
            "o", "r", "main", require_pull_request_reviews=True
        )

    assert client.put.call_args.kwargs["json"]["required_pull_request_reviews"] is None


@pytest.mark.asyncio
async def test_update_branch_protection_ignores_review_details_when_not_required():
    with _client("permissions", put=_resp(200)) as client:
        await github_update_branch_protection(
            "o", "r", "main", dismiss_stale_reviews=True, push_allowances_users=["u"]
        )

    sent = client.put.call_args.kwargs["json"]
    assert sent["required_pull_request_reviews"] is None
    assert sent["restrictions"] is None


@pytest.mark.asyncio
async def test_update_branch_protection_sends_empty_lists_when_restricted_without_lists():
    with _client("permissions", put=_resp(200)) as client:
        await github_update_branch_protection("o", "r", "main", restrict_pushes=True)

    assert client.put.call_args.kwargs["json"]["restrictions"] == {
        "users": [],
        "teams": [],
    }


@pytest.mark.asyncio
async def test_update_branch_protection_returns_failure_when_status_not_200_or_201():
    with _client("permissions", put=_resp(422, text="bad")):
        result = await github_update_branch_protection("o", "r", "main")

    assert result == "❌ Failed to update branch protection: 422 - bad"
    assert isinstance(result, ToolFailure)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ValueError("no token"), "❌ no token"),
        (ConnectionError("down"), "❌ Network connection failed: down"),
        (RuntimeError("boom"), "❌ Error updating branch protection: boom"),
    ],
)
@pytest.mark.asyncio
async def test_update_branch_protection_returns_failure_when_client_raises(
    error, expected
):
    with _raising("permissions", error):
        result = await github_update_branch_protection("o", "r", "main")

    assert result == expected
    assert isinstance(result, ToolFailure)


# ---------------------------------------------------------- get_branch_protection

FULL_PROTECTION = {
    "required_status_checks": {"strict": True, "contexts": ["a", "b"]},
    "required_pull_request_reviews": {
        "dismiss_stale_reviews": True,
        "require_code_owner_reviews": False,
        "required_approving_review_count": 2,
        "require_last_push_approval": True,
    },
    "enforce_admins": {"enabled": True},
    "restrictions": {"users": [{"login": "u1"}], "teams": [{"slug": "t1"}]},
    "required_linear_history": {"enabled": True},
    "allow_force_pushes": {"enabled": False},
    "allow_deletions": {"enabled": True},
    "required_conversation_resolution": {"enabled": False},
    "lock_branch": {"enabled": True},
}


@pytest.mark.asyncio
async def test_get_branch_protection_returns_exact_report_when_fully_configured():
    with _client("permissions", get=_resp(200, FULL_PROTECTION)) as client:
        result = await github_get_branch_protection("o", "r", "main")

    client.get.assert_called_once_with(BP_URL)
    assert result == (
        "Branch Protection for o/r:main\n"
        "\n"
        "✅ Required Status Checks:\n"
        "   Strict: ✅\n"
        "   Contexts: a, b\n"
        "\n"
        "✅ Required Pull Request Reviews:\n"
        "   Dismiss Stale Reviews: ✅\n"
        "   Require Code Owner Reviews: ❌\n"
        "   Required Approving Review Count: 2\n"
        "   Require Last Push Approval: ✅\n"
        "\n"
        "👮 Enforce Admins: ✅\n"
        "\n"
        "🔒 Push Restrictions: Enabled\n"
        "   Users: u1\n"
        "   Teams: t1\n"
        "\n"
        "📋 Other Settings:\n"
        "   Required Linear History: ✅\n"
        "   Allow Force Pushes: ❌\n"
        "   Allow Deletions: ✅\n"
        "   Required Conversation Resolution: ❌\n"
        "   Lock Branch: ✅"
    )


@pytest.mark.asyncio
async def test_get_branch_protection_returns_exact_report_when_nothing_configured():
    with _client("permissions", get=_resp(200, {})):
        result = await github_get_branch_protection("o", "r", "dev")

    assert result == (
        "Branch Protection for o/r:dev\n"
        "\n"
        "❌ Required Status Checks: Not configured\n"
        "\n"
        "❌ Required Pull Request Reviews: Not configured\n"
        "\n"
        "🔓 Push Restrictions: Not configured\n"
        "\n"
        "📋 Other Settings:\n"
        "   Required Linear History: ❌\n"
        "   Allow Force Pushes: ❌\n"
        "   Allow Deletions: ❌\n"
        "   Required Conversation Resolution: ❌\n"
        "   Lock Branch: ❌"
    )


@pytest.mark.asyncio
async def test_get_branch_protection_shows_none_contexts_when_checks_have_no_contexts():
    data = {"required_status_checks": {"strict": False, "contexts": []}}
    with _client("permissions", get=_resp(200, data)):
        result = await github_get_branch_protection("o", "r", "main")

    assert "✅ Required Status Checks:\n   Strict: ❌\n   Contexts: (none)\n" in result


@pytest.mark.asyncio
async def test_get_branch_protection_omits_user_and_team_lines_when_restrictions_empty():
    data = {"restrictions": {"users": [], "teams": []}, "enforce_admins": {}}
    with _client("permissions", get=_resp(200, data)):
        result = await github_get_branch_protection("o", "r", "main")

    assert "\n🔒 Push Restrictions: Enabled\n\n📋 Other Settings:" in result
    assert "\n👮 Enforce Admins" not in result


@pytest.mark.asyncio
async def test_get_branch_protection_defaults_review_count_to_zero_when_absent():
    data = {"required_pull_request_reviews": {"dismiss_stale_reviews": True}}
    with _client("permissions", get=_resp(200, data)):
        result = await github_get_branch_protection("o", "r", "main")

    assert "   Required Approving Review Count: 0\n" in result


@pytest.mark.asyncio
async def test_get_branch_protection_returns_failure_when_status_404():
    with _client("permissions", get=_resp(404)):
        result = await github_get_branch_protection("o", "r", "x")

    assert result == (
        "❌ Branch protection not found for x. "
        "The branch may not exist or have no protection rules."
    )
    assert isinstance(result, ToolFailure)


@pytest.mark.asyncio
async def test_get_branch_protection_returns_failure_when_status_unexpected():
    with _client("permissions", get=_resp(500, text="oops")):
        result = await github_get_branch_protection("o", "r", "main")

    assert result == "❌ Failed to get branch protection: 500 - oops"
    assert isinstance(result, ToolFailure)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ValueError("no token"), "❌ no token"),
        (ConnectionError("down"), "❌ Network connection failed: down"),
        (RuntimeError("boom"), "❌ Error getting branch protection: boom"),
    ],
)
@pytest.mark.asyncio
async def test_get_branch_protection_returns_failure_when_client_raises(
    error, expected
):
    with _raising("permissions", error):
        result = await github_get_branch_protection("o", "r", "main")

    assert result == expected
    assert isinstance(result, ToolFailure)


# ------------------------------------------------------------ get_security_analysis

SA_HEAD = "Security Analysis for o/r:\n"
SA_LINK = "\n🔗 Security Settings: https://github.com/o/r/settings/security_analysis"
REPO_SECURITY = {
    "visibility": "public",
    "private": False,
    "archived": True,
    "security_and_analysis": {
        "secret_scanning": {"status": "enabled"},
        "secret_scanning_push_protection": {"status": "disabled"},
    },
}


@pytest.mark.asyncio
async def test_get_security_analysis_returns_exact_report_when_all_checks_succeed():
    responses = [
        _resp(204),
        _resp(200, {"enabled": True, "paused": True}),
        _resp(200, REPO_SECURITY),
    ]
    with _client("security", get=responses) as client:
        result = await github_get_security_analysis("o", "r")

    assert [c.args[0] for c in client.get.call_args_list] == [
        "/repos/o/r/vulnerability-alerts",
        "/repos/o/r/automated-security-fixes",
        "/repos/o/r",
    ]
    assert result == (
        f"{SA_HEAD}\n"
        "✅ Vulnerability Alerts (Dependabot): ENABLED\n"
        "✅ Automated Security Fixes: ENABLED (PAUSED)\n"
        "\n"
        "📋 Repository Security Settings:\n"
        "   Visibility: public\n"
        "   Private: ❌\n"
        "   Archived: ✅\n"
        "\n"
        "🔐 Security & Analysis Features:\n"
        "   ✅ Secret Scanning: ENABLED\n"
        "   ❌ Secret Scanning Push Protection: DISABLED\n"
        "   ❌ Dependabot Security Updates: DISABLED"
        f"\n{SA_LINK}"
    )


@pytest.mark.asyncio
async def test_get_security_analysis_reports_disabled_when_statuses_negative():
    responses = [_resp(404), _resp(404), _resp(200, {})]
    with _client("security", get=responses):
        result = await github_get_security_analysis("o", "r")

    assert result == (
        f"{SA_HEAD}\n"
        "❌ Vulnerability Alerts (Dependabot): DISABLED\n"
        "❌ Automated Security Fixes: DISABLED or unavailable\n"
        "\n"
        "📋 Repository Security Settings:\n"
        "   Visibility: unknown\n"
        "   Private: ❌\n"
        "   Archived: ❌"
        f"\n{SA_LINK}"
    )


@pytest.mark.asyncio
async def test_get_security_analysis_reports_unable_when_statuses_unexpected():
    responses = [_resp(500), _resp(200, {}), _resp(503)]
    with _client("security", get=responses):
        result = await github_get_security_analysis("o", "r")

    assert result == (
        f"{SA_HEAD}\n"
        "⚠️ Vulnerability Alerts: Unable to determine (HTTP 500)\n"
        "❌ Automated Security Fixes: DISABLED\n"
        "\n"
        "⚠️ Repository Settings: Unable to fetch (HTTP 503)"
        f"\n{SA_LINK}"
    )


@pytest.mark.asyncio
async def test_get_security_analysis_adds_failure_note_when_checks_raise():
    responses = [RuntimeError("a"), RuntimeError("b"), _resp(200, {"private": True})]
    with _client("security", get=responses):
        result = await github_get_security_analysis("o", "r")

    assert result == (
        f"{SA_HEAD}\n"
        "⚠️ Vulnerability Alerts: Check failed (a)\n"
        "⚠️ Automated Security Fixes: Check failed (b)\n"
        "\n"
        "📋 Repository Security Settings:\n"
        "   Visibility: unknown\n"
        "   Private: ✅\n"
        "   Archived: ❌\n"
        "\n"
        "⚠️ Note: 2 of 3 checks failed"
        f"\n{SA_LINK}"
    )


@pytest.mark.asyncio
async def test_get_security_analysis_reports_repo_check_failed_when_repo_call_raises():
    responses = [_resp(204), _resp(404), RuntimeError("c")]
    with _client("security", get=responses):
        result = await github_get_security_analysis("o", "r")

    assert "\n⚠️ Repository Settings: Check failed (c)\n" in result
    assert "\n⚠️ Note: 1 of 3 checks failed\n" in result


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ValueError("no token"), "❌ no token"),
        (ConnectionError("down"), "❌ Network connection failed: down"),
        (RuntimeError("boom"), "❌ Error getting security analysis: boom"),
    ],
)
@pytest.mark.asyncio
async def test_get_security_analysis_returns_failure_when_client_raises(
    error, expected
):
    with _raising("security", error):
        result = await github_get_security_analysis("o", "r")

    assert result == expected
    assert isinstance(result, ToolFailure)


# ------------------------------------------------------------------ get_content


def _file(content: str, **extra) -> dict:
    return {
        "type": "file",
        "encoding": "base64",
        "content": base64.b64encode(content.encode()).decode(),
        "sha": "s1",
        "size": 5,
        **extra,
    }


@pytest.mark.asyncio
async def test_get_content_returns_header_and_text_when_file_found_at_ref():
    with _client("contents", get=_resp(200, _file("hello"))) as client:
        result = await github_get_content("o", "r", "/a/b.py", ref="dev")

    client.get.assert_called_once_with("/repos/o/r/contents/a/b.py?ref=dev")
    assert result == "Content of o/r//a/b.py @ dev\nsha: s1 | size: 5 bytes\n\nhello"


@pytest.mark.asyncio
async def test_get_content_omits_ref_when_ref_not_given():
    with _client("contents", get=_resp(200, _file("hi"))) as client:
        result = await github_get_content("o", "r", "a.py")

    client.get.assert_called_once_with("/repos/o/r/contents/a.py")
    assert result == "Content of o/r/a.py\nsha: s1 | size: 5 bytes\n\nhi"


@pytest.mark.asyncio
async def test_get_content_lists_entries_when_path_is_directory():
    entries = [{"type": "dir", "name": "d"}, {"type": "file", "name": "f", "size": 3}]
    with _client("contents", get=_resp(200, entries)):
        result = await github_get_content("o", "r", "src", ref="v1")

    assert result == (
        "Directory listing for o/r/src @ v1 (2 entries):\n"
        "\n"
        "  [dir] d (0 bytes)\n"
        "  [file] f (3 bytes)"
    )


@pytest.mark.asyncio
async def test_get_content_lists_header_only_when_directory_empty_without_ref():
    with _client("contents", get=_resp(200, [])):
        result = await github_get_content("o", "r", "src")

    assert result == "Directory listing for o/r/src (0 entries):\n"


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        (None, "❌ Path 'p' not found in o/r"),
        ("dev", "❌ Path 'p' not found in o/r at ref 'dev'"),
    ],
)
@pytest.mark.asyncio
async def test_get_content_returns_failure_when_status_404(ref, expected):
    with _client("contents", get=_resp(404)):
        result = await github_get_content("o", "r", "p", ref=ref)

    assert result == expected
    assert isinstance(result, ToolFailure)


@pytest.mark.asyncio
async def test_get_content_returns_failure_when_status_unexpected():
    with _client("contents", get=_resp(500, text="oops")):
        result = await github_get_content("o", "r", "p")

    assert result == "❌ Failed to get content: 500 - oops"
    assert isinstance(result, ToolFailure)


@pytest.mark.asyncio
async def test_get_content_returns_failure_when_entry_is_not_a_file():
    with _client("contents", get=_resp(200, {"type": "symlink", "sha": "s9"})):
        result = await github_get_content("o", "r", "p")

    assert result == "❌ Path 'p' is a symlink, not a file (sha: s9)"
    assert isinstance(result, ToolFailure)


@pytest.mark.parametrize(
    "data",
    [
        {"type": "file", "encoding": "none", "content": "", "sha": "s2", "size": 9},
        {"type": "file", "encoding": "utf-8", "content": "", "sha": "s2", "size": 9},
    ],
)
@pytest.mark.asyncio
async def test_get_content_returns_failure_when_file_too_large(data):
    with _client("contents", get=_resp(200, data)):
        result = await github_get_content("o", "r", "big.bin")

    assert result == (
        "❌ File 'big.bin' is too large for the contents API (9 bytes). "
        "Use the Git blobs API or a raw download. (sha: s2)"
    )
    assert isinstance(result, ToolFailure)


@pytest.mark.asyncio
async def test_get_content_returns_raw_when_encoding_unexpected_but_content_present():
    data = {"type": "file", "encoding": "utf-8", "content": "raw!", "sha": "s3"}
    with _client("contents", get=_resp(200, data)):
        result = await github_get_content("o", "r", "p")

    assert result == "Content of o/r/p\nsha: s3 | size: 0 bytes\n\nraw!"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ValueError("no token"), "❌ no token"),
        (ConnectionError("down"), "❌ Network connection failed: down"),
        (RuntimeError("boom"), "❌ Error getting content: boom"),
    ],
)
@pytest.mark.asyncio
async def test_get_content_returns_failure_when_client_raises(error, expected):
    with _raising("contents", error):
        result = await github_get_content("o", "r", "p")

    assert result == expected
    assert isinstance(result, ToolFailure)
