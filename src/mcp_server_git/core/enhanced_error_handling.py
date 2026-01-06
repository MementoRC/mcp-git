"""Enhanced error handling and recovery mechanisms for MCP Git Server.

This module provides comprehensive error handling with granular exception management,
automated recovery strategies, and detailed error reporting capabilities.
"""

import json
import logging
import traceback
from enum import Enum
from typing import Any, Callable

# Safe git import that handles ClaudeCode redirector conflicts
from ..utils.git_import import GitCommandError, InvalidGitRepositoryError

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels for categorization."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories for better error handling."""

    CONFIGURATION = "configuration"
    AUTHENTICATION = "authentication"
    NETWORK = "network"
    REPOSITORY = "repository"
    VALIDATION = "validation"
    PERMISSION = "permission"
    RESOURCE = "resource"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class MCPError(Exception):
    """Base exception for MCP Git Server operations."""

    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ):
        super().__init__(message)
        self.category = category
        self.severity = severity
        self.context = context or {}
        self.suggestion = suggestion


class GitOperationError(MCPError):
    """Exception for Git operation failures."""

    def __init__(
        self,
        message: str,
        operation: str | None = None,
        repo_path: str | None = None,
        **kwargs,
    ):
        super().__init__(message, category=ErrorCategory.REPOSITORY, **kwargs)
        self.operation = operation
        self.repo_path = repo_path


class GitHubAPIError(MCPError):
    """Exception for GitHub API failures."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        api_endpoint: str | None = None,
        **kwargs,
    ):
        super().__init__(message, category=ErrorCategory.NETWORK, **kwargs)
        self.status_code = status_code
        self.api_endpoint = api_endpoint


class AzureAPIError(MCPError):
    """Exception for Azure DevOps API failures."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        api_endpoint: str | None = None,
        **kwargs,
    ):
        super().__init__(message, category=ErrorCategory.NETWORK, **kwargs)
        self.status_code = status_code
        self.api_endpoint = api_endpoint


class ValidationError(MCPError):
    """Exception for validation failures."""

    def __init__(
        self,
        message: str,
        field: str | None = None,
        value: Any = None,
        **kwargs,
    ):
        super().__init__(message, category=ErrorCategory.VALIDATION, **kwargs)
        self.field = field
        self.value = value


