#!/usr/bin/env python3
"""
Test Status Manager - Tool for managing test implementation status

This script provides commands to:
1. Update test status as features are implemented
2. Move to next development phase
3. Add/remove tests from expected fail lists
4. Generate reports on implementation progress
5. Validate test status configuration

Usage:
    python scripts/test_status_manager.py status
    python scripts/test_status_manager.py next-phase
    python scripts/test_status_manager.py mark-implemented "test_pattern"
    python scripts/test_status_manager.py mark-failing "test_pattern"
    python scripts/test_status_manager.py validate
    python scripts/test_status_manager.py report
"""

import json
import sys
import argparse
from pathlib import Path
from typing import Dict, Any
from datetime import datetime


class TestStatusManager:
    def __init__(self, project_root: Path = None):
        if project_root is None:
            project_root = Path(__file__).parent.parent
        
        self.project_root = project_root
        self.status_file = project_root / ".taskmaster" / "test-status.json"
        self.status_data = self._load_status()
    
    def _load_status(self) -> Dict[str, Any]:
        """Load test status configuration"""
        if self.status_file.exists():
            with open(self.status_file, 'r') as f:
                return json.load(f)
        else:
            return self._create_default_status()
    
    def _save_status(self):
        """Save test status configuration"""
        self.status_data["last_updated"] = datetime.now().isoformat()
        
        # Ensure directory exists
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.status_file, 'w') as f:
            json.dump(self.status_data, f, indent=2)
    
    def _create_default_status(self) -> Dict[str, Any]:
        """Create default test status configuration"""
        return {
            "project": "mcp-git LLM Compliance Enhancement",
            "version": "0.6.3",
            "test_phases": {
                "phase_1_foundation": {
                    "description": "Core type system and basic structures",
                    "status": "in_progress",
                    "expected_passing": [],
                    "expected_failing": [
                        "tests/unit/types/test_git_types.py::*",
                        "tests/unit/types/test_github_types.py::*",
                        "tests/unit/types/test_mcp_types.py::*",
                        "tests/unit/types/test_validation_types.py::*",
                        "tests/unit/types/test_composite_types.py::*"
                    ],
                    "target_commit": "TBD"
                }
            },
            "current_phase": "phase_1_foundation",
            "last_updated": datetime.now().isoformat(),
            "commit_hash": "unknown"
        }
    
    def show_status(self):
        """Display current test status"""
        current_phase = self.status_data.get("current_phase", "unknown")
        print("📊 Test Status Report")
        print("=" * 50)
        print(f"Project: {self.status_data.get('project', 'Unknown')}")
        print(f"Version: {self.status_data.get('version', 'Unknown')}")
        print(f"Current Phase: {current_phase}")
        print(f"Last Updated: {self.status_data.get('last_updated', 'Unknown')}")
        print()
        
        if current_phase in self.status_data.get("test_phases", {}):
            phase_info = self.status_data["test_phases"][current_phase]
            print("Phase Details:")
            print(f"  Description: {phase_info.get('description', 'N/A')}")
            print(f"  Status: {phase_info.get('status', 'unknown')}")
            print(f"  Target Commit: {phase_info.get('target_commit', 'TBD')}")
            print()
            
            expected_passing = phase_info.get("expected_passing", [])
            expected_failing = phase_info.get("expected_failing", [])
            
            print(f"Expected Passing Tests ({len(expected_passing)}):")
            for pattern in expected_passing:
                print(f"  ✅ {pattern}")
            
            print(f"\nExpected Failing Tests ({len(expected_failing)}):")
            for pattern in expected_failing:
                print(f"  ❌ {pattern}")
    
    def mark_implemented(self, test_pattern: str):
        """Mark a test pattern as implemented (move from failing to passing)"""
        current_phase = self.status_data.get("current_phase", "")
        if current_phase not in self.status_data.get("test_phases", {}):
            print(f"❌ Current phase '{current_phase}' not found")
            return
        
        phase_info = self.status_data["test_phases"][current_phase]
        expected_failing = phase_info.get("expected_failing", [])
        expected_passing = phase_info.get("expected_passing", [])
        
        # Remove from failing list
        if test_pattern in expected_failing:
            expected_failing.remove(test_pattern)
            print(f"✅ Removed '{test_pattern}' from expected failing list")
        else:
            print(f"⚠️ Pattern '{test_pattern}' not found in expected failing list")
        
        # Add to passing list if not already there
        if test_pattern not in expected_passing:
            expected_passing.append(test_pattern)
            print(f"✅ Added '{test_pattern}' to expected passing list")
        
        phase_info["expected_failing"] = expected_failing
        phase_info["expected_passing"] = expected_passing
        self._save_status()
        print("💾 Status updated and saved")
    
    def mark_failing(self, test_pattern: str):
        """Mark a test pattern as intentionally failing"""
        current_phase = self.status_data.get("current_phase", "")
        if current_phase not in self.status_data.get("test_phases", {}):
            print(f"❌ Current phase '{current_phase}' not found")
            return
        
        phase_info = self.status_data["test_phases"][current_phase]
        expected_failing = phase_info.get("expected_failing", [])
        expected_passing = phase_info.get("expected_passing", [])
        
        # Remove from passing list
        if test_pattern in expected_passing:
            expected_passing.remove(test_pattern)
            print(f"✅ Removed '{test_pattern}' from expected passing list")
        
        # Add to failing list if not already there
        if test_pattern not in expected_failing:
            expected_failing.append(test_pattern)
            print(f"✅ Added '{test_pattern}' to expected failing list")
        else:
            print(f"⚠️ Pattern '{test_pattern}' already in expected failing list")
        
        phase_info["expected_failing"] = expected_failing
        phase_info["expected_passing"] = expected_passing
        self._save_status()
        print("💾 Status updated and saved")
    
    def next_phase(self):
        """Move to the next development phase"""
        current_phase = self.status_data.get("current_phase", "")
        phase_order = ["phase_1_foundation", "phase_2_implementation", "phase_3_integration"]
        
        try:
            current_index = phase_order.index(current_phase)
            if current_index < len(phase_order) - 1:
                next_phase = phase_order[current_index + 1]
                self.status_data["current_phase"] = next_phase
                
                # Mark current phase as completed
                if current_phase in self.status_data.get("test_phases", {}):
                    self.status_data["test_phases"][current_phase]["status"] = "completed"
                
                # Set next phase to in_progress if it exists
                if next_phase not in self.status_data.get("test_phases", {}):
                    self._create_next_phase(next_phase)
                else:
                    self.status_data["test_phases"][next_phase]["status"] = "in_progress"
                
                self._save_status()
                print(f"✅ Moved from {current_phase} to {next_phase}")
            else:
                print(f"✅ Already at final phase: {current_phase}")
        except ValueError:
            print(f"❌ Unknown current phase: {current_phase}")
    
    def _create_next_phase(self, phase_name: str):
        """Create configuration for next phase"""
        phase_configs = {
            "phase_2_implementation": {
                "description": "Implement core type classes",
                "status": "in_progress",
                "expected_passing": [
                    "tests/unit/types/test_git_types.py::TestGitRepositoryPath::*",
                    "tests/unit/types/test_github_types.py::TestGitHubRepository::*"
                ],
                "expected_failing": [
                    "tests/unit/types/test_composite_types.py::TestIntegratedOperationResult::*",
                    "tests/unit/types/test_validation_types.py::TestCompositeValidator::*"
                ],
                "target_commit": "TBD"
            },
            "phase_3_integration": {
                "description": "Integration and composite types",
                "status": "in_progress",
                "expected_passing": [
                    "tests/unit/types/test_composite_types.py::*"
                ],
                "expected_failing": [
                    "tests/integration/test_end_to_end.py::*"
                ],
                "target_commit": "TBD"
            }
        }
        
        if phase_name in phase_configs:
            self.status_data["test_phases"][phase_name] = phase_configs[phase_name]
    
    def validate(self):
        """Validate test status configuration"""
        print("🔍 Validating test status configuration...")
        errors = []
        
        # Check required fields
        required_fields = ["project", "current_phase", "test_phases"]
        for field in required_fields:
            if field not in self.status_data:
                errors.append(f"Missing required field: {field}")
        
        # Check current phase exists
        current_phase = self.status_data.get("current_phase")
        if current_phase and current_phase not in self.status_data.get("test_phases", {}):
            errors.append(f"Current phase '{current_phase}' not defined in test_phases")
        
        # Check phase structure
        for phase_name, phase_info in self.status_data.get("test_phases", {}).items():
            required_phase_fields = ["description", "status", "expected_passing", "expected_failing"]
            for field in required_phase_fields:
                if field not in phase_info:
                    errors.append(f"Phase '{phase_name}' missing field: {field}")
        
        if errors:
            print("❌ Validation failed:")
            for error in errors:
                print(f"  - {error}")
        else:
            print("✅ Configuration is valid")
    
    def report(self):
        """Generate detailed implementation progress report"""
        print("📈 Implementation Progress Report")
        print("=" * 50)
        
        for phase_name, phase_info in self.status_data.get("test_phases", {}).items():
            print(f"\n📋 {phase_name.replace('_', ' ').title()}")
            print(f"   Status: {phase_info.get('status', 'unknown')}")
            print(f"   Description: {phase_info.get('description', 'N/A')}")
            
            expected_passing = phase_info.get("expected_passing", [])
            expected_failing = phase_info.get("expected_failing", [])
            
            total_tests = len(expected_passing) + len(expected_failing)
            if total_tests > 0:
                completion_rate = len(expected_passing) / total_tests * 100
                print(f"   Progress: {len(expected_passing)}/{total_tests} ({completion_rate:.1f}%)")
            else:
                print("   Progress: No tests defined")


def main():
    parser = argparse.ArgumentParser(description="Test Status Manager")
    parser.add_argument("command", choices=[
        "status", "next-phase", "mark-implemented", "mark-failing", 
        "validate", "report"
    ])
    parser.add_argument("pattern", nargs="?", help="Test pattern for mark commands")
    
    args = parser.parse_args()
    
    manager = TestStatusManager()
    
    if args.command == "status":
        manager.show_status()
    elif args.command == "next-phase":
        manager.next_phase()
    elif args.command == "mark-implemented":
        if not args.pattern:
            print("❌ Test pattern required for mark-implemented")
            sys.exit(1)
        manager.mark_implemented(args.pattern)
    elif args.command == "mark-failing":
        if not args.pattern:
            print("❌ Test pattern required for mark-failing")
            sys.exit(1)
        manager.mark_failing(args.pattern)
    elif args.command == "validate":
        manager.validate()
    elif args.command == "report":
        manager.report()


if __name__ == "__main__":
    main()