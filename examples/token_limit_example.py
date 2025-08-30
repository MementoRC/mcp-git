"""
Example usage of the Token Limit Protection System.

This example demonstrates how to integrate and use the token limit protection
system with the MCP Git Server, including configuration, middleware setup,
and different usage scenarios.
"""

import asyncio
import logging

# Setup logging to see the system in action
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import the token limit system components
from src.mcp_server_git.config.token_limits import (
    TokenLimitConfigManager,
    TokenLimitProfile,
    TokenLimitSettings,
)
from src.mcp_server_git.middlewares.token_limit import (
    TokenLimitConfig,
    TokenLimitMiddleware,
)
from src.mcp_server_git.utils.content_optimization import (
    ContentOptimizer,
    ResponseFormatter,
)
from src.mcp_server_git.utils.token_management import (
    ClientDetector,
    ClientType,
    IntelligentTruncationManager,
    TokenEstimator,
)


def example_basic_token_estimation():
    """Demonstrate basic token estimation for different content types."""
    print("\n=== Basic Token Estimation Example ===")

    estimator = TokenEstimator()

    # Different types of git content
    examples = [
        (
            "Simple status",
            "On branch main\nnothing to commit, working tree clean",
            "text",
        ),
        (
            "Code diff",
            '''diff --git a/app.py b/app.py
index 1234567..abcdefg 100644
--- a/app.py
+++ b/app.py
@@ -1,5 +1,8 @@
 def hello():
-    print("world")
+    print("hello world")
+    return "success"''',
            "diff",
        ),
        (
            "Git log",
            """commit abc123def456ghi789jkl012mno345pqr678stu
Author: Developer <dev@example.com>
Date: Mon Jan 1 12:00:00 2024 +0000

    Add new feature for user authentication

    - Implement OAuth2 integration
    - Add user session management
    - Update documentation""",
            "log",
        ),
    ]

    for name, content, content_type in examples:
        from src.mcp_server_git.utils.token_management import ContentType

        ct = getattr(ContentType, content_type.upper())

        estimate = estimator.estimate_tokens(content, ct)
        print(f"\n{name}:")
        print(f"  Characters: {estimate.char_count}")
        print(f"  Estimated tokens: {estimate.estimated_tokens}")
        print(f"  Confidence: {estimate.confidence:.2f}")


def example_client_detection():
    """Demonstrate client type detection."""
    print("\n=== Client Detection Example ===")

    detector = ClientDetector()

    # Test various user agents
    test_agents = [
        "Claude/1.0 AI Assistant",
        "ChatGPT API Client v2.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/91.0",
        "Custom Git Client v1.0",
        "OpenAI-Python/1.0.0",
        "curl/7.68.0",
    ]

    for user_agent in test_agents:
        client_type = detector.detect_client_type(user_agent)
        print(f"'{user_agent}' -> {client_type.value}")


def example_content_optimization():
    """Demonstrate content optimization for different client types."""
    print("\n=== Content Optimization Example ===")

    optimizer = ContentOptimizer()

    # Example git output with human-friendly formatting
    git_output = """✅ Successfully committed changes to repository
🔒 Enforced GPG signing with key 1234567890ABCDEF
⚠️  MCP Git Server used - no fallback to system git commands

Files changed:
📝 src/app.py (modified)
🆕 tests/test_app.py (new file)
🗑️  old_file.py (deleted)

🎯 Next steps: Push changes to remote repository"""

    print("Original content:")
    print(git_output)

    # Optimize for LLM
    llm_optimized = optimizer.optimize_for_client(
        git_output, ClientType.LLM, "git_commit"
    )
    print("\nOptimized for LLM:")
    print(llm_optimized)

    # Human version (unchanged)
    human_version = optimizer.optimize_for_client(
        git_output, ClientType.HUMAN, "git_commit"
    )
    print("\nHuman version (unchanged):")
    print(human_version)


def example_intelligent_truncation():
    """Demonstrate intelligent truncation for different operation types."""
    print("\n=== Intelligent Truncation Example ===")

    manager = IntelligentTruncationManager()

    # Create a large diff that exceeds token limits
    large_diff = (
        """diff --git a/large_file.py b/large_file.py
index 1234567..abcdefg 100644
--- a/large_file.py
+++ b/large_file.py
@@ -1,100 +1,120 @@
 def process_data(data):
     results = []
-    for item in data:
-        processed = transform_item(item)
-        results.append(processed)
+    for i, item in enumerate(data):
+        # Add progress tracking
+        if i % 100 == 0:
+            print(f"Processing item {i}")
+        processed = transform_item(item)
+        validated = validate_item(processed)
+        results.append(validated)
     return results
"""
        + "\n+    # Additional processing line" * 200
    )  # Make it very long

    print(f"Original diff length: {len(large_diff)} characters")

    # Truncate with different token limits
    for limit in [500, 1000, 2000]:
        result = manager.truncate_for_operation(large_diff, "git_diff", limit)
        print(f"\nTruncated to {limit} tokens:")
        print(f"  Final tokens: {result.final_tokens}")
        print(f"  Truncated: {result.truncated}")
        print(f"  Summary: {result.truncation_summary}")
        if result.truncated:
            print(f"  Content preview: {result.content[:200]}...")


