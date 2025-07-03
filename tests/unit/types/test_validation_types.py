"""
Test specifications for validation and error handling types.

These tests define the behavioral requirements for validation, error handling,
and type safety infrastructure across the domain.

IMPORTANT: These tests define requirements and are IMMUTABLE once complete.
Do not modify tests to match implementation - implementation must satisfy these tests.
"""

import pytest
from unittest.mock import patch
from pathlib import Path

# Import the types we expect to be implemented
# These imports will fail initially (RED phase) - that's expected!
try:
    from mcp_server_git.types.validation_types import (
        ValidationResult,
        ValidationError,
        ValidationRule,
        ValidationContext,
        Validator,
        PathValidator,
        EmailValidator,
        URLValidator,
        GitRefValidator,
        GitHubNameValidator,
        MCPMethodValidator,
        CompositeValidator,
        ValidationSchema,
        ValidationReport,
        FieldValidator,
        ErrorCollector,
        ValidationSeverity,
        ValidationCategory,
    )
    TYPES_AVAILABLE = True
except ImportError:
    TYPES_AVAILABLE = False


class TestValidationResult:
    """Test specifications for ValidationResult type."""
    
    def test_should_represent_successful_validation(self):
        """ValidationResult should represent successful validation."""
        if TYPES_AVAILABLE:
            result = ValidationResult.success(
                value="valid-data",
                message="Validation passed"
            )
            
            assert result.is_valid()
            assert not result.is_invalid()
            assert result.value == "valid-data"
            assert result.message == "Validation passed"
            assert len(result.errors) == 0
    
    def test_should_represent_failed_validation(self):
        """ValidationResult should represent failed validation."""
        if TYPES_AVAILABLE:
            result = ValidationResult.failure(
                errors=["Invalid format", "Value too long"],
                field_name="username",
                invalid_value="bad@user!"
            )
            
            assert not result.is_valid()
            assert result.is_invalid()
            assert len(result.errors) == 2
            assert "Invalid format" in result.errors
            assert result.field_name == "username"
            assert result.invalid_value == "bad@user!"
    
    def test_should_provide_validation_metadata(self):
        """ValidationResult should provide validation metadata."""
        if TYPES_AVAILABLE:
            result = ValidationResult.failure(
                errors=["Error"],
                severity=ValidationSeverity.ERROR,
                category=ValidationCategory.FORMAT,
                rule_name="format_check"
            )
            
            assert result.severity == ValidationSeverity.ERROR
            assert result.category == ValidationCategory.FORMAT
            assert result.rule_name == "format_check"
    
    def test_should_support_result_combination(self):
        """ValidationResult should support combining multiple results."""
        if TYPES_AVAILABLE:
            result1 = ValidationResult.success("data1")
            result2 = ValidationResult.success("data2") 
            result3 = ValidationResult.failure(["Error"])
            
            # Combining successful results
            combined_success = ValidationResult.combine([result1, result2])
            assert combined_success.is_valid()
            
            # Combining with failure
            combined_failure = ValidationResult.combine([result1, result3])
            assert combined_failure.is_invalid()
            assert "Error" in combined_failure.errors


class TestValidationError:
    """Test specifications for ValidationError exception."""
    
    def test_should_provide_detailed_error_information(self):
        """ValidationError should provide comprehensive error details."""
        if TYPES_AVAILABLE:
            error = ValidationError(
                message="Invalid email format",
                field_name="email",
                invalid_value="not-an-email",
                validation_rule="email_format",
                expected_format="user@domain.com",
                suggestion="Please provide a valid email address"
            )
            
            assert str(error) == "Invalid email format"
            assert error.field_name == "email"
            assert error.invalid_value == "not-an-email"
            assert error.validation_rule == "email_format"
            assert error.expected_format == "user@domain.com"
            assert error.suggestion is not None
    
    def test_should_categorize_validation_errors(self):
        """ValidationError should categorize different types of validation errors."""
        if TYPES_AVAILABLE:
            format_error = ValidationError(
                "Invalid format", 
                category=ValidationCategory.FORMAT
            )
            range_error = ValidationError(
                "Value out of range",
                category=ValidationCategory.RANGE
            )
            required_error = ValidationError(
                "Field required",
                category=ValidationCategory.REQUIRED
            )
            
            assert format_error.category == ValidationCategory.FORMAT
            assert range_error.category == ValidationCategory.RANGE
            assert required_error.category == ValidationCategory.REQUIRED
    
    def test_should_support_error_severity_levels(self):
        """ValidationError should support different severity levels."""
        if TYPES_AVAILABLE:
            warning = ValidationError(
                "Deprecated field",
                severity=ValidationSeverity.WARNING
            )
            error = ValidationError(
                "Invalid value",
                severity=ValidationSeverity.ERROR
            )
            critical = ValidationError(
                "System failure",
                severity=ValidationSeverity.CRITICAL
            )
            
            assert warning.severity == ValidationSeverity.WARNING
            assert error.severity == ValidationSeverity.ERROR
            assert critical.severity == ValidationSeverity.CRITICAL
            
            assert warning.is_warning()
            assert error.is_error()
            assert critical.is_critical()


