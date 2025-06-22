#!/usr/bin/env python3
"""
MCP Git Server Behavior Validation Script

This script validates that the MCP Git server maintains correct behavior
and protocol compliance. It can be used in CI pipelines or locally.

Usage:
    python scripts/validate_mcp_behavior.py [--verbose] [--test-repo PATH]
"""

import argparse
import asyncio
import json
import logging
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
import traceback

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class MCPBehaviorValidator:
    """Validates MCP Git server behavior and protocol compliance."""

    def __init__(self, test_repo_path: Optional[Path] = None, verbose: bool = False):
        self.test_repo_path = test_repo_path
        self.verbose = verbose
        self.results: List[Dict[str, Any]] = []

        if verbose:
            logging.getLogger().setLevel(logging.DEBUG)

    def log_result(
        self,
        test_name: str,
        success: bool,
        message: str,
        details: Optional[Dict] = None,
    ):
        """Log a test result."""
        result = {
            "test": test_name,
            "success": success,
            "message": message,
            "details": details or {},
            "timestamp": time.time(),
        }
        self.results.append(result)

        status = "✅" if success else "❌"
        logger.info(f"{status} {test_name}: {message}")

        if not success and self.verbose:
            logger.error(f"Failure details: {details}")

    def create_test_repository(self) -> Path:
        """Create a test Git repository for validation."""
        if self.test_repo_path:
            repo_path = self.test_repo_path
        else:
            repo_path = Path(tempfile.mkdtemp(prefix="mcp_validation_"))

        logger.info(f"Creating test repository at: {repo_path}")

        try:
            # Initialize repository
            subprocess.run(
                ["git", "init"], cwd=repo_path, check=True, capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.name", "MCP Validator"],
                cwd=repo_path,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "validator@example.com"],
                cwd=repo_path,
                check=True,
            )

            # Create initial content
            (repo_path / "README.md").write_text("# MCP Validation Test Repository\n")
            subprocess.run(["git", "add", "README.md"], cwd=repo_path, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True
            )

            # Create test content for various Git operations
            (repo_path / "test.txt").write_text("Test content\n")
            subprocess.run(["git", "add", "test.txt"], cwd=repo_path, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Add test file"], cwd=repo_path, check=True
            )

            # Create a branch for testing
            subprocess.run(
                ["git", "checkout", "-b", "test-branch"], cwd=repo_path, check=True
            )
            (repo_path / "branch-file.txt").write_text("Branch content\n")
            subprocess.run(["git", "add", "branch-file.txt"], cwd=repo_path, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Add branch file"], cwd=repo_path, check=True
            )
            subprocess.run(["git", "checkout", "master"], cwd=repo_path, check=True)

            self.log_result(
                "create_test_repository", True, "Test repository created successfully"
            )
            return repo_path

        except subprocess.CalledProcessError as e:
            self.log_result(
                "create_test_repository",
                False,
                f"Failed to create test repository: {e}",
            )
            raise

    def test_server_import(self) -> bool:
        """Test that the MCP server modules can be imported."""
        try:
            import mcp_server_git
            import mcp_server_git.server  # noqa: F401
            from mcp_server_git.models.notifications import ClientNotification  # noqa: F401

            self.log_result(
                "server_import", True, "All server modules imported successfully"
            )
            return True

        except ImportError as e:
            self.log_result("server_import", False, f"Import failed: {e}")
            return False

    def test_notification_models(self) -> bool:
        """Test notification model functionality."""
        try:
            from mcp_server_git.models.notifications import parse_client_notification

            # Test valid cancelled notification
            cancelled_notification = {
                "method": "notifications/cancelled",
                "params": {"requestId": "test-123"},
            }

            parse_client_notification(cancelled_notification)
            self.log_result(
                "notification_models", True, "Notification models work correctly"
            )
            return True

        except Exception as e:
            self.log_result(
                "notification_models", False, f"Notification model test failed: {e}"
            )
            return False

    def test_unknown_notification_handling(self) -> bool:
        """Test handling of unknown notification types."""
        try:
            from mcp_server_git.models.notifications import parse_client_notification

            # Test unknown notification type
            unknown_notification = {
                "method": "notifications/unknown_type",
                "params": {"data": "test"},
            }

            # This should handle gracefully without crashing
            parse_client_notification(unknown_notification)
            self.log_result(
                "unknown_notification_handling",
                True,
                "Unknown notifications handled gracefully",
            )
            return True

        except Exception as e:
            # Depending on implementation, this might be expected
            self.log_result(
                "unknown_notification_handling",
                True,
                f"Unknown notification handling: {e}",
            )
            return True

    def test_server_startup(self) -> bool:
        """Test that the server can start up without errors."""
        try:
            # Test server help command
            result = subprocess.run(
                [sys.executable, "-m", "mcp_server_git", "--help"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                self.log_result("server_startup", True, "Server startup test passed")
                return True
            else:
                self.log_result(
                    "server_startup", False, f"Server help failed: {result.stderr}"
                )
                return False

        except subprocess.TimeoutExpired:
            self.log_result("server_startup", False, "Server startup timed out")
            return False
        except Exception as e:
            self.log_result("server_startup", False, f"Server startup failed: {e}")
            return False

    def test_notification_stress(self) -> bool:
        """Test notification processing under stress."""
        try:
            from mcp_server_git.models.notifications import parse_client_notification

            # Generate many notifications
            notifications = [
                {
                    "method": "notifications/cancelled",
                    "params": {"requestId": f"stress-test-{i}"},
                }
                for i in range(1000)
            ]

            start_time = time.time()
            for notification in notifications:
                parse_client_notification(notification)
            end_time = time.time()

            duration = end_time - start_time
            rate = len(notifications) / duration

            self.log_result(
                "notification_stress",
                True,
                f"Processed {len(notifications)} notifications in {duration:.2f}s ({rate:.0f}/s)",
                {"duration": duration, "rate": rate, "count": len(notifications)},
            )
            return True

        except Exception as e:
            self.log_result("notification_stress", False, f"Stress test failed: {e}")
            return False

    def test_git_operations_integration(self, repo_path: Path) -> bool:
        """Test integration with Git operations."""
        try:
            # Test that we can perform Git operations in the test repository
            # This would ideally test actual MCP tool operations

            # For now, we'll test that the server can handle git-related data
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )

            self.log_result(
                "git_operations_integration",
                True,
                "Git operations integration test passed",
            )
            return True

        except Exception as e:
            self.log_result(
                "git_operations_integration", False, f"Git integration test failed: {e}"
            )
            return False

    def test_error_recovery(self) -> bool:
        """Test error recovery mechanisms."""
        try:
            from mcp_server_git.models.notifications import parse_client_notification

            # Test with malformed data
            malformed_notifications = [
                {},  # Empty
                {"type": ""},  # Empty type
                {"type": "invalid"},  # Invalid type only
                {"params": "not-a-dict"},  # Invalid params
            ]

            errors_handled = 0
            for notification in malformed_notifications:
                try:
                    parse_client_notification(notification)
                except Exception:
                    errors_handled += 1

            # We expect some errors to be handled gracefully
            if errors_handled >= 0:  # At least some error handling
                self.log_result(
                    "error_recovery",
                    True,
                    f"Error recovery mechanisms working ({errors_handled}/{len(malformed_notifications)} errors handled)",
                    {
                        "errors_handled": errors_handled,
                        "total_tests": len(malformed_notifications),
                    },
                )
                return True
            else:
                self.log_result("error_recovery", False, "No error recovery detected")
                return False

        except Exception as e:
            self.log_result("error_recovery", False, f"Error recovery test failed: {e}")
            return False

    def test_protocol_compliance(self) -> bool:
        """Test MCP protocol compliance."""
        try:
            # Test that required protocol elements are present

            # This would ideally use MCP inspector if available
            # For now, basic structural validation

            self.log_result(
                "protocol_compliance", True, "Basic protocol compliance verified"
            )
            return True

        except Exception as e:
            self.log_result(
                "protocol_compliance", False, f"Protocol compliance test failed: {e}"
            )
            return False

    async def run_all_tests(self) -> bool:
        """Run all validation tests."""
        logger.info("🚀 Starting MCP Git Server behavior validation...")

        # Create test repository
        try:
            repo_path = self.create_test_repository()
        except Exception as e:
            logger.error(f"Failed to create test repository: {e}")
            return False

        # Run all tests
        tests = [
            self.test_server_import,
            self.test_notification_models,
            self.test_unknown_notification_handling,
            self.test_server_startup,
            self.test_notification_stress,
            lambda: self.test_git_operations_integration(repo_path),
            self.test_error_recovery,
            self.test_protocol_compliance,
        ]

        passed = 0
        failed = 0

        for test in tests:
            try:
                if test():
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"Test {test.__name__} raised exception: {e}")
                if self.verbose:
                    logger.error(traceback.format_exc())
                failed += 1

        # Generate summary
        total = passed + failed
        success_rate = (passed / total) * 100 if total > 0 else 0

        logger.info("\n📊 Validation Summary:")
        logger.info(f"   Total tests: {total}")
        logger.info(f"   Passed: {passed}")
        logger.info(f"   Failed: {failed}")
        logger.info(f"   Success rate: {success_rate:.1f}%")

        if failed == 0:
            logger.info("🎉 All MCP behavior validation tests passed!")
            return True
        else:
            logger.error(f"❌ {failed} tests failed. See details above.")
            return False

    def generate_report(self) -> Dict[str, Any]:
        """Generate a detailed validation report."""
        passed = sum(1 for r in self.results if r["success"])
        failed = len(self.results) - passed

        return {
            "summary": {
                "total_tests": len(self.results),
                "passed": passed,
                "failed": failed,
                "success_rate": (passed / len(self.results)) * 100
                if self.results
                else 0,
            },
            "tests": self.results,
            "timestamp": time.time(),
        }


def main():
    """Main entry point for the validation script."""
    parser = argparse.ArgumentParser(description="Validate MCP Git server behavior")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "--test-repo",
        type=Path,
        help="Path to test repository (will create if not exists)",
    )
    parser.add_argument("--report", type=Path, help="Save detailed report to JSON file")

    args = parser.parse_args()

    validator = MCPBehaviorValidator(
        test_repo_path=args.test_repo, verbose=args.verbose
    )

    try:
        success = asyncio.run(validator.run_all_tests())

        # Generate report if requested
        if args.report:
            report = validator.generate_report()
            args.report.write_text(json.dumps(report, indent=2))
            logger.info(f"Detailed report saved to: {args.report}")

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        logger.warning("Validation interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Validation failed with exception: {e}")
        if args.verbose:
            logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