def example_configuration_management():
    """Demonstrate configuration management."""
    print("\n=== Configuration Management Example ===")

    # Create configuration from different sources
    config_manager = TokenLimitConfigManager()

    # Example 1: Use predefined profile
    conservative_settings = TokenLimitSettings.from_profile(
        TokenLimitProfile.CONSERVATIVE
    )
    print("Conservative profile settings:")
    print(f"  LLM token limit: {conservative_settings.llm_token_limit}")
    print(
        f"  Content optimization: {conservative_settings.enable_content_optimization}"
    )

    # Example 2: Load with overrides
    custom_settings = config_manager.load_configuration(
        profile=TokenLimitProfile.BALANCED,
        llm_token_limit=15000,  # Custom override
        enable_client_detection=True,
    )
    print("\nCustom settings (balanced + overrides):")
    print(f"  LLM token limit: {custom_settings.llm_token_limit}")
    print(f"  Client detection: {custom_settings.enable_client_detection}")

    # Example 3: Operation-specific limits
    custom_settings.operation_limits = {
        "git_diff": 25000,  # Allow larger diffs
        "git_log": 10000,  # Restrict logs more
        "git_status": 5000,  # Keep status concise
    }
    print(f"\nOperation-specific limits: {custom_settings.operation_limits}")


def example_middleware_integration():
    """Demonstrate middleware integration."""
    print("\n=== Middleware Integration Example ===")

    # Create middleware with custom configuration
    config = TokenLimitConfig(
        llm_token_limit=20000,
        human_token_limit=0,  # Unlimited for humans
        unknown_token_limit=25000,
        enable_content_optimization=True,
        enable_intelligent_truncation=True,
        operation_overrides={
            "git_diff": 30000,  # Allow larger diffs
            "github_get_pr_files": 15000,  # Restrict PR files
        },
    )

    middleware = TokenLimitMiddleware(config)

    print("Middleware created with configuration:")
    print(f"  LLM token limit: {config.llm_token_limit}")
    print(f"  Content optimization: {config.enable_content_optimization}")
    print(f"  Operation overrides: {config.operation_overrides}")

    # Show metrics (would be populated during actual use)
    metrics = middleware.get_metrics()
    print("\nMiddleware metrics:")
    for key, value in metrics.items():
        print(f"  {key}: {value}")


async def example_end_to_end_processing():
    """Demonstrate end-to-end processing simulation."""
    print("\n=== End-to-End Processing Example ===")

    # Simulate a large git operation result
    large_git_result = (
        """🔍 Git Status Report
✅ Repository: /path/to/repo (branch: feature/new-feature)

📊 Repository Statistics:
  📁 Total files: 1,247
  📝 Modified files: 23
  🆕 New files: 8
  🗑️  Deleted files: 3

📋 Staged Changes:
"""
        + "\n".join([f"  📝 file_{i}.py (modified)" for i in range(100)])
        + """

📋 Unstaged Changes:
"""
        + "\n".join([f"  📝 src/component_{i}.tsx (modified)" for i in range(150)])
        + """

🔍 Git Log (last 50 commits):
"""
        + "\n".join(
            [
                f"""commit {hex(hash(f'commit_{i}'))[:40]}
Author: Developer {i} <dev{i}@example.com>
Date: 2024-01-{i%30+1:02d} 12:00:00 +0000

    Commit message {i} - implemented feature {i}

    Detailed description of changes made in commit {i}.
    This commit includes various improvements and bug fixes.
"""
                for i in range(50)
            ]
        )
    )

    print(f"Original content: {len(large_git_result)} characters")

    # Process through the complete pipeline

    # 1. Detect client type (simulate LLM client)
    detector = ClientDetector()
    client_type = detector.detect_client_type("Claude/1.0 AI Assistant")
    print(f"Detected client type: {client_type.value}")

    # 2. Optimize content for client
    formatter = ResponseFormatter()
    optimized_content = formatter.format_response(
        large_git_result, client_type, "git_status"
    )
    print(f"After optimization: {len(optimized_content)} characters")

    # 3. Apply intelligent truncation if needed
    manager = IntelligentTruncationManager()
    final_result = manager.truncate_for_operation(
        optimized_content,
        "git_status",
        2000,  # 2K token limit
    )

    print(f"After truncation: {len(final_result.content)} characters")
    print(f"Final tokens: {final_result.final_tokens}")
    print(f"Truncated: {final_result.truncated}")
    if final_result.truncated:
        print(f"Truncation summary: {final_result.truncation_summary}")

    print("\nFinal optimized content:")
    print(
        final_result.content[:500] + "..."
        if len(final_result.content) > 500
        else final_result.content
    )


def main():
    """Run all examples."""
    print("Token Limit Protection System - Usage Examples")
    print("=" * 60)

    # Run all examples
    example_basic_token_estimation()
    example_client_detection()
    example_content_optimization()
    example_intelligent_truncation()
    example_configuration_management()
    example_middleware_integration()

    # Run async example
    asyncio.run(example_end_to_end_processing())

    print(f"\n{'=' * 60}")
    print("All examples completed!")
    print("\nTo integrate this system:")
    print(
        "1. Import the middleware: from mcp_server_git.middlewares.token_limit import create_token_limit_middleware"
    )
    print("2. Configure settings: Use TokenLimitConfigManager or environment variables")
    print(
        "3. Add to middleware chain: chain.add_middleware(create_token_limit_middleware())"
    )
    print(
        "4. The system will automatically process responses based on client type and token limits"
    )


if __name__ == "__main__":
    main()
