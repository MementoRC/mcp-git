from abc import abstractmethod
from typing import Protocol, Any, Dict, Optional, TypeVar

# Define a TypeVar for the state type, allowing flexibility for different component states
_StateT = TypeVar('_StateT', bound=Dict[str, Any])


class DebuggableComponent(Protocol[_StateT]):
    """
    Protocol defining an interface for components that can expose their internal state
    and debugging information.

    This protocol is designed to facilitate introspection and debugging of
    various components within the system.
    """

    @abstractmethod
    async def get_component_state(self) -> _StateT:
        """
        Asynchronously retrieves the current internal state of the component.

        This method should return a snapshot of the component's significant
        variables and data structures.

        Returns:
            _StateT: A dictionary or a Pydantic model representing the component's state.
        """
        ...

    @abstractmethod
    async def get_validation_status(self) -> bool:
        """
        Asynchronously checks and returns the current validation status of the component.

        This indicates whether the component is in a valid operational state
        according to its internal rules or external dependencies.

        Returns:
            bool: True if the component is valid, False otherwise.
        """
        ...

    @abstractmethod
    async def get_debug_info(self) -> Dict[str, Any]:
        """
        Asynchronously retrieves additional debugging information about the component.

        This can include logs, configuration details, performance counters,
        or any other data useful for diagnosing issues.

        Returns:
            Dict[str, Any]: A dictionary containing various debugging details.
        """
        ...

    @abstractmethod
    async def inspect_state(self, path: Optional[str] = None) -> Any:
        """
        Asynchronously allows for granular inspection of the component's state.

        This method can be used to retrieve specific parts of the state,
        potentially navigating through nested structures using a 'path' argument.

        Args:
            path: Optional. A string representing a path or key to a specific
                  part of the component's state (e.g., "config.database_url", "cache_size").
                  If None, the entire state might be returned or a default view.

        Returns:
            Any: The value or sub-structure found at the specified path, or a default
                 inspection view if no path is provided.
        """
        ...
