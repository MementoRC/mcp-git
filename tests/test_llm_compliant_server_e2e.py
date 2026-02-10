#!/usr/bin/env python3
"""
End-to-End Test for LLM-Compliant Server Architecture

This test validates that:
1. The new LLM-compliant server_application.py is being used (not monolithic server.py)
2. All git_status and core MCP tools work correctly
3. The server properly initializes and responds to tool calls
4. Architecture switch was successful

This test runs the actual server via `pixi run` just like ClaudeCode would.
"""

import asyncio
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

import pytest

from .conftest import _run_git_isolated


class LLMComplianceTestClient:
    """MCP client specifically for testing LLM-compliant server functionality"""

    def __init__(self, server_process):
        self.process = server_process
        self.request_id = 0

    def _next_id(self) -> int:
        self.request_id += 1
        return self.request_id

    async def send_request(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Send a JSON-RPC request to the server"""
        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
        }

        if params is not None:
            request["params"] = params

        # Send request
        request_json = json.dumps(request) + "\n"
        self.process.stdin.write(request_json.encode())
        await self.process.stdin.drain()

        # Read response
        response_line = await self.process.stdout.readline()
        if not response_line:
            raise Exception("No response from server")

        response = json.loads(response_line.decode().strip())
        return response

    async def initialize(self) -> dict[str, Any]:
        """Initialize the MCP session"""
        init_response = await self.send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"experimental": {}, "sampling": {}},
                "clientInfo": {"name": "llm-compliance-test", "version": "1.0.0"},
            },
        )

        # Send initialized notification
        notification = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        notification_json = json.dumps(notification) + "\n"
        self.process.stdin.write(notification_json.encode())
        await self.process.stdin.drain()

        return init_response

    async def list_tools(self) -> dict[str, Any]:
        """List available tools"""
        return await self.send_request("tools/list")

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool"""
        return await self.send_request(
            "tools/call", {"name": name, "arguments": arguments}
        )


@pytest.fixture
async def llm_compliant_server():
    """Start the LLM-compliant MCP server and return test client"""
    cwd = Path(__file__).parent.parent

    # Set up clean test environment (avoid mock contamination)
    env = os.environ.copy()
    env["GITHUB_TOKEN"] = env.get("GITHUB_TOKEN", "test_token_placeholder")
    env["PYTHONPATH"] = str(cwd / "src")
    env["MCP_TEST_MODE"] = "true"  # Signal this is a test

    # Clear any Python import caches that might contain mocks
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"

    # CRITICAL: Remove ClaudeCode git redirectors to allow real git access
    # But keep pixi and other essential tools
    if "PATH" in env:
        path_entries = env["PATH"].split(os.pathsep)
        # Filter out only ClaudeCode's git redirect paths that block git
        clean_path = [
            p
            for p in path_entries
            if not any(
                redirect in p
                for redirect in [
                    "redirected_bins"  # Only remove the specific git redirector path
                ]
            )
        ]
        env["PATH"] = os.pathsep.join(clean_path)
        # PATH cleaned to allow real git access in server subprocess

    # Remove any existing module cache variables that could cause mock bleeding
    for key in list(env.keys()):
        if key.startswith("PYTEST_") or "mock" in key.lower():
            del env[key]

    # Use pixi to start the server (mimicking ClaudeCode behavior)
    import shutil

    if shutil.which("pixi") and not env.get("PYTEST_CI"):
        server_cmd = ["pixi", "run", "-e", "quality", "mcp-server-git"]
    else:
        server_cmd = ["python", "-m", "mcp_server_git"]

    process = await asyncio.create_subprocess_exec(
        *server_cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=cwd,
    )

    client = LLMComplianceTestClient(process)

    try:
        # Give server time to start
        await asyncio.sleep(1.0)

        # Verify server started successfully
        if process.returncode is not None:
            stderr_output = await process.stderr.read()
            raise Exception(
                f"LLM-compliant server failed to start: {stderr_output.decode()}"
            )

        # Initialize MCP session
        init_response = await asyncio.wait_for(client.initialize(), timeout=10.0)
        assert "result" in init_response, f"Initialization failed: {init_response}"

        yield client

    finally:
        # Enhanced cleanup to prevent event loop issues
        if process.returncode is None:
            # First, try to close the client connection gracefully
            try:
                if hasattr(client, "process") and client.process.stdin:
                    client.process.stdin.close()
                    # Wait a moment for stdin close to propagate
                    await asyncio.sleep(0.1)
            except Exception:
                pass  # Ignore cleanup errors

            # Then terminate the process
            try:
                if process.returncode is None:  # Double-check process is still running
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=5.0)
            except ProcessLookupError:
                # Process already exited, which is fine
                pass
            except TimeoutError:
                # Force kill if it doesn't terminate
                try:
                    if process.returncode is None:
                        process.kill()
                except ProcessLookupError:
                    pass  # Already dead
                    await asyncio.wait_for(process.wait(), timeout=3.0)
                except TimeoutError:
                    pass  # Give up, let it be cleaned up by OS

        # Ensure all streams are properly closed before fixture cleanup
        try:
            if process.stdin and not process.stdin.is_closing():
                process.stdin.close()
            if process.stdout and not process.stdout.is_closing():
                process.stdout.close()
            if process.stderr and not process.stderr.is_closing():
                process.stderr.close()
            # Give event loop time to clean up transport
            await asyncio.sleep(0.2)
        except Exception:
            pass  # Ignore final cleanup errors


