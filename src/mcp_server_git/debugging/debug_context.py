"""Debug context management for maintaining debugging state across operations.

This module provides context managers and utilities for tracking debugging
information across complex operations and maintaining context for LLM analysis.
"""

import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from ..protocols.debugging_protocol import DebuggableComponent


@dataclass
class DebugOperation:
    """Information about a debugging operation."""

    operation_id: str
    operation_name: str
    start_time: datetime
    end_time: datetime | None = None
    status: str = "running"  # running, completed, failed, cancelled
    metadata: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sub_operations: list["DebugOperation"] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float | None:
        """Calculate operation duration in seconds."""
        if self.end_time and self.start_time:
            return (self.end_time - self.start_time).total_seconds()
        return None

    @property
    def is_completed(self) -> bool:
        """Check if operation is completed."""
        return self.status in ("completed", "failed", "cancelled")

    def add_error(self, error_message: str) -> None:
        """Add an error to this operation."""
        self.errors.append(error_message)
        if self.status == "running":
            self.status = "failed"

    def add_warning(self, warning_message: str) -> None:
        """Add a warning to this operation."""
        self.warnings.append(warning_message)

    def complete(self, status: str = "completed") -> None:
        """Mark operation as completed."""
        self.end_time = datetime.now()
        self.status = status

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "operation_id": self.operation_id,
            "operation_name": self.operation_name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration_seconds,
            "status": self.status,
            "metadata": self.metadata,
            "errors": self.errors,
            "warnings": self.warnings,
            "sub_operations": [sub_op.to_dict() for sub_op in self.sub_operations],
        }


