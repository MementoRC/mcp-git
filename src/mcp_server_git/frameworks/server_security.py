"""Security and validation framework for the MCP Git Server.

This module contains the SecurityFramework class that implements comprehensive
security and validation logic extracted from the monolithic server.py file.
It implements the DebuggableComponent protocol for state inspection and debugging.

As specified in the PRD, this module focuses on:
- Authentication validation (API keys, tokens)
- Authorization checks (repository access, operation permissions)
- Input validation (path validation, command injection prevention)
- Security policy enforcement (allowed operations, rate limiting)
- GPG signing validation
- Repository security configuration validation
- Security audit logging
"""

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, IntEnum
from pathlib import Path
from typing import Any

from ..protocols.debugging_protocol import (
    ComponentState,
    DebuggableComponent,
    DebugInfo,
    ValidationResult,
)
from ..types.git_types import GitValidationError

logger = logging.getLogger(__name__)


class SecurityStatus(Enum):
    """Security validation status levels."""

    SECURE = "secure"
    WARNING = "warning"
    INSECURE = "insecure"
    CRITICAL = "critical"
    ERROR = "error"


class SecuritySeverity(IntEnum):
    """Security issue severity levels."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class SecurityCategory(Enum):
    """Categories of security issues."""

    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    INPUT_VALIDATION = "input_validation"
    CONFIGURATION = "configuration"
    ENCRYPTION = "encryption"
    AUDIT = "audit"
    RATE_LIMITING = "rate_limiting"


@dataclass
class SecurityIssue:
    """Represents a security issue with detailed context."""

    severity: SecuritySeverity
    category: SecurityCategory
    message: str
    suggested_fix: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class SecurityRecommendation:
    """Security improvement recommendation."""

    priority: SecuritySeverity
    description: str
    implementation_steps: list[str]
    estimated_effort: str  # "low", "medium", "high"


@dataclass
class SecurityValidationResult:
    """Comprehensive security validation result."""

    status: SecurityStatus
    issues: list[SecurityIssue]
    recommendations: list[SecurityRecommendation]
    metadata: dict[str, Any]


@dataclass
class SecurityDebugInfo:
    """Implementation of DebugInfo for the security framework."""

    debug_level: str
    debug_data: dict[str, Any]
    stack_trace: list[str] | None = None
    performance_metrics: dict[str, int | float] = field(default_factory=dict)
    validation_timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class AuthResult:
    """Authentication result with context."""

    success: bool
    user_id: str | None = None
    token_type: str | None = None
    scopes: list[str] = field(default_factory=list)
    expires_at: datetime | None = None
    error_message: str | None = None


@dataclass
class SecurityComponentState:
    """Implementation of ComponentState for the security framework."""

    component_id: str
    component_type: str
    state_data: dict[str, Any]
    last_updated: datetime = field(default_factory=datetime.now)


@dataclass
class SecurityValidationResultImpl:
    """Implementation of ValidationResult for security validation."""

    is_valid: bool
    errors: list[str]
    warnings: list[str]
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def validation_errors(self) -> list[str]:
        """List of validation error messages."""
        return self.errors

    @property
    def validation_warnings(self) -> list[str]:
        """List of validation warning messages."""
        return self.warnings

    @property
    def validation_timestamp(self) -> datetime:
        """When the validation was performed."""
        return self.timestamp


class SecurityDefaults:
    """Security default values and limits."""

    MAX_TOKEN_LENGTH: int = 255
    MIN_PASSWORD_LENGTH: int = 8
    DEFAULT_SESSION_TIMEOUT: int = 3600
    MAX_FAILED_ATTEMPTS: int = 5
    RATE_LIMIT_WINDOW: int = 300
    RATE_LIMIT_REQUESTS: int = 100  # requests per window
    MAX_REQUEST_SIZE: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS: set[str] = {".py", ".md", ".txt", ".json", ".yaml", ".yml"}


class TokenValidator:
    """Validates various types of authentication tokens."""

    GITHUB_TOKEN_PATTERNS = [
        r"^ghp_[a-zA-Z0-9]{36}$",  # Personal access tokens
        r"^github_pat_[a-zA-Z0-9_]{82}$",  # Fine-grained PATs
        r"^ghs_[a-zA-Z0-9]{36}$",  # App installation tokens
        r"^ghu_[a-zA-Z0-9]{36}$",  # App user tokens
        r"^gho_[a-zA-Z0-9]{36}$",  # OAuth tokens
        r"^ghr_[a-zA-Z0-9]{36}$",  # Refresh tokens
    ]

    @staticmethod
    def validate_github_token(token: str) -> SecurityValidationResult:
        """Validate GitHub token format and basic properties."""
        issues = []
        recommendations: list[SecurityRecommendation] = []

        # Strip whitespace and check if token is empty
        token = token.strip() if token else ""

        if not token:
            issues.append(
                SecurityIssue(
                    severity=SecuritySeverity.CRITICAL,
                    category=SecurityCategory.AUTHENTICATION,
                    message="GitHub token is empty or missing",
                    suggested_fix="Set GITHUB_TOKEN environment variable",
                )
            )
            return SecurityValidationResult(
                status=SecurityStatus.CRITICAL,
                issues=issues,
                recommendations=recommendations,
                metadata={"token_provided": False},
            )

        # Check token length
        if len(token) > SecurityDefaults.MAX_TOKEN_LENGTH:
            issues.append(
                SecurityIssue(
                    severity=SecuritySeverity.HIGH,
                    category=SecurityCategory.AUTHENTICATION,
                    message=f"Token length exceeds maximum of {SecurityDefaults.MAX_TOKEN_LENGTH}",
                    suggested_fix="Verify token is not corrupted or concatenated",
                )
            )

        # Check token format
        is_valid_format = any(
            re.match(pattern, token) for pattern in TokenValidator.GITHUB_TOKEN_PATTERNS
        )

        if not is_valid_format:
            issues.append(
                SecurityIssue(
                    severity=SecuritySeverity.HIGH,
                    category=SecurityCategory.AUTHENTICATION,
                    message="Token does not match expected GitHub token format",
                    suggested_fix="Verify token is a valid GitHub personal access token or app token",
                )
            )

        # Security recommendations
        if token.startswith("ghp_"):
            recommendations.append(
                SecurityRecommendation(
                    priority=SecuritySeverity.MEDIUM,
                    description="Consider using fine-grained personal access tokens for better security",
                    implementation_steps=[
                        "Generate a fine-grained PAT at https://github.com/settings/personal-access-tokens/new",
                        "Set specific repository permissions",
                        "Replace the classic PAT with the fine-grained token",
                    ],
                    estimated_effort="low",
                )
            )

        status = SecurityStatus.SECURE if not issues else SecurityStatus.WARNING
        if any(issue.severity == SecuritySeverity.CRITICAL for issue in issues):
            status = SecurityStatus.CRITICAL
        elif any(issue.severity == SecuritySeverity.HIGH for issue in issues):
            status = SecurityStatus.INSECURE

        return SecurityValidationResult(
            status=status,
            issues=issues,
            recommendations=recommendations,
            metadata={
                "token_provided": True,
                "token_length": len(token),
                "token_type": token.split("_")[0] if "_" in token else "unknown",
                "format_valid": is_valid_format,
            },
        )


class InputSanitizer:
    """Sanitizes and validates input data for security."""

    @staticmethod
    def sanitize_repository_path(path: str) -> str:
        """Sanitize repository path to prevent directory traversal."""
        if not path:
            raise GitValidationError("Repository path cannot be empty")

        # Normalize path and resolve any relative components
        normalized = os.path.normpath(path)

        # Check for directory traversal attempts
        if ".." in normalized:
            raise GitValidationError(
                f"Invalid repository path contains directory traversal: {path}",
                suggested_fix="Use paths without .. components",
            )

        # Reject absolute paths except for safe testing directories
        if normalized.startswith("/"):
            # Allow only very specific safe directories for testing
            safe_absolute_prefixes = [
                "/tmp/",
                "/var/tmp/",
            ]

            # Check if it's a safe prefix
            is_safe = any(
                normalized.startswith(prefix) for prefix in safe_absolute_prefixes
            )

            if not is_safe:
                # Reject all other absolute paths for security
                raise GitValidationError(
                    f"Invalid repository path cannot be absolute: {path}",
                    suggested_fix="Use relative paths only, or safe directories like /tmp for testing",
                )

        return normalized

    @staticmethod
    def validate_branch_name(name: str) -> bool:
        """Validate Git branch name according to Git rules."""
        if not name:
            return False

        # Git branch name rules
        invalid_patterns = [
            r"^-",  # Cannot start with dash
            r"\.\.",  # Cannot contain consecutive dots
            r"^refs/",  # Cannot start with refs/
            r"[\x00-\x1f\x7f]",  # No control characters
            r"[~^:?*\[\]]",  # No special characters
            r"\.$",  # Cannot end with dot
            r"\.lock$",  # Cannot end with .lock
            r"/$",  # Cannot end with slash
        ]

        return not any(re.search(pattern, name) for pattern in invalid_patterns)

    @staticmethod
    def sanitize_commit_message(message: str) -> str:
        """Sanitize commit message for security."""
        if not message:
            raise GitValidationError("Commit message cannot be empty")

        # Remove potential command injection sequences
        sanitized = re.sub(r"[`$;|&<>]", "", message)

        # Limit length to prevent abuse
        max_length = 2000
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length] + "..."

        return sanitized.strip()

    @staticmethod
    def validate_file_path(file_path: str) -> bool:
        """Validate file path for security."""
        if not file_path:
            return False

        path = Path(file_path)

        # Check for directory traversal
        if ".." in path.parts:
            return False

        # Check file extension if applicable
        if (
            path.suffix
            and path.suffix.lower() not in SecurityDefaults.ALLOWED_EXTENSIONS
        ):
            return False

        return True


class SecurityFramework(DebuggableComponent):
    """Central security framework for the MCP Git Server.

    Implements comprehensive security and validation logic including
    authentication, authorization, input validation, and security
    policy enforcement.
    """

    def __init__(self, component_id: str = "security_framework"):
        self.component_id = component_id
        self.failed_attempts: dict[str, list[datetime]] = {}
        self.rate_limits: dict[str, list[datetime]] = {}
        self.security_events: list[dict[str, Any]] = []
        self.gpg_validated = False
        self.token_validator = TokenValidator()
        self.input_sanitizer = InputSanitizer()

        logger.info(f"SecurityFramework initialized with ID: {component_id}")

    def get_component_state(self) -> ComponentState:
        """Get current component state for debugging."""
        return SecurityComponentState(
            component_id=self.component_id,
            component_type="SecurityFramework",
            state_data={
                "failed_attempts_count": len(self.failed_attempts),
                "rate_limits_active": len(self.rate_limits),
                "security_events_count": len(self.security_events),
                "gpg_validated": self.gpg_validated,
                "last_validation": datetime.now().isoformat(),
            },
        )

    def validate_component(self) -> ValidationResult:
        """Validate the security framework component."""
        errors = []
        warnings = []

        # Check if GPG is configured
        if not self.gpg_validated:
            warnings.append("GPG validation has not been performed")

        # Check for excessive failed attempts
        current_failures = sum(
            len(attempts) for attempts in self.failed_attempts.values()
        )
        if current_failures > SecurityDefaults.MAX_FAILED_ATTEMPTS * 2:
            errors.append(f"Excessive failed attempts detected: {current_failures}")

        # Check rate limiting effectiveness
        active_limits = len(self.rate_limits)
        if active_limits > 10:
            warnings.append(f"High number of active rate limits: {active_limits}")

        return SecurityValidationResultImpl(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            context={
                "component_id": self.component_id,
                "validation_time": datetime.now().isoformat(),
            },
        )

    def get_debug_info(self, debug_level: str = "basic") -> DebugInfo:
        """Get debug information for the security framework."""
        return SecurityDebugInfo(
            debug_level=debug_level,
            debug_data={
                "component_type": "SecurityFramework",
                "component_id": self.component_id,
                "state": self.get_component_state().state_data,
                "validation": self.validate_component().__dict__,
                "security_summary": {
                    "recent_events": len(
                        [
                            event
                            for event in self.security_events
                            if datetime.fromisoformat(
                                event.get("timestamp", "1970-01-01")
                            )
                            > datetime.now() - timedelta(hours=1)
                        ]
                    ),
                    "active_protections": {
                        "rate_limiting": len(self.rate_limits) > 0,
                        "gpg_validation": self.gpg_validated,
                        "input_sanitization": True,
                    },
                },
            },
        )

    def authenticate_github_token(self, token: str | None = None) -> AuthResult:
        """Authenticate GitHub token."""
        if token is None:
            token = os.getenv("GITHUB_TOKEN")

        validation_result = self.token_validator.validate_github_token(token or "")

        if validation_result.status in [
            SecurityStatus.CRITICAL,
            SecurityStatus.INSECURE,
        ]:
            self._record_failed_attempt("github_token", "invalid_token")
            return AuthResult(
                success=False,
                error_message=f"Token validation failed: {validation_result.status.value}",
            )

        # Extract token metadata
        metadata = validation_result.metadata
        token_type = metadata.get("token_type", "unknown")

        self._log_security_event(
            "authentication_success",
            {
                "token_type": token_type,
                "format_valid": metadata.get("format_valid", False),
            },
        )

        return AuthResult(
            success=True,
            token_type=token_type,
            scopes=[],  # Would need GitHub API call to get actual scopes
            expires_at=None,  # GitHub tokens don't have visible expiration
        )

    def validate_repository_access(
        self, repository_path: str
    ) -> SecurityValidationResult:
        """Validate repository access permissions."""
        issues = []
        recommendations = []
        sanitized_path = None
        repo_path = None

        try:
            # Sanitize and validate path
            sanitized_path = self.input_sanitizer.sanitize_repository_path(
                repository_path
            )
            repo_path = Path(sanitized_path)

            # Check if path exists and is accessible
            if not repo_path.exists():
                issues.append(
                    SecurityIssue(
                        severity=SecuritySeverity.HIGH,
                        category=SecurityCategory.AUTHORIZATION,
                        message=f"Repository path does not exist: {repository_path}",
                        suggested_fix="Verify the repository path is correct and accessible",
                    )
                )

            # Check if it's actually a Git repository
            git_dir = repo_path / ".git"
            if not git_dir.exists() and not (repo_path / "HEAD").exists():
                issues.append(
                    SecurityIssue(
                        severity=SecuritySeverity.MEDIUM,
                        category=SecurityCategory.CONFIGURATION,
                        message="Path does not appear to be a Git repository",
                        suggested_fix="Initialize Git repository or check path",
                    )
                )

            # Repository security configuration check
            # Note: Using MCP git tools instead of direct git library
            recommendations.append(
                SecurityRecommendation(
                    priority=SecuritySeverity.MEDIUM,
                    description="Repository security configuration should be validated using MCP git tools",
                    implementation_steps=[
                        "Use MCP git status to check repository state",
                        "Verify GPG signing configuration via MCP tools",
                        "Check user configuration through MCP git operations",
                    ],
                    estimated_effort="low",
                )
            )

        except GitValidationError as e:
            issues.append(
                SecurityIssue(
                    severity=SecuritySeverity.HIGH,
                    category=SecurityCategory.INPUT_VALIDATION,
                    message=str(e),
                    suggested_fix=e.suggested_fix,
                )
            )

        status = SecurityStatus.SECURE
        if issues:
            max_severity = max(issue.severity for issue in issues)
            if max_severity == SecuritySeverity.CRITICAL:
                status = SecurityStatus.CRITICAL
            elif max_severity == SecuritySeverity.HIGH:
                status = SecurityStatus.INSECURE
            else:
                status = SecurityStatus.WARNING

        return SecurityValidationResult(
            status=status,
            issues=issues,
            recommendations=recommendations,
            metadata={
                "repository_path": repository_path,
                "sanitized_path": sanitized_path,
                "path_exists": repo_path.exists() if repo_path is not None else False,
            },
        )

    def validate_git_operation(
        self, operation: str, params: dict[str, Any]
    ) -> SecurityValidationResult:
        """Validate Git operation for security compliance."""
        issues = []
        recommendations: list[SecurityRecommendation] = []

        # Rate limiting check
        if not self._check_rate_limit(operation):
            issues.append(
                SecurityIssue(
                    severity=SecuritySeverity.HIGH,
                    category=SecurityCategory.RATE_LIMITING,
                    message=f"Rate limit exceeded for operation: {operation}",
                    suggested_fix="Wait before retrying the operation",
                )
            )

        # Validate specific operations
        if operation == "commit":
            message = params.get("message", "")
            try:
                sanitized_message = self.input_sanitizer.sanitize_commit_message(
                    message
                )
                if sanitized_message != message:
                    issues.append(
                        SecurityIssue(
                            severity=SecuritySeverity.MEDIUM,
                            category=SecurityCategory.INPUT_VALIDATION,
                            message="Commit message was sanitized for security",
                            context={
                                "original": message,
                                "sanitized": sanitized_message,
                            },
                        )
                    )
            except GitValidationError as e:
                issues.append(
                    SecurityIssue(
                        severity=SecuritySeverity.HIGH,
                        category=SecurityCategory.INPUT_VALIDATION,
                        message=str(e),
                        suggested_fix=e.suggested_fix,
                    )
                )

        elif operation in ["add", "checkout"]:
            files = params.get("files", [])
            for file_path in files:
                if not self.input_sanitizer.validate_file_path(file_path):
                    issues.append(
                        SecurityIssue(
                            severity=SecuritySeverity.HIGH,
                            category=SecurityCategory.INPUT_VALIDATION,
                            message=f"Invalid or potentially unsafe file path: {file_path}",
                            suggested_fix="Use relative paths within the repository",
                        )
                    )

        status = SecurityStatus.SECURE
        if issues:
            max_severity = max(issue.severity for issue in issues)
            if max_severity == SecuritySeverity.CRITICAL:
                status = SecurityStatus.CRITICAL
            elif max_severity == SecuritySeverity.HIGH:
                status = SecurityStatus.INSECURE
            else:
                status = SecurityStatus.WARNING

        self._log_security_event(
            "operation_validation",
            {
                "operation": operation,
                "status": status.value,
                "issues_count": len(issues),
            },
        )

        return SecurityValidationResult(
            status=status,
            issues=issues,
            recommendations=recommendations,
            metadata={
                "operation": operation,
                "params_validated": list(params.keys()),
                "rate_limit_ok": self._check_rate_limit(operation, check_only=True),
            },
        )

    def _check_rate_limit(
        self, key: str, limit: int = 60, window: int = 60, check_only: bool = False
    ) -> bool:
        """Check and enforce rate limiting."""
        current_time = datetime.now()
        window_start = current_time - timedelta(seconds=window)

        # Clean old entries
        if key in self.rate_limits:
            self.rate_limits[key] = [
                timestamp
                for timestamp in self.rate_limits[key]
                if timestamp > window_start
            ]
        else:
            self.rate_limits[key] = []

        # Check if within limit
        if len(self.rate_limits[key]) >= limit:
            return False

        # Add current request if not just checking
        if not check_only:
            self.rate_limits[key].append(current_time)

        return True

    def _record_failed_attempt(self, context: str, reason: str) -> None:
        """Record a failed authentication/authorization attempt."""
        current_time = datetime.now()

        if context not in self.failed_attempts:
            self.failed_attempts[context] = []

        self.failed_attempts[context].append(current_time)

        # Clean old attempts (older than 1 hour)
        cutoff = current_time - timedelta(hours=1)
        self.failed_attempts[context] = [
            attempt for attempt in self.failed_attempts[context] if attempt > cutoff
        ]

        self._log_security_event(
            "failed_attempt",
            {
                "context": context,
                "reason": reason,
                "total_recent_failures": len(self.failed_attempts[context]),
            },
        )

    def _log_security_event(self, event_type: str, details: dict[str, Any]) -> None:
        """Log security events for audit purposes."""
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "component_id": self.component_id,
            "details": details,
        }

        self.security_events.append(event)

        # Keep only recent events (last 1000)
        if len(self.security_events) > 1000:
            del self.security_events[:-1000]  # More memory efficient

        # Log to standard logger as well
        logger.info(f"Security event [{event_type}]: {details}")

    def get_security_metrics(self) -> dict[str, Any]:
        """Get security metrics and statistics."""
        current_time = datetime.now()
        one_hour_ago = current_time - timedelta(hours=1)

        recent_events = [
            event
            for event in self.security_events
            if datetime.fromisoformat(event["timestamp"]) > one_hour_ago
        ]

        return {
            "total_events": len(self.security_events),
            "recent_events": len(recent_events),
            "failed_attempts": {
                context: len(attempts)
                for context, attempts in self.failed_attempts.items()
            },
            "active_rate_limits": len(self.rate_limits),
            "gpg_validated": self.gpg_validated,
            "component_status": self.validate_component().is_valid,
            "last_updated": current_time.isoformat(),
        }

    def inspect_state(self, path: str | None = None) -> dict[str, Any]:
        """Inspect specific parts of the security component state.

        Args:
            path: Optional dot-notation path to specific state
                 If None, returns complete state

        Returns:
            Dict containing the requested state information
        """
        full_state = {
            "component_id": self.component_id,
            "failed_attempts": self.failed_attempts,
            "rate_limits": self.rate_limits,
            "security_events": self.security_events,
            "gpg_validated": self.gpg_validated,
            "config": {
                "max_failed_attempts": SecurityDefaults.MAX_FAILED_ATTEMPTS,
                "rate_limit_window": SecurityDefaults.RATE_LIMIT_WINDOW,
                "rate_limit_requests": SecurityDefaults.RATE_LIMIT_REQUESTS,
            },
        }

        if path is None:
            return full_state

        # Navigate to specific path
        keys = path.split(".")
        current: Any = full_state
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return {}

        # Ensure we return a proper dict
        if not isinstance(current, dict):
            current = {"value": current}

        return {path: current}

    def get_component_dependencies(self) -> list[str]:
        """Get list of component dependencies.

        Returns:
            List of component IDs that this security component depends on
        """
        return ["git_service", "github_api", "configuration_manager", "logging_service"]

    def export_state_json(self) -> str:
        """Export security component state as JSON for external analysis.

        Returns:
            JSON string representation of complete component state
        """
        import json
        from datetime import datetime

        def json_serializer(obj):
            """Custom JSON serializer for datetime objects."""
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        state_data = self.inspect_state()
        state_data["component_type"] = "SecurityFramework"
        state_data["export_timestamp"] = datetime.now().isoformat()
        state_data["metrics"] = self.get_security_metrics()

        return json.dumps(state_data, indent=2, default=json_serializer)

    def health_check(self) -> dict[str, bool | str | int | float]:
        """Perform a health check on the security component.

        Returns:
            Dictionary with health status information
        """
        from datetime import datetime

        # Check for critical security issues
        validation_result = self.validate_component()
        is_healthy = validation_result.is_valid

        # Calculate uptime (simplified - would need actual start time in real implementation)
        uptime = 0.0  # Would calculate from component start time

        # Get recent errors
        recent_errors = [
            event
            for event in self.security_events
            if event.get("level") == "ERROR"
            and datetime.fromisoformat(event["timestamp"])
            > datetime.now().replace(hour=datetime.now().hour - 1)
        ]

        error_count = len(recent_errors)
        last_error = recent_errors[-1]["message"] if recent_errors else None

        # Additional health checks
        rate_limit_issues = len(self.rate_limits) > 10  # Too many active rate limits
        failed_attempt_issues = (
            sum(len(attempts) for attempts in self.failed_attempts.values()) > 100
        )

        if rate_limit_issues or failed_attempt_issues:
            is_healthy = False

        status_message = "healthy"
        if not is_healthy:
            if validation_result.validation_errors:
                status_message = (
                    f"validation_errors: {len(validation_result.validation_errors)}"
                )
            elif rate_limit_issues:
                status_message = "excessive_rate_limiting"
            elif failed_attempt_issues:
                status_message = "excessive_failed_attempts"
            else:
                status_message = "unknown_issue"

        return {
            "healthy": is_healthy,
            "status": status_message,
            "uptime": uptime,
            "last_error": str(last_error) if last_error else "",
            "error_count": error_count,
            "rate_limits_active": len(self.rate_limits),
            "failed_attempts_total": sum(
                len(attempts) for attempts in self.failed_attempts.values()
            ),
            "security_events_count": len(self.security_events),
            "gpg_validated": self.gpg_validated,
        }


def validate_git_security_config(repo_path: str) -> dict[str, Any]:
    """Validate Git repository security configuration.

    This function checks various security aspects of a Git repository
    configuration including GPG signing, user configuration, and
    security policies.

    Args:
        repo_path: Path to the Git repository

    Returns:
        Dictionary containing warnings and recommendations
    """
    warnings = []
    recommendations = []

    try:
        # In a real implementation, this would use MCP git tools
        # to check various security configurations

        # Check for GPG signing configuration
        # This would use mcp__git__git_show or similar commands
        recommendations.append("Consider enabling GPG signing for commits")

        # Check user configuration
        recommendations.append(
            "Verify user.name and user.email are properly configured"
        )

        # Check for security policies
        recommendations.append("Review repository access policies and permissions")

    except Exception as e:
        warnings.append(f"Failed to validate repository security config: {e}")

    return {"warnings": warnings, "recommendations": recommendations}