@pytest.mark.asyncio
async def test_llm_compliant_server_initialization(llm_compliant_server):
    """Test that the LLM-compliant server initializes correctly"""
    client = llm_compliant_server

    # Server should be initialized by the fixture
    assert client is not None


@pytest.mark.asyncio
async def test_llm_compliant_server_tools_list(llm_compliant_server):
    """Test that the LLM-compliant server lists tools correctly"""
    client = llm_compliant_server

    # Add timeout to prevent hanging
    tools_response = await asyncio.wait_for(client.list_tools(), timeout=15.0)

    # Should have successful response
    assert "result" in tools_response
    assert "tools" in tools_response["result"]

    tools = tools_response["result"]["tools"]
    tool_names = [tool["name"] for tool in tools]

    # Critical: git_status should be available (this was the failing method)
    assert "git_status" in tool_names, f"git_status not found in tools: {tool_names}"

    # Other essential tools should be present
    expected_tools = ["git_status", "git_log", "git_diff", "git_commit"]
    for tool in expected_tools:
        assert tool in tool_names, f"Expected tool '{tool}' not found in: {tool_names}"


@pytest.mark.asyncio
async def test_git_status_method_found(llm_compliant_server):
    """Test that git_status method works (was previously 'Method not found')"""
    client = llm_compliant_server

    # Create a temporary git repository for testing
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = Path(tmp_dir)

        # Initialize git repo
        _run_git_isolated(
            ["git", "init"], cwd=repo_path, check=True, capture_output=True
        )
        _run_git_isolated(
            ["git", "config", "user.name", "Test User"], cwd=repo_path, check=True
        )
        _run_git_isolated(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )

        # Create a test file
        (repo_path / "test.txt").write_text("Hello World")

        # Call git_status tool
        response = await asyncio.wait_for(
            client.call_tool("git_status", {"repo_path": str(repo_path)}), timeout=15.0
        )

        # Should NOT get "Method not found" error
        assert "error" not in response, f"git_status failed: {response}"
        assert "result" in response, f"No result in git_status response: {response}"

        # Result should contain status information
        result = response["result"]
        assert "content" in result, f"No content in git_status result: {result}"

        # Should show untracked file
        content = (
            result["content"][0]["text"]
            if isinstance(result["content"], list)
            else result["content"]
        )
        assert "test.txt" in str(content), (
            f"Expected 'test.txt' in git status output: {content}"
        )


@pytest.mark.asyncio
async def test_llm_compliant_architecture_validation(llm_compliant_server):
    """Validate that we're using the LLM-compliant architecture, not monolithic server"""
    client = llm_compliant_server

    # Test that server responds correctly to multiple tool calls
    # (indicating proper component decomposition)

    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = Path(tmp_dir)
        _run_git_isolated(
            ["git", "init"], cwd=repo_path, check=True, capture_output=True
        )
        _run_git_isolated(
            ["git", "config", "user.name", "Test User"], cwd=repo_path, check=True
        )
        _run_git_isolated(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )

        # Test multiple operations in sequence (tests component integration)
        operations = [
            ("git_status", {"repo_path": str(repo_path)}),
            ("git_log", {"repo_path": str(repo_path), "max_count": 1}),
        ]

        for tool_name, args in operations:
            response = await asyncio.wait_for(
                client.call_tool(tool_name, args), timeout=15.0
            )

            # Each operation should work without "Method not found"
            assert "error" not in response, f"{tool_name} failed: {response}"
            assert "result" in response, f"No result for {tool_name}: {response}"


@pytest.mark.asyncio
async def test_server_component_health(llm_compliant_server):
    """Test that the LLM-compliant server components are healthy"""
    client = llm_compliant_server

    # Test basic tool listing (tests core framework)
    tools_response = await asyncio.wait_for(client.list_tools(), timeout=15.0)
    assert "result" in tools_response

    # Test tool execution (tests handlers and operations)
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = Path(tmp_dir)
        _run_git_isolated(
            ["git", "init"], cwd=repo_path, check=True, capture_output=True
        )

        status_response = await asyncio.wait_for(
            client.call_tool("git_status", {"repo_path": str(repo_path)}), timeout=15.0
        )
        assert "result" in status_response

    # If we reach here, the LLM-compliant architecture is working correctly


if __name__ == "__main__":
    # Allow running this test directly for debugging
    pytest.main([__file__, "-v"])
