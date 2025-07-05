"""
Test specifications for MCP protocol types.

These tests define the behavioral requirements for MCP protocol-related type definitions
including requests, responses, tools, and protocol validation.

IMPORTANT: These tests define requirements and are IMMUTABLE once complete.
Do not modify tests to match implementation - implementation must satisfy these tests.
"""

import pytest

# Import the types we expect to be implemented
# These imports will fail initially (RED phase) - that's expected!
try:
    from mcp_server_git.types.mcp_types import (
        MCPRequest,
        MCPResponse,
        MCPNotification,
        MCPError,
        MCPTool,
        MCPToolInput,
        MCPToolOutput,
        MCPResource,
        MCPPrompt,
        MCPMessage,
        MCPCapabilities,
        MCPServerInfo,
        MCPClientInfo,
        MCPSession,
        MCPValidationError,
        MCPProtocolError,
        MCPErrorCode,
        MCPToolSchema,
        MCPResourceType,
        MCPContentType,
    )
    TYPES_AVAILABLE = True
except ImportError:
    TYPES_AVAILABLE = False


class TestMCPRequest:
    """Test specifications for MCPRequest type."""
    
    def test_should_represent_valid_mcp_requests(self):
        """MCPRequest should represent valid MCP protocol requests."""
        if TYPES_AVAILABLE:
            request = MCPRequest(
                jsonrpc="2.0",
                id=1,
                method="tools/list",
                params={}
            )
            
            assert request.jsonrpc == "2.0"
            assert request.id == 1
            assert request.method == "tools/list"
            assert request.params == {}
    
    def test_should_validate_jsonrpc_version(self):
        """MCPRequest should validate JSON-RPC version."""
        if TYPES_AVAILABLE:
            # Should reject invalid JSON-RPC versions
            with pytest.raises(MCPValidationError):
                MCPRequest(
                    jsonrpc="1.0",  # Invalid version
                    id=1,
                    method="test/method"
                )
    
    def test_should_validate_request_methods(self):
        """MCPRequest should validate MCP method names."""
        valid_methods = [
            "initialize",
            "tools/list",
            "tools/call",
            "resources/list",
            "resources/read",
            "prompts/list",
            "prompts/get"
        ]
        
        if TYPES_AVAILABLE:
            for method in valid_methods:
                request = MCPRequest(jsonrpc="2.0", id=1, method=method)
                assert request.method == method
                assert request.is_valid_method()
    
    def test_should_reject_invalid_methods(self):
        """MCPRequest should reject invalid MCP method names."""
        invalid_methods = [
            "",  # Empty
            "invalid-method",  # Invalid format
            "tools/invalid",  # Invalid tool method
            "custom/method"  # Non-standard method
        ]
        
        if TYPES_AVAILABLE:
            for method in invalid_methods:
                with pytest.raises(MCPValidationError):
                    MCPRequest(jsonrpc="2.0", id=1, method=method)
    
    def test_should_handle_request_parameters(self):
        """MCPRequest should handle typed request parameters."""
        if TYPES_AVAILABLE:
            # Request with complex parameters
            request = MCPRequest(
                jsonrpc="2.0",
                id=2,
                method="tools/call",
                params={
                    "name": "git_status",
                    "arguments": {"repo_path": "/tmp/repo"}
                }
            )
            
            assert request.params["name"] == "git_status"
            assert request.params["arguments"]["repo_path"] == "/tmp/repo"
            
            # Should provide parameter access helpers
            assert hasattr(request, 'get_param')
            assert request.get_param("name") == "git_status"


