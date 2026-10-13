"""Explicit-null tolerance for the GitHub ops outside the refactored modules (#273).

GitHub sends ``null`` for absent objects; ``x.get("k", {})`` only guards a
missing key. Each test feeds one null where the code used to dereference it.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_server_git.github._payload import login_of, obj_of
from mcp_server_git.github.api import github_resolve_ref
from mcp_server_git.github.permissions import github_get_branch_protection
from mcp_server_git.github.pr import github_list_pull_requests
from mcp_server_git.github.security import github_get_security_analysis


def _client(payload) -> MagicMock:
    response = AsyncMock()
    response.status = 200
    response.json = AsyncMock(return_value=payload)
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    return client


async def _run(module: str, payload, call):
    with patch(f"mcp_server_git.github.{module}.github_client_context") as ctx:
        ctx.return_value.__aenter__.return_value = _client(payload)
        return await call()


class TestPayloadHelpers:
    def test_login_of_returns_na_when_object_is_null(self):
        assert login_of({"user": None}) == "N/A"

    def test_login_of_returns_default_when_key_missing(self):
        assert login_of({}, "actor", "unknown") == "unknown"

    def test_login_of_returns_login_when_present(self):
        assert login_of({"user": {"login": "bob"}}) == "bob"

    def test_obj_of_returns_empty_dict_when_value_is_null(self):
        assert obj_of({"head": None}, "head") == {}


class TestListPullRequestsNulls:
    @pytest.mark.asyncio
    async def test_list_prs_shows_na_when_user_base_and_head_are_null(self):
        pr = {"number": 1, "title": "T", "user": None, "base": None, "head": None}
        result = await _run(
            "pr", [pr], lambda: github_list_pull_requests("o", "r", state="open")
        )
        lines = result.split("\n")
        assert "   Author: N/A" in lines
        assert "   Base: N/A ← Head: N/A" in lines


class TestResolveRefNulls:
    @pytest.mark.asyncio
    async def test_resolve_ref_omits_author_when_commit_is_null(self):
        result = await _run(
            "contents",
            {"sha": "a" * 40, "commit": None},
            lambda: github_resolve_ref("o", "r", "main"),
        )
        assert result == f"Ref 'main' in o/r:\n🔑 Commit SHA: {'a' * 40}"

    @pytest.mark.asyncio
    async def test_resolve_ref_omits_author_when_commit_author_is_null(self):
        payload = {"sha": "b" * 40, "commit": {"author": None, "message": "m"}}
        result = await _run(
            "contents", payload, lambda: github_resolve_ref("o", "r", "main")
        )
        assert result.endswith("📝 Message: m")
        assert "👤" not in result


class TestBranchProtectionNulls:
    @pytest.mark.asyncio
    async def test_branch_protection_marks_disabled_when_setting_is_null(self):
        payload = {
            "required_linear_history": None,
            "allow_force_pushes": None,
            "allow_deletions": None,
            "required_conversation_resolution": None,
            "lock_branch": None,
        }
        result = await _run(
            "permissions",
            payload,
            lambda: github_get_branch_protection("o", "r", "main"),
        )
        lines = result.split("\n")
        assert "   Required Linear History: ❌" in lines
        assert "   Lock Branch: ❌" in lines


class TestSecurityAnalysisNulls:
    @pytest.mark.asyncio
    async def test_security_analysis_reports_disabled_when_feature_blocks_are_null(
        self,
    ):
        repo = {
            "visibility": "public",
            "security_and_analysis": {
                "secret_scanning": None,
                "secret_scanning_push_protection": None,
                "dependabot_security_updates": None,
            },
        }
        result = await _run(
            "security", repo, lambda: github_get_security_analysis("o", "r")
        )
        assert "❌ Secret Scanning: DISABLED" in result
        assert "❌ Secret Scanning Push Protection: DISABLED" in result
        assert "❌ Dependabot Security Updates: DISABLED" in result
        assert "Check failed" not in result
