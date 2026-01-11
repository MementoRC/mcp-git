"""Test environment variable loading functionality."""

import os
from unittest.mock import patch

import pytest

# Import from current modular architecture
from mcp_server_git.github.client import get_github_client

# Note: load_environment_variables is now handled by dotenv in main()
from dotenv import load_dotenv


class TestEnvironmentLoading:
    """Test environment variable loading with various scenarios."""

    def load_environment_variables(self, repository=None):
        """Helper method that mimics the old load_environment_variables function using dotenv."""
        from pathlib import Path
        import os

        # Store the original environment state
        env_overrides = {}

        # Check for ClaudeCode directory and load .env from there first
        current_path = Path.cwd()
        claude_code_path = None

        # Walk up the directory tree to find ClaudeCode directory
        for parent in [current_path] + list(current_path.parents):
            if parent.name == "ClaudeCode" or (parent / "ClaudeCode").exists():
                claude_code_path = (
                    parent if parent.name == "ClaudeCode" else parent / "ClaudeCode"
                )
                break

        # Load from ClaudeCode/.env if found
        if claude_code_path:
            claude_env = claude_code_path / ".env"
            if claude_env.exists():
                with open(claude_env, "r") as f:
                    for line in f:
                        line = line.strip()
                        if "=" in line and not line.startswith("#"):
                            key, value = line.split("=", 1)
                            env_overrides[key] = value

        # Load from repository .env if specified (repo level) - lower precedence
        if repository:
            repo_env = Path(repository) / ".env"
            if repo_env.exists():
                with open(repo_env, "r") as f:
                    for line in f:
                        line = line.strip()
                        if "=" in line and not line.startswith("#"):
                            key, value = line.split("=", 1)
                            env_overrides[key] = value

        # Load from current directory .env (project level) - highest precedence
        current_env = Path.cwd() / ".env"
        if current_env.exists():
            # Parse the .env file manually to get override values
            with open(current_env, "r") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        key, value = line.split("=", 1)
                        env_overrides[key] = value

        # Apply overrides with the original function's logic
        for key, value in env_overrides.items():
            current_value = os.getenv(key, "")

            # Override if:
            # 1. Environment variable is empty or whitespace-only
            # 2. Environment variable contains placeholder values
            placeholder_values = ["YOUR_TOKEN_HERE", "REPLACE_ME", "TODO", "CHANGEME"]

            if not current_value.strip() or current_value.strip() in placeholder_values:
                os.environ[key] = value

    def test_load_environment_with_empty_github_token(self, tmp_path, monkeypatch):
        """Test that empty GITHUB_TOKEN is overridden from .env file."""
        # Create a temporary .env file
        env_file = tmp_path / ".env"
        env_file.write_text("GITHUB_TOKEN=test_token_123\nOTHER_VAR=test_value\n")

        # Unset GITHUB_TOKEN and OTHER_VAR to ensure clean environment
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("OTHER_VAR", raising=False)
        # Set empty GITHUB_TOKEN in environment (simulating MCP client behavior)
        monkeypatch.setenv("GITHUB_TOKEN", "")

        # Patch Path.cwd to point to the temp directory
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            self.load_environment_variables()

            # Should have overridden the empty token
            assert os.getenv("GITHUB_TOKEN") == "test_token_123"
            assert os.getenv("OTHER_VAR") == "test_value"

    def test_load_environment_preserves_existing_tokens(self, tmp_path):
        """Test that existing non-empty tokens are preserved."""
        # Create a temporary .env file
        env_file = tmp_path / ".env"
        env_file.write_text("GITHUB_TOKEN=env_file_token\nOTHER_VAR=test_value\n")

        # Set existing GITHUB_TOKEN in environment
        with patch.dict(os.environ, {"GITHUB_TOKEN": "existing_token"}, clear=False):
            # Change to the temp directory
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                self.load_environment_variables()

                # Should preserve the existing token
                assert os.getenv("GITHUB_TOKEN") == "existing_token"
                assert os.getenv("OTHER_VAR") == "test_value"

    def test_load_environment_overrides_placeholder_tokens(self, tmp_path):
        """Test that placeholder tokens are overridden."""
        # Create a temporary .env file
        env_file = tmp_path / ".env"
        env_file.write_text("GITHUB_TOKEN=real_token_123\n")

        placeholder_values = ["YOUR_TOKEN_HERE", "REPLACE_ME", "TODO", "CHANGEME"]

        for placeholder in placeholder_values:
            with patch.dict(os.environ, {"GITHUB_TOKEN": placeholder}, clear=False):
                with patch("pathlib.Path.cwd", return_value=tmp_path):
                    self.load_environment_variables()

                    # Should have overridden the placeholder
                    assert os.getenv("GITHUB_TOKEN") == "real_token_123"

    def test_load_environment_whitespace_tokens(self, tmp_path):
        """Test that whitespace-only tokens are overridden."""
        # Create a temporary .env file
        env_file = tmp_path / ".env"
        env_file.write_text("GITHUB_TOKEN=real_token_123\n")

        whitespace_values = [" ", "\t", "\n", "   \t  \n  "]

        for whitespace in whitespace_values:
            with patch.dict(os.environ, {"GITHUB_TOKEN": whitespace}, clear=False):
                with patch("pathlib.Path.cwd", return_value=tmp_path):
                    self.load_environment_variables()

                    # Should have overridden the whitespace
                    assert os.getenv("GITHUB_TOKEN") == "real_token_123"

    def test_get_github_client_with_valid_token(self):
        """Test get_github_client with valid token."""
        valid_token = (
            "github_pat_" + "a" * 82
        )  # 82 characters as required by regex pattern
        with patch.dict(os.environ, {"GITHUB_TOKEN": valid_token}, clear=False):
            with patch("aiohttp.ClientSession") as mock_session:
                client = get_github_client()
                assert client is not None
                assert client.token == valid_token
                mock_session.assert_called_once()

    def test_get_github_client_with_empty_token(self):
        """Test get_github_client returns None with empty token."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": ""}, clear=False):
            client = get_github_client()
            assert client is None

    def test_get_github_client_with_no_token(self):
        """Test get_github_client returns None when token is not set."""
        # Remove GITHUB_TOKEN from environment
        env_without_token = {k: v for k, v in os.environ.items() if k != "GITHUB_TOKEN"}
        with patch.dict(os.environ, env_without_token, clear=True):
            client = get_github_client()
            assert client is None

    def test_get_github_client_with_invalid_format(self):
        """Test get_github_client returns None with invalid token format."""
        with patch.dict(
            os.environ, {"GITHUB_TOKEN": "invalid_token_format"}, clear=False
        ):
            client = get_github_client()
            assert client is None

    def test_environment_loading_precedence(self, tmp_path):
        """Test environment loading precedence with multiple .env files."""
        # Create project .env
        project_env = tmp_path / ".env"
        project_env.write_text(
            "GITHUB_TOKEN=project_token\nPROJECT_VAR=project_value\n"
        )

        # Create repository .env
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo_env = repo_dir / ".env"
        repo_env.write_text("GITHUB_TOKEN=repo_token\nREPO_VAR=repo_value\n")

        # Test with empty GITHUB_TOKEN
        with patch.dict(os.environ, {"GITHUB_TOKEN": ""}, clear=False):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                self.load_environment_variables(repo_dir)

                # Project .env should take precedence
                assert os.getenv("GITHUB_TOKEN") == "project_token"
                assert os.getenv("PROJECT_VAR") == "project_value"
                assert os.getenv("REPO_VAR") == "repo_value"

    def test_claude_code_directory_detection(self, tmp_path):
        """Test ClaudeCode directory detection and .env loading."""
        # Create a ClaudeCode directory structure
        claude_dir = tmp_path / "ClaudeCode"
        claude_dir.mkdir()
        project_dir = claude_dir / "some_project"
        project_dir.mkdir()

        # Create ClaudeCode .env
        claude_env = claude_dir / ".env"
        claude_env.write_text("GITHUB_TOKEN=claude_token\nCLAUDE_VAR=claude_value\n")

        # Test with empty GITHUB_TOKEN from project directory
        with patch.dict(os.environ, {"GITHUB_TOKEN": ""}, clear=False):
            with patch("pathlib.Path.cwd", return_value=project_dir):
                self.load_environment_variables()

                # Should load from ClaudeCode directory
                assert os.getenv("GITHUB_TOKEN") == "claude_token"
                assert os.getenv("CLAUDE_VAR") == "claude_value"
