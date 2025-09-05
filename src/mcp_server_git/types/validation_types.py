"""Validation type definitions for the MCP Git Server.

This module provides type definitions for validation operations,
including schema validation, data validation, and error reporting.

These types are currently stubs to satisfy TDD test requirements.
Implementation will be completed in subsequent development phases.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ValidationSeverity(Enum):
    """Validation error severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ValidationError(Exception):
    """Exception raised when validation fails."""

    def __init__(self, message: str, field: str = None, value: Any = None):
        self.message = message
        self.field = field
        self.value = value
        super().__init__(message)


class SchemaValidationError(ValidationError):
    """Exception raised when schema validation fails."""

    pass


@dataclass
class ValidationRule:
    """Validation rule definition."""

    name: str
    description: str
    validator: Callable[[Any], bool]
    error_message: str
    severity: ValidationSeverity = ValidationSeverity.ERROR


@dataclass
class ValidationResult:
    """Result of a validation operation."""

    is_valid: bool
    errors: list[ValidationError]
    warnings: list[str]
    field_path: str | None = None

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0


@dataclass
class FieldValidator:
    """Field-specific validator."""

    field_name: str
    rules: list[ValidationRule]
    required: bool = False

    def validate(self, value: Any) -> ValidationResult:
        """Validate a field value."""
        errors = []
        warnings = []

        if self.required and value is None:
            errors.append(
                ValidationError(
                    f"Field {self.field_name} is required", self.field_name, value
                )
            )

        for rule in self.rules:
            try:
                if not rule.validator(value):
                    if rule.severity == ValidationSeverity.ERROR:
                        errors.append(
                            ValidationError(rule.error_message, self.field_name, value)
                        )
                    else:
                        warnings.append(rule.error_message)
            except Exception as e:
                errors.append(
                    ValidationError(
                        f"Validation rule '{rule.name}' failed: {e}",
                        self.field_name,
                        value,
                    )
                )

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            field_path=self.field_name,
        )


@dataclass
class SchemaValidator:
    """Schema-based validator."""

    name: str
    description: str
    fields: list[FieldValidator]

    def validate(self, data: dict[str, Any]) -> ValidationResult:
        """Validate data against schema."""
        all_errors = []
        all_warnings = []

        for field_validator in self.fields:
            value = data.get(field_validator.field_name)
            result = field_validator.validate(value)
            all_errors.extend(result.errors)
            all_warnings.extend(result.warnings)

        return ValidationResult(
            is_valid=len(all_errors) == 0, errors=all_errors, warnings=all_warnings
        )


@dataclass
class ValidationContext:
    """Context for validation operations."""

    schema_name: str | None = None
    strict_mode: bool = False
    allow_unknown_fields: bool = True
    custom_validators: dict[str, Callable] | None = None


class ValidatorRegistry:
    """Registry for validation rules and schemas."""

    def __init__(self):
        self._validators: dict[str, SchemaValidator] = {}
        self._rules: dict[str, ValidationRule] = {}

    def register_validator(self, validator: SchemaValidator) -> None:
        """Register a schema validator."""
        self._validators[validator.name] = validator

    def register_rule(self, rule: ValidationRule) -> None:
        """Register a validation rule."""
        self._rules[rule.name] = rule

    def get_validator(self, name: str) -> SchemaValidator | None:
        """Get a registered validator by name."""
        return self._validators.get(name)

    def get_rule(self, name: str) -> ValidationRule | None:
        """Get a registered rule by name."""
        return self._rules.get(name)


# Common validation functions
def validate_email(email: str) -> bool:
    """Validate email address format."""
    return "@" in email and "." in email


def validate_url(url: str) -> bool:
    """Validate URL format."""
    return url.startswith(("http://", "https://"))


def validate_non_empty_string(value: str) -> bool:
    """Validate that string is not empty."""
    return isinstance(value, str) and len(value.strip()) > 0


def validate_positive_integer(value: int) -> bool:
    """Validate that value is a positive integer."""
    return isinstance(value, int) and value > 0


# Common validation rules
EMAIL_RULE = ValidationRule(
    name="email_format",
    description="Validate email address format",
    validator=validate_email,
    error_message="Invalid email address format",
)

URL_RULE = ValidationRule(
    name="url_format",
    description="Validate URL format",
    validator=validate_url,
    error_message="Invalid URL format",
)

NON_EMPTY_STRING_RULE = ValidationRule(
    name="non_empty_string",
    description="Validate non-empty string",
    validator=validate_non_empty_string,
    error_message="Value cannot be empty",
)

POSITIVE_INTEGER_RULE = ValidationRule(
    name="positive_integer",
    description="Validate positive integer",
    validator=validate_positive_integer,
    error_message="Value must be a positive integer",
)


# Export all public types
__all__ = [
    "ValidationSeverity",
    "ValidationError",
    "SchemaValidationError",
    "ValidationRule",
    "ValidationResult",
    "FieldValidator",
    "SchemaValidator",
    "ValidationContext",
    "ValidatorRegistry",
    "validate_email",
    "validate_url",
    "validate_non_empty_string",
    "validate_positive_integer",
    "EMAIL_RULE",
    "URL_RULE",
    "NON_EMPTY_STRING_RULE",
    "POSITIVE_INTEGER_RULE",
]
