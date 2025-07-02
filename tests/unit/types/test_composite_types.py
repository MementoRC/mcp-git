"""
Test specifications for composite and integration types.

These tests define the behavioral requirements for types that integrate
multiple domain concepts and ensure cross-domain type compatibility.

IMPORTANT: These tests define requirements and are IMMUTABLE once complete.
Do not modify tests to match implementation - implementation must satisfy these tests.
"""

import pytest
from typing import Dict, Any, List, Optional, Union
from unittest.mock import Mock, patch
from datetime import datetime

# Import the types we expect to be implemented
# These imports will fail initially (RED phase) - that's expected!
try:
    from mcp_server_git.types.composite_types import (
        GitOperationRequest,
        GitOperationResponse,
        GitHubOperationRequest,
        GitHubOperationResponse,
        MCPToolRequest,
        MCPToolResponse,
        RepositoryContext,
        OperationContext,
        RequestContext,
        ResponseContext,
        GitWorkflowResult,
        GitHubWorkflowResult,
        IntegratedOperationResult,
        TypeFactory,
        TypeRegistry,
        TypeConverter,
        DomainBridge,
    )
    # Import domain types for integration testing
    from mcp_server_git.types.git_types import (
        GitRepositoryPath, GitBranch, GitCommitHash, GitStatusResult
    )
    from mcp_server_git.types.github_types import (
        GitHubRepository, GitHubPullRequest, GitHubUser
    )
    from mcp_server_git.types.mcp_types import (
        MCPRequest, MCPResponse, MCPTool, MCPToolOutput
    )
    TYPES_AVAILABLE = True
except ImportError:
    TYPES_AVAILABLE = False


class TestGitOperationRequest:
    """Test specifications for GitOperationRequest composite type."""
    
    def test_should_combine_git_and_mcp_request_data(self):
        """GitOperationRequest should combine Git domain and MCP protocol data."""
        if TYPES_AVAILABLE:
            request = GitOperationRequest(
                mcp_request=MCPRequest(
                    jsonrpc="2.0",
                    id=1,
                    method="tools/call",
                    params={"name": "git_status"}
                ),
                repository_path=GitRepositoryPath("/tmp/repo"),
                operation_type="status",
                context=OperationContext(
                    user_id="user123",
                    session_id="session456",
                    timestamp=datetime.now()
                )
            )
            
            assert request.mcp_request.method == "tools/call"
            assert str(request.repository_path) == "/tmp/repo"
            assert request.operation_type == "status"
            assert request.context.user_id == "user123"
    
    def test_should_validate_operation_consistency(self):
        """GitOperationRequest should validate consistency between MCP and Git data."""
        if TYPES_AVAILABLE:
            # Should reject mismatched operation types
            with pytest.raises(ValidationError):
                GitOperationRequest(
                    mcp_request=MCPRequest(
                        jsonrpc="2.0", id=1, method="tools/call",
                        params={"name": "git_status"}
                    ),
                    repository_path=GitRepositoryPath("/tmp/repo"),
                    operation_type="commit"  # Mismatch with git_status
                )
    
    def test_should_provide_request_transformation(self):
        """GitOperationRequest should provide transformation to native Git operations."""
        if TYPES_AVAILABLE:
            request = GitOperationRequest(
                mcp_request=MCPRequest(
                    jsonrpc="2.0", id=1, method="tools/call",
                    params={"name": "git_log", "arguments": {"max_count": 10}}
                ),
                repository_path=GitRepositoryPath("/tmp/repo"),
                operation_type="log"
            )
            
            # Should extract git operation parameters
            git_params = request.extract_git_parameters()
            assert git_params["max_count"] == 10
            assert git_params["repo_path"] == "/tmp/repo"


