"""State inspection framework for comprehensive debugging and LLM analysis.

This module implements the ComponentStateInspector class and related components
for capturing, analyzing, and reporting on component state information.
"""

import json
import threading
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from ..protocols.debugging_protocol import (
    DebuggableComponent,
)


@dataclass(frozen=True)
class StateSnapshot:
    """Immutable snapshot of component state at a specific point in time.

    This dataclass captures complete state information including metadata,
    timestamps, and validation results for comprehensive debugging analysis.
    """

    component_id: str
    component_type: str
    state_data: dict[str, Any]
    snapshot_timestamp: datetime
    validation_result: dict[str, Any] | None = None
    debug_metadata: dict[str, Any] = field(default_factory=dict)
    performance_metrics: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert snapshot to dictionary for JSON serialization."""
        snapshot_dict = asdict(self)
        # Convert datetime to ISO string for JSON serialization
        snapshot_dict["snapshot_timestamp"] = self.snapshot_timestamp.isoformat()
        return snapshot_dict

    def to_json(self) -> str:
        """Convert snapshot to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)


class ComponentStateInspector:
    """Central state inspector for managing and analyzing component state.

    This class provides thread-safe component registration, state capture,
    and analysis capabilities with LLM-friendly reporting features.

    Features:
    - Thread-safe component registration and management
    - State snapshot capture with timestamp and metadata
    - State history tracking and comparison
    - LLM-optimized reporting and analysis
    - Performance metrics integration
    - Validation result tracking
    """

    def __init__(self, max_history_per_component: int = 50):
        """Initialize the state inspector.

        Args:
            max_history_per_component: Maximum number of historical snapshots
                                     to keep per component
        """
        self._components: dict[str, DebuggableComponent] = {}
        self._state_history: dict[str, list[StateSnapshot]] = defaultdict(list)
        self._component_metadata: dict[str, dict[str, Any]] = defaultdict(dict)
        self._lock = threading.RLock()
        self._max_history = max_history_per_component

    def register_component(
        self, component_id: str, component: DebuggableComponent
    ) -> None:
        """Register a component for state inspection.

        Args:
            component_id: Unique identifier for the component
            component: The debuggable component to register
        """
        with self._lock:
            self._components[component_id] = component
            self._component_metadata[component_id] = {
                "registration_time": datetime.now(),
                "component_type": type(component).__name__,
                "snapshot_count": 0,
                "last_snapshot_time": None,
            }

    def unregister_component(self, component_id: str) -> bool:
        """Unregister a component from state inspection.

        Args:
            component_id: Identifier of component to unregister

        Returns:
            True if component was found and removed, False otherwise
        """
        with self._lock:
            removed = component_id in self._components
            self._components.pop(component_id, None)
            # Keep history but mark as unregistered
            if component_id in self._component_metadata:
                self._component_metadata[component_id]["unregistration_time"] = (
                    datetime.now()
                )
            return removed

    def get_registered_components(self) -> set[str]:
        """Get set of currently registered component IDs."""
        with self._lock:
            return set(self._components.keys())

    def capture_state_snapshot(self, component_id: str) -> StateSnapshot | None:
        """Capture a complete state snapshot of a component.

        Args:
            component_id: Identifier of component to snapshot

        Returns:
            StateSnapshot if component exists, None otherwise
        """
        with self._lock:
            component = self._components.get(component_id)
            if not component:
                return None

            try:
                # Get current state
                component_state = component.get_component_state()

                # Get validation result
                validation_result = component.validate_component()
                validation_dict = {
                    "is_valid": validation_result.is_valid,
                    "errors": validation_result.validation_errors,
                    "warnings": validation_result.validation_warnings,
                    "timestamp": validation_result.validation_timestamp.isoformat(),
                }

                # Get debug info and performance metrics
                debug_info = component.get_debug_info()
                performance_metrics = debug_info.performance_metrics

                # Create snapshot
                snapshot = StateSnapshot(
                    component_id=component_id,
                    component_type=component_state.component_type,
                    state_data=component_state.state_data,
                    snapshot_timestamp=datetime.now(),
                    validation_result=validation_dict,
                    debug_metadata={
                        "debug_level": debug_info.debug_level,
                        "debug_data": debug_info.debug_data,
                        "stack_trace": debug_info.stack_trace,
                    },
                    performance_metrics=performance_metrics,
                )

                # Add to history
                history = self._state_history[component_id]
                history.append(snapshot)

                # Trim history if needed
                if len(history) > self._max_history:
                    history.pop(0)

                # Update metadata
                self._component_metadata[component_id]["snapshot_count"] += 1
                self._component_metadata[component_id]["last_snapshot_time"] = (
                    snapshot.snapshot_timestamp
                )

                return snapshot

            except Exception as e:
                # Create error snapshot
                error_snapshot = StateSnapshot(
                    component_id=component_id,
                    component_type=type(component).__name__,
                    state_data={"error": str(e), "error_type": type(e).__name__},
                    snapshot_timestamp=datetime.now(),
                    debug_metadata={"capture_error": True, "error_details": str(e)},
                )

                # Still add to history
                self._state_history[component_id].append(error_snapshot)
                return error_snapshot

    def get_state_history(
        self, component_id: str, limit: int = 10
    ) -> list[StateSnapshot]:
        """Get historical state snapshots for a component.

        Args:
            component_id: Component identifier
            limit: Maximum number of snapshots to return

        Returns:
            List of snapshots, newest first
        """
        with self._lock:
            history = self._state_history.get(component_id, [])
            return list(reversed(history[-limit:]))

    def compare_states(
        self, component_id: str, snapshot1: StateSnapshot, snapshot2: StateSnapshot
    ) -> dict[str, Any]:
        """Compare two state snapshots and identify differences.

        Args:
            component_id: Component identifier
            snapshot1: First snapshot to compare
            snapshot2: Second snapshot to compare

        Returns:
            Dictionary containing comparison results and differences
        """
        comparison = {
            "component_id": component_id,
            "comparison_timestamp": datetime.now().isoformat(),
            "snapshot1_time": snapshot1.snapshot_timestamp.isoformat(),
            "snapshot2_time": snapshot2.snapshot_timestamp.isoformat(),
            "time_delta_seconds": (
                snapshot2.snapshot_timestamp - snapshot1.snapshot_timestamp
            ).total_seconds(),
            "differences": {},
            "summary": {},
        }

        # Compare state data
        state1 = snapshot1.state_data
        state2 = snapshot2.state_data

        # Find added, removed, and changed keys
        keys1 = set(state1.keys())
        keys2 = set(state2.keys())

        added_keys = keys2 - keys1
        removed_keys = keys1 - keys2
        common_keys = keys1 & keys2

        changed_keys = []
        for key in common_keys:
            if state1[key] != state2[key]:
                changed_keys.append(key)

        comparison["differences"] = {
            "added_keys": list(added_keys),
            "removed_keys": list(removed_keys),
            "changed_keys": changed_keys,
            "changes": {
                key: {"old": state1[key], "new": state2[key]} for key in changed_keys
            },
        }

        # Compare validation results
        validation_changed = snapshot1.validation_result != snapshot2.validation_result
        comparison["validation_changed"] = validation_changed

        # Compare performance metrics
        perf1 = snapshot1.performance_metrics
        perf2 = snapshot2.performance_metrics
        perf_changes = {}
        for metric in set(perf1.keys()) | set(perf2.keys()):
            old_val = perf1.get(metric, 0)
            new_val = perf2.get(metric, 0)
            if old_val != new_val:
                perf_changes[metric] = {
                    "old": old_val,
                    "new": new_val,
                    "delta": new_val - old_val,
                    "percent_change": ((new_val - old_val) / old_val * 100)
                    if old_val != 0
                    else float("inf"),
                }

        comparison["performance_changes"] = perf_changes

        # Summary
        comparison["summary"] = {
            "has_changes": bool(
                added_keys
                or removed_keys
                or changed_keys
                or validation_changed
                or perf_changes
            ),
            "change_count": len(added_keys) + len(removed_keys) + len(changed_keys),
            "validation_status_changed": validation_changed,
            "performance_metrics_changed": len(perf_changes),
        }

        return comparison

    def generate_llm_friendly_report(self, component_id: str | None = None) -> str:
        """Generate a comprehensive, LLM-friendly debugging report.

        Args:
            component_id: Specific component to report on, or None for all components

        Returns:
            Formatted report string optimized for LLM analysis
        """
        with self._lock:
            report_lines = []
            report_timestamp = datetime.now()

            report_lines.append("# Component State Inspection Report")
            report_lines.append(f"Generated: {report_timestamp.isoformat()}")
            report_lines.append("")

            if component_id:
                components_to_report = (
                    [component_id] if component_id in self._components else []
                )
            else:
                components_to_report = list(self._components.keys())

            if not components_to_report:
                report_lines.append("No components available for reporting.")
                return "\n".join(report_lines)

            # Summary section
            report_lines.append("## Summary")
            report_lines.append(f"Total registered components: {len(self._components)}")
            report_lines.append(
                f"Components in this report: {len(components_to_report)}"
            )
            report_lines.append("")

            # Component details
            for comp_id in components_to_report:
                report_lines.append(f"## Component: {comp_id}")

                # Component metadata
                metadata = self._component_metadata.get(comp_id, {})
                report_lines.append(
                    f"**Type**: {metadata.get('component_type', 'Unknown')}"
                )
                report_lines.append(
                    f"**Registered**: {metadata.get('registration_time', 'Unknown')}"
                )
                report_lines.append(
                    f"**Snapshots captured**: {metadata.get('snapshot_count', 0)}"
                )

                # Current state snapshot
                current_snapshot = self.capture_state_snapshot(comp_id)
                if current_snapshot:
                    report_lines.append("### Current State")
                    report_lines.append(
                        f"**Timestamp**: {current_snapshot.snapshot_timestamp.isoformat()}"
                    )

                    # Validation status
                    if current_snapshot.validation_result:
                        val_result = current_snapshot.validation_result
                        status = "✅ VALID" if val_result["is_valid"] else "❌ INVALID"
                        report_lines.append(f"**Validation**: {status}")

                        if val_result["errors"]:
                            report_lines.append("**Validation Errors**:")
                            for error in val_result["errors"]:
                                report_lines.append(f"  - {error}")

                        if val_result["warnings"]:
                            report_lines.append("**Validation Warnings**:")
                            for warning in val_result["warnings"]:
                                report_lines.append(f"  - {warning}")

                    # Performance metrics
                    if current_snapshot.performance_metrics:
                        report_lines.append("**Performance Metrics**:")
                        for (
                            metric,
                            value,
                        ) in current_snapshot.performance_metrics.items():
                            report_lines.append(f"  - {metric}: {value}")

                    # State data summary
                    state_data = current_snapshot.state_data
                    report_lines.append(
                        f"**State data keys**: {list(state_data.keys())}"
                    )

                    # Recent history summary
                    history = self.get_state_history(comp_id, limit=5)
                    if len(history) > 1:
                        report_lines.append(
                            f"**Recent history**: {len(history)} snapshots available"
                        )

                        # Compare with previous state
                        if len(history) >= 2:
                            comparison = self.compare_states(
                                comp_id, history[1], history[0]
                            )
                            if comparison["summary"]["has_changes"]:
                                report_lines.append("**Recent changes detected**:")
                                changes = comparison["differences"]
                                if changes["added_keys"]:
                                    report_lines.append(
                                        f"  - Added keys: {changes['added_keys']}"
                                    )
                                if changes["removed_keys"]:
                                    report_lines.append(
                                        f"  - Removed keys: {changes['removed_keys']}"
                                    )
                                if changes["changed_keys"]:
                                    report_lines.append(
                                        f"  - Changed keys: {changes['changed_keys']}"
                                    )
                            else:
                                report_lines.append("**No recent changes detected**")

                report_lines.append("")

            # Analysis section
            report_lines.append("## Analysis")

            # Overall health summary
            healthy_components = 0
            warning_components = 0
            error_components = 0

            for comp_id in components_to_report:
                snapshot = self.capture_state_snapshot(comp_id)
                if snapshot and snapshot.validation_result:
                    if snapshot.validation_result["is_valid"]:
                        healthy_components += 1
                    elif snapshot.validation_result["warnings"]:
                        warning_components += 1
                    else:
                        error_components += 1

            report_lines.append(f"- Healthy components: {healthy_components}")
            report_lines.append(f"- Components with warnings: {warning_components}")
            report_lines.append(f"- Components with errors: {error_components}")

            if error_components > 0:
                report_lines.append("\n**⚠️ Components requiring attention detected**")
            elif warning_components > 0:
                report_lines.append("\n**⚡ Components with warnings detected**")
            else:
                report_lines.append("\n**✅ All components appear healthy**")

            report_lines.append("")
            report_lines.append("---")
            report_lines.append(
                "*This report is optimized for LLM analysis and human debugging*"
            )

            return "\n".join(report_lines)

    def export_full_state(self) -> dict[str, Any]:
        """Export complete state of all components and inspector metadata.

        Returns:
            Dictionary containing all state information
        """
        with self._lock:
            export_data = {
                "export_timestamp": datetime.now().isoformat(),
                "registered_components": list(self._components.keys()),
                "component_metadata": dict(self._component_metadata),
                "current_snapshots": {},
                "state_history_summary": {},
            }

            # Capture current snapshots
            for comp_id in self._components:
                snapshot = self.capture_state_snapshot(comp_id)
                if snapshot:
                    export_data["current_snapshots"][comp_id] = snapshot.to_dict()

            # History summaries
            for comp_id, history in self._state_history.items():
                export_data["state_history_summary"][comp_id] = {
                    "total_snapshots": len(history),
                    "oldest_snapshot": history[0].snapshot_timestamp.isoformat()
                    if history
                    else None,
                    "newest_snapshot": history[-1].snapshot_timestamp.isoformat()
                    if history
                    else None,
                }

            return export_data