class TestMCPResponse:
    """Test specifications for MCPResponse type."""
    
    def test_should_represent_successful_responses(self):
        """MCPResponse should represent successful MCP responses."""
        if TYPES_AVAILABLE:
            response = MCPResponse.success(
                id=1,
                result={"tools": [{"name": "git_status"}]}
            )
            
            assert response.jsonrpc == "2.0"
            assert response.id == 1
            assert response.result["tools"][0]["name"] == "git_status"
            assert response.is_success()
            assert not response.is_error()
    
    def test_should_represent_error_responses(self):
        """MCPResponse should represent MCP error responses."""
        if TYPES_AVAILABLE:
            response = MCPResponse.error(
                id=1,
                error_code=MCPErrorCode.INVALID_PARAMS,
                error_message="Invalid parameters provided"
            )
            
            assert response.jsonrpc == "2.0"
            assert response.id == 1
            assert not response.is_success()
            assert response.is_error()
            assert response.error.code == MCPErrorCode.INVALID_PARAMS
    
    def test_should_validate_response_structure(self):
        """MCPResponse should validate MCP response structure."""
        if TYPES_AVAILABLE:
            # Response must have either result or error, not both
            with pytest.raises(MCPValidationError):
                MCPResponse(
                    jsonrpc="2.0",
                    id=1,
                    result={"success": True},
                    error=MCPError(MCPErrorCode.INTERNAL_ERROR, "Error")
                )


class TestMCPNotification:
    """Test specifications for MCPNotification type."""
    
    def test_should_represent_mcp_notifications(self):
        """MCPNotification should represent MCP notifications."""
        if TYPES_AVAILABLE:
            notification = MCPNotification(
                jsonrpc="2.0",
                method="notifications/initialized",
                params={}
            )
            
            assert notification.jsonrpc == "2.0"
            assert notification.method == "notifications/initialized"
            assert not hasattr(notification, 'id')  # Notifications don't have IDs
    
    def test_should_validate_notification_methods(self):
        """MCPNotification should validate notification method names."""
        valid_notifications = [
            "notifications/initialized",
            "notifications/roots/list_changed",
            "notifications/resources/list_changed",
            "notifications/resources/updated",
            "notifications/tools/list_changed"
        ]
        
        if TYPES_AVAILABLE:
            for method in valid_notifications:
                notification = MCPNotification(jsonrpc="2.0", method=method)
                assert notification.method == method
                assert notification.is_valid_notification()


class TestMCPTool:
    """Test specifications for MCPTool type."""
    
    def test_should_define_mcp_tools(self):
        """MCPTool should define MCP tool specifications."""
        if TYPES_AVAILABLE:
            tool = MCPTool(
                name="git_status",
                description="Show the working tree status",
                input_schema={
                    "type": "object",
                    "properties": {
                        "repo_path": {
                            "type": "string",
                            "description": "Path to Git repository"
                        }
                    },
                    "required": ["repo_path"]
                }
            )
            
            assert tool.name == "git_status"
            assert tool.description == "Show the working tree status"
            assert "repo_path" in tool.input_schema["properties"]
            assert "repo_path" in tool.input_schema["required"]
    
    def test_should_validate_tool_names(self):
        """MCPTool should validate tool naming conventions."""
        valid_names = [
            "git_status",
            "github_get_pr_checks",
            "git_commit",
            "tool_name_123"
        ]
        
        if TYPES_AVAILABLE:
            for name in valid_names:
                tool = MCPTool(name=name, description="Test tool")
                assert tool.name == name
                assert tool.is_valid_name()
    
    def test_should_reject_invalid_tool_names(self):
        """MCPTool should reject invalid tool names."""
        invalid_names = [
            "",  # Empty
            "invalid-name",  # Hyphens not allowed
            "Invalid Name",  # Spaces not allowed
            "123_tool",  # Cannot start with number
            "tool.name",  # Dots not allowed
        ]
        
        if TYPES_AVAILABLE:
            for name in invalid_names:
                with pytest.raises(MCPValidationError):
                    MCPTool(name=name, description="Test tool")
    
    def test_should_validate_json_schemas(self):
        """MCPTool should validate JSON Schema specifications."""
        if TYPES_AVAILABLE:
            # Should accept valid JSON Schema
            valid_schema = {
                "type": "object",
                "properties": {
                    "param1": {"type": "string"},
                    "param2": {"type": "integer", "minimum": 0}
                },
                "required": ["param1"]
            }
            
            tool = MCPTool(
                name="test_tool",
                description="Test tool",
                input_schema=valid_schema
            )
            assert tool.input_schema == valid_schema
            
            # Should reject invalid JSON Schema
            with pytest.raises(MCPValidationError):
                MCPTool(
                    name="test_tool",
                    description="Test tool",
                    input_schema={"type": "invalid_type"}  # Invalid type
                )


