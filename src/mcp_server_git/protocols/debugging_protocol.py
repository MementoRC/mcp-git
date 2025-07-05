"""
Debugging protocol definitions for component state inspection and debugging.

This module defines the DebuggableComponent protocol and related interfaces
for enabling comprehensive debugging and state inspection capabilities.
"""

from typing import Protocol, Dict, Any, List, Optional, Union
from abc import abstractmethod
from datetime import datetime


class ComponentState(Protocol):
    """Protocol for representing component state information."""
    
    @property
    @abstractmethod
    def component_id(self) -> str:
        """Unique identifier for the component."""
        ...
    
    @property
    @abstractmethod
    def component_type(self) -> str:
        """Type/class name of the component."""
        ...
    
    @property
    @abstractmethod
    def state_data(self) -> Dict[str, Any]:
        """Current state data of the component."""
        ...
    
    @property
    @abstractmethod
    def last_updated(self) -> datetime:
        """Timestamp of last state update."""
        ...


class ValidationResult(Protocol):
    """Protocol for component validation results."""
    
    @property
    @abstractmethod
    def is_valid(self) -> bool:
        """Whether the component passes validation."""
        ...
    
    @property
    @abstractmethod
    def validation_errors(self) -> List[str]:
        """List of validation error messages."""
        ...
    
    @property
    @abstractmethod
    def validation_warnings(self) -> List[str]:
        """List of validation warning messages."""
        ...
    
    @property
    @abstractmethod
    def validation_timestamp(self) -> datetime:
        """When the validation was performed."""
        ...


class DebugInfo(Protocol):
    """Protocol for debug information structure."""
    
    @property
    @abstractmethod
    def debug_level(self) -> str:
        """Debug level (DEBUG, INFO, WARN, ERROR)."""
        ...
    
    @property
    @abstractmethod
    def debug_data(self) -> Dict[str, Any]:
        """Debug-specific data and metadata."""
        ...
    
    @property
    @abstractmethod
    def stack_trace(self) -> Optional[List[str]]:
        """Stack trace information if available."""
        ...
    
    @property
    @abstractmethod
    def performance_metrics(self) -> Dict[str, Union[int, float]]:
        """Performance metrics for the component."""
        ...


class DebuggableComponent(Protocol):
    """
    Protocol for components that support debugging and state inspection.
    
    This protocol defines the interface that all debuggable components must implement
    to enable comprehensive debugging, state inspection, and validation capabilities.
    
    As specified in PRD section 4.4.1, this protocol provides standardized methods
    for introspecting component state and enabling LLM-assisted debugging.
    """
    
    @abstractmethod
    def get_component_state(self) -> ComponentState:
        """
        Get the current state of the component.
        
        Returns:
            ComponentState: Complete state information including ID, type, data, and timestamp
            
        Example:
            >>> component = MyDebuggableComponent()
            >>> state = component.get_component_state()
            >>> print(f"Component {state.component_id} is of type {state.component_type}")
        """
        ...
    
    @abstractmethod
    def validate_component(self) -> ValidationResult:
        """
        Validate the current state and configuration of the component.
        
        Returns:
            ValidationResult: Validation status with errors, warnings, and timestamp
            
        Example:
            >>> component = MyDebuggableComponent()
            >>> result = component.validate_component()
            >>> if not result.is_valid:
            ...     print(f"Validation failed: {result.validation_errors}")
        """
        ...
    
    @abstractmethod
    def get_debug_info(self, debug_level: str = "INFO") -> DebugInfo:
        """
        Get debug information for the component.
        
        Args:
            debug_level: Level of debug information to return (DEBUG, INFO, WARN, ERROR)
            
        Returns:
            DebugInfo: Debug information including data, stack traces, and metrics
            
        Example:
            >>> component = MyDebuggableComponent()
            >>> debug_info = component.get_debug_info("DEBUG")
            >>> print(f"Performance metrics: {debug_info.performance_metrics}")
        """
        ...
    
    @abstractmethod
    def inspect_state(self, path: Optional[str] = None) -> Dict[str, Any]:
        """
        Inspect specific parts of the component state.
        
        Args:
            path: Optional dot-notation path to specific state (e.g., "config.database.host")
                 If None, returns complete state
                 
        Returns:
            Dict containing the requested state information
            
        Example:
            >>> component = MyDebuggableComponent()
            >>> db_config = component.inspect_state("config.database")
            >>> all_state = component.inspect_state()
        """
        ...
    
    @abstractmethod
    def get_component_dependencies(self) -> List[str]:
        """
        Get list of component dependencies.
        
        Returns:
            List of component IDs or names that this component depends on
            
        Example:
            >>> component = MyDebuggableComponent()
            >>> deps = component.get_component_dependencies()
            >>> print(f"Component depends on: {', '.join(deps)}")
        """
        ...
    
    @abstractmethod
    def export_state_json(self) -> str:
        """
        Export component state as JSON for external analysis.
        
        Returns:
            JSON string representation of complete component state
            
        Example:
            >>> component = MyDebuggableComponent()
            >>> json_state = component.export_state_json()
            >>> state_dict = json.loads(json_state)
        """
        ...
    
    @abstractmethod
    def health_check(self) -> Dict[str, Union[bool, str, int, float]]:
        """
        Perform a health check on the component.
        
        Returns:
            Dictionary with health status information including:
            - healthy: boolean indicating overall health
            - status: string description of health status
            - uptime: component uptime in seconds
            - last_error: last error message if any
            - error_count: number of errors since startup
            
        Example:
            >>> component = MyDebuggableComponent()
            >>> health = component.health_check()
            >>> if health["healthy"]:
            ...     print(f"Component healthy, uptime: {health['uptime']}s")
        """
        ...


class StateInspector(Protocol):
    """Protocol for advanced state inspection capabilities."""
    
    @abstractmethod
    def get_state_history(self, limit: int = 10) -> List[ComponentState]:
        """
        Get historical state information.
        
        Args:
            limit: Maximum number of historical states to return
            
        Returns:
            List of historical ComponentState objects, newest first
        """
        ...
    
    @abstractmethod
    def compare_states(self, state1: ComponentState, state2: ComponentState) -> Dict[str, Any]:
        """
        Compare two component states and return differences.
        
        Args:
            state1: First state to compare
            state2: Second state to compare
            
        Returns:
            Dictionary containing state differences and comparison metadata
        """
        ...
    
    @abstractmethod
    def get_state_diff(self, timestamp: datetime) -> Dict[str, Any]:
        """
        Get state differences since a specific timestamp.
        
        Args:
            timestamp: Reference timestamp for comparison
            
        Returns:
            Dictionary containing changes since the specified timestamp
        """
        ...


class DebuggingContext(Protocol):
    """Protocol for debugging context management."""
    
    @abstractmethod
    def register_component(self, component: DebuggableComponent) -> None:
        """Register a component for debugging."""
        ...
    
    @abstractmethod
    def unregister_component(self, component_id: str) -> None:
        """Unregister a component from debugging."""
        ...
    
    @abstractmethod
    def get_all_components(self) -> List[DebuggableComponent]:
        """Get all registered debuggable components."""
        ...
    
    @abstractmethod
    def validate_all_components(self) -> Dict[str, ValidationResult]:
        """Validate all registered components."""
        ...
    
    @abstractmethod
    def export_debug_report(self) -> str:
        """Export comprehensive debug report for all components."""
        ...