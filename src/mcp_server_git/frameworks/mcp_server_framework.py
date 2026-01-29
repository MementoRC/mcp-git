"""
MCP Server Framework - Core architectural patterns for MCP server implementation.

This module provides the foundational framework for building MCP (Model Context Protocol)
servers with plugin architecture, component lifecycle management, and dependency injection.

As part of the 5-level architecture hierarchy (Level 4: Templates/Layouts), this framework
defines structural patterns that services and applications build upon.

Key features:
- Plugin architecture with dynamic component loading
- Component lifecycle management (register, start, stop)
- Dependency injection and service discovery
- Event-driven notification system
- Configuration management integration
- Comprehensive error handling and recovery
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, TypeVar

from ..protocols.debugging_protocol import (
    ComponentState,
    DebuggableComponent,
    DebugInfo,
    ValidationResult,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class FrameworkComponentState:
    """Implementation of ComponentState for the framework."""

    component_id: str
    component_type: str
    state_data: dict[str, Any]
    last_updated: datetime = field(default_factory=datetime.now)


@dataclass
class FrameworkValidationResult:
    """Implementation of ValidationResult for the framework."""

    is_valid: bool
    validation_errors: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)
    validation_timestamp: datetime = field(default_factory=datetime.now)

    @property
    def issues(self) -> list[str]:
        """Compatibility property for existing code."""
        return self.validation_errors + self.validation_warnings

    @property
    def component_id(self) -> str:
        """Component ID for compatibility."""
        return "mcp_server_framework"


@dataclass
class FrameworkDebugInfo:
    """Implementation of DebugInfo for the framework."""

    component_id: str
    debug_data: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    debug_level: str = "INFO"
    stack_trace: list[str] | None = None
    performance_metrics: dict[str, int | float] = field(default_factory=dict)


class MCPComponent(Protocol):
    """Protocol for MCP server components."""

    async def initialize(self) -> None:
        """Initialize the component."""
        ...

    async def start(self) -> None:
        """Start the component."""
        ...

    async def stop(self) -> None:
        """Stop the component."""
        ...

    @property
    def name(self) -> str:
        """Component name."""
        ...


class MCPPlugin(ABC):
    """Abstract base class for MCP server plugins."""

    def __init__(self, name: str):
        self.name = name
        self._initialized = False
        self._running = False

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the plugin."""
        pass

    @abstractmethod
    async def start(self) -> None:
        """Start the plugin."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the plugin."""
        pass

    @property
    def initialized(self) -> bool:
        """Check if plugin is initialized."""
        return self._initialized

    @property
    def running(self) -> bool:
        """Check if plugin is running."""
        return self._running


@dataclass
class ComponentRegistration:
    """Registration information for a framework component."""

    name: str
    component: Any
    dependencies: list[str] = field(default_factory=list)
    priority: int = 100
    auto_start: bool = True
    registered_at: datetime = field(default_factory=datetime.now)


@dataclass
class EventSubscription:
    """Event subscription information."""

    event_type: str
    callback: Callable
    component_name: str
    priority: int = 100


