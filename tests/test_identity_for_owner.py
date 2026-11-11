"""Owner-level identity resolution for GitHub Projects (#345)."""

import pytest

from mcp_server_git.identity import (
    IdentityError,
    current_identity,
    identity_for_owner,
    identity_scope,
)

TOKEN_A = "ghp_" + "a" * 36
TOKEN_B = "ghp_" + "b" * 36


def _config(tmp_path, monkeypatch, entries: dict[str, list[str]]) -> None:
    lines = []
    for name, repos in entries.items():
        env = tmp_path / f"{name}.env"
        env.write_text(f"GITHUB_TOKEN={TOKEN_A if name == 'a' else TOKEN_B}\n")
        lines.append(f'[identities.{name}]\nenv_file = "{env}"\nrepos = {repos!r}\n')
    cfg = tmp_path / "identities.toml"
    cfg.write_text("\n".join(lines).replace("'", '"'))
    monkeypatch.setenv("MCP_GIT_IDENTITIES", str(cfg))


def test_identity_for_owner_returns_identity_when_owner_mapped(tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch, {"a": ["Acme/one", "acme/two"]})

    identity = identity_for_owner("ACME")

    assert identity is not None and identity.token == TOKEN_A


def test_identity_for_owner_returns_none_when_owner_unmapped(tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch, {"a": ["acme/one"]})

    assert identity_for_owner("other") is None


def test_identity_for_owner_does_not_match_prefix_when_owner_name_is_longer(
    tmp_path, monkeypatch
):
    _config(tmp_path, monkeypatch, {"a": ["acme-corp/one"]})

    assert identity_for_owner("acme") is None


def test_identity_for_owner_raises_when_owner_repos_conflict(tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch, {"a": ["acme/one"], "b": ["acme/two"]})

    with pytest.raises(IdentityError, match="conflicting"):
        identity_for_owner("acme")


def test_identity_scope_activates_owner_identity_when_owner_params_given(
    tmp_path, monkeypatch
):
    _config(tmp_path, monkeypatch, {"a": ["acme/one"]})

    with identity_scope({"owner": "acme", "owner_type": "org", "project_number": 1}):
        active = current_identity.get()

    assert active is not None and active.name == "a"
    assert current_identity.get() is None


def test_identity_scope_raises_when_owner_identities_conflict(tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch, {"a": ["acme/one"], "b": ["acme/two"]})

    with pytest.raises(IdentityError):
        with identity_scope({"owner": "acme", "owner_type": "org"}):
            pass


def test_identity_scope_ignores_owner_when_owner_type_absent(tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch, {"a": ["acme/one"], "b": ["acme/two"]})

    with identity_scope({"owner": "acme"}):
        assert current_identity.get() is None
