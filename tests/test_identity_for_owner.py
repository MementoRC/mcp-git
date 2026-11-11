"""Owner-level identity resolution for GitHub Projects (#345, #347)."""

import pytest

from mcp_server_git.identity import (
    IdentityError,
    current_identity,
    identity_for_owner,
    identity_scope,
)

TOKEN_A = "ghp_" + "a" * 36
TOKEN_B = "ghp_" + "b" * 36


def _config(tmp_path, monkeypatch, entries: dict[str, dict]) -> None:
    """Write a real identities.toml. entries: name -> {repos?, owners?}."""
    lines = []
    for name, keys in entries.items():
        env = tmp_path / f"{name}.env"
        env.write_text(f"GITHUB_TOKEN={TOKEN_A if name == 'a' else TOKEN_B}\n")
        lines.append(f'[identities.{name}]\nenv_file = "{env}"')
        for key, value in keys.items():
            lines.append(f"{key} = {value!r}".replace("'", '"'))
        lines.append("")
    cfg = tmp_path / "identities.toml"
    cfg.write_text("\n".join(lines))
    monkeypatch.setenv("MCP_GIT_IDENTITIES", str(cfg))


def test_identity_for_owner_returns_none_when_only_repo_mapped(tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch, {"a": {"repos": ["MementoRC/roth_planner"]}})

    assert identity_for_owner("MementoRC") is None


def test_identity_for_owner_returns_identity_when_owner_listed_case_insensitively(
    tmp_path, monkeypatch
):
    _config(tmp_path, monkeypatch, {"a": {"owners": ["Acme"]}})

    identity = identity_for_owner("ACME")

    assert identity is not None and identity.token == TOKEN_A


def test_identity_for_owner_returns_none_when_owner_unlisted(tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch, {"a": {"owners": ["acme"]}})

    assert identity_for_owner("other") is None


def test_identity_for_owner_does_not_match_prefix_when_owner_name_is_shorter(
    tmp_path, monkeypatch
):
    _config(tmp_path, monkeypatch, {"a": {"owners": ["MementoRC"]}})

    assert identity_for_owner("Memento") is None


def test_identity_for_owner_raises_when_owner_listed_under_two_identities(
    tmp_path, monkeypatch
):
    _config(
        tmp_path,
        monkeypatch,
        {"a": {"owners": ["acme"]}, "b": {"owners": ["ACME"]}},
    )

    with pytest.raises(IdentityError, match="invalid"):
        identity_for_owner("acme")


def test_identity_for_owner_raises_when_owners_is_not_a_list(tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch, {"a": {"owners": "acme"}})

    with pytest.raises(IdentityError, match="owners must be a list of strings"):
        identity_for_owner("acme")


def test_identity_scope_activates_owner_identity_when_owner_params_given(
    tmp_path, monkeypatch
):
    _config(tmp_path, monkeypatch, {"a": {"owners": ["acme"]}})

    with identity_scope({"owner": "acme", "owner_type": "org", "project_number": 1}):
        active = current_identity.get()

    assert active is not None and active.name == "a"
    assert current_identity.get() is None


def test_identity_scope_raises_when_owner_listed_under_two_identities(
    tmp_path, monkeypatch
):
    _config(
        tmp_path, monkeypatch, {"a": {"owners": ["acme"]}, "b": {"owners": ["acme"]}}
    )

    with pytest.raises(IdentityError):
        with identity_scope({"owner": "acme", "owner_type": "org"}):
            pass


def test_identity_scope_ignores_owner_when_owner_type_absent(tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch, {"a": {"owners": ["acme"]}})

    with identity_scope({"owner": "acme"}):
        assert current_identity.get() is None