class MCPServerFramework(DebuggableComponent):
    """
    Core MCP server framework providing plugin architecture and component management.

    This framework implements the foundational patterns for MCP server development:
    - Component registration and lifecycle management
    - Plugin architecture with dynamic loading
    - Dependency injection and service discovery
    - Event-driven notification system
    - Configuration management integration

    Example usage:
        >>> framework = MCPServerFramework()
        >>> framework.register_component("git_service", git_service, dependencies=["config"])
        >>> framework.register_component("github_service", github_service, dependencies=["git_service"])
        >>> await framework.initialize()
        >>> await framework.start()
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the MCP server framework.

        Args:
            config: Optional configuration dictionary
        """
        self._config = config or {}
        self._components: dict[str, ComponentRegistration] = {}
        self._plugins: dict[str, MCPPlugin] = {}
        self._event_subscriptions: dict[str, list[EventSubscription]] = {}
        self._started = False
        self._initialized = False
        self._initialization_order: list[str] = []
        self._shutdown_handlers: list[Callable] = []

        # Component state tracking
        self._component_states: dict[str, ComponentState] = {}
        self._framework_started_at: datetime | None = None

        logger.info("MCPServerFramework initialized")

    def register_component(
        self,
        name: str,
        component: Any,
        dependencies: list[str] | None = None,
        priority: int = 100,
        auto_start: bool = True,
    ) -> None:
        """
        Register a component with the framework.

        Args:
            name: Unique component name
            component: Component instance
            dependencies: List of component names this component depends on
            priority: Component priority (lower numbers start first)
            auto_start: Whether to automatically start this component

        Raises:
            ValueError: If component name already registered
        """
        if name in self._components:
            raise ValueError(f"Component '{name}' already registered")

        registration = ComponentRegistration(
            name=name,
            component=component,
            dependencies=dependencies or [],
            priority=priority,
            auto_start=auto_start,
        )

        self._components[name] = registration
        logger.info(f"Registered component: {name} (priority: {priority})")

    def register_plugin(self, plugin: MCPPlugin) -> None:
        """
        Register a plugin with the framework.

        Args:
            plugin: Plugin instance

        Raises:
            ValueError: If plugin name already registered
        """
        if plugin.name in self._plugins:
            raise ValueError(f"Plugin '{plugin.name}' already registered")

        self._plugins[plugin.name] = plugin
        logger.info(f"Registered plugin: {plugin.name}")

    def subscribe_to_event(
        self,
        event_type: str,
        callback: Callable,
        component_name: str,
        priority: int = 100,
    ) -> None:
        """
        Subscribe to framework events.

        Args:
            event_type: Type of event to subscribe to
            callback: Callback function to execute
            component_name: Name of subscribing component
            priority: Event handling priority
        """
        if event_type not in self._event_subscriptions:
            self._event_subscriptions[event_type] = []

        subscription = EventSubscription(
            event_type=event_type,
            callback=callback,
            component_name=component_name,
            priority=priority,
        )

        self._event_subscriptions[event_type].append(subscription)
        self._event_subscriptions[event_type].sort(key=lambda x: x.priority)

        logger.debug(f"Subscribed {component_name} to event: {event_type}")

    async def emit_event(self, event_type: str, event_data: Any = None) -> None:
        """
        Emit an event to all subscribers.

        Args:
            event_type: Type of event to emit
            event_data: Optional event data
        """
        if event_type not in self._event_subscriptions:
            return

        logger.debug(f"Emitting event: {event_type}")

        for subscription in self._event_subscriptions[event_type]:
            try:
                if asyncio.iscoroutinefunction(subscription.callback):
                    await subscription.callback(event_data)
                else:
                    subscription.callback(event_data)
            except Exception as e:
                logger.error(
                    f"Error in event callback for {subscription.component_name}: {e}"
                )

    def get_component(self, name: str) -> Any | None:
        """
        Get a registered component by name.

        Args:
            name: Component name

        Returns:
            Component instance or None if not found
        """
        registration = self._components.get(name)
        return registration.component if registration else None

    def _resolve_initialization_order(self) -> list[str]:
        """
        Resolve component initialization order based on dependencies and priorities.

        Returns:
            List of component names in initialization order

        Raises:
            ValueError: If circular dependencies detected
        """
        # Simple topological sort with priority consideration
        visited = set()
        temp_visited = set()
        order = []

        def visit(component_name: str) -> None:
            if component_name in temp_visited:
                raise ValueError(
                    f"Circular dependency detected involving: {component_name}"
                )

            if component_name in visited:
                return

            temp_visited.add(component_name)

            registration = self._components.get(component_name)
            if registration:
                for dep in registration.dependencies:
                    if dep not in self._components:
                        raise ValueError(
                            f"Dependency '{dep}' not found for component '{component_name}'"
                        )
                    visit(dep)

            temp_visited.remove(component_name)
            visited.add(component_name)
            order.append(component_name)

        # Sort by priority first, then resolve dependencies
        component_names = sorted(
            self._components.keys(), key=lambda name: self._components[name].priority
        )

        for name in component_names:
            if name not in visited:
                visit(name)

        return order

    async def initialize(self) -> None:
        """
        Initialize all registered components and plugins.

        Raises:
            RuntimeError: If framework already initialized
            ValueError: If dependency resolution fails
        """
        if self._initialized:
            raise RuntimeError("Framework already initialized")

        logger.info("Initializing MCP server framework")

        # Resolve initialization order
        self._initialization_order = self._resolve_initialization_order()

        # Initialize plugins first
        for plugin in self._plugins.values():
            try:
                await plugin.initialize()
                plugin._initialized = True
                logger.debug(f"Initialized plugin: {plugin.name}")
            except Exception as e:
                logger.error(f"Failed to initialize plugin {plugin.name}: {e}")
                raise

        # Initialize components in dependency order
        for component_name in self._initialization_order:
            registration = self._components[component_name]
            component = registration.component

            try:
                if hasattr(component, "initialize"):
                    await component.initialize()

                # Update component state
                self._component_states[component_name] = FrameworkComponentState(
                    component_id=component_name,
                    component_type=type(component).__name__,
                    state_data={
                        "status": "initialized",
                        "initialized_at": datetime.now().isoformat(),
                    },
                )

                logger.debug(f"Initialized component: {component_name}")
            except Exception as e:
                logger.error(f"Failed to initialize component {component_name}: {e}")
                raise

        self._initialized = True
        await self.emit_event("framework_initialized")
        logger.info("MCP server framework initialization completed")

    async def start(self) -> None:
        """
        Start all registered components and plugins.

        Raises:
            RuntimeError: If framework not initialized or already started
        """
        if not self._initialized:
            raise RuntimeError("Framework not initialized. Call initialize() first.")

        if self._started:
            raise RuntimeError("Framework already started")

        logger.info("Starting MCP server framework")
        self._framework_started_at = datetime.now()

        # Start plugins
        for plugin in self._plugins.values():
            try:
                await plugin.start()
                plugin._running = True
                logger.debug(f"Started plugin: {plugin.name}")
            except Exception as e:
                logger.error(f"Failed to start plugin {plugin.name}: {e}")
                raise

        # Start components in initialization order
        for component_name in self._initialization_order:
            registration = self._components[component_name]

            if not registration.auto_start:
                continue

            component = registration.component

            try:
                if hasattr(component, "start"):
                    await component.start()

                # Update component state
                if component_name in self._component_states:
                    self._component_states[component_name].state_data.update(
                        {"status": "running", "started_at": datetime.now().isoformat()}
                    )

                logger.debug(f"Started component: {component_name}")
            except Exception as e:
                logger.error(f"Failed to start component {component_name}: {e}")
                raise

        self._started = True
        await self.emit_event("framework_started")
        logger.info("MCP server framework started successfully")

    async def stop(self) -> None:
        """Stop all components and plugins in reverse order."""
        if not self._started:
            return

        logger.info("Stopping MCP server framework")

        # Execute shutdown handlers
        for handler in reversed(self._shutdown_handlers):
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler()
                else:
                    handler()
            except Exception as e:
                logger.error(f"Error in shutdown handler: {e}")

        # Stop components in reverse order
        for component_name in reversed(self._initialization_order):
            registration = self._components[component_name]
            component = registration.component

            try:
                if hasattr(component, "stop"):
                    await component.stop()

                # Update component state
                if component_name in self._component_states:
                    self._component_states[component_name].state_data.update(
                        {"status": "stopped", "stopped_at": datetime.now().isoformat()}
                    )

                logger.debug(f"Stopped component: {component_name}")
            except Exception as e:
                logger.error(f"Error stopping component {component_name}: {e}")

        # Stop plugins
        for plugin in reversed(list(self._plugins.values())):
            try:
                await plugin.stop()
                plugin._running = False
                logger.debug(f"Stopped plugin: {plugin.name}")
            except Exception as e:
                logger.error(f"Error stopping plugin {plugin.name}: {e}")

        self._started = False
        await self.emit_event("framework_stopped")
        logger.info("MCP server framework stopped")

    def add_shutdown_handler(self, handler: Callable) -> None:
        """
        Add a shutdown handler to be called during framework shutdown.

        Args:
            handler: Callable to execute during shutdown
        """
        self._shutdown_handlers.append(handler)

    # DebuggableComponent implementation
    def get_component_state(self) -> ComponentState:
        """Get current framework component state."""
        return FrameworkComponentState(
            component_id="mcp_server_framework",
            component_type="MCPServerFramework",
            state_data={
                "started": self._started,
                "components_count": len(self._components),
                "plugins_count": len(self._plugins),
                "event_subscriptions": len(self._event_subscriptions),
                "framework_started_at": self._framework_started_at.isoformat()
                if self._framework_started_at
                else None,
                "initialization_order": self._initialization_order,
                "component_states": {
                    name: state.state_data
                    for name, state in self._component_states.items()
                },
            },
        )

    def validate_component(self) -> ValidationResult:
        """Validate framework component state."""
        errors = []
        warnings = []

        # Check for circular dependencies and unregistered dependencies
        try:
            self._resolve_initialization_order()
        except ValueError as e:
            # The dependency resolution already includes comprehensive error checking
            errors.append(f"Dependency resolution error: {e}")

        # Check for orphaned event subscriptions
        for _event_type, subscriptions in self._event_subscriptions.items():
            for subscription in subscriptions:
                if (
                    subscription.component_name not in self._components
                    and subscription.component_name not in self._plugins
                ):
                    warnings.append(
                        f"Event subscription from unknown component: {subscription.component_name}"
                    )

        return FrameworkValidationResult(
            is_valid=len(errors) == 0,
            validation_errors=errors,
            validation_warnings=warnings,
        )

    def get_debug_info(self, debug_level: str = "INFO") -> DebugInfo:
        """Get framework debug information."""
        basic_info = {
            "framework_started": self._started,
            "components_registered": len(self._components),
            "plugins_registered": len(self._plugins),
            "event_subscriptions": len(self._event_subscriptions),
        }

        # Add performance metrics
        performance_metrics = {
            "components_count": len(self._components),
            "plugins_count": len(self._plugins),
            "uptime_seconds": (
                datetime.now() - self._framework_started_at
            ).total_seconds()
            if self._framework_started_at
            else 0,
        }

        if (
            debug_level.upper() in ["DEBUG", "DETAILED"]
            or debug_level.lower() == "detailed"
        ):
            basic_info.update(
                {
                    "component_names": list(self._components.keys()),
                    "plugin_names": list(self._plugins.keys()),
                    "initialization_order": self._initialization_order,
                    "event_types": list(self._event_subscriptions.keys()),
                }
            )

        return FrameworkDebugInfo(
            component_id="mcp_server_framework",
            debug_data=basic_info,
            debug_level=debug_level.upper(),
            performance_metrics=performance_metrics,
        )

    def inspect_state(self, path: str | None = None) -> dict[str, Any]:
        """Inspect specific parts of the framework state."""
        full_state = {
            "started": self._started,
            "components": {
                name: {
                    "component_type": type(reg.component).__name__,
                    "dependencies": reg.dependencies,
                    "priority": reg.priority,
                    "auto_start": reg.auto_start,
                    "registered_at": reg.registered_at.isoformat(),
                }
                for name, reg in self._components.items()
            },
            "plugins": {
                name: {
                    "plugin_type": type(plugin).__name__,
                    "initialized": plugin.initialized,
                    "running": plugin.running,
                }
                for name, plugin in self._plugins.items()
            },
            "events": {
                event_type: [
                    {"component_name": sub.component_name, "priority": sub.priority}
                    for sub in subscriptions
                ]
                for event_type, subscriptions in self._event_subscriptions.items()
            },
            "initialization_order": self._initialization_order,
            "framework_started_at": self._framework_started_at.isoformat()
            if self._framework_started_at
            else None,
        }

        if path is None:
            return full_state

        # Navigate to specific path
        current = full_state
        for part in path.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return {}

        return current if isinstance(current, dict) else {path: current}

    def get_component_dependencies(self) -> list[str]:
        """Get list of component dependencies."""
        dependencies = set()
        for registration in self._components.values():
            dependencies.update(registration.dependencies)
        return list(dependencies)

    def export_state_json(self) -> str:
        """Export framework state as JSON."""
        state = self.inspect_state()
        try:
            return json.dumps(state, indent=2, default=str)
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to export state as JSON: {e}")
            return json.dumps({"error": f"JSON export failed: {e}"})

    def health_check(self) -> dict[str, bool | str | int | float | None]:
        """Perform framework health check."""
        healthy = True
        status = "healthy"
        error_count = 0
        last_error = None

        # Check framework state
        if not self._initialization_order:
            healthy = False
            status = "not_initialized"
            error_count += 1
            last_error = "Framework not initialized"

        # Validate components
        validation_result = self.validate_component()
        if not validation_result.is_valid:
            healthy = False
            status = "validation_failed"
            error_count += len(validation_result.validation_errors)
            last_error = (
                validation_result.validation_errors[0]
                if validation_result.validation_errors
                else None
            )

        # Calculate uptime
        uptime = 0.0
        if self._framework_started_at:
            uptime = (datetime.now() - self._framework_started_at).total_seconds()

        return {
            "healthy": healthy,
            "status": status,
            "uptime": uptime,
            "last_error": last_error,
            "error_count": error_count,
            "components_registered": len(self._components),
            "plugins_registered": len(self._plugins),
            "framework_started": self._started,
        }
