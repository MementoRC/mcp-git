#!/usr/bin/env python3
"""
Session Notebook Manager - Scientist's logbook for development sessions

This tool helps maintain systematic notes about:
- Issues encountered and solutions applied
- Methodologies developed and refined  
- Lessons learned and insights gained
- Patterns for future UCKN integration

Usage:
    python scripts/session_notebook.py start "Session Title"
    python scripts/session_notebook.py issue "Problem description" "Solution applied"
    python scripts/session_notebook.py method "Methodology name" "Description"
    python scripts/session_notebook.py insight "Key insight gained"
    python scripts/session_notebook.py complete "Session summary"
    python scripts/session_notebook.py export-uckn
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any


class SessionNotebook:
    def __init__(self, project_root: Path = None):
        if project_root is None:
            project_root = Path(__file__).parent.parent
        
        self.project_root = project_root
        self.notebook_file = project_root / ".taskmaster" / "session-notebook.md"
        self.session_data_file = project_root / ".taskmaster" / "session-data.json"
        self.current_session = self._load_current_session()
    
    def _load_current_session(self) -> Dict[str, Any]:
        """Load current session data"""
        if self.session_data_file.exists():
            with open(self.session_data_file, 'r') as f:
                return json.load(f)
        return self._create_new_session()
    
    def _save_session_data(self):
        """Save session data to JSON file"""
        self.session_data_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.session_data_file, 'w') as f:
            json.dump(self.current_session, f, indent=2)
    
    def _create_new_session(self) -> Dict[str, Any]:
        """Create new session data structure"""
        return {
            "session_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "start_time": datetime.now().isoformat(),
            "title": "",
            "status": "active",
            "issues": [],
            "methods": [],
            "insights": [],
            "metrics": {
                "before": {},
                "after": {}
            },
            "tools_used": [],
            "timeline": []
        }
    
    def start_session(self, title: str):
        """Start a new session"""
        self.current_session = self._create_new_session()
        self.current_session["title"] = title
        
        # Add to timeline
        self.current_session["timeline"].append({
            "time": datetime.now().isoformat(),
            "event": "session_start",
            "description": f"Started session: {title}"
        })
        
        self._save_session_data()
        print(f"✅ Started new session: {title}")
        print(f"📝 Session ID: {self.current_session['session_id']}")
    
    def add_issue(self, problem: str, solution: str):
        """Add an issue and its solution to the current session"""
        issue_entry = {
            "timestamp": datetime.now().isoformat(),
            "problem": problem,
            "solution": solution,
            "status": "resolved"
        }
        
        self.current_session["issues"].append(issue_entry)
        self.current_session["timeline"].append({
            "time": datetime.now().isoformat(),
            "event": "issue_resolved",
            "description": f"Resolved: {problem[:50]}..."
        })
        
        self._save_session_data()
        print("🔧 Added issue resolution:")
        print(f"   Problem: {problem}")
        print(f"   Solution: {solution}")
    
    def add_method(self, name: str, description: str):
        """Add a methodology to the current session"""
        method_entry = {
            "timestamp": datetime.now().isoformat(),
            "name": name,
            "description": description,
            "effectiveness": "unknown"
        }
        
        self.current_session["methods"].append(method_entry)
        self.current_session["timeline"].append({
            "time": datetime.now().isoformat(),
            "event": "method_documented",
            "description": f"Documented methodology: {name}"
        })
        
        self._save_session_data()
        print("🧠 Added methodology:")
        print(f"   Name: {name}")
        print(f"   Description: {description}")
    
    def add_insight(self, insight: str):
        """Add an insight to the current session"""
        insight_entry = {
            "timestamp": datetime.now().isoformat(),
            "insight": insight,
            "category": "general"
        }
        
        self.current_session["insights"].append(insight_entry)
        self.current_session["timeline"].append({
            "time": datetime.now().isoformat(),
            "event": "insight_captured",
            "description": f"Captured insight: {insight[:50]}..."
        })
        
        self._save_session_data()
        print("💡 Added insight:")
        print(f"   {insight}")
    
    def record_tool_usage(self, tool_name: str, purpose: str, effectiveness: str = "effective"):
        """Record tool usage during session"""
        tool_entry = {
            "timestamp": datetime.now().isoformat(),
            "tool": tool_name,
            "purpose": purpose,
            "effectiveness": effectiveness
        }
        
        self.current_session["tools_used"].append(tool_entry)
        self._save_session_data()
        print(f"🛠️ Recorded tool usage: {tool_name} for {purpose}")
    
    def set_metrics(self, metric_type: str, metrics: Dict[str, Any]):
        """Set before/after metrics for the session"""
        if metric_type in ["before", "after"]:
            self.current_session["metrics"][metric_type] = {
                "timestamp": datetime.now().isoformat(),
                **metrics
            }
            self._save_session_data()
            print(f"📊 Updated {metric_type} metrics")
    
    def complete_session(self, summary: str):
        """Complete the current session"""
        self.current_session["end_time"] = datetime.now().isoformat()
        self.current_session["status"] = "completed"
        self.current_session["summary"] = summary
        
        self.current_session["timeline"].append({
            "time": datetime.now().isoformat(),
            "event": "session_complete",
            "description": f"Completed session: {summary}"
        })
        
        # Calculate session duration
        start_time = datetime.fromisoformat(self.current_session["start_time"])
        end_time = datetime.fromisoformat(self.current_session["end_time"])
        duration = end_time - start_time
        self.current_session["duration_minutes"] = duration.total_seconds() / 60
        
        self._save_session_data()
        self._update_notebook()
        
        print("✅ Session completed:")
        print(f"   Duration: {duration}")
        print(f"   Issues resolved: {len(self.current_session['issues'])}")
        print(f"   Methods documented: {len(self.current_session['methods'])}")
        print(f"   Insights captured: {len(self.current_session['insights'])}")
    
    def _update_notebook(self):
        """Update the main notebook file with session data"""
        # This would append to the main notebook - implementation depends on format
        print("📝 Notebook updated with session data")
    
    def show_status(self):
        """Show current session status"""
        if self.current_session["status"] == "active":
            print(f"📝 Active Session: {self.current_session['title']}")
            print(f"   ID: {self.current_session['session_id']}")
            print(f"   Started: {self.current_session['start_time']}")
            print(f"   Issues: {len(self.current_session['issues'])}")
            print(f"   Methods: {len(self.current_session['methods'])}")
            print(f"   Insights: {len(self.current_session['insights'])}")
        else:
            print("📝 No active session")
    
    def export_for_uckn(self):
        """Export session data in format suitable for UCKN knowledge base"""
        if self.current_session["status"] != "completed":
            print("⚠️ Session not completed yet - export may be incomplete")
        
        uckn_export = {
            "pattern_type": "development_session",
            "session_metadata": {
                "id": self.current_session["session_id"],
                "title": self.current_session["title"],
                "duration_minutes": self.current_session.get("duration_minutes", "unknown"),
                "date": self.current_session["start_time"][:10]
            },
            "problems_solved": [
                {
                    "problem": issue["problem"],
                    "solution": issue["solution"],
                    "pattern_category": "issue_resolution"
                }
                for issue in self.current_session["issues"]
            ],
            "methodologies": [
                {
                    "name": method["name"],
                    "description": method["description"],
                    "pattern_category": "methodology"
                }
                for method in self.current_session["methods"]
            ],
            "insights": [
                {
                    "insight": insight["insight"],
                    "pattern_category": "lesson_learned"
                }
                for insight in self.current_session["insights"]
            ],
            "tools_effectiveness": [
                {
                    "tool": tool["tool"],
                    "purpose": tool["purpose"],
                    "effectiveness": tool["effectiveness"],
                    "pattern_category": "tool_usage"
                }
                for tool in self.current_session["tools_used"]
            ],
            "metrics": self.current_session["metrics"]
        }
        
        export_file = self.project_root / ".taskmaster" / f"uckn-export-{self.current_session['session_id']}.json"
        with open(export_file, 'w') as f:
            json.dump(uckn_export, f, indent=2)
        
        print(f"📤 UCKN export created: {export_file}")
        print(f"   Patterns: {len(uckn_export['problems_solved']) + len(uckn_export['methodologies']) + len(uckn_export['insights'])}")
        return export_file


def main():
    parser = argparse.ArgumentParser(description="Session Notebook Manager")
    parser.add_argument("command", choices=[
        "start", "issue", "method", "insight", "tool", "metrics", 
        "complete", "status", "export-uckn"
    ])
    parser.add_argument("args", nargs="*", help="Command arguments")
    
    args = parser.parse_args()
    notebook = SessionNotebook()
    
    if args.command == "start":
        if not args.args:
            print("❌ Session title required")
            sys.exit(1)
        notebook.start_session(" ".join(args.args))
    
    elif args.command == "issue":
        if len(args.args) < 2:
            print("❌ Problem and solution required")
            sys.exit(1)
        problem = args.args[0]
        solution = " ".join(args.args[1:])
        notebook.add_issue(problem, solution)
    
    elif args.command == "method":
        if len(args.args) < 2:
            print("❌ Method name and description required")
            sys.exit(1)
        name = args.args[0]
        description = " ".join(args.args[1:])
        notebook.add_method(name, description)
    
    elif args.command == "insight":
        if not args.args:
            print("❌ Insight text required")
            sys.exit(1)
        insight = " ".join(args.args)
        notebook.add_insight(insight)
    
    elif args.command == "tool":
        if len(args.args) < 2:
            print("❌ Tool name and purpose required")
            sys.exit(1)
        tool_name = args.args[0]
        purpose = " ".join(args.args[1:])
        effectiveness = "effective"  # Could be made configurable
        notebook.record_tool_usage(tool_name, purpose, effectiveness)
    
    elif args.command == "complete":
        if not args.args:
            print("❌ Session summary required")
            sys.exit(1)
        summary = " ".join(args.args)
        notebook.complete_session(summary)
    
    elif args.command == "status":
        notebook.show_status()
    
    elif args.command == "export-uckn":
        notebook.export_for_uckn()


if __name__ == "__main__":
    main()