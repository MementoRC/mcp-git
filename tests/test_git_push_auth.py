"""Tests for enhanced git_push authentication functionality"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from mcp_server_git.git.operations import git_push, _get_github_cli_token, _try_system_git_push

# Import git conditionally to avoid issues in Claude Code environment
if os.getenv("CLAUDECODE") != "1":
    from git import Repo, GitCommandError
else:
    # Mock git module for Claude Code environment
    class MockGitCommandError(Exception):
        pass
    
    class MockRepo:
        def __init__(self, working_dir="/tmp"):
            self.working_dir = working_dir
            self.active_branch = MagicMock()
            self.active_branch.name = "main"
            self.git = MagicMock()
            
        def remote(self, name):
            mock_remote = MagicMock()
            mock_remote.url = "https://github.com/user/repo.git"
            mock_remote.set_url = MagicMock()
            return mock_remote
    
    Repo = MockRepo
    GitCommandError = MockGitCommandError


class TestGitHubCLITokenDetection:
    """Test GitHub CLI token detection functionality"""

    def test_gh_command_not_found(self):
        """Test when gh command is not available"""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = FileNotFoundError()
            result = _get_github_cli_token()
            assert result is None

    def test_gh_command_succeeds(self):
        """Test when gh auth token succeeds"""
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "gho_test_token_123\n"
            mock_run.return_value = mock_result
            
            result = _get_github_cli_token()
            assert result == "gho_test_token_123"

    def test_gh_command_fails(self):
        """Test when gh auth token fails"""
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stdout = ""
            mock_run.return_value = mock_result
            
            result = _get_github_cli_token()
            assert result is None

    def test_gh_command_timeout(self):
        """Test when gh command times out"""
        with patch('subprocess.run') as mock_run:
            import subprocess
            mock_run.side_effect = subprocess.TimeoutExpired("gh", 10)
            result = _get_github_cli_token()
            assert result is None


class TestSystemGitPushFallback:
    """Test system git push fallback functionality"""

    def test_successful_system_push(self):
        """Test successful system git push"""
        mock_repo = MagicMock()
        mock_repo.working_dir = "/tmp"
        
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "Everything up-to-date"
            mock_run.return_value = mock_result
            
            success, message = _try_system_git_push(mock_repo, "origin", "main", ["origin", "main"])
            assert success
            assert "✅ Successfully pushed main to origin" in message
            assert "🔐 Used system git authentication" in message

    def test_failed_system_push(self):
        """Test failed system git push"""
        mock_repo = MagicMock()
        mock_repo.working_dir = "/tmp"
        
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = "Permission denied"
            mock_run.return_value = mock_result
            
            success, message = _try_system_git_push(mock_repo, "origin", "main", ["origin", "main"])
            assert not success
            assert "❌ Push failed: Permission denied" in message

    def test_system_push_timeout(self):
        """Test system git push timeout"""
        mock_repo = MagicMock()
        mock_repo.working_dir = "/tmp"
        
        with patch('subprocess.run') as mock_run:
            import subprocess
            mock_run.side_effect = subprocess.TimeoutExpired("git", 60)
            
            success, message = _try_system_git_push(mock_repo, "origin", "main", ["origin", "main"])
            assert not success
            assert "❌ Push timed out after 60 seconds" in message

    def test_system_push_with_upstream(self):
        """Test system git push with set upstream"""
        mock_repo = MagicMock()
        mock_repo.working_dir = "/tmp"
        
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result
            
            success, message = _try_system_git_push(
                mock_repo, "origin", "main", ["--set-upstream", "origin", "main"]
            )
            assert success
            assert "set upstream tracking" in message


class TestGitPushAuthenticationFallback:
    """Test complete git_push authentication fallback chain"""

    def setup_method(self):
        """Set up test environment"""
        self.mock_repo = MagicMock()
        self.mock_repo.working_dir = "/tmp"
        self.mock_repo.active_branch.name = "main"
        
        mock_remote = MagicMock()
        mock_remote.url = "https://github.com/user/repo.git"
        self.mock_repo.remote.return_value = mock_remote

    def test_github_token_priority(self):
        """Test that GITHUB_TOKEN has highest priority"""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "gho_env_token_123"}):
            with patch('mcp_server_git.git.operations._get_github_cli_token') as mock_gh_token:
                with patch('mcp_server_git.git.operations._try_system_git_push') as mock_sys_push:
                    self.mock_repo.git.push.return_value = None  # Successful push
                    
                    result = git_push(self.mock_repo, "origin", "main")
                    
                    # Should use GITHUB_TOKEN and not call fallbacks
                    mock_gh_token.assert_not_called()
                    mock_sys_push.assert_not_called()
                    assert "🔐 Used GitHub token authentication" in result

    def test_github_cli_fallback(self):
        """Test fallback to GitHub CLI when no GITHUB_TOKEN"""
        with patch.dict(os.environ, {}, clear=True):  # Clear GITHUB_TOKEN
            with patch('mcp_server_git.git.operations._get_github_cli_token') as mock_gh_token:
                with patch('mcp_server_git.git.operations._try_system_git_push') as mock_sys_push:
                    mock_gh_token.return_value = "gho_cli_token_123"
                    mock_sys_push.return_value = (True, "✅ Success with system git")
                    
                    # Mock GitHub CLI push to succeed
                    self.mock_repo.git.push.return_value = None
                    
                    result = git_push(self.mock_repo, "origin", "main")
                    
                    # Should try GitHub CLI and succeed
                    mock_gh_token.assert_called_once()
                    mock_sys_push.assert_not_called()  # Should not reach system git
                    assert "🔐 Used GitHub CLI authentication" in result

    def test_system_git_fallback(self):
        """Test fallback to system git when GitHub CLI fails"""
        with patch.dict(os.environ, {}, clear=True):  # Clear GITHUB_TOKEN
            with patch('mcp_server_git.git.operations._get_github_cli_token') as mock_gh_token:
                with patch('mcp_server_git.git.operations._try_system_git_push') as mock_sys_push:
                    mock_gh_token.return_value = "gho_cli_token_123"
                    mock_sys_push.return_value = (True, "✅ Success with system git")
                    
                    # Mock GitHub CLI push to fail, triggering system git fallback
                    self.mock_repo.git.push.side_effect = GitCommandError("git push", "Authentication failed")
                    
                    result = git_push(self.mock_repo, "origin", "main")
                    
                    # Should try GitHub CLI first, then fall back to system git
                    mock_gh_token.assert_called_once()
                    mock_sys_push.assert_called_once()
                    assert "✅ Success with system git" in result

    def test_no_authentication_available(self):
        """Test when no authentication methods are available"""
        with patch.dict(os.environ, {}, clear=True):  # Clear GITHUB_TOKEN
            with patch('mcp_server_git.git.operations._get_github_cli_token') as mock_gh_token:
                with patch('mcp_server_git.git.operations._try_system_git_push') as mock_sys_push:
                    mock_gh_token.return_value = None  # No GitHub CLI token
                    mock_sys_push.return_value = (False, "System git failed")
                    
                    result = git_push(self.mock_repo, "origin", "main")
                    
                    # Should provide helpful error message with suggestions
                    assert "❌ GitHub HTTPS push failed" in result
                    assert "Set GITHUB_TOKEN environment variable" in result
                    assert "gh auth login" in result
                    assert "git config credential.helper" in result

    def test_ssh_remote_bypasses_https_auth(self):
        """Test that SSH remotes bypass HTTPS authentication logic"""
        # Set up SSH remote
        mock_remote = MagicMock()
        mock_remote.url = "git@github.com:user/repo.git"
        self.mock_repo.remote.return_value = mock_remote
        
        with patch('mcp_server_git.git.operations._get_github_cli_token') as mock_gh_token:
            with patch('mcp_server_git.git.operations._try_system_git_push') as mock_sys_push:
                self.mock_repo.git.push.return_value = None  # Successful push
                
                result = git_push(self.mock_repo, "origin", "main")
                
                # Should not use any HTTPS authentication methods
                mock_gh_token.assert_not_called()
                mock_sys_push.assert_not_called()
                assert "✅ Successfully pushed main to origin" in result
                assert "🔐" not in result  # No auth method mentioned

    def test_non_github_remote(self):
        """Test that non-GitHub remotes bypass GitHub-specific authentication"""
        # Set up non-GitHub remote
        mock_remote = MagicMock()
        mock_remote.url = "https://gitlab.com/user/repo.git"
        self.mock_repo.remote.return_value = mock_remote
        
        with patch('mcp_server_git.git.operations._get_github_cli_token') as mock_gh_token:
            with patch('mcp_server_git.git.operations._try_system_git_push') as mock_sys_push:
                self.mock_repo.git.push.return_value = None  # Successful push
                
                result = git_push(self.mock_repo, "origin", "main")
                
                # Should not use GitHub-specific authentication methods
                mock_gh_token.assert_not_called()
                mock_sys_push.assert_not_called()
                assert "✅ Successfully pushed main to origin" in result

    def test_detached_head_error(self):
        """Test error handling for detached HEAD"""
        self.mock_repo.active_branch.name = None
        self.mock_repo.active_branch.side_effect = TypeError("detached HEAD")
        
        result = git_push(self.mock_repo)
        assert "❌ No active branch found and no branch specified" in result

    def test_enhanced_error_messages(self):
        """Test enhanced error messages for different failure types"""
        # Test 401 authentication error
        with patch.dict(os.environ, {}, clear=True):
            self.mock_repo.git.push.side_effect = GitCommandError("git push", "401")
            
            result = git_push(self.mock_repo, "origin", "main")
            assert "❌ Authentication failed" in result
            assert "Set GITHUB_TOKEN environment variable" in result

        # Test 403 permission error  
        self.mock_repo.git.push.side_effect = GitCommandError("git push", "403")
        result = git_push(self.mock_repo, "origin", "main")
        assert "❌ Permission denied" in result

        # Test non-fast-forward error
        self.mock_repo.git.push.side_effect = GitCommandError("git push", "non-fast-forward")
        result = git_push(self.mock_repo, "origin", "main")
        assert "❌ Push rejected (non-fast-forward)" in result
        assert "--force flag" in result


@pytest.mark.skipif(
    os.getenv("CLAUDECODE") == "1",
    reason="Integration tests not supported in Claude Code environment"
)
class TestGitPushIntegration:
    """Integration tests for git_push (only run outside Claude Code environment)"""

    @pytest.fixture
    def test_repo(self, tmp_path):
        """Create a test repository"""
        repo_path = tmp_path / "test_repo"
        repo = Repo.init(repo_path)
        
        # Configure user for the repo
        repo.config_writer().set_value("user", "name", "Test User").release()
        repo.config_writer().set_value("user", "email", "test@example.com").release()
        
        # Create initial commit
        test_file = repo_path / "test.txt"
        test_file.write_text("test content")
        repo.index.add(["test.txt"])
        repo.index.commit("Initial commit")
        
        return repo

    def test_integration_no_remote(self, test_repo):
        """Integration test: git_push with no remote configured"""
        result = git_push(test_repo, "origin", "master")
        assert "❌ Push failed" in result
        assert "does not appear to be a git repository" in result

    def test_integration_github_https_no_token(self, test_repo):
        """Integration test: GitHub HTTPS remote without authentication"""
        # Add fake GitHub remote
        test_repo.create_remote("origin", "https://github.com/test/test.git")
        
        # Clear any existing GITHUB_TOKEN
        with patch.dict(os.environ, {}, clear=True):
            result = git_push(test_repo, "origin", "master")
            
            # Should either succeed with system git or fail with helpful message
            assert ("✅" in result and "🔐 Used system git authentication" in result) or \
                   ("❌ GitHub HTTPS push failed" in result and "Try one of:" in result)