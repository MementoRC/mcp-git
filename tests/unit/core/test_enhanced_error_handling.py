"""Tests for enhanced error handling system.

This module contains comprehensive tests for the error handling decorators,
exception classes, and error recovery mechanisms.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock

from mcp_server_git.core.enhanced_error_handling import (
    ErrorSeverity,
    ErrorCategory,
    MCPError,
    GitOperationError,
    GitHubAPIError,
    ValidationError,
    EnhancedErrorHandler,
    with_git_error_handling,
    with_github_error_handling,
    with_validation_error_handling,
    error_handler,
)
from mcp_server_git.utils.git_import import GitCommandError, InvalidGitRepositoryError


class TestMCPError:
    """Test the base MCPError exception class."""

    def test_mcp_error_basic_creation(self):
        """Test basic MCPError creation."""
        error = MCPError("Test error")
        assert str(error) == "Test error"
        assert error.category == ErrorCategory.UNKNOWN
        assert error.severity == ErrorSeverity.MEDIUM
        assert error.context == {}
        assert error.suggestion is None

    def test_mcp_error_full_creation(self):
        """Test MCPError creation with all parameters."""
        context = {"test": "context"}
        error = MCPError(
            "Test error",
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.HIGH,
            context=context,
            suggestion="Fix the network",
        )
        assert str(error) == "Test error"
        assert error.category == ErrorCategory.NETWORK
        assert error.severity == ErrorSeverity.HIGH
        assert error.context == context
        assert error.suggestion == "Fix the network"


class TestGitOperationError:
    """Test GitOperationError exception class."""

    def test_git_operation_error_basic(self):
        """Test basic GitOperationError creation."""
        error = GitOperationError("Git failed")
        assert str(error) == "Git failed"
        assert error.category == ErrorCategory.REPOSITORY
        assert error.operation is None
        assert error.repo_path is None

    def test_git_operation_error_full(self):
        """Test GitOperationError with all parameters."""
        error = GitOperationError(
            "Git failed",
            operation="commit",
            repo_path="/test/repo",
            severity=ErrorSeverity.HIGH,
        )
        assert str(error) == "Git failed"
        assert error.operation == "commit"
        assert error.repo_path == "/test/repo"
        assert error.severity == ErrorSeverity.HIGH


class TestGitHubAPIError:
    """Test GitHubAPIError exception class."""

    def test_github_api_error_basic(self):
        """Test basic GitHubAPIError creation."""
        error = GitHubAPIError("API failed")
        assert str(error) == "API failed"
        assert error.category == ErrorCategory.NETWORK
        assert error.status_code is None
        assert error.api_endpoint is None

    def test_github_api_error_full(self):
        """Test GitHubAPIError with all parameters."""
        error = GitHubAPIError(
            "API failed",
            status_code=404,
            api_endpoint="/repos/test/repo",
            severity=ErrorSeverity.HIGH,
        )
        assert str(error) == "API failed"
        assert error.status_code == 404
        assert error.api_endpoint == "/repos/test/repo"
        assert error.severity == ErrorSeverity.HIGH


class TestValidationError:
    """Test ValidationError exception class."""

    def test_validation_error_basic(self):
        """Test basic ValidationError creation."""
        error = ValidationError("Validation failed")
        assert str(error) == "Validation failed"
        assert error.category == ErrorCategory.VALIDATION
        assert error.field is None
        assert error.value is None

    def test_validation_error_full(self):
        """Test ValidationError with all parameters."""
        error = ValidationError(
            "Invalid value",
            field="username",
            value="invalid@user",
            severity=ErrorSeverity.MEDIUM,
        )
        assert str(error) == "Invalid value"
        assert error.field == "username"
        assert error.value == "invalid@user"
        assert error.severity == ErrorSeverity.MEDIUM


class TestEnhancedErrorHandler:
    """Test the EnhancedErrorHandler class."""

    def setup_method(self):
        """Set up test environment."""
        self.handler = EnhancedErrorHandler()

    def test_error_handler_initialization(self):
        """Test error handler initializes correctly."""
        assert self.handler.error_counts == {}
        assert self.handler.recent_errors == []
        assert self.handler.max_recent_errors == 100

    def test_log_error(self):
        """Test error logging functionality."""
        error = ValueError("Test error")
        self.handler._log_error(error, "test_operation")

        assert len(self.handler.recent_errors) == 1
        assert "test_operation:ValueError" in self.handler.error_counts
        assert self.handler.error_counts["test_operation:ValueError"] == 1

    def test_create_error_response_mcp_error(self):
        """Test error response creation for MCPError."""
        error = MCPError(
            "Test error",
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.HIGH,
            suggestion="Fix network",
        )
        response = self.handler._create_error_response(error, "test_op")
        response_dict = json.loads(response)

        assert response_dict["error"] is True
        assert response_dict["operation"] == "test_op"
        assert response_dict["category"] == "network"
        assert response_dict["severity"] == "high"
        assert response_dict["suggestion"] == "Fix network"

    def test_create_error_response_standard_error(self):
        """Test error response creation for standard exceptions."""
        error = ValueError("Test error")
        response = self.handler._create_error_response(error, "test_op")
        response_dict = json.loads(response)

        assert response_dict["error"] is True
        assert response_dict["operation"] == "test_op"
        assert response_dict["category"] == "unknown"
        assert response_dict["severity"] == "medium"
        assert response_dict["type"] == "ValueError"

    def test_get_error_statistics(self):
        """Test error statistics retrieval."""
        error1 = ValueError("Error 1")
        error2 = TypeError("Error 2")

        self.handler._log_error(error1, "op1")
        self.handler._log_error(error2, "op2")
        self.handler._log_error(error1, "op1")  # Same error again

        stats = self.handler.get_error_statistics()
        assert stats["total_errors"] == 3
        assert stats["error_counts_by_type"]["op1:ValueError"] == 2
        assert stats["error_counts_by_type"]["op2:TypeError"] == 1
        assert stats["recent_errors_count"] == 3

    def test_clear_error_statistics(self):
        """Test error statistics clearing."""
        error = ValueError("Test error")
        self.handler._log_error(error, "test_op")

        assert len(self.handler.error_counts) > 0
        assert len(self.handler.recent_errors) > 0

        self.handler.clear_error_statistics()

        assert len(self.handler.error_counts) == 0
        assert len(self.handler.recent_errors) == 0


class TestGitErrorHandling:
    """Test git operation error handling decorators."""

    def setup_method(self):
        """Set up test environment."""
        self.handler = EnhancedErrorHandler()

    def test_git_error_handling_success(self):
        """Test successful git operation."""

        @with_git_error_handling("test_git_op")
        def test_function():
            return "success"

        result = test_function()
        assert result == "success"

    def test_git_error_handling_invalid_repo(self):
        """Test handling of InvalidGitRepositoryError."""

        @with_git_error_handling("test_git_op")
        def test_function():
            raise InvalidGitRepositoryError("Not a git repo")

        result = test_function()
        response = json.loads(result)

        assert response["error"] is True
        assert response["category"] == "repository"
        assert response["severity"] == "high"
        assert "Invalid git repository" in response["message"]

    def test_git_error_handling_command_error(self):
        """Test handling of GitCommandError."""

        @with_git_error_handling("test_git_op")
        def test_function():
            raise GitCommandError("git commit", 1, "stderr", "stdout")

        result = test_function()
        response = json.loads(result)

        assert response["error"] is True
        assert response["category"] == "repository"
        assert response["severity"] == "medium"
        assert "Git command failed" in response["message"]

    def test_git_error_handling_permission_error(self):
        """Test handling of PermissionError."""

        @with_git_error_handling("test_git_op")
        def test_function():
            raise PermissionError("Permission denied")

        result = test_function()
        response = json.loads(result)

        assert response["error"] is True
        assert response["category"] == "permission"
        assert response["severity"] == "high"

    def test_git_error_handling_file_not_found(self):
        """Test handling of FileNotFoundError."""

        @with_git_error_handling("test_git_op")
        def test_function():
            raise FileNotFoundError("File not found")

        result = test_function()
        response = json.loads(result)

        assert response["error"] is True
        assert response["category"] == "repository"
        assert response["severity"] == "high"

    def test_git_error_handling_value_error(self):
        """Test handling of ValueError."""

        @with_git_error_handling("test_git_op")
        def test_function():
            raise ValueError("Invalid value")

        result = test_function()
        response = json.loads(result)

        assert response["error"] is True
        assert response["category"] == "validation"
        assert response["severity"] == "medium"

    def test_git_error_handling_unexpected_error(self):
        """Test handling of unexpected exceptions."""

        @with_git_error_handling("test_git_op")
        def test_function():
            raise RuntimeError("Unexpected error")

        result = test_function()
        response = json.loads(result)

        assert response["error"] is True
        assert response["category"] == "unknown"
        assert response["severity"] == "high"


class TestGitHubErrorHandling:
    """Test GitHub API error handling decorators."""

    @pytest.mark.asyncio
    async def test_github_error_handling_success(self):
        """Test successful GitHub API operation."""

        @with_github_error_handling("test_github_op")
        async def test_function():
            return "success"

        result = await test_function()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_github_error_handling_connection_error(self):
        """Test handling of ConnectionError."""

        @with_github_error_handling("test_github_op")
        async def test_function():
            raise ConnectionError("Connection failed")

        result = await test_function()
        response = json.loads(result)

        assert response["error"] is True
        assert response["category"] == "network"
        assert response["severity"] == "high"

    @pytest.mark.asyncio
    async def test_github_error_handling_timeout_error(self):
        """Test handling of TimeoutError."""

        @with_github_error_handling("test_github_op")
        async def test_function():
            raise TimeoutError("Request timed out")

        result = await test_function()
        response = json.loads(result)

        assert response["error"] is True
        assert response["category"] == "timeout"
        assert response["severity"] == "medium"

    @pytest.mark.asyncio
    async def test_github_error_handling_auth_value_error(self):
        """Test handling of authentication ValueError."""

        @with_github_error_handling("test_github_op")
        async def test_function():
            raise ValueError("authentication failed")

        result = await test_function()
        response = json.loads(result)

        assert response["error"] is True
        assert response["category"] == "authentication"
        assert response["severity"] == "high"

    @pytest.mark.asyncio
    async def test_github_error_handling_json_decode_error(self):
        """Test handling of JSONDecodeError."""

        @with_github_error_handling("test_github_op")
        async def test_function():
            raise json.JSONDecodeError("Invalid JSON", "test", 0)

        result = await test_function()
        response = json.loads(result)

        assert response["error"] is True
        assert response["category"] == "network"
        assert response["severity"] == "medium"


class TestValidationErrorHandling:
    """Test validation error handling decorators."""

    def test_validation_error_handling_success(self):
        """Test successful validation operation."""

        @with_validation_error_handling("test_validation_op")
        def test_function():
            return "success"

        result = test_function()
        assert result == "success"

    def test_validation_error_handling_type_error(self):
        """Test handling of TypeError."""

        @with_validation_error_handling("test_validation_op")
        def test_function():
            raise TypeError("Invalid type")

        result = test_function()
        response = json.loads(result)

        assert response["error"] is True
        assert response["category"] == "validation"
        assert response["severity"] == "medium"

    def test_validation_error_handling_value_error(self):
        """Test handling of ValueError."""

        @with_validation_error_handling("test_validation_op")
        def test_function():
            raise ValueError("Invalid value")

        result = test_function()
        response = json.loads(result)

        assert response["error"] is True
        assert response["category"] == "validation"
        assert response["severity"] == "medium"

    def test_validation_error_handling_key_error(self):
        """Test handling of KeyError."""

        @with_validation_error_handling("test_validation_op")
        def test_function():
            raise KeyError("missing_key")

        result = test_function()
        response = json.loads(result)

        assert response["error"] is True
        assert response["category"] == "validation"
        assert response["severity"] == "high"
        assert "missing_key" in response["message"]

    def test_validation_error_handling_unexpected_error(self):
        """Test handling of unexpected exceptions."""

        @with_validation_error_handling("test_validation_op")
        def test_function():
            raise RuntimeError("Unexpected error")

        result = test_function()
        response = json.loads(result)

        assert response["error"] is True
        assert response["category"] == "validation"
        assert response["severity"] == "high"


class TestGlobalErrorHandler:
    """Test the global error handler instance."""

    def test_global_error_handler_exists(self):
        """Test that global error handler exists and is properly initialized."""
        assert error_handler is not None
        assert isinstance(error_handler, EnhancedErrorHandler)
        assert hasattr(error_handler, "error_counts")
        assert hasattr(error_handler, "recent_errors")
