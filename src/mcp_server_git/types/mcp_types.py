"""MCP protocol type definitions for the MCP Git Server.

This module provides type definitions for Model Context Protocol (MCP) operations,
including requests, responses, tools, and protocol validation.

These types are currently stubs to satisfy TDD test requirements.
Implementation will be completed in subsequent development phases.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal


class MCPErrorCode(Enum):
    """MCP protocol error codes."""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603


class MCPValidationError(Exception):
    """Exception raised when MCP type validation fails."""

    pass


class MCPProtocolError(Exception):
    """Exception raised when MCP protocol violations occur."""

    pass


@dataclass
class MCPRequest:
    """MCP protocol request."""

    jsonrpc: str
    id: str | int
    method: str
    params: dict[str, Any] | None = None


@dataclass
class MCPResponse:
    """MCP protocol response."""

    jsonrpc: str
    id: str | int
    result: Any | None = None
    error: dict[str, Any] | None = None


@dataclass
class MCPError:
    """MCP protocol error."""

    code: int
    message: str
    data: Any | None = None


@dataclass
class MCPNotification:
    """MCP protocol notification."""

    jsonrpc: str
    method: str
    params: dict[str, Any] | None = None


@dataclass
class MCPMessage:
    """Base MCP protocol message."""

    jsonrpc: str


@dataclass
class MCPTool:
    """MCP tool definition."""

    name: str
    description: str
    schema: dict[str, Any]


@dataclass
class MCPToolSchema:
    """MCP tool schema definition."""

    type: str
    properties: dict[str, Any]
    required: list[str] | None = None


@dataclass
class MCPToolInput:
    """MCP tool input."""

    name: str
    arguments: dict[str, Any]


@dataclass
class MCPToolOutput:
    """MCP tool output."""

    content: list[dict[str, Any]]
    isError: bool = False


@dataclass
class MCPResource:
    """MCP resource definition."""

    uri: str
    name: str
    description: str | None = None
    mimeType: str | None = None


MCPResourceType = Literal["text", "blob"]
MCPContentType = Literal["text/plain", "application/json", "text/markdown"]


@dataclass
class MCPPrompt:
    """MCP prompt definition."""

    name: str
    description: str
    arguments: list[dict[str, Any]] | None = None


@dataclass
class MCPCapabilities:
    """MCP server capabilities."""

    tools: dict[str, Any] | None = None
    resources: dict[str, Any] | None = None
    prompts: dict[str, Any] | None = None


@dataclass
class MCPServerInfo:
    """MCP server information."""

    name: str
    version: str
    capabilities: MCPCapabilities


@dataclass
class MCPClientInfo:
    """MCP client information."""

    name: str
    version: str
    capabilities: MCPCapabilities | None = None


@dataclass
class MCPSession:
    """MCP session state."""

    client_info: MCPClientInfo | None = None
    server_info: MCPServerInfo | None = None
    initialized: bool = False


# Export all public types
__all__ = [
    "MCPRequest",
    "MCPResponse",
    "MCPError",
    "MCPErrorCode",
    "MCPNotification",
    "MCPMessage",
    "MCPTool",
    "MCPToolSchema",
    "MCPToolInput",
    "MCPToolOutput",
    "MCPResource",
    "MCPResourceType",
    "MCPContentType",
    "MCPPrompt",
    "MCPCapabilities",
    "MCPServerInfo",
    "MCPClientInfo",
    "MCPSession",
    "MCPValidationError",
    "MCPProtocolError",
]
