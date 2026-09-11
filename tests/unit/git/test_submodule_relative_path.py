"""Regression tests for issue #168 — git_submodule_add relative path preservation.

Verifies that:
1. git_submodule_add accepts repo-relative paths (the bug was that the lean
   interface forced callers to supply absolute paths, which then landed verbatim
   in .gitmodules, making the repo non-portable).
2. Path traversal via ".." is still rejected even for the exempted parameter.
3. The _validate_path_parameters exemption mechanism works correctly in isolation.
"""

from unittest.mock import MagicMock

import pytest

from mcp_server_git.git._submodule_ops import git_submodule_add
from mcp_server_git.lean.interface import GitLeanInterface

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_minimal_interface() -> GitLeanInterface:
    """Build a GitLeanInterface with real tool registry (no network calls)."""
    return GitLeanInterface(MagicMock(), MagicMock(), MagicMock())


# ---------------------------------------------------------------------------
# Unit tests for the _validate_path_parameters exemption mechanism
# ---------------------------------------------------------------------------


class TestValidatePathParametersExemption:
    """Unit-test the validator with the relative_path_params exemption set."""

    def setup_method(self):
        self.iface = _make_minimal_interface()

    def test_exempt_param_accepts_relative_path(self):
        """Exempted parameter must not raise for a clean relative path."""
        # Should not raise
        self.iface._validate_path_parameters(
            {"path": "sub-packages/remote-iface"},
            relative_path_params={"path"},
        )

    def test_exempt_param_still_rejects_dotdot(self):
        """ ".." traversal in an exempted parameter must still raise ValueError."""
        with pytest.raises(ValueError, match="traversal"):
            self.iface._validate_path_parameters(
                {"path": "../escape"},
                relative_path_params={"path"},
            )

    def test_exempt_param_still_rejects_dotdot_nested(self):
        """ ".." embedded in a deeper path must still raise ValueError."""
        with pytest.raises(ValueError, match="traversal"):
            self.iface._validate_path_parameters(
                {"path": "a/b/../../../etc/passwd"},
                relative_path_params={"path"},
            )

    def test_non_exempt_param_still_requires_absolute(self):
        """A non-exempted path param must still require an absolute path."""
        with pytest.raises(ValueError, match="Relative path"):
            self.iface._validate_path_parameters(
                {"repo_path": "relative/path"},
                relative_path_params={"path"},
            )

    def test_no_exemption_set_rejects_relative(self):
        """Without an exemption set, all path params must be absolute."""
        with pytest.raises(ValueError, match="Relative path"):
            self.iface._validate_path_parameters(
                {"path": "sub/module"},
            )

    def test_exempt_param_rejects_empty_string(self):
        """Empty string must still be rejected even for exempted param."""
        with pytest.raises(ValueError):
            self.iface._validate_path_parameters(
                {"path": ""},
                relative_path_params={"path"},
            )


# ---------------------------------------------------------------------------
# Unit test: git_submodule_add function passes relative path verbatim
# ---------------------------------------------------------------------------


class TestGitSubmoduleAddRelativePath:
    """Direct unit tests for git_submodule_add path forwarding."""

    def test_submodule_add_accepts_relative_path_regression_168(self):
        """Regression test for #168: relative path forwarded verbatim to git.

        Before the fix, callers were forced to pass an absolute path which then
        landed verbatim in .gitmodules, making repos non-portable.
        """
        mock_repo = MagicMock()
        mock_repo.git.submodule.return_value = ""

        result = git_submodule_add(
            mock_repo,
            url="https://github.com/example/lib.git",
            path="lib/submod",
        )

        mock_repo.git.submodule.assert_called_once()
        call_args = mock_repo.git.submodule.call_args[0]
        # args are positional: ("add", url, path)
        assert "lib/submod" in call_args, (
            f"Expected 'lib/submod' in submodule call args, got: {call_args}"
        )
        # Must NOT have mutated the path into an absolute path
        absolute_args = [
            a for a in call_args if isinstance(a, str) and a.startswith("/")
        ]
        assert not absolute_args, (
            f"Absolute path(s) unexpectedly found in submodule args: {absolute_args}"
        )
        assert "✅" in result

    def test_submodule_add_with_branch_passes_relative_path(self):
        """Relative path is also preserved when a branch is specified."""
        mock_repo = MagicMock()
        mock_repo.git.submodule.return_value = ""

        result = git_submodule_add(
            mock_repo,
            url="https://github.com/example/lib.git",
            path="sub-packages/remote-iface",
            branch="main",
        )

        mock_repo.git.submodule.assert_called_once()
        call_args = mock_repo.git.submodule.call_args[0]
        assert "sub-packages/remote-iface" in call_args
        assert "✅" in result


# ---------------------------------------------------------------------------
# Integration tests: execute_tool_direct path through lean interface
# ---------------------------------------------------------------------------


class TestSubmoduleAddViaLeanInterface:
    """Integration tests for git_submodule_add via execute_tool_direct."""

    def setup_method(self):
        self.iface = _make_minimal_interface()

    @pytest.mark.asyncio
    async def test_submodule_add_rejects_path_traversal(self):
        """Traversal in the path parameter must be rejected even for submodule_add."""
        result = await self.iface.execute_tool_direct(
            "git_submodule_add",
            {
                "repo_path": "/tmp/fake-repo",
                "url": "https://github.com/example/lib.git",
                "path": "../escape",
            },
        )
        assert result["status"] == "error"
        assert "traversal" in result["error"].lower() or ".." in result["error"]

    @pytest.mark.asyncio
    async def test_submodule_add_validates_repo_path_is_absolute(self):
        """repo_path must still be validated as absolute (non-exempted param)."""
        result = await self.iface.execute_tool_direct(
            "git_submodule_add",
            {
                "repo_path": "relative/repo",
                "url": "https://github.com/example/lib.git",
                "path": "lib/submod",
            },
        )
        assert result["status"] == "error"
        assert "Relative path" in result["error"]
