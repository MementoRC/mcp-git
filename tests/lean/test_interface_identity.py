"""execute_tool_direct (HTTP path) runs tools under the repo identity (#340)."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mcp_server_git.identity import current_identity
from mcp_server_git.lean.interface import GitLeanInterface, ToolDefinition


@pytest.fixture
def identity_map(tmp_path: Path, monkeypatch) -> Path:
    env_file = tmp_path / "acme.env"
    env_file.write_text(
        "GITHUB_TOKEN=tok-identity-aaaaaaaa\n"
        "GPG_SIGNING_KEY=ABC\n"
        "GIT_AUTHOR_NAME=Acme Bot\n"
        "GIT_AUTHOR_EMAIL=bot@acme.example\n"
    )
    cfg = tmp_path / "identities.toml"
    cfg.write_text(
        f'[identities.acme]\nenv_file = "{env_file}"\nrepos = ["acme/widget"]\n'
    )
    monkeypatch.setenv("MCP_GIT_IDENTITIES", str(cfg))
    return cfg


@pytest.fixture
def recorded() -> list:
    return []


@pytest.fixture
def interface(recorded) -> GitLeanInterface:
    iface = GitLeanInterface(MagicMock(), MagicMock(), MagicMock())

    def probe(repo_owner: str, repo_name: str) -> dict:
        recorded.append(current_identity.get())
        return {"ok": True}

    iface.register_tool(
        ToolDefinition(
            name="probe_identity",
            implementation=probe,
            description="records active identity",
            schema={"type": "object"},
            domain="test",
            complexity="focused",
        )
    )
    return iface


async def test_execute_tool_direct_runs_tool_under_identity_when_repo_mapped(
    interface, recorded, identity_map
):
    result = await interface.execute_tool_direct(
        "probe_identity", {"repo_owner": "acme", "repo_name": "widget"}
    )

    assert result["status"] == "success"
    assert recorded[0] is not None
    assert recorded[0].name == "acme"
    assert recorded[0].token == "tok-identity-aaaaaaaa"
    assert current_identity.get() is None


async def test_execute_tool_direct_runs_tool_without_identity_when_repo_unmapped(
    interface, recorded, identity_map
):
    result = await interface.execute_tool_direct(
        "probe_identity", {"repo_owner": "other", "repo_name": "widget"}
    )

    assert result["status"] == "success"
    assert recorded == [None]
    assert current_identity.get() is None


async def test_execute_tool_direct_returns_error_when_identity_map_invalid(
    interface, recorded, tmp_path, monkeypatch
):
    cfg = tmp_path / "bad.toml"
    cfg.write_text("[identities.acme\nnot toml")
    monkeypatch.setenv("MCP_GIT_IDENTITIES", str(cfg))

    result = await interface.execute_tool_direct(
        "probe_identity", {"repo_owner": "acme", "repo_name": "widget"}
    )

    assert result["status"] == "error"
    assert "identity map" in result["error"]
    assert recorded == []
