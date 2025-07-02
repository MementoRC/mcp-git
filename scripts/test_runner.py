#!/usr/bin/env python3
"""
TDD Test Runner Script

Provides commands for running tests with different coverage and reporting options.
Enforces TDD governance rules and quality gates.
"""

import sys
import subprocess
from pathlib import Path
from typing import List, Optional

class TDDTestRunner:
    """Test runner that enforces TDD governance rules."""
    
    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path(__file__).parent.parent
        self.coverage_threshold = 80
        
    def run_unit_tests(self, verbose: bool = False) -> int:
        """Run unit tests only (fast feedback loop)."""
        cmd = ["uv", "run", "pytest", "-m", "unit"]
        if verbose:
            cmd.append("-v")
        
        print("🔬 Running unit tests...")
        return subprocess.run(cmd, cwd=self.project_root).returncode
    
    def run_integration_tests(self, verbose: bool = False) -> int:
        """Run integration tests."""
        cmd = ["uv", "run", "pytest", "-m", "integration"]
        if verbose:
            cmd.append("-v")
            
        print("🔗 Running integration tests...")
        return subprocess.run(cmd, cwd=self.project_root).returncode
    
    def run_system_tests(self, verbose: bool = False) -> int:
        """Run system tests."""
        cmd = ["uv", "run", "pytest", "-m", "system"]
        if verbose:
            cmd.append("-v")
            
        print("🏗️ Running system tests...")
        return subprocess.run(cmd, cwd=self.project_root).returncode
    
    def run_all_tests(self, with_coverage: bool = True, verbose: bool = False) -> int:
        """Run all tests with optional coverage reporting."""
        cmd = ["uv", "run", "pytest"]
        
        if with_coverage:
            cmd.extend([
                "--cov=src",
                "--cov-report=term-missing",
                "--cov-report=html",
                f"--cov-fail-under={self.coverage_threshold}"
            ])
        
        if verbose:
            cmd.append("-v")
            
        print("🧪 Running complete test suite...")
        result = subprocess.run(cmd, cwd=self.project_root)
        
        if result.returncode == 0:
            print("✅ All tests passed!")
            if with_coverage:
                print(f"✅ Coverage threshold ({self.coverage_threshold}%) met!")
        else:
            print("❌ Tests failed or coverage threshold not met!")
            
        return result.returncode
    
    def run_tdd_cycle(self, test_pattern: str) -> int:
        """Run TDD Red-Green-Refactor cycle for specific test."""
        print(f"🔄 Running TDD cycle for: {test_pattern}")
        
        # Red: Run specific test (should fail)
        print("🔴 RED: Running test (should fail)...")
        cmd = ["uv", "run", "pytest", "-k", test_pattern, "-v"]
        result = subprocess.run(cmd, cwd=self.project_root)
        
        if result.returncode == 0:
            print("⚠️ Test already passes - implement more requirements!")
        else:
            print("✅ Test failed as expected - ready for implementation!")
            
        return result.returncode
    
    def validate_tdd_governance(self) -> bool:
        """Validate TDD governance rules compliance."""
        print("🔐 Validating TDD governance compliance...")
        
        # Check if tests exist for implementation files
        src_files = list(self.project_root.glob("src/**/*.py"))
        test_files = list(self.project_root.glob("tests/**/*.py"))
        
        implementation_files = [f for f in src_files if not f.name.startswith("__")]
        test_count = len([f for f in test_files if f.name.startswith("test_")])
        
        print(f"📊 Implementation files: {len(implementation_files)}")
        print(f"📊 Test files: {test_count}")
        
        if test_count == 0:
            print("❌ No test files found - TDD requires tests first!")
            return False
            
        print("✅ TDD governance validation passed!")
        return True


def main():
    """Main CLI interface for TDD test runner."""
    import argparse
    
    parser = argparse.ArgumentParser(description="TDD Test Runner")
    parser.add_argument("command", choices=[
        "unit", "integration", "system", "all", "tdd", "validate"
    ], help="Test command to run")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("-k", "--pattern", help="Test pattern for TDD cycle")
    parser.add_argument("--no-coverage", action="store_true", help="Skip coverage reporting")
    
    args = parser.parse_args()
    
    runner = TDDTestRunner()
    
    if args.command == "unit":
        return runner.run_unit_tests(args.verbose)
    elif args.command == "integration":
        return runner.run_integration_tests(args.verbose)
    elif args.command == "system":
        return runner.run_system_tests(args.verbose)
    elif args.command == "all":
        return runner.run_all_tests(not args.no_coverage, args.verbose)
    elif args.command == "tdd":
        if not args.pattern:
            print("❌ TDD cycle requires test pattern (-k)")
            return 1
        return runner.run_tdd_cycle(args.pattern)
    elif args.command == "validate":
        return 0 if runner.validate_tdd_governance() else 1
    
    return 1


if __name__ == "__main__":
    sys.exit(main())