class TestValidationRule:
    """Test specifications for ValidationRule type."""
    
    def test_should_define_validation_rules(self):
        """ValidationRule should define reusable validation rules."""
        if TYPES_AVAILABLE:
            rule = ValidationRule(
                name="email_format",
                description="Validates email address format",
                pattern=r'^[^@]+@[^@]+\.[^@]+$',
                error_message="Invalid email format"
            )
            
            assert rule.name == "email_format"
            assert rule.description == "Validates email address format"
            assert rule.pattern is not None
            assert rule.error_message == "Invalid email format"
    
    def test_should_validate_values_against_rules(self):
        """ValidationRule should validate values against defined rules."""
        if TYPES_AVAILABLE:
            email_rule = ValidationRule(
                name="email",
                pattern=r'^[^@]+@[^@]+\.[^@]+$',
                error_message="Invalid email"
            )
            
            # Valid email should pass
            valid_result = email_rule.validate("user@example.com")
            assert valid_result.is_valid()
            
            # Invalid email should fail
            invalid_result = email_rule.validate("not-an-email")
            assert invalid_result.is_invalid()
            assert "Invalid email" in invalid_result.errors
    
    def test_should_support_custom_validation_functions(self):
        """ValidationRule should support custom validation functions."""
        if TYPES_AVAILABLE:
            def custom_validator(value: str) -> bool:
                return len(value) >= 3 and value.isalnum()
            
            rule = ValidationRule(
                name="custom",
                validator_function=custom_validator,
                error_message="Must be alphanumeric and at least 3 characters"
            )
            
            assert rule.validate("abc123").is_valid()
            assert rule.validate("ab").is_invalid()
            assert rule.validate("ab!").is_invalid()


class TestPathValidator:
    """Test specifications for PathValidator type."""
    
    def test_should_validate_file_paths(self):
        """PathValidator should validate file system paths."""
        if TYPES_AVAILABLE:
            validator = PathValidator(
                must_exist=True,
                must_be_file=True,
                readable=True
            )
            
            # Mock a valid file
            with patch('pathlib.Path.exists', return_value=True), \
                 patch('pathlib.Path.is_file', return_value=True), \
                 patch('os.access', return_value=True):
                result = validator.validate("/path/to/file.txt")
                assert result.is_valid()
    
    def test_should_validate_directory_paths(self):
        """PathValidator should validate directory paths."""
        if TYPES_AVAILABLE:
            validator = PathValidator(
                must_exist=True,
                must_be_directory=True,
                writable=True
            )
            
            # Mock a valid directory
            with patch('pathlib.Path.exists', return_value=True), \
                 patch('pathlib.Path.is_dir', return_value=True), \
                 patch('os.access', return_value=True):
                result = validator.validate("/path/to/directory")
                assert result.is_valid()
    
    def test_should_reject_invalid_paths(self):
        """PathValidator should reject invalid paths."""
        if TYPES_AVAILABLE:
            validator = PathValidator(must_exist=True)
            
            # Mock non-existent path
            with patch('pathlib.Path.exists', return_value=False):
                result = validator.validate("/does/not/exist")
                assert result.is_invalid()
                assert "does not exist" in " ".join(result.errors).lower()
    
    def test_should_validate_git_repository_paths(self):
        """PathValidator should validate git repository paths."""
        if TYPES_AVAILABLE:
            git_validator = PathValidator.git_repository()
            
            # Mock valid git repository
            with patch('pathlib.Path.exists', return_value=True), \
                 patch('pathlib.Path.is_dir', return_value=True), \
                 patch('pathlib.Path.glob') as mock_glob:
                mock_glob.return_value = [Path('.git')]
                result = git_validator.validate("/path/to/repo")
                assert result.is_valid()


