#!/usr/bin/env python3
"""
End-to-end test for MCP Git Server
Tests the server as if called by `uv run` with real MCP client interaction
"""

import asyncio
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

import pytest


class MCPTestClient:
    """Simple MCP client for testing the server"""

    def __init__(self, server_process):
        self.process = server_process
        self.request_id = 0

    def _next_id(self) -> int:
        self.request_id += 1
        return self.request_id

    async def send_request(
        self, method: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Send a JSON-RPC request to the server"""
        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params or {},
        }

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

    async def initialize(self) -> Dict[str, Any]:
        """Initialize the MCP session"""
        return await self.send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"experimental": {}, "sampling": {}},
                "clientInfo": {"name": "test-client", "version": "1.0.0"},
            },
        )

    async def list_tools(self) -> Dict[str, Any]:
        """List available tools"""
        return await self.send_request("tools/list")

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool"""
        return await self.send_request(
            "tools/call", {"name": name, "arguments": arguments}
        )


@pytest.fixture
@pytest.mark.e2e
@pytest.mark.ci_skip
async def mcp_server():
    """Start MCP server as subprocess and return test client"""
    # Set up environment with a test GitHub token if available
    env = os.environ.copy()
    env["GITHUB_TOKEN"] = env.get("GITHUB_TOKEN", "test_token_placeholder")

    # Start server process
    server_cmd = ["uv", "run", "python", "-m", "mcp_server_git"]

    cwd = Path(__file__).parent.parent
    process = await asyncio.create_subprocess_exec(
        *server_cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=cwd,
    )

    # Create test client
    client = MCPTestClient(process)

    # Initialize the session
    try:
        init_response = await asyncio.wait_for(client.initialize(), timeout=10.0)
        assert "result" in init_response, f"Initialization failed: {init_response}"

        yield client

    finally:
        # Clean up
        if process.returncode is None:
            process.terminate()
            await process.wait()


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.ci_skip
async def test_server_startup_and_initialization(mcp_server):
    """Test that server starts up and initializes properly"""
    client = mcp_server

    # Should already be initialized by fixture
    # Test listing tools
    tools_response = await client.list_tools()
    assert "result" in tools_response, f"List tools failed: {tools_response}"

    tools = tools_response["result"]["tools"]
    tool_names = [tool["name"] for tool in tools]

    # Verify GitHub API tools are present
    github_tools = [
        "github_get_pr_details",
        "github_get_pr_checks",
        "github_list_pull_requests",
        "github_get_pr_status",
        "github_get_pr_files",
    ]

    for tool_name in github_tools:
        assert tool_name in tool_names, (
            f"GitHub tool {tool_name} not found in available tools"
        )

    print(f"✅ Server initialized successfully with {len(tools)} tools")


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.ci_skip
async def test_github_api_tools_routing(mcp_server):
    """Test that GitHub API tools are properly routed (not returning 'not implemented')"""
    client = mcp_server

    # Test with a GitHub API tool that should work even without real token
    response = await client.call_tool(
        "github_get_pr_details",
        {"repo_owner": "test", "repo_name": "test", "pr_number": 1},
    )

    # Should not get "not implemented" error anymore
    assert "result" in response, f"Tool call failed: {response}"

    result_text = response["result"]["content"][0]["text"]
    assert "not implemented" not in result_text.lower(), (
        f"Tool still showing as not implemented: {result_text}"
    )

    # May get authentication error or other GitHub API error, but not "not implemented"
    print(f"✅ GitHub API tool routing works - got response: {result_text[:100]}...")


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.ci_skip
async def test_git_tools_still_work(mcp_server):
    """Test that regular git tools still work after our changes"""
    client = mcp_server

    # Create a temporary git repo for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir)

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=repo_path, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )

        # Test git status tool
        response = await client.call_tool("git_status", {"repo_path": str(repo_path)})

        assert "result" in response, f"Git status tool failed: {response}"
        result_text = response["result"]["content"][0]["text"]
        assert "Repository status" in result_text, (
            f"Unexpected git status response: {result_text}"
        )

        print("✅ Git tools still work correctly")


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.ci_skip
async def test_tool_separation(mcp_server):
    """Test that GitHub API tools and Git tools are properly separated"""
    client = mcp_server

    # GitHub API tools should work without repo_path
    github_response = await client.call_tool(
        "github_list_pull_requests", {"repo_owner": "test", "repo_name": "test"}
    )

    assert "result" in github_response, (
        f"GitHub tool without repo_path failed: {github_response}"
    )

    # Git tools should require repo_path
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir)
        subprocess.run(["git", "init"], cwd=repo_path, check=True)

        git_response = await client.call_tool(
            "git_status", {"repo_path": str(repo_path)}
        )

        assert "result" in git_response, (
            f"Git tool with repo_path failed: {git_response}"
        )

    print("✅ Tool separation working correctly")
