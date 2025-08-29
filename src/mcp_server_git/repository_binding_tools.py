"""
MCP Tools for Repository Binding Operations.

This module provides MCP tool definitions for repository binding operations
including bind, unbind, status, and explicit remote change functionality.

These tools are designed to be integrated into the main MCP server to provide
explicit repository binding management and prevent cross-session contamination.
"""

from pathlib import Path

from mcp.types import Tool
from pydantic import BaseModel

from .repository_binding import (
    RemoteContaminationError,
    RemoteProtectionError,
    RepositoryBindingError,
)


# Pydantic models for tool inputs
class RepositoryBind(BaseModel):
    """Model for repository bind operation."""

    repository_path: str
    expected_remote_url: str
    verify_remote: bool = True
    force: bool = False


class RepositoryUnbind(BaseModel):
    """Model for repository unbind operation."""

    force: bool = False


class ExplicitRemoteChange(BaseModel):
    """Model for explicit remote change operation."""

    repo_path: str
    new_remote_url: str
    confirmation_token: str
    remote_name: str = "origin"


def get_repository_binding_tools() -> list[Tool]:
    """
    Get the list of repository binding MCP tools.

    Returns:
        List of Tool instances for repository binding operations
    """
    return [
        Tool(
            name="repository_bind",
            description="Bind server to repository with remote protection",
            inputSchema=RepositoryBind.model_json_schema(),
        ),
        Tool(
            name="repository_unbind",
            description="Unbind server from repository",
            inputSchema=RepositoryUnbind.model_json_schema(),
        ),
        Tool(
            name="repository_status",
            description="Get repository binding status",
            inputSchema={},  # No input parameters needed
        ),
        Tool(
            name="explicit_remote_change",
            description="Explicitly change remote URL with confirmation token",
            inputSchema=ExplicitRemoteChange.model_json_schema(),
        ),
    ]


async def handle_repository_bind(
    server_core,
    repository_path: str,
    expected_remote_url: str,
    verify_remote: bool = True,
    force: bool = False,
) -> str:
    """
    Handle repository bind operation.

    Args:
        server_core: MCPGitServerCore instance
        repository_path: Path to git repository
        expected_remote_url: Expected remote URL for validation
        verify_remote: Verify remote URL matches expectation
        force: Force binding even if already bound

    Returns:
        Operation result message
    """
    try:
        result = await server_core.bind_repository(
            Path(repository_path), expected_remote_url, verify_remote, force
        )

        binding_info = result["binding"]["binding"]
        return (
            f"✅ Repository bound successfully\n"
            f"Server: {server_core.server_name}\n"
            f"Repository: {binding_info['repository_path']}\n"
            f"Remote URL: {binding_info['expected_remote_url']}\n"
            f"Binding Hash: {binding_info['binding_hash'][:16]}...\n"
            f"Session: {result['binding']['session_id']}"
        )
    except RepositoryBindingError as e:
        return f"❌ Repository binding failed: {e}"
    except RemoteContaminationError as e:
        return f"🚨 Remote contamination detected: {e}"
    except Exception as e:
        return f"💥 Unexpected error during binding: {e}"


async def handle_repository_unbind(server_core, force: bool = False) -> str:
    """
    Handle repository unbind operation.

    Args:
        server_core: MCPGitServerCore instance
        force: Force unbind even if operations are in progress

    Returns:
        Operation result message
    """
    try:
        result = await server_core.unbind_repository(force)

        return (
            f"✅ Repository unbound successfully\n"
            f"Server: {server_core.server_name}\n"
            f"Status: {result['status']}"
        )
    except RepositoryBindingError as e:
        return f"❌ Repository unbind failed: {e}"
    except Exception as e:
        return f"💥 Unexpected error during unbind: {e}"


def handle_repository_status(server_core) -> str:
    """
    Handle repository status request.

    Args:
        server_core: MCPGitServerCore instance

    Returns:
        Repository binding status information
    """
    try:
        status = server_core.get_repository_status()

        if status["state"] == "unbound":
            return (
                f"📊 Repository Status\n"
                f"Server: {status['server_name']}\n"
                f"State: ⚪ Unbound\n"
                f"Session: {status['session_id']}\n"
                f"⚠️ No repository protection active"
            )

        binding = status["binding"]
        state_emoji = {
            "bound": "🟢",
            "protected": "🔒",
            "corrupted": "🔴",
            "binding": "🟡",
        }.get(status["state"], "❓")

        return (
            f"📊 Repository Status\n"
            f"Server: {status['server_name']}\n"
            f"State: {state_emoji} {status['state'].title()}\n"
            f"Repository: {binding['repository_path']}\n"
            f"Remote URL: {binding['expected_remote_url']}\n"
            f"Remote Name: {binding['remote_name']}\n"
            f"Binding Time: {binding['binding_timestamp']}\n"
            f"Binding Hash: {binding['binding_hash'][:16]}...\n"
            f"Session: {status['session_id']}"
        )
    except Exception as e:
        return f"💥 Error getting repository status: {e}"


async def handle_explicit_remote_change(
    server_core,
    repo_path: str,
    new_remote_url: str,
    confirmation_token: str,
    remote_name: str = "origin",
) -> str:
    """
    Handle explicit remote change operation.

    Args:
        server_core: MCPGitServerCore instance
        repo_path: Repository path
        new_remote_url: New remote URL
        confirmation_token: Confirmation token (must be "CONFIRM_REMOTE_CHANGE")
        remote_name: Remote name to change

    Returns:
        Operation result message
    """
    try:
        protected_ops = server_core.get_protected_operations()
        if not protected_ops:
            return "❌ Protected operations not available"

        result = await protected_ops.explicit_remote_change(
            repo_path, new_remote_url, confirmation_token, remote_name
        )

        return (
            f"⚠️ Remote URL changed explicitly\n"
            f"Repository: {repo_path}\n"
            f"New Remote URL: {new_remote_url}\n"
            f"Remote Name: {remote_name}\n"
            f"🔓 Server unbound due to remote change\n"
            f"Result: {result}"
        )
    except RemoteProtectionError as e:
        return f"🛡️ Remote protection error: {e}"
    except RepositoryBindingError as e:
        return f"❌ Repository binding error: {e}"
    except Exception as e:
        return f"💥 Unexpected error during remote change: {e}"
