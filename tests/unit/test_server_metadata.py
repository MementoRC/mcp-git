"""Unit tests for src/mcp_server_git/server_metadata.py (issue #196 defect 3).

Issue #196 reported two related metadata defects: the fallback version could
silently drift from pyproject.toml (reporting "unknown" in source checkouts),
and server_info's domain tool counts disagreed with discover_tools' counts
for the same registry (git 30/github 52/azure 4 vs 48/64/3) because each was
computed independently.
"""

import re
import tomllib
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

from mcp_server_git.lean.interface import GitLeanInterface
from mcp_server_git.server_metadata import (
    __version__,
    build_server_info,
    domain_counts,
    get_version,
)


def _find_pyproject_toml() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "pyproject.toml"
        if candidate.exists():
            return candidate
    raise FileNotFoundError("pyproject.toml not found walking up from test file")


class TestServerMetadataVersion:
    """Guard against __version__ silently going stale relative to pyproject.toml."""

    def test_dunder_version_matches_pyproject_version_when_compared(self):
        """Regression test for issue #196: __version__ is the fallback used
        whenever importlib.metadata lookup fails (e.g. an editable/source
        checkout with no installed distribution). If it drifts from
        [project].version in pyproject.toml, bug reports can no longer be
        reliably pinned to a release. This test fails loudly instead of
        letting that fallback go stale.
        """
        pyproject_path = _find_pyproject_toml()
        with pyproject_path.open("rb") as f:
            data = tomllib.load(f)

        assert __version__ == data["project"]["version"]


class TestDomainCounts:
    """Test domain_counts() per-domain tallying."""

    def test_domain_counts_returns_totals_per_domain_when_registry_has_mixed_domains(
        self,
    ):
        # Arrange
        registry = {
            "a": types.SimpleNamespace(domain="git"),
            "b": types.SimpleNamespace(domain="git"),
            "c": types.SimpleNamespace(domain="github"),
            "d": types.SimpleNamespace(domain="azure"),
        }

        # Act
        counts = domain_counts(registry)

        # Assert
        assert counts == {"git": 2, "github": 1, "azure": 1}

    def test_domain_counts_ignores_unknown_domain_when_present_in_registry(self):
        # Arrange
        registry = {
            "a": types.SimpleNamespace(domain="git"),
            "b": types.SimpleNamespace(domain="totally-unknown"),
        }

        # Act
        counts = domain_counts(registry)

        # Assert
        assert counts == {"git": 1, "github": 0, "azure": 0}
        assert "totally-unknown" not in counts


class TestBuildServerInfo:
    """Test build_server_info() live count reporting."""

    def test_build_server_info_reports_live_counts_when_registry_given(self):
        # Arrange
        registry = {
            "a": types.SimpleNamespace(domain="git"),
            "b": types.SimpleNamespace(domain="git"),
            "c": types.SimpleNamespace(domain="github"),
        }

        # Act
        info = build_server_info(registry, transport="http")

        # Assert
        assert info["domains"]["git"] == "Local git operations (2 tools)"
        assert info["domains"]["github"] == "GitHub API (1 tools)"
        assert info["domains"]["azure"] == "Azure DevOps (0 tools)"
        assert info["total_tools"] == len(registry)


class TestGetVersion:
    """Test get_version() fallback behavior."""

    def test_get_version_returns_dunder_fallback_when_metadata_lookup_raises(self):
        # Arrange / Act
        with patch(
            "importlib.metadata.version", side_effect=Exception("not installed")
        ):
            result = get_version()

        # Assert
        assert result == __version__
        assert result != "unknown"


def _extract_tool_count(domain_description: str) -> int:
    match = re.search(r"\((\d+) tools\)", domain_description)
    assert match, f"unexpected domain description format: {domain_description}"
    return int(match.group(1))


class TestServerMetadataConsistency:
    """Regression test for issue #196: server_info and discover_tools must
    agree on domain tool counts for the SAME registry. The reported bug had
    them disagree (git 30/github 52/azure 4 vs 48/64/3) because server_info
    and discover_tools computed counts independently.
    """

    def test_build_server_info_domain_counts_match_discover_tools_when_same_registry_used(
        self,
    ):
        # Arrange
        interface = GitLeanInterface(MagicMock(), MagicMock(), MagicMock())

        # Act
        discover_counts = interface.discover_tools()["domains"]
        info = build_server_info(interface.tool_registry, "test")
        info_counts = {
            domain: _extract_tool_count(text)
            for domain, text in info["domains"].items()
        }

        # Assert
        assert info_counts == discover_counts
        assert info["total_tools"] == interface.discover_tools()["total_tools"]
