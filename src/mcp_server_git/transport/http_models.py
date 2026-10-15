"""Pydantic request/response models for the MCP Git HTTP server."""

from typing import Any

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    """Request model for creating a new session."""

    repository_path: str = Field(..., description="Absolute path to the git repository")
    expected_remote_url: str = Field(
        ..., description="Expected remote URL for validation"
    )


class CreateSessionResponse(BaseModel):
    """Response model for session creation."""

    session_id: str = Field(..., description="Unique session identifier")
    status: str = Field(default="bound", description="Session status")
    repository_path: str = Field(..., description="Bound repository path")


class SessionStatusResponse(BaseModel):
    """Response model for session status."""

    session_id: str
    created_at: float
    last_activity: float
    age: float
    idle_time: float
    binding_info: dict[str, Any]


class CloseSessionResponse(BaseModel):
    """Response model for session closure."""

    status: str = Field(default="closed", description="Closure status")


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str = Field(default="healthy", description="Server health status")
    active_sessions: int = Field(..., description="Number of active sessions")


class JSONRPCRequest(BaseModel):
    """JSON-RPC 2.0 request model."""

    jsonrpc: str = Field(default="2.0", description="JSON-RPC version")
    method: str = Field(..., description="Method name (e.g., 'tools/call')")
    params: dict[str, Any] | None = Field(default=None, description="Method parameters")
    id: int | str | None = Field(None, description="Request ID")


class JSONRPCResponse(BaseModel):
    """JSON-RPC 2.0 response model."""

    jsonrpc: str = Field(default="2.0", description="JSON-RPC version")
    result: dict[str, Any] | None = Field(None, description="Result data")
    error: dict[str, Any] | None = Field(None, description="Error data")
    id: int | str | None = Field(None, description="Request ID")
