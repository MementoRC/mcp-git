"""
MCP protocol message fixtures for testing.

Provides mock MCP protocol messages for testing server compliance
and message handling.
"""

from typing import Dict, Any, List, Optional
import pytest
from unittest.mock import MagicMock


class MCPMessageFactory:
    """Factory for creating MCP protocol messages."""
    
    @staticmethod
    def initialize_request(protocol_version: str = "2024-11-05") -> Dict[str, Any]:
        """Create an MCP initialize request."""
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": protocol_version,
                "capabilities": {
                    "roots": {
                        "listChanged": True
                    },
                    "sampling": {}
                },
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            }
        }
    
    @staticmethod
    def initialize_response(server_name: str = "mcp-server-git") -> Dict[str, Any]:
        """Create an MCP initialize response."""
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                    "resources": {},
                    "prompts": {},
                    "logging": {}
                },
                "serverInfo": {
                    "name": server_name,
                    "version": "0.6.3"
                }
            }
        }
    
    @staticmethod
    def list_tools_request() -> Dict[str, Any]:
        """Create a tools/list request."""
        return {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list"
        }
    
    @staticmethod
    def list_tools_response(tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Create a tools/list response."""
        if tools is None:
            tools = [
                {
                    "name": "git_status",
                    "description": "Show the working tree status",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "repo_path": {
                                "type": "string",
                                "description": "Path to Git repository"
                            }
                        },
                        "required": ["repo_path"]
                    }
                }
            ]
        
        return {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {
                "tools": tools
            }
        }
    
    @staticmethod
    def call_tool_request(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Create a tools/call request."""
        return {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
    
    @staticmethod
    def call_tool_response(content: str, is_error: bool = False) -> Dict[str, Any]:
        """Create a tools/call response."""
        return {
            "jsonrpc": "2.0",
            "id": 3,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": content
                    }
                ],
                "isError": is_error
            }
        }
    
    @staticmethod
    def error_response(error_code: int, error_message: str, request_id: int = 1) -> Dict[str, Any]:
        """Create an error response."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": error_code,
                "message": error_message
            }
        }
    
    @staticmethod
    def notification(method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create an MCP notification."""
        message = {
            "jsonrpc": "2.0",
            "method": method
        }
        
        if params is not None:
            message["params"] = params
            
        return message


@pytest.fixture
def mcp_message_factory():
    """Provide access to MCPMessageFactory."""
    return MCPMessageFactory


@pytest.fixture
def mock_mcp_transport():
    """Create a mock MCP transport."""
    transport = MagicMock()
    
    # Configure transport methods
    transport.send_message = MagicMock()
    transport.receive_message = MagicMock()
    transport.close = MagicMock()
    
    return transport


@pytest.fixture
def mcp_protocol_messages():
    """Common MCP protocol message patterns."""
    return {
        "initialize": MCPMessageFactory.initialize_request(),
        "initialized": MCPMessageFactory.notification("notifications/initialized"),
        "list_tools": MCPMessageFactory.list_tools_request(),
        "call_git_status": MCPMessageFactory.call_tool_request(
            "git_status", 
            {"repo_path": "/tmp/test-repo"}
        ),
        "server_error": MCPMessageFactory.error_response(-32603, "Internal error"),
        "invalid_params": MCPMessageFactory.error_response(-32602, "Invalid params"),
        "method_not_found": MCPMessageFactory.error_response(-32601, "Method not found")
    }


@pytest.fixture
def mcp_test_session():
    """Create a complete MCP test session with message sequence."""
    return [
        MCPMessageFactory.initialize_request(),
        MCPMessageFactory.initialize_response(),
        MCPMessageFactory.notification("notifications/initialized"),
        MCPMessageFactory.list_tools_request(),
        MCPMessageFactory.list_tools_response(),
        MCPMessageFactory.call_tool_request("git_status", {"repo_path": "/tmp/test"}),
        MCPMessageFactory.call_tool_response("On branch main\nnothing to commit, working tree clean")
    ]