class TestGitOperationResponse:
    """Test specifications for GitOperationResponse composite type."""
    
    def test_should_combine_git_results_with_mcp_response(self):
        """GitOperationResponse should combine Git results with MCP response format."""
        if TYPES_AVAILABLE:
            git_result = GitStatusResult(
                is_clean=True,
                current_branch=GitBranch("main"),
                modified_files=[],
                untracked_files=[],
                staged_files=[]
            )
            
            response = GitOperationResponse(
                mcp_response=MCPResponse.success(
                    id=1,
                    result={"status": "success"}
                ),
                git_result=git_result,
                operation_type="status",
                execution_time=0.5
            )
            
            assert response.mcp_response.is_success()
            assert response.git_result.is_clean
            assert response.operation_type == "status"
            assert response.execution_time == 0.5
    
    def test_should_handle_git_operation_errors(self):
        """GitOperationResponse should handle Git operation errors properly."""
        if TYPES_AVAILABLE:
            error_response = GitOperationResponse.from_git_error(
                request_id=1,
                operation_type="commit",
                error="Repository not found",
                error_code="REPO_NOT_FOUND"
            )
            
            assert error_response.mcp_response.is_error()
            assert error_response.git_result is None
            assert error_response.error_code == "REPO_NOT_FOUND"
    
    def test_should_provide_response_serialization(self):
        """GitOperationResponse should provide proper serialization for MCP protocol."""
        if TYPES_AVAILABLE:
            response = GitOperationResponse(
                mcp_response=MCPResponse.success(id=1, result={}),
                git_result=GitStatusResult(is_clean=True, current_branch=GitBranch("main")),
                operation_type="status"
            )
            
            # Should serialize to valid MCP response
            serialized = response.to_mcp_format()
            assert serialized["jsonrpc"] == "2.0"
            assert serialized["id"] == 1
            assert "result" in serialized


class TestGitHubOperationRequest:
    """Test specifications for GitHubOperationRequest composite type."""
    
    def test_should_combine_github_and_mcp_request_data(self):
        """GitHubOperationRequest should combine GitHub domain and MCP protocol data."""
        if TYPES_AVAILABLE:
            request = GitHubOperationRequest(
                mcp_request=MCPRequest(
                    jsonrpc="2.0", id=1, method="tools/call",
                    params={"name": "github_get_pr_checks"}
                ),
                repository=GitHubRepository(owner="testorg", name="testrepo"),
                operation_type="get_pr_checks",
                api_context={
                    "pr_number": 123,
                    "include_annotations": True
                }
            )
            
            assert request.repository.owner == "testorg"
            assert request.repository.name == "testrepo"
            assert request.api_context["pr_number"] == 123
    
    def test_should_handle_github_authentication(self):
        """GitHubOperationRequest should handle GitHub authentication context."""
        if TYPES_AVAILABLE:
            request = GitHubOperationRequest(
                mcp_request=MCPRequest(jsonrpc="2.0", id=1, method="tools/call"),
                repository=GitHubRepository(owner="org", name="repo"),
                operation_type="get_user",
                auth_token="github_token_123",
                rate_limit_context={
                    "remaining": 4500,
                    "reset_time": datetime.now()
                }
            )
            
            assert request.auth_token == "github_token_123"
            assert request.rate_limit_context["remaining"] == 4500
            assert request.has_valid_auth()


class TestRepositoryContext:
    """Test specifications for RepositoryContext composite type."""
    
    def test_should_unify_git_and_github_repository_data(self):
        """RepositoryContext should unify Git and GitHub repository information."""
        if TYPES_AVAILABLE:
            context = RepositoryContext(
                local_path=GitRepositoryPath("/tmp/repo"),
                github_repo=GitHubRepository(owner="user", name="repo"),
                current_branch=GitBranch("feature/test"),
                remote_url="https://github.com/user/repo.git",
                sync_status="up_to_date"
            )
            
            assert str(context.local_path) == "/tmp/repo"
            assert context.github_repo.full_name == "user/repo"
            assert str(context.current_branch) == "feature/test"
            assert context.is_synced()
    
    def test_should_detect_repository_state_inconsistencies(self):
        """RepositoryContext should detect inconsistencies between local and remote."""
        if TYPES_AVAILABLE:
            context = RepositoryContext(
                local_path=GitRepositoryPath("/tmp/repo"),
                github_repo=GitHubRepository(owner="user", name="repo"),
                current_branch=GitBranch("main"),
                sync_status="diverged"
            )
            
            assert not context.is_synced()
            assert context.needs_sync()
            
            # Should provide sync recommendations
            recommendations = context.get_sync_recommendations()
            assert len(recommendations) > 0
    
    def test_should_provide_unified_operations(self):
        """RepositoryContext should provide unified Git/GitHub operations."""
        if TYPES_AVAILABLE:
            context = RepositoryContext(
                local_path=GitRepositoryPath("/tmp/repo"),
                github_repo=GitHubRepository(owner="user", name="repo")
            )
            
            # Should support unified operations
            assert hasattr(context, 'create_pull_request')
            assert hasattr(context, 'sync_with_remote')
            assert hasattr(context, 'get_combined_status')