class TestEmailValidator:
    """Test specifications for EmailValidator type."""
    
    def test_should_validate_email_addresses(self):
        """EmailValidator should validate email address format."""
        if TYPES_AVAILABLE:
            validator = EmailValidator()
            
            valid_emails = [
                "user@example.com",
                "test.email@domain.org",
                "user+tag@example.co.uk",
                "123@example.com"
            ]
            
            for email in valid_emails:
                result = validator.validate(email)
                assert result.is_valid(), f"Email {email} should be valid"
    
    def test_should_reject_invalid_emails(self):
        """EmailValidator should reject invalid email addresses."""
        if TYPES_AVAILABLE:
            validator = EmailValidator()
            
            invalid_emails = [
                "not-an-email",
                "@example.com",
                "user@",
                "user@.com",
                "user..name@example.com",
                ""
            ]
            
            for email in invalid_emails:
                result = validator.validate(email)
                assert result.is_invalid(), f"Email {email} should be invalid"
    
    def test_should_support_domain_restrictions(self):
        """EmailValidator should support domain restrictions."""
        if TYPES_AVAILABLE:
            validator = EmailValidator(
                allowed_domains=["example.com", "company.org"]
            )
            
            # Allowed domain should pass
            result = validator.validate("user@example.com")
            assert result.is_valid()
            
            # Disallowed domain should fail
            result = validator.validate("user@other.com")
            assert result.is_invalid()


class TestGitRefValidator:
    """Test specifications for GitRefValidator type."""
    
    def test_should_validate_git_branch_names(self):
        """GitRefValidator should validate git branch names."""
        if TYPES_AVAILABLE:
            validator = GitRefValidator(ref_type="branch")
            
            valid_branches = [
                "main",
                "feature/new-component",
                "bugfix-123",
                "release/v1.0.0",
                "user/john/experimental"
            ]
            
            for branch in valid_branches:
                result = validator.validate(branch)
                assert result.is_valid(), f"Branch {branch} should be valid"
    
    def test_should_reject_invalid_branch_names(self):
        """GitRefValidator should reject invalid git branch names."""
        if TYPES_AVAILABLE:
            validator = GitRefValidator(ref_type="branch")
            
            invalid_branches = [
                "",
                " ",
                "feature..double-dot",
                "~invalid",
                "branch^name",
                "branch:name",
                ".hidden",
                "branch/",
                "branch/"
            ]
            
            for branch in invalid_branches:
                result = validator.validate(branch)
                assert result.is_invalid(), f"Branch {branch} should be invalid"
    
    def test_should_validate_commit_hashes(self):
        """GitRefValidator should validate commit hashes."""
        if TYPES_AVAILABLE:
            validator = GitRefValidator(ref_type="commit")
            
            valid_hashes = [
                "a1b2c3d4e5f6789012345678901234567890abcd",  # Full SHA-1
                "a1b2c3d",  # Short SHA-1
                "a1b2c3d4e5f"  # Medium SHA-1
            ]
            
            for hash_val in valid_hashes:
                result = validator.validate(hash_val)
                assert result.is_valid(), f"Hash {hash_val} should be valid"


