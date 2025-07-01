#!/usr/bin/env python3
"""
Test script to verify the defensive environment variable loading fix.
This simulates the exact scenario where ClaudeCode makes MCP tool calls.
"""

import os
import asyncio
import sys
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from mcp_server_git.github.client import get_github_client
from mcp_server_git.github.api import github_list_pull_requests


async def test_defensive_loading():
    """Test the defensive environment variable loading fix."""
    print("🧪 Testing Defensive Environment Variable Loading Fix\n")

    # Step 1: Clear environment to simulate MCP context issue
    print("1. Simulating MCP context where GITHUB_TOKEN is not initially available...")
    original_token = os.environ.get("GITHUB_TOKEN")
    if "GITHUB_TOKEN" in os.environ:
        del os.environ["GITHUB_TOKEN"]

    # Verify token is not available
    token_check = os.getenv("GITHUB_TOKEN")
    print(f"   GITHUB_TOKEN status: {'❌ NOT SET' if not token_check else '✅ SET'}")
    print()

    # Step 2: Test GitHub client creation with defensive loading
    print("2. Testing GitHub client creation with defensive loading...")
    client = get_github_client()

    if client:
        print("   ✅ GitHub client created successfully with defensive loading!")
        print(f"   Token length: {len(client.token)}")
        print(f"   Token preview: {client.token[:10]}...")

        # Test API call
        print("\n3. Testing GitHub API call...")
        try:
            response = await client.get("/user")
            if response.status == 200:
                user_data = await response.json()
                print(
                    f"   ✅ API call successful! User: {user_data.get('login', 'Unknown')}"
                )

                # Test a full MCP tool function
                print(
                    "\n4. Testing full MCP tool function (github_list_pull_requests)..."
                )
                await client.session.close()  # Close the test client

                # Clear environment again to test the full tool call
                if "GITHUB_TOKEN" in os.environ:
                    del os.environ["GITHUB_TOKEN"]

                result = await github_list_pull_requests(
                    "MementoRC",
                    "ClaudeCode",
                    "open",
                    None,
                    None,
                    "created",
                    "desc",
                    5,
                    1,
                )

                if "❌" not in result:
                    print("   ✅ Full MCP tool call successful!")
                    print(f"   Result preview: {result[:200]}...")
                else:
                    print(f"   ❌ Full MCP tool call failed: {result}")

            else:
                print(f"   ❌ API call failed with status: {response.status}")
                response_text = await response.text()
                print(f"   Response: {response_text[:200]}")
        except Exception as e:
            print(f"   ❌ API call failed with exception: {e}")
        finally:
            if (
                hasattr(client, "session")
                and client.session
                and not client.session.closed
            ):
                await client.session.close()
    else:
        print("   ❌ GitHub client creation failed even with defensive loading")
        print(
            "   This suggests the .env files are not accessible or don't contain GITHUB_TOKEN"
        )

    # Step 3: Restore original environment if it existed
    if original_token:
        os.environ["GITHUB_TOKEN"] = original_token

    print("\n🎯 TEST RESULTS:")
    if client:
        print("   ✅ DEFENSIVE LOADING FIX IS WORKING!")
        print("   - Environment variables can be loaded on-demand")
        print(
            "   - GitHub client creation succeeds even when token is initially missing"
        )
        print("   - MCP tool calls should now work reliably")
    else:
        print("   ❌ DEFENSIVE LOADING FIX NEEDS REFINEMENT")
        print("   - Check if .env files exist and contain GITHUB_TOKEN")
        print("   - Verify .env file paths and permissions")


async def test_current_env_status():
    """Test current environment status for debugging."""
    print("\n📋 Current Environment Status:")

    # Check for .env files
    possible_env_files = [
        Path.cwd() / ".env",
        Path.cwd().parent / ".env",
        Path.home() / ".claude" / ".env",
        Path("/tmp/claude-code") / ".env"
        if Path("/tmp/claude-code").exists()
        else None,
    ]

    print("   .env file locations:")
    for env_file in possible_env_files:
        if env_file and env_file.exists():
            print(f"   ✅ {env_file} (exists)")
            try:
                with open(env_file, "r") as f:
                    content = f.read()
                    has_github_token = "GITHUB_TOKEN" in content
                    print(
                        f"      Contains GITHUB_TOKEN: {'✅' if has_github_token else '❌'}"
                    )
            except Exception as e:
                print(f"      Error reading file: {e}")
        elif env_file:
            print(f"   ❌ {env_file} (not found)")

    # Check current working directory
    print(f"\n   Current working directory: {Path.cwd()}")

    # Check if we're in a ClaudeCode context
    cwd_str = str(Path.cwd())
    if "ClaudeCode" in cwd_str:
        print("   ✅ Running in ClaudeCode context")
    else:
        print("   ⚠️ Not in ClaudeCode context")


if __name__ == "__main__":
    asyncio.run(test_current_env_status())
    asyncio.run(test_defensive_loading())