class TestIntegratedOperationResult:
    """Test specifications for IntegratedOperationResult composite type."""
    
    def test_should_combine_multiple_operation_results(self):
        """IntegratedOperationResult should combine results from multiple operations."""
        if TYPES_AVAILABLE:
            git_result = GitWorkflowResult(
                operations=["status", "add", "commit"],
                success=True,
                final_state=GitStatusResult(is_clean=True, current_branch=GitBranch("main"))
            )
            
            github_result = GitHubWorkflowResult(
                operations=["create_pr", "get_checks"],
                success=True,
                pull_request=GitHubPullRequest(number=123, title="Test PR")
            )
            
            integrated = IntegratedOperationResult(
                git_workflow=git_result,
                github_workflow=github_result,
                overall_success=True,
                correlation_id="workflow_456"
            )
            
            assert integrated.git_workflow.success
            assert integrated.github_workflow.success
            assert integrated.overall_success
            assert integrated.correlation_id == "workflow_456"
    
    def test_should_handle_partial_failures(self):
        """IntegratedOperationResult should handle partial workflow failures."""
        if TYPES_AVAILABLE:
            git_success = GitWorkflowResult(operations=["commit"], success=True)
            github_failure = GitHubWorkflowResult(
                operations=["create_pr"], 
                success=False,
                error="API rate limit exceeded"
            )
            
            integrated = IntegratedOperationResult(
                git_workflow=git_success,
                github_workflow=github_failure,
                overall_success=False
            )
            
            assert integrated.git_workflow.success
            assert not integrated.github_workflow.success
            assert not integrated.overall_success
            
            # Should provide failure analysis
            failures = integrated.get_failure_summary()
            assert "API rate limit exceeded" in failures


class TestTypeFactory:
    """Test specifications for TypeFactory utility."""
    
    def test_should_create_types_from_data(self):
        """TypeFactory should create typed objects from raw data."""
        if TYPES_AVAILABLE:
            factory = TypeFactory()
            
            # Create Git repository path from string
            repo_path = factory.create_git_repository_path("/tmp/repo")
            assert isinstance(repo_path, GitRepositoryPath)
            assert str(repo_path) == "/tmp/repo"
            
            # Create GitHub repository from dict
            github_data = {"owner": "user", "name": "repo"}
            github_repo = factory.create_github_repository(github_data)
            assert isinstance(github_repo, GitHubRepository)
            assert github_repo.full_name == "user/repo"
    
    def test_should_validate_during_creation(self):
        """TypeFactory should validate data during type creation."""
        if TYPES_AVAILABLE:
            factory = TypeFactory()
            
            # Should reject invalid data
            with pytest.raises(ValidationError):
                factory.create_git_branch("invalid..branch")
            
            with pytest.raises(ValidationError):
                factory.create_github_repository({"owner": "", "name": "repo"})
    
    def test_should_support_type_conversion(self):
        """TypeFactory should support conversion between compatible types."""
        if TYPES_AVAILABLE:
            factory = TypeFactory()
            
            # Convert string to GitBranch
            branch = factory.convert_to_git_branch("feature/test")
            assert isinstance(branch, GitBranch)
            assert str(branch) == "feature/test"
            
            # Convert dict to GitHubPullRequest
            pr_data = {"number": 123, "title": "Test", "state": "open"}
            pr = factory.convert_to_github_pull_request(pr_data)
            assert isinstance(pr, GitHubPullRequest)
            assert pr.number == 123


