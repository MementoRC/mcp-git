"""
Unit tests for GitHub parameter validation in server application.

This module tests the validation that prevents GitHub operations from
incorrectly using local repository paths instead of repo_owner/repo_name.
"""

import pytest

from mcp_server_git.applications.server_application import GitServerApplication
from mcp_server_git.frameworks.server_configuration import GitServerConfig


class TestGitHubParameterValidation:
    """Test validation of GitHub API parameters."""

    def setup_method(self):
        """Set up test fixtures."""
        config = GitServerConfig()
        self.app = GitServerApplication(config)

    def test_validate_github_params_valid_simple(self):
        """Test validation accepts simple valid repository identifiers."""
        # Should not raise any exception
        self.app._validate_github_params("MementoRC", "mcp-git")
        self.app._validate_github_params("facebook", "react")
        self.app._validate_github_params("microsoft", "vscode")

    def test_validate_github_params_valid_with_hyphens(self):
        """Test validation accepts identifiers with hyphens."""
        # Should not raise any exception
        self.app._validate_github_params("my-org", "my-repo")
        self.app._validate_github_params("some-company", "some-project-name")

    def test_validate_github_params_valid_with_underscores(self):
        """Test validation accepts identifiers with underscores."""
        # Should not raise any exception
        self.app._validate_github_params("my_org", "my_repo")
        self.app._validate_github_params("some_company", "some_project_name")

    def test_validate_github_params_valid_with_dots(self):
        """Test validation accepts identifiers with dots."""
        # Should not raise any exception
        self.app._validate_github_params("my.org", "my.repo")
        self.app._validate_github_params("company.com", "project.name")

    def test_validate_github_params_reject_unix_path_owner(self):
        """Test validation rejects Unix-style path in repo_owner."""
        with pytest.raises(ValueError, match="appears to be a file path"):
            self.app._validate_github_params(
                "/home/user/repos/project", "mcp-git"
            )

    def test_validate_github_params_reject_unix_path_name(self):
        """Test validation rejects Unix-style path in repo_name."""
        with pytest.raises(ValueError, match="appears to be a file path"):
            self.app._validate_github_params(
                "MementoRC", "/home/user/repos/mcp-git"
            )

    def test_validate_github_params_reject_windows_path_owner(self):
        """Test validation rejects Windows-style path in repo_owner."""
        with pytest.raises(ValueError, match="appears to be a file path"):
            self.app._validate_github_params(
                "C:\\Users\\user\\repos\\project", "mcp-git"
            )

    def test_validate_github_params_reject_windows_path_name(self):
        """Test validation rejects Windows-style path in repo_name."""
        with pytest.raises(ValueError, match="appears to be a file path"):
            self.app._validate_github_params(
                "MementoRC", "C:\\Users\\user\\repos\\mcp-git"
            )

    def test_validate_github_params_reject_relative_path_owner(self):
        """Test validation rejects relative path in repo_owner."""
        with pytest.raises(ValueError, match="appears to be a file path"):
            self.app._validate_github_params("../repos/project", "mcp-git")

    def test_validate_github_params_reject_relative_path_name(self):
        """Test validation rejects relative path in repo_name."""
        with pytest.raises(ValueError, match="appears to be a file path"):
            self.app._validate_github_params("MementoRC", "./mcp-git")

    def test_validate_github_params_reject_owner_with_slash(self):
        """Test validation rejects repo_owner containing forward slash."""
        with pytest.raises(ValueError, match="appears to be a file path"):
            self.app._validate_github_params("owner/something", "repo")

    def test_validate_github_params_reject_name_with_slash(self):
        """Test validation rejects repo_name containing forward slash."""
        with pytest.raises(ValueError, match="appears to be a file path"):
            self.app._validate_github_params("owner", "repo/something")

    def test_validate_github_params_reject_owner_with_backslash(self):
        """Test validation rejects repo_owner containing backslash."""
        with pytest.raises(ValueError, match="appears to be a file path"):
            self.app._validate_github_params("owner\\something", "repo")

    def test_validate_github_params_reject_name_with_backslash(self):
        """Test validation rejects repo_name containing backslash."""
        with pytest.raises(ValueError, match="appears to be a file path"):
            self.app._validate_github_params("owner", "repo\\something")

    def test_validate_github_params_error_message_clarity(self):
        """Test that error messages clearly explain the issue."""
        with pytest.raises(ValueError) as exc_info:
            self.app._validate_github_params(
                "/home/memento/ClaudeCode/Servers/hexagonal-architecture/development",
                "mcp-git"
            )
        
        error_msg = str(exc_info.value)
        # Check that error message contains helpful information
        assert "appears to be a file path" in error_msg
        assert "GitHub API operations" in error_msg
        assert "repo_owner" in error_msg or "repo_name" in error_msg
        assert "'--repository'" in error_msg or "bound" in error_msg

    def test_validate_github_params_preserves_case(self):
        """Test validation preserves case of identifiers."""
        # Should not raise and should preserve case
        self.app._validate_github_params("MementoRC", "mcp-git")
        self.app._validate_github_params("OWNER", "REPO")
        self.app._validate_github_params("MiXeDCaSe", "RePoNaMe")
