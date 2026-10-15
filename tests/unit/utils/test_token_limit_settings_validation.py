"""Characterization tests for TokenLimitSettings.__post_init__ (issue #255)."""

import logging

import pytest

from mcp_server_git.config.token_limits import TokenLimitSettings

_LOGGER = "mcp_server_git.config.token_limits"


def test_post_init_keeps_defaults_when_no_overrides(caplog):
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        settings = TokenLimitSettings()
    assert settings.llm_token_limit == 20000
    assert settings.human_token_limit == 0
    assert settings.unknown_token_limit == 12000
    assert settings.max_processing_time_ms == 100
    assert settings.operation_limits == {}
    assert caplog.records == []


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"llm_token_limit": -1}, "LLM token limit must be non-negative"),
        ({"human_token_limit": -1}, "Human token limit must be non-negative"),
        (
            {"unknown_token_limit": -1},
            "Unknown client token limit must be non-negative",
        ),
        ({"max_processing_time_ms": -1}, "Max processing time must be non-negative"),
        (
            {"operation_limits": {"git_log": -5}},
            "Operation limit for 'git_log' must be non-negative",
        ),
    ],
)
def test_post_init_raises_value_error_when_value_negative(kwargs, message):
    with pytest.raises(ValueError) as exc:
        TokenLimitSettings(**kwargs)
    assert str(exc.value) == message


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"llm_token_limit": 1000001}, "Very large LLM token limit: 1000001"),
        ({"human_token_limit": 1000001}, "Very large human token limit: 1000001"),
        (
            {"unknown_token_limit": 1000001},
            "Very large unknown client token limit: 1000001",
        ),
        (
            {"max_processing_time_ms": 10001},
            "Very large max processing time: 10001ms",
        ),
        (
            {"operation_limits": {"git_log": 1000001}},
            "Very large operation limit for 'git_log': 1000001",
        ),
    ],
)
def test_post_init_warns_when_value_exceeds_upper_bound(kwargs, message, caplog):
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        TokenLimitSettings(**kwargs)
    assert [r.getMessage() for r in caplog.records] == [message]


def test_post_init_does_not_warn_when_values_exactly_at_upper_bound(caplog):
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        TokenLimitSettings(
            llm_token_limit=1000000,
            human_token_limit=1000000,
            unknown_token_limit=1000000,
            max_processing_time_ms=10000,
            operation_limits={"x": 1000000},
        )
    assert caplog.records == []


def test_post_init_accepts_zero_values_when_unlimited():
    settings = TokenLimitSettings(
        llm_token_limit=0,
        human_token_limit=0,
        unknown_token_limit=0,
        max_processing_time_ms=0,
        operation_limits={"x": 0},
    )
    assert settings.operation_limits == {"x": 0}


def test_post_init_warns_before_raising_when_earlier_limit_large_and_later_negative(
    caplog,
):
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        with pytest.raises(ValueError, match="Unknown client token limit"):
            TokenLimitSettings(llm_token_limit=2000000, unknown_token_limit=-1)
    assert [r.getMessage() for r in caplog.records] == [
        "Very large LLM token limit: 2000000"
    ]


def test_post_init_raises_first_error_when_multiple_limits_negative():
    with pytest.raises(ValueError, match="LLM token limit"):
        TokenLimitSettings(llm_token_limit=-1, human_token_limit=-1)