class DebugContext:
    """Context manager for debugging operations with hierarchical operation tracking.

    This class maintains debugging context across complex operations, tracking
    metadata, errors, warnings, and nested operations for comprehensive debugging.
    """

    # Thread-local storage for current debug context
    _local_storage = threading.local()

    # Global registry of all debug contexts
    _global_contexts: dict[str, "DebugContext"] = {}
    _global_lock = threading.RLock()

    def __init__(self, context_name: str, context_id: str | None = None):
        """Initialize debug context.

        Args:
            context_name: Human-readable name for the context
            context_id: Optional unique identifier (auto-generated if not provided)
        """
        self.context_id = context_id or str(uuid.uuid4())
        self.context_name = context_name
        self.creation_time = datetime.now()
        self.metadata: dict[str, Any] = {}
        self.operations: list[DebugOperation] = []
        self.registered_components: dict[str, DebuggableComponent] = {}
        self.context_errors: list[str] = []
        self.context_warnings: list[str] = []
        self._lock = threading.RLock()
        self._current_operation: DebugOperation | None = None

        # Register globally
        with DebugContext._global_lock:
            DebugContext._global_contexts[self.context_id] = self

    def __enter__(self) -> "DebugContext":
        """Enter the debug context."""
        # Set as current context in thread-local storage
        if not hasattr(DebugContext._local_storage, "context_stack"):
            DebugContext._local_storage.context_stack = []

        DebugContext._local_storage.context_stack.append(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the debug context."""
        # Remove from thread-local stack
        if hasattr(DebugContext._local_storage, "context_stack"):
            try:
                DebugContext._local_storage.context_stack.remove(self)
            except ValueError:
                pass

        # Complete any running operation
        if self._current_operation and not self._current_operation.is_completed:
            if exc_type:
                self._current_operation.add_error(
                    f"Context exited with exception: {exc_type.__name__}: {exc_val}"
                )
                self._current_operation.complete("failed")
            else:
                self._current_operation.complete("completed")

    @classmethod
    def get_current_context(cls) -> Optional["DebugContext"]:
        """Get the current debug context for this thread."""
        if (
            hasattr(cls._local_storage, "context_stack")
            and cls._local_storage.context_stack
        ):
            return cls._local_storage.context_stack[-1]
        return None

    @classmethod
    def get_context_by_id(cls, context_id: str) -> Optional["DebugContext"]:
        """Get a debug context by its ID."""
        with cls._global_lock:
            return cls._global_contexts.get(context_id)

    @classmethod
    def list_all_contexts(cls) -> list[str]:
        """List all registered debug context IDs."""
        with cls._global_lock:
            return list(cls._global_contexts.keys())

    def add_metadata(self, key: str, value: Any) -> None:
        """Add metadata to the debug context."""
        with self._lock:
            self.metadata[key] = value

    def add_error(self, error_message: str) -> None:
        """Add a context-level error."""
        with self._lock:
            self.context_errors.append(error_message)
            if self._current_operation:
                self._current_operation.add_error(error_message)

    def add_warning(self, warning_message: str) -> None:
        """Add a context-level warning."""
        with self._lock:
            self.context_warnings.append(warning_message)
            if self._current_operation:
                self._current_operation.add_warning(warning_message)

    def register_component(
        self, component_id: str, component: DebuggableComponent
    ) -> None:
        """Register a component with this debug context."""
        with self._lock:
            self.registered_components[component_id] = component

    def start_operation(
        self, operation_name: str, operation_id: str | None = None
    ) -> DebugOperation:
        """Start a new debug operation.

        Args:
            operation_name: Name of the operation
            operation_id: Optional unique identifier

        Returns:
            DebugOperation instance
        """
        with self._lock:
            operation = DebugOperation(
                operation_id=operation_id or str(uuid.uuid4()),
                operation_name=operation_name,
                start_time=datetime.now(),
            )

            # If there's a current operation, make this a sub-operation
            if self._current_operation and not self._current_operation.is_completed:
                self._current_operation.sub_operations.append(operation)
            else:
                self.operations.append(operation)

            self._current_operation = operation
            return operation

    def complete_operation(self, status: str = "completed") -> None:
        """Complete the current operation."""
        with self._lock:
            if self._current_operation:
                self._current_operation.complete(status)
                # Find parent operation if this was a sub-operation
                parent_op = self._find_parent_operation(self._current_operation)
                self._current_operation = parent_op

    def _find_parent_operation(
        self, operation: DebugOperation
    ) -> DebugOperation | None:
        """Find the parent operation of a given operation."""
        for op in self.operations:
            if operation in op.sub_operations:
                return op
            # Check nested sub-operations
            parent = self._find_parent_in_subops(op, operation)
            if parent:
                return parent
        return None

    def _find_parent_in_subops(
        self, parent: DebugOperation, target: DebugOperation
    ) -> DebugOperation | None:
        """Recursively find parent operation in sub-operations."""
        for sub_op in parent.sub_operations:
            if target in sub_op.sub_operations:
                return sub_op
            result = self._find_parent_in_subops(sub_op, target)
            if result:
                return result
        return None

    @contextmanager
    def operation(self, operation_name: str) -> Iterator[DebugOperation]:
        """Context manager for a debug operation.

        Args:
            operation_name: Name of the operation

        Yields:
            DebugOperation instance
        """
        op = self.start_operation(operation_name)
        try:
            yield op
            self.complete_operation("completed")
        except Exception as e:
            op.add_error(f"Operation failed: {str(e)}")
            self.complete_operation("failed")
            raise

    def capture_component_states(self) -> dict[str, dict[str, Any]]:
        """Capture current state of all registered components."""
        with self._lock:
            states = {}
            for comp_id, component in self.registered_components.items():
                try:
                    state = component.get_component_state()
                    validation = component.validate_component()
                    debug_info = component.get_debug_info()

                    states[comp_id] = {
                        "component_type": state.component_type,
                        "state_data": state.state_data,
                        "last_updated": state.last_updated.isoformat(),
                        "validation": {
                            "is_valid": validation.is_valid,
                            "errors": validation.validation_errors,
                            "warnings": validation.validation_warnings,
                        },
                        "performance_metrics": debug_info.performance_metrics,
                    }
                except Exception as e:
                    states[comp_id] = {
                        "error": f"Failed to capture state: {str(e)}",
                        "error_type": type(e).__name__,
                    }

            return states

    def generate_context_report(self) -> str:
        """Generate a comprehensive report of the debug context."""
        with self._lock:
            report_lines = []

            report_lines.append(f"# Debug Context Report: {self.context_name}")
            report_lines.append(f"**Context ID**: {self.context_id}")
            report_lines.append(f"**Created**: {self.creation_time.isoformat()}")
            report_lines.append("")

            # Metadata
            if self.metadata:
                report_lines.append("## Context Metadata")
                for key, value in self.metadata.items():
                    report_lines.append(f"- **{key}**: {value}")
                report_lines.append("")

            # Errors and warnings
            if self.context_errors:
                report_lines.append("## Context Errors")
                for error in self.context_errors:
                    report_lines.append(f"- ❌ {error}")
                report_lines.append("")

            if self.context_warnings:
                report_lines.append("## Context Warnings")
                for warning in self.context_warnings:
                    report_lines.append(f"- ⚠️ {warning}")
                report_lines.append("")

            # Operations
            report_lines.append("## Operations")
            if self.operations:
                for op in self.operations:
                    report_lines.extend(self._format_operation_report(op, indent=0))
            else:
                report_lines.append("No operations recorded.")
            report_lines.append("")

            # Registered components
            if self.registered_components:
                report_lines.append("## Registered Components")
                component_states = self.capture_component_states()
                for comp_id, state in component_states.items():
                    report_lines.append(f"### {comp_id}")
                    if "error" in state:
                        report_lines.append(f"❌ **Error**: {state['error']}")
                    else:
                        report_lines.append(
                            f"**Type**: {state.get('component_type', 'Unknown')}"
                        )
                        report_lines.append(
                            f"**Last Updated**: {state.get('last_updated', 'Unknown')}"
                        )

                        validation = state.get("validation", {})
                        status = (
                            "✅ Valid"
                            if validation.get("is_valid", False)
                            else "❌ Invalid"
                        )
                        report_lines.append(f"**Validation**: {status}")

                        if validation.get("errors"):
                            report_lines.append("**Errors**:")
                            for error in validation["errors"]:
                                report_lines.append(f"  - {error}")

                        metrics = state.get("performance_metrics", {})
                        if metrics:
                            report_lines.append("**Performance**:")
                            for metric, value in metrics.items():
                                report_lines.append(f"  - {metric}: {value}")

                    report_lines.append("")

            return "\n".join(report_lines)

    def _format_operation_report(
        self, operation: DebugOperation, indent: int = 0
    ) -> list[str]:
        """Format an operation for the report."""
        lines = []
        prefix = "  " * indent

        # Operation header
        status_emoji = {
            "completed": "✅",
            "failed": "❌",
            "cancelled": "⏹️",
            "running": "🔄",
        }.get(operation.status, "❓")

        lines.append(
            f"{prefix}{status_emoji} **{operation.operation_name}** ({operation.operation_id})"
        )
        lines.append(f"{prefix}  - **Started**: {operation.start_time.isoformat()}")

        if operation.end_time:
            lines.append(f"{prefix}  - **Completed**: {operation.end_time.isoformat()}")
            lines.append(f"{prefix}  - **Duration**: {operation.duration_seconds:.3f}s")

        lines.append(f"{prefix}  - **Status**: {operation.status}")

        # Metadata
        if operation.metadata:
            lines.append(f"{prefix}  - **Metadata**:")
            for key, value in operation.metadata.items():
                lines.append(f"{prefix}    - {key}: {value}")

        # Errors and warnings
        if operation.errors:
            lines.append(f"{prefix}  - **Errors**:")
            for error in operation.errors:
                lines.append(f"{prefix}    - {error}")

        if operation.warnings:
            lines.append(f"{prefix}  - **Warnings**:")
            for warning in operation.warnings:
                lines.append(f"{prefix}    - {warning}")

        # Sub-operations
        if operation.sub_operations:
            lines.append(f"{prefix}  - **Sub-operations**:")
            for sub_op in operation.sub_operations:
                lines.extend(self._format_operation_report(sub_op, indent + 2))

        return lines

    def to_dict(self) -> dict[str, Any]:
        """Convert context to dictionary for serialization."""
        with self._lock:
            return {
                "context_id": self.context_id,
                "context_name": self.context_name,
                "creation_time": self.creation_time.isoformat(),
                "metadata": self.metadata,
                "operations": [op.to_dict() for op in self.operations],
                "registered_components": list(self.registered_components.keys()),
                "context_errors": self.context_errors,
                "context_warnings": self.context_warnings,
                "component_states": self.capture_component_states(),
            }


@contextmanager
def debug_operation(
    operation_name: str, context: DebugContext | None = None
) -> Iterator[DebugOperation]:
    """Standalone context manager for debug operations.

    Args:
        operation_name: Name of the operation
        context: Optional debug context (uses current context if not provided)

    Yields:
        DebugOperation instance
    """
    ctx = context or DebugContext.get_current_context()

    if ctx:
        with ctx.operation(operation_name) as op:
            yield op
    else:
        # Create a minimal operation if no context available
        op = DebugOperation(
            operation_id=str(uuid.uuid4()),
            operation_name=operation_name,
            start_time=datetime.now(),
        )
        try:
            yield op
            op.complete("completed")
        except Exception as e:
            op.add_error(f"Operation failed: {str(e)}")
            op.complete("failed")
            raise


class GlobalDebugContextManager:
    """Global manager for debug contexts with cleanup and monitoring capabilities."""

    @staticmethod
    def cleanup_old_contexts(max_age_hours: int = 24) -> int:
        """Clean up old debug contexts.

        Args:
            max_age_hours: Maximum age in hours before contexts are cleaned up

        Returns:
            Number of contexts cleaned up
        """
        cutoff_time = datetime.now().timestamp() - (max_age_hours * 3600)
        cleaned_up = 0

        with DebugContext._global_lock:
            contexts_to_remove = []
            for context_id, context in DebugContext._global_contexts.items():
                if context.creation_time.timestamp() < cutoff_time:
                    contexts_to_remove.append(context_id)

            for context_id in contexts_to_remove:
                del DebugContext._global_contexts[context_id]
                cleaned_up += 1

        return cleaned_up

    @staticmethod
    def get_global_statistics() -> dict[str, Any]:
        """Get global statistics about debug contexts."""
        with DebugContext._global_lock:
            contexts = list(DebugContext._global_contexts.values())

        total_contexts = len(contexts)
        total_operations = sum(len(ctx.operations) for ctx in contexts)
        total_errors = sum(len(ctx.context_errors) for ctx in contexts)
        total_warnings = sum(len(ctx.context_warnings) for ctx in contexts)

        # Calculate average context age
        if contexts:
            now = datetime.now()
            total_age = sum(
                (now - ctx.creation_time).total_seconds() for ctx in contexts
            )
            avg_age_seconds = total_age / len(contexts)
        else:
            avg_age_seconds = 0

        return {
            "total_contexts": total_contexts,
            "total_operations": total_operations,
            "total_errors": total_errors,
            "total_warnings": total_warnings,
            "average_context_age_seconds": avg_age_seconds,
        }

    @staticmethod
    def generate_global_report() -> str:
        """Generate a global report of all debug contexts."""
        stats = GlobalDebugContextManager.get_global_statistics()

        report_lines = [
            "# Global Debug Context Report",
            f"Generated: {datetime.now().isoformat()}",
            "",
            "## Statistics",
            f"- Total active contexts: {stats['total_contexts']}",
            f"- Total operations: {stats['total_operations']}",
            f"- Total errors: {stats['total_errors']}",
            f"- Total warnings: {stats['total_warnings']}",
            f"- Average context age: {stats['average_context_age_seconds']:.1f} seconds",
            "",
        ]

        with DebugContext._global_lock:
            contexts = list(DebugContext._global_contexts.values())

        if contexts:
            report_lines.append("## Active Contexts")
            for ctx in sorted(contexts, key=lambda x: x.creation_time, reverse=True):
                report_lines.append(f"### {ctx.context_name} ({ctx.context_id})")
                report_lines.append(f"- Created: {ctx.creation_time.isoformat()}")
                report_lines.append(f"- Operations: {len(ctx.operations)}")
                report_lines.append(f"- Errors: {len(ctx.context_errors)}")
                report_lines.append(f"- Warnings: {len(ctx.context_warnings)}")
                report_lines.append(f"- Components: {len(ctx.registered_components)}")
                report_lines.append("")

        return "\n".join(report_lines)