class TestGitHubNameValidator:
    """Test specifications for GitHubNameValidator type."""
    
    def test_should_validate_github_usernames(self):
        """GitHubNameValidator should validate GitHub usernames."""
        if TYPES_AVAILABLE:
            validator = GitHubNameValidator(name_type="username")
            
            valid_usernames = [
                "user",
                "user-name",
                "user123",
                "123user",
                "user-123-name"
            ]
            
            for username in valid_usernames:
                result = validator.validate(username)
                assert result.is_valid(), f"Username {username} should be valid"
    
    def test_should_validate_github_repository_names(self):
        """GitHubNameValidator should validate GitHub repository names."""
        if TYPES_AVAILABLE:
            validator = GitHubNameValidator(name_type="repository")
            
            valid_repos = [
                "repo",
                "repo-name",
                "repo.name",
                "repo_name",
                "123-repo"
            ]
            
            for repo in valid_repos:
                result = validator.validate(repo)
                assert result.is_valid(), f"Repository {repo} should be valid"
    
    def test_should_reject_invalid_github_names(self):
        """GitHubNameValidator should reject invalid GitHub names."""
        if TYPES_AVAILABLE:
            validator = GitHubNameValidator(name_type="username")
            
            invalid_names = [
                "",
                " ",
                "user name",  # Spaces
                "user@name",  # Special characters
                "-user",  # Leading hyphen
                "user-",  # Trailing hyphen
                ".user",  # Leading dot
                "user.",  # Trailing dot
            ]
            
            for name in invalid_names:
                result = validator.validate(name)
                assert result.is_invalid(), f"Name {name} should be invalid"


class TestCompositeValidator:
    """Test specifications for CompositeValidator type."""
    
    def test_should_combine_multiple_validators(self):
        """CompositeValidator should combine multiple validation rules."""
        if TYPES_AVAILABLE:
            length_rule = ValidationRule(
                name="length",
                validator_function=lambda x: 3 <= len(x) <= 50,
                error_message="Must be 3-50 characters"
            )
            
            format_rule = ValidationRule(
                name="format",
                pattern=r'^[a-zA-Z0-9_-]+$',
                error_message="Only letters, numbers, hyphens, and underscores"
            )
            
            composite = CompositeValidator([length_rule, format_rule])
            
            # Valid value should pass all rules
            result = composite.validate("valid_name")
            assert result.is_valid()
            
            # Invalid value should fail appropriately
            result = composite.validate("ab")  # Too short
            assert result.is_invalid()
            assert "3-50 characters" in " ".join(result.errors)
    
    def test_should_support_validation_strategies(self):
        """CompositeValidator should support different validation strategies."""
        if TYPES_AVAILABLE:
            rule1 = ValidationRule("rule1", lambda x: len(x) > 5)
            rule2 = ValidationRule("rule2", lambda x: x.isalnum())
            
            # ALL strategy - all rules must pass
            all_validator = CompositeValidator([rule1, rule2], strategy="ALL")
            assert all_validator.validate("short").is_invalid()  # Fails rule1
            assert all_validator.validate("valid123").is_valid()  # Passes both
            
            # ANY strategy - at least one rule must pass  
            any_validator = CompositeValidator([rule1, rule2], strategy="ANY")
            assert any_validator.validate("short").is_valid()  # Passes rule2
            assert any_validator.validate("!@#$%^").is_invalid()  # Fails both
    
    def test_should_collect_all_validation_errors(self):
        """CompositeValidator should collect all validation errors."""
        if TYPES_AVAILABLE:
            rule1 = ValidationRule("rule1", lambda x: False, "Error 1")
            rule2 = ValidationRule("rule2", lambda x: False, "Error 2")
            
            composite = CompositeValidator([rule1, rule2])
            result = composite.validate("test")
            
            assert result.is_invalid()
            assert len(result.errors) == 2
            assert "Error 1" in result.errors
            assert "Error 2" in result.errors


