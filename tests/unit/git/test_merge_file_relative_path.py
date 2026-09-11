"""Regression tests for issue #214 — git_merge_file unreachable via lean MCP interface.

Root cause: `git_merge_file`'s `path` parameter names a path INSIDE a git
revision (resolved via `git show <rev>:<path>`), not a path on disk, so it
must be repo-relative. The tool was registered without a `relative_path_params`
exemption, so `GitLeanInterface._validate_path_parameters` rejected every
repo-relative value and mangled every absolute one into an unresolvable
`git show` argument. No input worked.

These tests assert at the REGISTRY/VALIDATION layer (not the implementation
layer) because tests/unit/git/test_git_merge_file.py calls the implementation
directly with a mocked Repo and never traverses the lean registry — which is
why that suite did not catch the tool being 100% broken.
"""

from unittest.mock import MagicMock

import pytest

from mcp_server_git.lean.interface import GitLeanInterface


def _make_minimal_interface() -> GitLeanInterface:
    """Build a GitLeanInterface with real tool registry (no network calls)."""
    return GitLeanInterface(MagicMock(), MagicMock(), MagicMock())


class TestGitMergeFileRegistration:
    """The registry entry must carry the exemption for `path`."""

    def setup_method(self):
        self.iface = _make_minimal_interface()

    def test_git_merge_file_registered_with_path_exemption(self):
        tool_def = self.iface.tool_registry["git_merge_file"]
        assert "path" in tool_def.relative_path_params

    def test_git_merge_file_output_path_not_exempted(self):
        """The exemption must not leak to `output_path`, a real filesystem target."""
        tool_def = self.iface.tool_registry["git_merge_file"]
        assert "output_path" not in tool_def.relative_path_params


class TestGitMergeFileValidation:
    """Exercise `_validate_path_parameters` with the tool's registered exemption set."""

    def setup_method(self):
        self.iface = _make_minimal_interface()
        self.relative_path_params = self.iface.tool_registry[
            "git_merge_file"
        ].relative_path_params

    def test_relative_path_accepted_regression_214(self):
        """Repo-relative `path` (the only correct form) must not raise."""
        self.iface._validate_path_parameters(
            {"path": "src/app.py"},
            relative_path_params=self.relative_path_params,
        )

    def test_relative_path_with_traversal_still_rejected(self):
        with pytest.raises(ValueError, match="traversal"):
            self.iface._validate_path_parameters(
                {"path": "../escape/app.py"},
                relative_path_params=self.relative_path_params,
            )

    def test_output_path_absolute_still_accepted(self):
        """`output_path` is a real filesystem destination and stays absolute-only."""
        self.iface._validate_path_parameters(
            {"path": "src/app.py", "output_path": "/tmp/merged.py"},
            relative_path_params=self.relative_path_params,
        )

    def test_output_path_relative_still_rejected(self):
        """The exemption must not leak to `output_path`."""
        with pytest.raises(ValueError, match="Relative path"):
            self.iface._validate_path_parameters(
                {"path": "src/app.py", "output_path": "merged.py"},
                relative_path_params=self.relative_path_params,
            )


class TestGitMergeFileViaLeanInterface:
    """Integration tests through `execute_tool_direct`."""

    def setup_method(self):
        self.iface = _make_minimal_interface()

    @pytest.mark.asyncio
    async def test_merge_file_rejects_path_traversal(self):
        result = await self.iface.execute_tool_direct(
            "git_merge_file",
            {
                "repo_path": "/tmp/fake-repo",
                "path": "../escape",
                "base_rev": "main",
                "ours_rev": "HEAD",
                "theirs_rev": "feature",
            },
        )
        assert result["status"] == "error"
        assert "traversal" in result["error"].lower() or ".." in result["error"]

    @pytest.mark.asyncio
    async def test_merge_file_validates_repo_path_is_absolute(self):
        """repo_path must still be validated as absolute (non-exempted param)."""
        result = await self.iface.execute_tool_direct(
            "git_merge_file",
            {
                "repo_path": "relative/repo",
                "path": "src/app.py",
                "base_rev": "main",
                "ours_rev": "HEAD",
                "theirs_rev": "feature",
            },
        )
        assert result["status"] == "error"
        assert "Relative path" in result["error"]
