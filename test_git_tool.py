import json
import subprocess
import sys


def test_git_tool():
    """Test calling an actual git tool."""
    print("🔧 Testing git_status tool...")

    proc = subprocess.Popen(
        ["pixi", "run", "-e", "ci", "mcp-server-git", "--repository", "."],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Initialize
        init_request = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "id": 1,
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "test-client", "version": "1.0.0"},
            },
        }

        proc.stdin.write(json.dumps(init_request) + "\n")
        proc.stdin.flush()
        proc.stdout.readline()  # Read init response

        # Send initialized notification
        proc.stdin.write(
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
        )
        proc.stdin.flush()

        # Call git_status tool
        git_status_request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 3,
            "params": {"name": "git_status", "arguments": {"repo_path": "."}},
        }

        print("📤 Calling git_status tool...")
        proc.stdin.write(json.dumps(git_status_request) + "\n")
        proc.stdin.flush()

        # Read response
        response = proc.stdout.readline().strip()
        if response:
            result = json.loads(response)
            if "result" in result:
                print("✅ git_status tool executed successfully!")
                status_output = result["result"].get("content", [{}])[0].get("text", "")
                print(f"📊 Status output length: {len(status_output)} characters")
                print(f"📊 First 200 chars: {status_output[:200]}...")
                return True
            else:
                print(f"❌ Tool execution failed: {result}")
                return False

    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    finally:
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    success = test_git_tool()
    sys.exit(0 if success else 1)