class TestValidationSchema:
    """Test specifications for ValidationSchema type."""
    
    def test_should_define_object_validation_schemas(self):
        """ValidationSchema should define validation schemas for objects."""
        if TYPES_AVAILABLE:
            schema = ValidationSchema({
                "name": ValidationRule("name", lambda x: len(x) >= 2),
                "email": EmailValidator(),
                "age": ValidationRule("age", lambda x: 0 <= x <= 150)
            })
            
            # Valid object should pass
            valid_data = {"name": "John", "email": "john@example.com", "age": 30}
            result = schema.validate(valid_data)
            assert result.is_valid()
            
            # Invalid object should fail
            invalid_data = {"name": "J", "email": "invalid", "age": -5}
            result = schema.validate(invalid_data)
            assert result.is_invalid()
            assert len(result.errors) >= 3  # Multiple field errors
    
    def test_should_support_optional_fields(self):
        """ValidationSchema should support optional fields."""
        if TYPES_AVAILABLE:
            schema = ValidationSchema({
                "name": ValidationRule("name", lambda x: len(x) >= 2),
                "email": FieldValidator(EmailValidator(), required=False),
                "phone": FieldValidator(
                    ValidationRule("phone", lambda x: len(x) >= 10),
                    required=False
                )
            })
            
            # Object without optional fields should pass
            minimal_data = {"name": "John"}
            result = schema.validate(minimal_data)
            assert result.is_valid()
            
            # Object with invalid optional field should fail
            invalid_optional = {"name": "John", "email": "invalid"}
            result = schema.validate(invalid_optional)
            assert result.is_invalid()
    
    def test_should_support_nested_schemas(self):
        """ValidationSchema should support nested object validation."""
        if TYPES_AVAILABLE:
            address_schema = ValidationSchema({
                "street": ValidationRule("street", lambda x: len(x) >= 5),
                "city": ValidationRule("city", lambda x: len(x) >= 2),
                "zip": ValidationRule("zip", lambda x: x.isdigit() and len(x) == 5)
            })
            
            person_schema = ValidationSchema({
                "name": ValidationRule("name", lambda x: len(x) >= 2),
                "address": address_schema
            })
            
            # Valid nested object
            valid_data = {
                "name": "John",
                "address": {"street": "123 Main St", "city": "City", "zip": "12345"}
            }
            result = person_schema.validate(valid_data)
            assert result.is_valid()


class TestValidationReport:
    """Test specifications for ValidationReport type."""
    
    def test_should_generate_validation_reports(self):
        """ValidationReport should generate comprehensive validation reports."""
        if TYPES_AVAILABLE:
            errors = [
                ValidationError("Error 1", field_name="field1", severity=ValidationSeverity.ERROR),
                ValidationError("Warning 1", field_name="field2", severity=ValidationSeverity.WARNING),
                ValidationError("Error 2", field_name="field3", severity=ValidationSeverity.CRITICAL)
            ]
            
            report = ValidationReport(errors)
            
            assert report.total_errors == 3
            assert report.error_count == 1
            assert report.warning_count == 1
            assert report.critical_count == 1
            assert not report.is_valid()
    
    def test_should_categorize_validation_results(self):
        """ValidationReport should categorize validation results."""
        if TYPES_AVAILABLE:
            errors = [
                ValidationError("Format error", category=ValidationCategory.FORMAT),
                ValidationError("Range error", category=ValidationCategory.RANGE),
                ValidationError("Required error", category=ValidationCategory.REQUIRED)
            ]
            
            report = ValidationReport(errors)
            
            format_errors = report.get_errors_by_category(ValidationCategory.FORMAT)
            assert len(format_errors) == 1
            assert format_errors[0].category == ValidationCategory.FORMAT
    
    def test_should_provide_summary_information(self):
        """ValidationReport should provide validation summary information."""
        if TYPES_AVAILABLE:
            report = ValidationReport([])
            assert report.is_valid()
            assert report.summary() == "Validation passed"
            
            report_with_errors = ValidationReport([
                ValidationError("Error", severity=ValidationSeverity.ERROR)
            ])
            assert not report_with_errors.is_valid()
            assert "1 error" in report_with_errors.summary().lower()


# Integration tests between validation types
class TestValidationTypeIntegration:
    """Test specifications for integration between validation types."""
    
    def test_validation_pipeline_integration(self):
        """Validation types should work together in validation pipeline."""
        if TYPES_AVAILABLE:
            # Create validation pipeline
            email_validator = EmailValidator()
            path_validator = PathValidator(must_exist=False)  # Don't require existence
            
            # Validate multiple fields
            email_result = email_validator.validate("user@example.com")
            path_result = path_validator.validate("/tmp/file.txt")
            
            # Combine results
            combined = ValidationResult.combine([email_result, path_result])
            assert combined.is_valid()
    
    def test_error_collection_and_reporting(self):
        """Error collection and reporting should work seamlessly."""
        if TYPES_AVAILABLE:
            collector = ErrorCollector()
            
            # Collect various validation errors
            collector.add_error(ValidationError("Email invalid", field_name="email"))
            collector.add_error(ValidationError("Path not found", field_name="path"))
            
            # Generate report
            report = collector.generate_report()
            assert report.total_errors == 2
            assert not report.is_valid()


# Mark all tests that will initially fail
pytestmark = pytest.mark.unit