"""
Regression test: ResponseOffloader uses configured token limits, not the
MCPTokenLimiter hard-wired 2000-token default.

Bug: GitLeanInterface.__init__ built MCPTokenLimiter() with default_limit=2000
even when MCP_GIT_UNKNOWN_TOKEN_LIMIT was set to a larger value via env var.
"""

import pytest

import mcp_server_git.config.token_limits as _token_limits_mod
from mcp_server_git.config.token_limits import TokenLimitProfile
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

        iface = GitLeanInterface(
            git_service=None, github_service=None, azure_service=None
        )
        assert iface.token_limiter.default_limit == _CONFIGURED_LIMIT, (
            f"Expected default_limit={_CONFIGURED_LIMIT}, "
            f"got {iface.token_limiter.default_limit} (hard-wired 2000 bug still present)"
        )


# ---------------------------------------------------------------------------
# Regression: unknown_token_limit default must be below the client output cap
# ---------------------------------------------------------------------------

# The old default (25 000 tokens ≈ 88 KB at 3.5 ch/tok) sat above the Claude
# Code client MAX_MCP_OUTPUT_TOKENS cap (~60 KB for git-hash-heavy text).
# Outputs in the 60-88 KB range were returned inline and silently truncated by
# the client.  The new default (12 000 tokens ≈ 42 KB) ensures the server
# offloader triggers first.
_OLD_OFFLOADER_DEFAULT = 25_000
_NEW_OFFLOADER_DEFAULT = 12_000
_CHARS_PER_TOKEN_ESTIMATE = 3.5
_CLIENT_CAP_APPROX_TOKENS = int(60 * 1024 / _CHARS_PER_TOKEN_ESTIMATE)


class TestOffloaderDefaultBelowClientCap:
    """Guard the 25000→12000 reduction in unknown_token_limit."""

    def test_unknown_token_limit_default_is_12000(self) -> None:
        """TokenLimitSettings.unknown_token_limit default must be 12000.

        Regression guard: do not restore 25000 — that value sits above the
        client MAX_MCP_OUTPUT_TOKENS (~60 KB) and causes silent truncation.
        """
        settings = _token_limits_mod.TokenLimitSettings()
        assert settings.unknown_token_limit == _NEW_OFFLOADER_DEFAULT, (
            f"unknown_token_limit default regressed: expected {_NEW_OFFLOADER_DEFAULT}, "
            f"got {settings.unknown_token_limit}.  The old value ({_OLD_OFFLOADER_DEFAULT}) "
            f"exceeds the client cap and must not be restored."
        )

    def test_unknown_token_limit_default_is_below_client_cap(self) -> None:
        """Default unknown_token_limit must be strictly below the client output cap."""
        settings = _token_limits_mod.TokenLimitSettings()
        assert settings.unknown_token_limit < _CLIENT_CAP_APPROX_TOKENS, (
            f"unknown_token_limit ({settings.unknown_token_limit}) must be below the "
            f"approximate client cap ({_CLIENT_CAP_APPROX_TOKENS} tokens ≈ 60 KB) so the "
            f"server offloader spills before the client truncates."
        )

    def test_env_override_raises_limit_above_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """MCP_GIT_UNKNOWN_TOKEN_LIMIT env var must still override the default upward."""
        monkeypatch.setenv("MCP_GIT_UNKNOWN_TOKEN_LIMIT", "30000")
        manager = _token_limits_mod.TokenLimitConfigManager()
        settings = manager.load_configuration()
        assert settings.unknown_token_limit == 30_000

    def test_limiter_at_new_default_truncates_50kb_output(self) -> None:
        """A ~50 KB payload must be truncated by a limiter at the new 12 000-token default.

        50 KB / 3.5 ch per token ≈ 14 629 tokens — above 12 000, so the server
        offloader must trigger before the ~60 KB client cap is reached.
        """
        # ~50 KB dict value — representative of a large git log / diff output
        fifty_kb_chars = int(50 * 1024)
        large_payload = {"output": "a" * fifty_kb_chars}

        limiter = MCPTokenLimiter(default_limit=_NEW_OFFLOADER_DEFAULT)
        assert limiter.would_truncate(large_payload, "git_log"), (
            f"A ~50 KB payload (~{fifty_kb_chars // int(_CHARS_PER_TOKEN_ESTIMATE)} tokens) "
            f"must exceed the new {_NEW_OFFLOADER_DEFAULT}-token default so the offloader "
            f"triggers before the client cap."
        )

    def test_limiter_at_old_default_passes_50kb_output(self) -> None:
        """Regression anchor: the old 25 000-token default did NOT truncate ~50 KB output.

        This confirms the old default was the root cause of client-side truncation.
        """
        fifty_kb_chars = int(50 * 1024)
        large_payload = {"output": "a" * fifty_kb_chars}

        old_limiter = MCPTokenLimiter(default_limit=_OLD_OFFLOADER_DEFAULT)
        assert not old_limiter.would_truncate(large_payload, "git_log"), (
            "Sanity-check failed: old 25 000-token limiter should NOT truncate a "
            "~50 KB payload, confirming the regression was real."
        )


# ---------------------------------------------------------------------------
# Profile coverage: safe profiles must stay below the client output cap
# ---------------------------------------------------------------------------


class TestProfilesBelowClientCap:
    """Guard that CONSERVATIVE and BALANCED profiles stay below the client cap."""

    def test_conservative_unknown_token_limit_is_below_default_and_client_cap(
        self,
    ) -> None:
        """CONSERVATIVE profile unknown_token_limit must be below the new default (12000)
        and strictly below the client cap — a 'conservative' profile must be the most
        restrictive of the safe profiles.
        """
        settings = _token_limits_mod.TokenLimitSettings.from_profile(
            TokenLimitProfile.CONSERVATIVE
        )
        assert settings.unknown_token_limit <= _NEW_OFFLOADER_DEFAULT, (
            f"CONSERVATIVE unknown_token_limit ({settings.unknown_token_limit}) must be "
            f"<= the new default ({_NEW_OFFLOADER_DEFAULT})."
        )
        assert settings.unknown_token_limit < _CLIENT_CAP_APPROX_TOKENS, (
            f"CONSERVATIVE unknown_token_limit ({settings.unknown_token_limit}) must be "
            f"< client cap ({_CLIENT_CAP_APPROX_TOKENS} tokens ≈ 60 KB)."
        )

    def test_balanced_unknown_token_limit_equals_new_default_and_is_below_client_cap(
        self,
    ) -> None:
        """BALANCED profile unknown_token_limit must equal 12000 and be below the client cap."""
        settings = _token_limits_mod.TokenLimitSettings.from_profile(
            TokenLimitProfile.BALANCED
        )
        assert settings.unknown_token_limit == _NEW_OFFLOADER_DEFAULT, (
            f"BALANCED unknown_token_limit ({settings.unknown_token_limit}) must equal "
            f"{_NEW_OFFLOADER_DEFAULT}."
        )
        assert settings.unknown_token_limit < _CLIENT_CAP_APPROX_TOKENS, (
            f"BALANCED unknown_token_limit ({settings.unknown_token_limit}) must be "
            f"< client cap ({_CLIENT_CAP_APPROX_TOKENS} tokens ≈ 60 KB)."
        )