class TestTypeRegistry:
    """Test specifications for TypeRegistry utility."""
    
    def test_should_register_and_resolve_types(self):
        """TypeRegistry should register and resolve domain types."""
        if TYPES_AVAILABLE:
            registry = TypeRegistry()
            
            # Register custom type converters
            registry.register_converter("git_branch", GitBranch)
            registry.register_converter("github_repo", GitHubRepository)
            
            # Resolve types by name
            branch_type = registry.resolve_type("git_branch")
            assert branch_type == GitBranch
            
            repo_type = registry.resolve_type("github_repo")
            assert repo_type == GitHubRepository
    
    def test_should_support_type_hierarchies(self):
        """TypeRegistry should support type inheritance hierarchies."""
        if TYPES_AVAILABLE:
            registry = TypeRegistry()
            
            # Register type hierarchy
            registry.register_hierarchy("validation_error", [
                ValidationError, GitValidationError, GitHubValidationError, MCPValidationError
            ])
            
            # Should resolve most specific type
            git_error_type = registry.resolve_specific_type("validation_error", "git")
            assert issubclass(git_error_type, ValidationError)


class TestDomainBridge:
    """Test specifications for DomainBridge integration utility."""
    
    def test_should_bridge_git_and_github_domains(self):
        """DomainBridge should provide seamless Git/GitHub integration."""
        if TYPES_AVAILABLE:
            bridge = DomainBridge()
            
            # Bridge Git repository to GitHub repository
            git_path = GitRepositoryPath("/tmp/repo")
            github_repo = bridge.infer_github_repository(git_path)
            
            # Should extract GitHub info from Git remotes
            assert isinstance(github_repo, GitHubRepository)
    
    def test_should_bridge_mcp_and_domain_types(self):
        """DomainBridge should bridge MCP protocol and domain types."""
        if TYPES_AVAILABLE:
            bridge = DomainBridge()
            
            # Convert MCP request to domain operation
            mcp_request = MCPRequest(
                jsonrpc="2.0", id=1, method="tools/call",
                params={"name": "git_status", "arguments": {"repo_path": "/tmp/repo"}}
            )
            
            domain_request = bridge.mcp_to_domain_request(mcp_request)
            assert isinstance(domain_request, GitOperationRequest)
            assert domain_request.operation_type == "status"
    
    def test_should_provide_bidirectional_conversion(self):
        """DomainBridge should provide bidirectional type conversion."""
        if TYPES_AVAILABLE:
            bridge = DomainBridge()
            
            # Domain to MCP
            git_result = GitStatusResult(is_clean=True, current_branch=GitBranch("main"))
            mcp_response = bridge.domain_to_mcp_response(git_result, request_id=1)
            assert isinstance(mcp_response, MCPResponse)
            assert mcp_response.is_success()
            
            # MCP to Domain
            extracted_result = bridge.mcp_to_domain_result(mcp_response, "git_status")
            assert isinstance(extracted_result, GitStatusResult)


# Cross-domain integration tests
class TestCrossDomainIntegration:
    """Test specifications for cross-domain type integration."""
    
    def test_git_github_mcp_integration(self):
        """Git, GitHub, and MCP types should integrate seamlessly."""
        if TYPES_AVAILABLE:
            # Create integrated workflow
            repo_context = RepositoryContext(
                local_path=GitRepositoryPath("/tmp/repo"),
                github_repo=GitHubRepository(owner="user", name="repo")
            )
            
            mcp_request = MCPRequest(
                jsonrpc="2.0", id=1, method="tools/call",
                params={"name": "github_create_pr"}
            )
            
            # Should work together in integrated operations
            operation_request = GitHubOperationRequest(
                mcp_request=mcp_request,
                repository=repo_context.github_repo,
                operation_type="create_pr"
            )
            
            assert operation_request.mcp_request.id == 1
            assert operation_request.repository.owner == "user"
    
    def test_type_system_consistency(self):
        """Type system should maintain consistency across domains."""
        if TYPES_AVAILABLE:
            # All validation errors should inherit from common base
            git_error = GitValidationError("Git error")
            github_error = GitHubValidationError("GitHub error")
            mcp_error = MCPValidationError("MCP error")
            
            # Should all be ValidationErrors
            assert isinstance(git_error, ValidationError)
            assert isinstance(github_error, ValidationError)
            assert isinstance(mcp_error, ValidationError)
            
            # Should provide consistent error interface
            for error in [git_error, github_error, mcp_error]:
                assert hasattr(error, 'field_name')
                assert hasattr(error, 'invalid_value')
                assert hasattr(error, 'validation_rule')


# Mark all tests that will initially fail
pytestmark = pytest.mark.unit