class TestMCPToolInput:
    """Test specifications for MCPToolInput type."""
    
    def test_should_validate_tool_inputs(self):
        """MCPToolInput should validate inputs against tool schema."""
        if TYPES_AVAILABLE:
            schema = MCPToolSchema({
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "count": {"type": "integer", "minimum": 1}
                },
                "required": ["repo_path"]
            })
            
            # Valid input should pass
            valid_input = MCPToolInput(
                schema=schema,
                arguments={"repo_path": "/tmp/repo", "count": 5}
            )
            assert valid_input.is_valid()
            assert valid_input.get_argument("repo_path") == "/tmp/repo"
            
            # Invalid input should fail
            with pytest.raises(MCPValidationError):
                MCPToolInput(
                    schema=schema,
                    arguments={"count": 5}  # Missing required repo_path
                )
    
    def test_should_provide_type_coercion(self):
        """MCPToolInput should provide safe type coercion."""
        if TYPES_AVAILABLE:
            schema = MCPToolSchema({
                "type": "object",
                "properties": {
                    "count": {"type": "integer"},
                    "enabled": {"type": "boolean"}
                }
            })
            
            input_data = MCPToolInput(
                schema=schema,
                arguments={"count": "5", "enabled": "true"}  # String values
            )
            
            # Should coerce to correct types
            assert input_data.get_typed_argument("count") == 5
            assert input_data.get_typed_argument("enabled") is True


class TestMCPToolOutput:
    """Test specifications for MCPToolOutput type."""
    
    def test_should_represent_tool_outputs(self):
        """MCPToolOutput should represent MCP tool execution results."""
        if TYPES_AVAILABLE:
            output = MCPToolOutput.success(
                content=[{"type": "text", "text": "Operation successful"}],
                metadata={"execution_time": 0.5}
            )
            
            assert output.is_success()
            assert not output.is_error()
            assert len(output.content) == 1
            assert output.content[0]["type"] == "text"
            assert output.metadata["execution_time"] == 0.5
    
    def test_should_represent_tool_errors(self):
        """MCPToolOutput should represent tool execution errors."""
        if TYPES_AVAILABLE:
            output = MCPToolOutput.error(
                error_message="Repository not found",
                error_code="REPO_NOT_FOUND"
            )
            
            assert not output.is_success()
            assert output.is_error()
            assert output.error_message == "Repository not found"
            assert output.error_code == "REPO_NOT_FOUND"
    
    def test_should_validate_content_types(self):
        """MCPToolOutput should validate content type specifications."""
        if TYPES_AVAILABLE:
            # Valid content types
            valid_content = [
                {"type": "text", "text": "Hello"},
                {"type": "image", "data": "base64data", "mimeType": "image/png"},
                {"type": "resource", "resource": {"uri": "file://test.txt"}}
            ]
            
            output = MCPToolOutput.success(content=valid_content)
            assert len(output.content) == 3
            
            # Invalid content type should fail
            with pytest.raises(MCPValidationError):
                MCPToolOutput.success(
                    content=[{"type": "invalid", "data": "test"}]
                )


class TestMCPErrorCode:
    """Test specifications for MCPErrorCode enum."""
    
    def test_should_define_standard_error_codes(self):
        """MCPErrorCode should define all standard MCP error codes."""
        expected_codes = [
            -32700,  # Parse error
            -32600,  # Invalid request
            -32601,  # Method not found
            -32602,  # Invalid params
            -32603,  # Internal error
        ]
        
        if TYPES_AVAILABLE:
            for code in expected_codes:
                error_code = MCPErrorCode(code)
                assert error_code.value == code
                assert error_code.is_standard_error()
    
    def test_should_support_application_error_codes(self):
        """MCPErrorCode should support application-specific error codes."""
        if TYPES_AVAILABLE:
            # Application errors are in the range -32000 to -32099
            app_error = MCPErrorCode(-32001)
            assert app_error.is_application_error()
            assert not app_error.is_standard_error()


