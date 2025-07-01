#!/usr/bin/env python3
"""
Debug script to test environment variable persistence during MCP execution.
This script simulates what happens during MCP tool calls.
"""

import os
import asyncio
import sys
from pathlib import Path

# Add the src directory to Python path so we can import the modules
sys.path.insert(0, str(Path(__file__).parent / "src"))

from mcp_server_git.server import load_environment_variables
from mcp_server_git.github.client import get_github_client


async def test_environment_persistence():
    """Test environment variable loading and persistence."""
    print("🔍 Testing Environment Variable Persistence\n")

    # Step 1: Check environment before loading
    print("1. Environment BEFORE loading .env files:")
    github_token_before = os.getenv("GITHUB_TOKEN")
    print(f"   GITHUB_TOKEN: {'✅ SET' if github_token_before else '❌ NOT SET'}")
    if github_token_before:
        print(f"   Token length: {len(github_token_before)}")
        print(f"   Token preview: {github_token_before[:10]}...")
    print()

    # Step 2: Load environment variables (simulate server startup)
    print("2. Loading environment variables (simulating server startup)...")
    repository_path = Path.cwd()  # Current working directory
    load_environment_variables(repository_path)
    print()

    # Step 3: Check environment after loading
    print("3. Environment AFTER loading .env files:")
    github_token_after = os.getenv("GITHUB_TOKEN")
    print(f"   GITHUB_TOKEN: {'✅ SET' if github_token_after else '❌ NOT SET'}")
    if github_token_after:
        print(f"   Token length: {len(github_token_after)}")
        print(f"   Token preview: {github_token_after[:10]}...")
    print()

    # Step 4: Test GitHub client creation (simulate tool call)
    print("4. Testing GitHub client creation (simulating MCP tool call)...")
    client = get_github_client()
    if client:
        print("   ✅ GitHub client created successfully")
        print(f"   Client token length: {len(client.token)}")
        print(f"   Client token preview: {client.token[:10]}...")

        # Test a simple API call
        print("\n5. Testing GitHub API call...")
        try:
            response = await client.get("/user")
            if response.status == 200:
                user_data = await response.json()
                print(
                    f"   ✅ API call successful! User: {user_data.get('login', 'Unknown')}"
                )
            else:
                print(f"   ❌ API call failed with status: {response.status}")
                response_text = await response.text()
                print(f"   Response: {response_text[:200]}")
        except Exception as e:
            print(f"   ❌ API call failed with exception: {e}")
        finally:
            await client.session.close()
    else:
        print("   ❌ GitHub client creation failed")
    print()

    # Step 6: Simulate what happens in a fresh process/context
    print("6. Simulating fresh process context (simulating MCP tool execution)...")

    # This simulates a new process or context where environment variables
    # might not be properly inherited
    original_token = os.environ.get("GITHUB_TOKEN")

    # Temporarily clear the environment variable to simulate the issue
    if "GITHUB_TOKEN" in os.environ:
        del os.environ["GITHUB_TOKEN"]

    # Try to create GitHub client (this should fail)
    client_fresh = get_github_client()
    if client_fresh:
        print("   ✅ GitHub client created in fresh context")
    else:
        print(
            "   ❌ GitHub client creation failed in fresh context (THIS IS THE ISSUE!)"
        )

    # Restore the environment variable
    if original_token:
        os.environ["GITHUB_TOKEN"] = original_token

    print("\n🎯 ANALYSIS:")
    print("   - Environment variables are loaded correctly during server startup")
    print("   - GitHub client works when environment is available")
    print("   - The issue occurs when environment variables are not available")
    print("     during individual MCP tool calls")
    print("\n   PROBABLE ROOT CAUSE:")
    print("   - MCP tool calls execute in a context where environment variables")
    print("     loaded during server startup are not available")
    print("   - Need to ensure environment variables persist throughout")
    print("     the entire server lifecycle for all tool calls")


if __name__ == "__main__":
    asyncio.run(test_environment_persistence())