class EnhancedErrorHandler:
    """Enhanced error handling with granular exception management."""

    def __init__(self):
        self.error_counts: dict[str, int] = {}
        self.recent_errors: list[dict[str, Any]] = []
        self.max_recent_errors = 100

    def _log_error(
        self, error: Exception, operation: str, context: dict[str, Any] | None = None
    ) -> None:
        """Log error with comprehensive context information."""
        error_info = {
            "operation": operation,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context or {},
            "timestamp": logger.name,  # Use logger's timestamp
        }

        # Add to recent errors tracking
        self.recent_errors.append(error_info)
        if len(self.recent_errors) > self.max_recent_errors:
            self.recent_errors.pop(0)

        # Update error counts
        error_key = f"{operation}:{type(error).__name__}"
        self.error_counts[error_key] = self.error_counts.get(error_key, 0) + 1

        # Log with appropriate level based on error type
        if isinstance(error, MCPError):
            if error.severity == ErrorSeverity.CRITICAL:
                logger.critical(
                    f"Critical error in {operation}: {error}", extra=error_info
                )
            elif error.severity == ErrorSeverity.HIGH:
                logger.error(
                    f"High severity error in {operation}: {error}", extra=error_info
                )
            else:
                logger.warning(f"Error in {operation}: {error}", extra=error_info)
        else:
            logger.error(f"Unexpected error in {operation}: {error}", extra=error_info)

    def _create_error_response(self, error: Exception, operation: str) -> str:
        """Create user-friendly error response with actionable guidance."""
        if isinstance(error, MCPError):
            response = {
                "error": True,
                "operation": operation,
                "category": error.category.value,
                "severity": error.severity.value,
                "message": str(error),
                "context": error.context,
                "suggestion": error.suggestion,
            }
        else:
            response = {
                "error": True,
                "operation": operation,
                "category": ErrorCategory.UNKNOWN.value,
                "severity": ErrorSeverity.MEDIUM.value,
                "message": str(error),
                "type": type(error).__name__,
            }

        return json.dumps(response, indent=2)

    def handle_git_operation_error(
        self, func: Callable, operation_name: str
    ) -> Callable:
        """Decorator for handling git operation errors with granularity."""

        def decorator(*args, **kwargs):
            try:
                return func(*args, **kwargs)

            except InvalidGitRepositoryError as e:
                error = GitOperationError(
                    f"Invalid git repository: {e}",
                    operation=operation_name,
                    repo_path=kwargs.get("repo_path", "unknown"),
                    severity=ErrorSeverity.HIGH,
                    suggestion="Ensure the path points to a valid git repository or initialize one with 'git init'",
                )
                self._log_error(error, operation_name, {"args": args, "kwargs": kwargs})
                return self._create_error_response(error, operation_name)

            except GitCommandError as e:
                error = GitOperationError(
                    f"Git command failed: {e}",
                    operation=operation_name,
                    repo_path=kwargs.get("repo_path", "unknown"),
                    severity=ErrorSeverity.MEDIUM,
                    suggestion="Check git repository state and ensure the operation is valid",
                )
                self._log_error(
                    error, operation_name, {"command": str(e), "args": args}
                )
                return self._create_error_response(error, operation_name)

            except PermissionError as e:
                error = MCPError(
                    f"Permission denied: {e}",
                    category=ErrorCategory.PERMISSION,
                    severity=ErrorSeverity.HIGH,
                    suggestion="Check file/directory permissions and user access rights",
                )
                self._log_error(error, operation_name, {"path": str(e)})
                return self._create_error_response(error, operation_name)

            except FileNotFoundError as e:
                error = MCPError(
                    f"File or directory not found: {e}",
                    category=ErrorCategory.REPOSITORY,
                    severity=ErrorSeverity.HIGH,
                    suggestion="Verify the repository path exists and is accessible",
                )
                self._log_error(error, operation_name, {"path": str(e)})
                return self._create_error_response(error, operation_name)

            except ValueError as e:
                error = ValidationError(
                    f"Invalid parameter value: {e}",
                    field="unknown",
                    value=kwargs,
                    severity=ErrorSeverity.MEDIUM,
                    suggestion="Check parameter values and ensure they meet the required format",
                )
                self._log_error(error, operation_name, {"args": args, "kwargs": kwargs})
                return self._create_error_response(error, operation_name)

            except Exception as e:
                # Log unexpected errors with full traceback for debugging
                error_context = {
                    "args": args,
                    "kwargs": kwargs,
                    "traceback": traceback.format_exc(),
                }
                logger.error(
                    f"Unexpected error in {operation_name}: {e}", extra=error_context
                )

                error = MCPError(
                    f"Unexpected error in {operation_name}: {e}",
                    category=ErrorCategory.UNKNOWN,
                    severity=ErrorSeverity.HIGH,
                    context={"error_type": type(e).__name__},
                    suggestion="This is an unexpected error. Please report it to the development team.",
                )
                return self._create_error_response(error, operation_name)

        return decorator

    def handle_github_api_error(self, func: Callable, operation_name: str) -> Callable:
        """Decorator for handling GitHub API errors with granularity."""

        async def decorator(*args, **kwargs):
            try:
                return await func(*args, **kwargs)

            except ConnectionError as e:
                error = GitHubAPIError(
                    f"GitHub connection failed: {e}",
                    category=ErrorCategory.NETWORK,
                    severity=ErrorSeverity.HIGH,
                    suggestion="Check network connectivity and GitHub API status",
                )
                self._log_error(error, operation_name, {"args": args, "kwargs": kwargs})
                return self._create_error_response(error, operation_name)

            except TimeoutError as e:
                error = GitHubAPIError(
                    f"GitHub API request timed out: {e}",
                    category=ErrorCategory.TIMEOUT,
                    severity=ErrorSeverity.MEDIUM,
                    suggestion="The request took too long. Try again or check GitHub API status",
                )
                self._log_error(error, operation_name, {"timeout": True})
                return self._create_error_response(error, operation_name)

            except ValueError as e:
                if "authentication" in str(e).lower() or "token" in str(e).lower():
                    error = GitHubAPIError(
                        f"GitHub authentication failed: {e}",
                        category=ErrorCategory.AUTHENTICATION,
                        severity=ErrorSeverity.HIGH,
                        suggestion="Check your GitHub token and permissions",
                    )
                else:
                    error = ValidationError(
                        f"Invalid GitHub API parameter: {e}",
                        field="unknown",
                        value=kwargs,
                        severity=ErrorSeverity.MEDIUM,
                        suggestion="Verify API parameters match GitHub API requirements",
                    )
                self._log_error(error, operation_name, {"args": args, "kwargs": kwargs})
                return self._create_error_response(error, operation_name)

            except json.JSONDecodeError as e:
                error = GitHubAPIError(
                    f"Invalid JSON response from GitHub API: {e}",
                    category=ErrorCategory.NETWORK,
                    severity=ErrorSeverity.MEDIUM,
                    suggestion="GitHub API returned malformed data. Try again or check API status",
                )
                self._log_error(error, operation_name, {"json_error": str(e)})
                return self._create_error_response(error, operation_name)

            except Exception as e:
                # Log unexpected errors with full context
                error_context = {
                    "args": args,
                    "kwargs": kwargs,
                    "traceback": traceback.format_exc(),
                }
                logger.error(
                    f"Unexpected error in GitHub API {operation_name}: {e}",
                    extra=error_context,
                )

                error = GitHubAPIError(
                    f"Unexpected GitHub API error: {e}",
                    category=ErrorCategory.UNKNOWN,
                    severity=ErrorSeverity.HIGH,
                    context={"error_type": type(e).__name__},
                    suggestion="This is an unexpected error. Please report it to the development team.",
                )
                return self._create_error_response(error, operation_name)

        return decorator

    def handle_azure_api_error(self, func: Callable, operation_name: str) -> Callable:
        """Decorator for handling Azure DevOps API errors with granularity."""

        async def decorator(*args, **kwargs):
            try:
                return await func(*args, **kwargs)

            except ConnectionError as e:
                error = AzureAPIError(
                    f"Azure DevOps connection failed: {e}",
                    category=ErrorCategory.NETWORK,
                    severity=ErrorSeverity.HIGH,
                    suggestion="Check network connectivity and Azure DevOps API status",
                )
                self._log_error(error, operation_name, {"args": args, "kwargs": kwargs})
                return self._create_error_response(error, operation_name)

            except TimeoutError as e:
                error = AzureAPIError(
                    f"Azure DevOps API request timed out: {e}",
                    category=ErrorCategory.TIMEOUT,
                    severity=ErrorSeverity.MEDIUM,
                    suggestion="The request took too long. Try again or check Azure DevOps API status",
                )
                self._log_error(error, operation_name, {"timeout": True})
                return self._create_error_response(error, operation_name)

            except ValueError as e:
                if "authentication" in str(e).lower() or "token" in str(e).lower():
                    error = AzureAPIError(
                        f"Azure DevOps authentication failed: {e}",
                        category=ErrorCategory.AUTHENTICATION,
                        severity=ErrorSeverity.HIGH,
                        suggestion="Check your Azure DevOps token and permissions",
                    )
                else:
                    error = ValidationError(
                        f"Invalid Azure DevOps API parameter: {e}",
                        field="unknown",
                        value=kwargs,
                        severity=ErrorSeverity.MEDIUM,
                        suggestion="Verify API parameters match Azure DevOps API requirements",
                    )
                self._log_error(error, operation_name, {"args": args, "kwargs": kwargs})
                return self._create_error_response(error, operation_name)

            except json.JSONDecodeError as e:
                error = AzureAPIError(
                    f"Invalid JSON response from Azure DevOps API: {e}",
                    category=ErrorCategory.NETWORK,
                    severity=ErrorSeverity.MEDIUM,
                    suggestion="Azure DevOps API returned malformed data. Try again or check API status",
                )
                self._log_error(error, operation_name, {"json_error": str(e)})
                return self._create_error_response(error, operation_name)

            except Exception as e:
                # Log unexpected errors with full context
                error_context = {
                    "args": args,
                    "kwargs": kwargs,
                    "traceback": traceback.format_exc(),
                }
                logger.error(
                    f"Unexpected error in Azure DevOps API {operation_name}: {e}",
                    extra=error_context,
                )

                error = AzureAPIError(
                    f"Unexpected Azure DevOps API error: {e}",
                    category=ErrorCategory.UNKNOWN,
                    severity=ErrorSeverity.HIGH,
                    context={"error_type": type(e).__name__},
                    suggestion="This is an unexpected error. Please report it to the development team.",
                )
                return self._create_error_response(error, operation_name)

        return decorator

    def handle_validation_error(self, func: Callable, operation_name: str) -> Callable:
        """Decorator for handling validation errors with granularity."""

        def decorator(*args, **kwargs):
            try:
                return func(*args, **kwargs)

            except TypeError as e:
                error = ValidationError(
                    f"Invalid parameter type: {e}",
                    field="unknown",
                    value=kwargs,
                    severity=ErrorSeverity.MEDIUM,
                    suggestion="Check parameter types match the expected function signature",
                )
                self._log_error(error, operation_name, {"args": args, "kwargs": kwargs})
                return self._create_error_response(error, operation_name)

            except ValueError as e:
                error = ValidationError(
                    f"Invalid parameter value: {e}",
                    field="unknown",
                    value=kwargs,
                    severity=ErrorSeverity.MEDIUM,
                    suggestion="Ensure parameter values are within valid ranges and formats",
                )
                self._log_error(error, operation_name, {"args": args, "kwargs": kwargs})
                return self._create_error_response(error, operation_name)

            except KeyError as e:
                error = ValidationError(
                    f"Missing required parameter: {e}",
                    field=str(e),
                    value=None,
                    severity=ErrorSeverity.HIGH,
                    suggestion=f"Ensure the required parameter {e} is provided",
                )
                self._log_error(error, operation_name, {"missing_key": str(e)})
                return self._create_error_response(error, operation_name)

            except Exception as e:
                logger.error(
                    f"Unexpected validation error in {operation_name}: {e}",
                    extra={
                        "args": args,
                        "kwargs": kwargs,
                        "traceback": traceback.format_exc(),
                    },
                )

                error = MCPError(
                    f"Unexpected validation error: {e}",
                    category=ErrorCategory.VALIDATION,
                    severity=ErrorSeverity.HIGH,
                    suggestion="This is an unexpected validation error. Please report it.",
                )
                return self._create_error_response(error, operation_name)

        return decorator

    def get_error_statistics(self) -> dict[str, Any]:
        """Get error statistics for monitoring and debugging."""
        return {
            "total_errors": sum(self.error_counts.values()),
            "error_counts_by_type": self.error_counts.copy(),
            "recent_errors_count": len(self.recent_errors),
            "recent_errors": self.recent_errors[-10:]
            if self.recent_errors
            else [],  # Last 10 errors
        }

    def clear_error_statistics(self) -> None:
        """Clear error statistics (useful for testing or reset)."""
        self.error_counts.clear()
        self.recent_errors.clear()


# Global error handler instance
error_handler = EnhancedErrorHandler()


def with_git_error_handling(operation_name: str):
    """Decorator for git operations with enhanced error handling."""

    def decorator(func):
        return error_handler.handle_git_operation_error(func, operation_name)

    return decorator


def with_github_error_handling(operation_name: str):
    """Decorator for GitHub API operations with enhanced error handling."""

    def decorator(func):
        return error_handler.handle_github_api_error(func, operation_name)

    return decorator


def with_azure_error_handling(operation_name: str):
    """Decorator for Azure DevOps API operations with enhanced error handling."""

    def decorator(func):
        return error_handler.handle_azure_api_error(func, operation_name)

    return decorator


def with_validation_error_handling(operation_name: str):
    """Decorator for validation operations with enhanced error handling."""

    def decorator(func):
        return error_handler.handle_validation_error(func, operation_name)

    return decorator