class TestMCPCapabilities:
    """Test specifications for MCPCapabilities type."""
    
    def test_should_represent_server_capabilities(self):
        """MCPCapabilities should represent MCP server capabilities."""
        if TYPES_AVAILABLE:
            capabilities = MCPCapabilities(
                tools={"listChanged": True},
                resources={"subscribe": True, "listChanged": True},
                prompts={"listChanged": True},
                logging={}
            )
            
            assert capabilities.supports_tools()
            assert capabilities.supports_resources()
            assert capabilities.supports_prompts()
            assert capabilities.tools_support_list_changed()
    
    def test_should_validate_capability_structure(self):
        """MCPCapabilities should validate capability structure."""
        if TYPES_AVAILABLE:
            # Should reject invalid capability structures
            with pytest.raises(MCPValidationError):
                MCPCapabilities(
                    tools={"invalid_capability": True}  # Invalid capability
                )


class TestMCPSession:
    """Test specifications for MCPSession type."""
    
    def test_should_manage_session_state(self):
        """MCPSession should manage MCP session state."""
        if TYPES_AVAILABLE:
            session = MCPSession(
                client_info=MCPClientInfo(name="test-client", version="1.0.0"),
                server_info=MCPServerInfo(name="mcp-server-git", version="0.6.3")
            )
            
            assert not session.is_initialized()
            
            session.initialize()
            assert session.is_initialized()
            assert session.client_info.name == "test-client"
            assert session.server_info.name == "mcp-server-git"
    
    def test_should_track_session_capabilities(self):
        """MCPSession should track negotiated capabilities."""
        if TYPES_AVAILABLE:
            client_caps = MCPCapabilities(tools={"listChanged": True})
            server_caps = MCPCapabilities(tools={}, resources={"subscribe": True})
            
            session = MCPSession()
            session.negotiate_capabilities(client_caps, server_caps)
            
            # Should determine effective capabilities
            effective = session.effective_capabilities
            assert effective.supports_tools()  # Both support tools
            assert not effective.supports_resource_subscription()  # Only server supports


# Integration tests between MCP types
class TestMCPTypeIntegration:
    """Test specifications for integration between MCP types."""
    
    def test_request_response_cycle(self):
        """MCP request/response types should work together."""
        if TYPES_AVAILABLE:
            # ARRANGE: Create request
            request = MCPRequest(
                jsonrpc="2.0",
                id=1,
                method="tools/call",
                params={
                    "name": "git_status",
                    "arguments": {"repo_path": "/tmp/repo"}
                }
            )
            
            # ACT: Process request and create response
            response = MCPResponse.success(
                id=request.id,
                result={"content": [{"type": "text", "text": "Clean repo"}]}
            )
            
            # ASSERT: Should work together
            assert response.id == request.id
            assert response.is_success()
    
    def test_tool_execution_flow(self):
        """MCP tool types should support complete execution flow."""
        if TYPES_AVAILABLE:
            # Define tool
            tool = MCPTool(
                name="git_status",
                description="Show git status",
                input_schema={
                    "type": "object",
                    "properties": {"repo_path": {"type": "string"}},
                    "required": ["repo_path"]
                }
            )
            
            # Create input
            tool_input = MCPToolInput(
                schema=MCPToolSchema(tool.input_schema),
                arguments={"repo_path": "/tmp/repo"}
            )
            
            # Create output
            tool_output = MCPToolOutput.success(
                content=[{"type": "text", "text": "Status output"}]
            )
            
            # Should work together in tool execution
            assert tool_input.is_valid()
            assert tool_output.is_success()


@pytest.mark.unit
class TestMCPValidationError:
    """Test specifications for MCPValidationError exception."""
    
    def test_should_provide_mcp_context(self):
        """MCPValidationError should provide MCP-specific error context."""
        if TYPES_AVAILABLE:
            try:
                MCPRequest(jsonrpc="1.0", id=1, method="test")
            except MCPValidationError as e:
                assert hasattr(e, 'mcp_error_code')
                assert hasattr(e, 'field_path')
                assert hasattr(e, 'protocol_version')
    
    def test_should_convert_to_mcp_error_response(self):
        """MCPValidationError should convert to proper MCP error response."""
        if TYPES_AVAILABLE:
            validation_error = MCPValidationError("Invalid method")
            mcp_error = validation_error.to_mcp_error()
            
            assert isinstance(mcp_error, MCPError)
            assert mcp_error.code == MCPErrorCode.INVALID_PARAMS


# Mark all tests that will initially fail
pytestmark = pytest.mark.unit