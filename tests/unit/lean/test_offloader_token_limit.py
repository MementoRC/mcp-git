"""
Regression test: ResponseOffloader uses configured token limits, not the
MCPTokenLimiter hard-wired 2000-token default.

Bug: GitLeanInterface.__init__ built MCPTokenLimiter() with default_limit=2000
even when MCP_GIT_UNKNOWN_TOKEN_LIMIT was set to a larger value via env var.
"""

import pytest

import mcp_server_git.config.token_limits as _token_limits_mod
from mcp_server_git.lean.token_limiter import MCPTokenLimiter

# A payload length that sits between the old 2000-token default and the
# configured 20000-token limit.  The token estimator uses a ~4 chars/token
# ratio, so 12000 chars ≈ 3000 tokens — above 2000 but far below 20000.
_PAYLOAD_CHARS = 12_000
_CONFIGURED_LIMIT = 20_000


@pytest.fixture(autouse=True)
def _reset_config_manager():
    """Reset the global config_manager singleton before and after each test."""
    _token_limits_mod.config_manager._settings = None
    yield
    _token_limits_mod.config_manager._settings = None


class TestOffloaderUsesConfiguredLimit:
    def test_default_limiter_respects_unknown_token_limit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """GitLeanInterface's default token_limiter must use the env-configured
        unknown_token_limit, not the MCPTokenLimiter hard-wired 2000 default.

        A mid-sized payload (~3000 tokens) should NOT trigger would_truncate
        when MCP_GIT_UNKNOWN_TOKEN_LIMIT=20000 is set.
        """
        monkeypatch.setenv("MCP_GIT_UNKNOWN_TOKEN_LIMIT", str(_CONFIGURED_LIMIT))

        # Force config_manager to re-read env (reset already done by fixture)
        settings = _token_limits_mod.config_manager.get_current_settings()
        assert settings.unknown_token_limit == _CONFIGURED_LIMIT

        limiter = MCPTokenLimiter(
            default_limit=settings.unknown_token_limit,
            operation_limits=settings.operation_limits,
        )
        mid_payload = {"result": "x" * _PAYLOAD_CHARS}
        assert not limiter.would_truncate(mid_payload, "git_diff"), (
            "A mid-sized payload should NOT be truncated when limit is "
            f"{_CONFIGURED_LIMIT} tokens (old bug: limit was hard-wired to 2000)"
        )

    def test_old_default_2000_would_have_truncated_same_payload(self) -> None:
        """Sanity-check: the same mid-sized payload *does* exceed 2000 tokens,
        confirming that the original bare MCPTokenLimiter() would have triggered
        offloading unnecessarily.
        """
        old_limiter = MCPTokenLimiter(default_limit=2000)
        mid_payload = {"result": "x" * _PAYLOAD_CHARS}
        assert old_limiter.would_truncate(mid_payload, "git_diff"), (
            "Sanity check failed: mid-sized payload should exceed the old 2000-token default"
        )

    def test_git_lean_interface_token_limiter_uses_configured_limit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """End-to-end: GitLeanInterface built without an explicit token_limiter
        must derive its default_limit from MCP_GIT_UNKNOWN_TOKEN_LIMIT, not 2000.
        """
        monkeypatch.setenv("MCP_GIT_UNKNOWN_TOKEN_LIMIT", str(_CONFIGURED_LIMIT))

        # Re-load settings so the env var is picked up
        settings = _token_limits_mod.config_manager.get_current_settings()
        assert settings.unknown_token_limit == _CONFIGURED_LIMIT

        from mcp_server_git.lean.interface import GitLeanInterface

        iface = GitLeanInterface(git_service=None, github_service=None, azure_service=None)
        assert iface.token_limiter.default_limit == _CONFIGURED_LIMIT, (
            f"Expected default_limit={_CONFIGURED_LIMIT}, "
            f"got {iface.token_limiter.default_limit} (hard-wired 2000 bug still present)"
        )
