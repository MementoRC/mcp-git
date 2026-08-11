"""Regression tests for issue #206 — github_get_content rejected relative paths.

``path`` on ``github_get_content`` is a repo-relative identifier for the
GitHub contents API (nothing is read from local disk), so the interface's
blanket "must be absolute" path-guard left no valid input for it. Modeled on
tests/unit/git/test_submodule_relative_path.py (issue #168's analogous fix
for git_submodule_add's ``path``).
"""

from unittest.mock import MagicMock

import pytest

from mcp_server_git.lean.interface import GitLeanInterface


def _make_minimal_interface() -> GitLeanInterface:
    """Build a GitLeanInterface with the real tool registry (no network calls)."""
    return GitLeanInterface(MagicMock(), MagicMock(), MagicMock())


def _tool_def(iface: GitLeanInterface, name: str):
    return iface.tool_registry[name]


class TestGitHubGetContentRegistration:
    """The registered github_get_content tool must exempt its ``path`` param."""

    def setup_method(self):
        self.iface = _make_minimal_interface()

    def test_github_get_content_relative_path_params_contains_path(self):
        tool_def = _tool_def(self.iface, "github_get_content")
        assert "path" in tool_def.relative_path_params


class TestValidatePathParametersExemptionForGithubGetContent:
    """Unit-test the validator with github_get_content's exemption set."""

    def setup_method(self):
        self.iface = _make_minimal_interface()
        self.relative_path_params = _tool_def(
            self.iface, "github_get_content"
        ).relative_path_params

    def test_exact_issue_repro_call_accepted(self):
        """Regression for #206: the exact call from the issue no longer raises."""
        # Should not raise
        self.iface._validate_path_parameters(
            {
                "repo_owner": "conda-forge",
                "repo_name": "zig-feedstock",
                "path": "recipe/recipe.yaml",
                "ref": "dev",
            },
            relative_path_params=self.relative_path_params,
        )

    def test_bare_filename_accepted(self):
        """Second repro from the issue: a bare filename with no directory."""
        # Should not raise
        self.iface._validate_path_parameters(
            {"path": "build.zig"},
            relative_path_params=self.relative_path_params,
        )

    def test_dotdot_traversal_still_rejected(self):
        """ ".." traversal must still raise even for the exempted path param."""
        with pytest.raises(ValueError, match="traversal"):
            self.iface._validate_path_parameters(
                {"path": "../escape"},
                relative_path_params=self.relative_path_params,
            )

    def test_empty_string_still_rejected(self):
        """An empty path value must still raise even for the exempted param."""
        with pytest.raises(ValueError):
            self.iface._validate_path_parameters(
                {"path": ""},
                relative_path_params=self.relative_path_params,
            )


class TestGithubUploadReleaseAssetNotExempted:
    """file_path on github_upload_release_asset is a genuine local file path."""

    def setup_method(self):
        self.iface = _make_minimal_interface()

    def test_upload_release_asset_relative_path_params_excludes_file_path(self):
        tool_def = _tool_def(self.iface, "github_upload_release_asset")
        assert "file_path" not in tool_def.relative_path_params

    def test_upload_release_asset_file_path_still_requires_absolute(self):
        tool_def = _tool_def(self.iface, "github_upload_release_asset")
        with pytest.raises(ValueError, match="Relative path"):
            self.iface._validate_path_parameters(
                {"file_path": "dist/asset.tar.gz"},
                relative_path_params=tool_def.relative_path_params,
            )


class TestGithubGetContentViaLeanInterface:
    """Integration: execute_tool_direct no longer raises the path-guard error."""

    def setup_method(self):
        self.iface = _make_minimal_interface()

    @pytest.mark.asyncio
    async def test_execute_tool_direct_no_longer_raises_relative_path_error(
        self, monkeypatch
    ):
        """Regression for #206: driving the real tool through the interface
        no longer produces "Relative path ... not supported" for ``path``.

        No GITHUB_TOKEN is set, so the call still fails — but on the
        (expected, unrelated) missing-credentials path, not on path
        validation, and with no network access required.
        """
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        result = await self.iface.execute_tool_direct(
            "github_get_content",
            {
                "repo_owner": "conda-forge",
                "repo_name": "zig-feedstock",
                "path": "recipe/recipe.yaml",
                "ref": "dev",
            },
        )

        assert "Relative path" not in str(result)
        assert result["status"] == "success"
        assert "Relative path" not in result["result"]
