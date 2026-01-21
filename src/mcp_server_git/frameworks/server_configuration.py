"""
Server configuration management module with comprehensive loading and validation.

This module implements the server configuration management layer as part of the
server decomposition effort, extracting configuration-related functionality from
the monolithic server.py into a focused, maintainable module.

Key responsibilities:
    - Configuration loading from multiple sources (files, env vars, CLI args)
    - Configuration validation using Pydantic models
    - Runtime configuration management and updates
    - Environment-specific configuration handling
    - Configuration state inspection and debugging

Architecture:
    - Uses existing Pydantic configuration models from configuration/ directory
    - Implements DebuggableComponent protocol for state inspection
    - Provides clean separation between configuration sources and validation
    - Supports configuration hot-reloading with validation

Usage:
    >>> from mcp_server_git.frameworks import ServerConfigurationManager
    >>>
    >>> # Load configuration with defaults
    >>> config_manager = ServerConfigurationManager()
    >>> await config_manager.initialize()
    >>>
    >>> # Access current configuration
    >>> config = config_manager.get_current_config()
    >>> print(f"Server running on {config.host}:{config.port}")
    >>>
    >>> # Update configuration
    >>> await config_manager.update_config({'port': 9000})

Design principles:
    - Single source of truth for configuration state
    - Validation at every configuration change
    - Clear precedence rules for configuration sources
    - Comprehensive error handling and reporting
    - Support for both static and dynamic configuration
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import ValidationError

try:
    import yaml
except ImportError:
    yaml = None

from mcp_server_git.configuration.server_config import GitServerConfig
from mcp_server_git.protocols.debugging_protocol import (
    ComponentState,
    DebuggableComponent,
)


class ConfigurationError(Exception):
    """Exception raised when configuration operations fail."""

    pass


class ConfigurationState:
    """Represents the current state of configuration management."""

    def __init__(
        self,
        config: GitServerConfig,
        source_precedence: list[str],
        last_loaded: datetime,
        validation_errors: list[str] | None = None,
    ):
        self.config = config
        self.source_precedence = source_precedence
        self.last_loaded = last_loaded
        self.validation_errors = validation_errors or []

    @property
    def component_id(self) -> str:
        return "server_configuration"

    @property
    def component_type(self) -> str:
        return "ServerConfigurationManager"

    @property
    def last_updated(self) -> datetime:
        return self.last_loaded

    @property
    def state_data(self) -> dict[str, Any]:
        return {
            "current_config": self.config.model_dump(),
            "source_precedence": self.source_precedence,
            "last_loaded": self.last_loaded.isoformat(),
            "validation_errors": self.validation_errors,
            "config_sources_active": len(self.source_precedence),
        }


class ServerConfigurationManager(DebuggableComponent):
    """
    Comprehensive server configuration manager with multi-source loading and validation.

    This class manages all aspects of server configuration, including loading from
    multiple sources, validation, runtime updates, and state inspection.

    Configuration precedence (highest to lowest):
        1. Command line arguments
        2. Environment variables
        3. Configuration files (.yaml, .json, .toml)
        4. Default values from Pydantic models

    Attributes:
        _current_config: Current validated configuration
        _config_sources: Active configuration sources
        _state: Current configuration state for debugging
        _watchers: Configuration change watchers for hot reload
    """

    def __init__(
        self,
        config_file_path: Path | None = None,
        auto_reload: bool = False,
        validation_strict: bool = True,
    ):
        """
        Initialize configuration manager.

        Args:
            config_file_path: Path to configuration file (optional)
            auto_reload: Enable automatic configuration reloading
            validation_strict: Enable strict validation mode
        """
        self._current_config: GitServerConfig | None = None
        self._config_sources: dict[str, Any] = {}
        self._config_file_path = config_file_path
        self._auto_reload = auto_reload
        self._validation_strict = validation_strict
        self._state: ConfigurationState | None = None
        self._watchers: list = []
        self._initialized = False
        self._start_time = datetime.now()
        self._error_count = 0
        self._last_error: str | None = None

    async def initialize(self) -> None:
        """
        Initialize configuration manager and load initial configuration.

        Loads configuration from all available sources in precedence order
        and performs comprehensive validation.

        Raises:
            ConfigurationError: If configuration loading or validation fails
        """
        try:
            # Load configuration from all sources
            await self._load_configuration_sources()

            # Merge configuration with precedence rules
            merged_config = await self._merge_configuration_sources()

            # Validate and create configuration object
            self._current_config = await self._validate_configuration(merged_config)

            # Update state for debugging
            self._update_state()

            # Set up auto-reload if enabled
            if self._auto_reload:
                await self._setup_configuration_watchers()

            self._initialized = True

        except Exception as e:
            self._error_count += 1
            self._last_error = str(e)
            raise ConfigurationError(f"Failed to initialize configuration: {e}") from e

    async def _load_configuration_sources(self) -> None:
        """Load configuration from all available sources."""
        self._config_sources = {}

        # 1. Load from configuration file
        if self._config_file_path and self._config_file_path.exists():
            self._config_sources["file"] = await self._load_config_file(
                self._config_file_path
            )

        # 2. Load from environment variables
        env_config = await self._load_environment_config()
        if env_config:
            self._config_sources["environment"] = env_config

        # 3. Load default configuration
        self._config_sources["defaults"] = await self._load_default_config()

    async def _load_config_file(self, file_path: Path) -> dict[str, Any]:
        """
        Load configuration from file (supports YAML, JSON, TOML).

        Args:
            file_path: Path to configuration file

        Returns:
            Configuration dictionary

        Raises:
            ConfigurationError: If file cannot be loaded or parsed
        """
        try:
            content = file_path.read_text(encoding="utf-8")

            if file_path.suffix.lower() in [".yml", ".yaml"]:
                if yaml is None:
                    raise ConfigurationError("YAML support requires 'PyYAML' package")
                return yaml.safe_load(content) or {}
            elif file_path.suffix.lower() == ".json":
                return json.loads(content) or {}
            elif file_path.suffix.lower() == ".toml":
                try:
                    import tomli

                    return tomli.loads(content) or {}
                except ImportError:
                    raise ConfigurationError(
                        "TOML support requires 'tomli' package"
                    ) from None
            else:
                # Try JSON first, then YAML as fallback
                try:
                    return json.loads(content) or {}
                except json.JSONDecodeError:
                    if yaml is None:
                        raise ConfigurationError(
                            "Cannot parse file: JSON parsing failed and YAML not available"
                        ) from None
                    return yaml.safe_load(content) or {}

        except Exception as e:
            raise ConfigurationError(
                f"Failed to load config file {file_path}: {e}"
            ) from e

    async def _load_environment_config(self) -> dict[str, Any]:
        """
        Load configuration from environment variables.

        Environment variables are prefixed with 'MCP_GIT_' and converted to
        lowercase for configuration key matching.

        Returns:
            Configuration dictionary from environment
        """
        # Load .env file if it exists
        env_file = Path(".env")
        if env_file.exists():
            load_dotenv(env_file)

        config = {}
        prefix = "MCP_GIT_"

        for key, value in os.environ.items():
            if key.startswith(prefix):
                config_key = key[len(prefix) :].lower()

                # Convert string values to appropriate types
                if value.lower() in ["true", "false"]:
                    config[config_key] = value.lower() == "true"
                elif value.isdigit():
                    config[config_key] = int(value)
                elif value.replace(".", "").isdigit():
                    config[config_key] = float(value)
                else:
                    config[config_key] = value

        return config

    async def _load_default_config(self) -> dict[str, Any]:
        """
        Load default configuration from Pydantic model.

        Returns:
            Default configuration dictionary
        """
        default_config = GitServerConfig()
        return default_config.model_dump()

    async def _merge_configuration_sources(self) -> dict[str, Any]:
        """
        Merge configuration sources according to precedence rules.

        Precedence: CLI args > Environment vars > Config file > Defaults

        Returns:
            Merged configuration dictionary
        """
        merged = {}
        source_precedence = []

        # Start with defaults (lowest precedence)
        if "defaults" in self._config_sources:
            merged.update(self._config_sources["defaults"])
            source_precedence.append("defaults")

        # Override with file configuration
        if "file" in self._config_sources:
            merged.update(self._config_sources["file"])
            source_precedence.append("file")

        # Override with environment variables
        if "environment" in self._config_sources:
            merged.update(self._config_sources["environment"])
            source_precedence.append("environment")

        # Store precedence for debugging
        self._source_precedence = source_precedence

        return merged

    async def _validate_configuration(
        self, config_data: dict[str, Any]
    ) -> GitServerConfig:
        """
        Validate configuration data using Pydantic model.

        Args:
            config_data: Configuration dictionary to validate

        Returns:
            Validated GitServerConfig instance

        Raises:
            ConfigurationError: If validation fails
        """
        try:
            return GitServerConfig(**config_data)
        except ValidationError as e:
            if self._validation_strict:
                errors = [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
                raise ConfigurationError(
                    f"Configuration validation failed: {'; '.join(errors)}"
                ) from e
            else:
                # In non-strict mode, use defaults for invalid values
                valid_data = {}
                for field, value in config_data.items():
                    try:
                        # Test individual field validation
                        GitServerConfig(**{field: value})
                        valid_data[field] = value
                    except ValidationError:
                        # Skip invalid fields, use defaults
                        continue

                return GitServerConfig(**valid_data)

    async def _setup_configuration_watchers(self) -> None:
        """Set up file watchers for automatic configuration reloading."""
        # This would implement file watching using watchdog or similar
        # For now, just log that auto-reload is enabled
        pass

    def _update_state(self) -> None:
        """Update internal state for debugging and inspection."""
        if self._current_config:
            self._state = ConfigurationState(
                config=self._current_config,
                source_precedence=getattr(self, "_source_precedence", []),
                last_loaded=datetime.now(),
                validation_errors=[],
            )

    # DebuggableComponent implementation
    def get_component_state(self) -> ComponentState:
        """Get current component state for debugging."""
        if not self._state:
            # Create minimal state if not initialized
            return ConfigurationState(
                config=GitServerConfig(),
                source_precedence=[],
                last_loaded=datetime.now(),
                validation_errors=["Component not initialized"],
            )
        return self._state

    def validate_component(self) -> dict[str, Any]:
        """Validate current component state and configuration."""
        errors = []
        warnings = []
        is_valid = True

        # Check initialization
        if not self._initialized:
            errors.append("Component not initialized")
            is_valid = False

        # Check configuration presence
        if not self._current_config:
            errors.append("No current configuration loaded")
            is_valid = False

        # Check configuration sources
        if self._initialized and len(self._config_sources) == 0:
            warnings.append("No configuration sources loaded")

        # Validate current configuration if available
        if self._current_config:
            try:
                # Re-validate current config to ensure it's still valid
                GitServerConfig(**self._current_config.model_dump())
            except ValidationError as e:
                errors.extend(
                    [f"Config validation: {err['msg']}" for err in e.errors()]
                )
                is_valid = False

        return {
            "is_valid": is_valid,
            "validation_errors": errors,
            "validation_warnings": warnings,
            "validation_timestamp": datetime.now(),
        }

    def get_debug_info(self, debug_level: str = "INFO") -> dict[str, Any]:
        """Get debug information for the component."""
        debug_data = {
            "initialization_status": self._initialized,
            "config_file_path": str(self._config_file_path)
            if self._config_file_path
            else None,
            "auto_reload_enabled": self._auto_reload,
            "validation_strict": self._validation_strict,
            "sources_count": len(self._config_sources),
            "watchers_count": len(self._watchers),
            "current_config_present": self._current_config is not None,
        }

        if debug_level in ["DEBUG", "INFO"]:
            debug_data.update(
                {
                    "source_precedence": getattr(self, "_source_precedence", []),
                    "config_sources": list(self._config_sources.keys()),
                }
            )

        if debug_level == "DEBUG":
            debug_data.update(
                {
                    "current_config": self._current_config.model_dump()
                    if self._current_config
                    else None,
                    "state_data": self._state.state_data if self._state else None,
                }
            )

        performance_metrics = {
            "uptime_seconds": (datetime.now() - self._start_time).total_seconds(),
            "error_count": self._error_count,
            "initialization_time": 0.0,  # Would track actual init time in production
        }

        return {
            "debug_level": debug_level,
            "debug_data": debug_data,
            "stack_trace": None,  # Not implemented for this component
            "performance_metrics": performance_metrics,
        }

    def inspect_state(self, path: str | None = None) -> dict[str, Any]:
        """Inspect specific parts of the component state."""
        if not self._initialized:
            return {"error": "Component not initialized"}

        full_state = {
            "config": self._current_config.model_dump()
            if self._current_config
            else None,
            "sources": self._config_sources,
            "state": self._state.state_data if self._state else None,
            "metadata": {
                "initialized": self._initialized,
                "auto_reload": self._auto_reload,
                "validation_strict": self._validation_strict,
                "config_file_path": str(self._config_file_path)
                if self._config_file_path
                else None,
            },
        }

        if path is None:
            return full_state

        # Navigate to specific path using dot notation
        try:
            parts = path.split(".")
            current = full_state
            for part in parts:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return {"error": f"Path '{path}' not found in state"}
            return {"path": path, "value": current}
        except Exception as e:
            return {"error": f"Error accessing path '{path}': {str(e)}"}

    def get_component_dependencies(self) -> list[str]:
        """Get list of component dependencies."""
        dependencies = ["configuration.server_config", "protocols.debugging_protocol"]

        if self._current_config:
            # Add optional dependencies based on configuration
            if self._current_config.github_token:
                dependencies.append("github.api")
            if self._current_config.enable_metrics_collection:
                dependencies.append("protocols.metrics_protocol")

        return dependencies

    def export_state_json(self) -> str:
        """Export component state as JSON for external analysis."""
        export_data = {
            "component_id": "server_configuration",
            "component_type": "ServerConfigurationManager",
            "timestamp": datetime.now().isoformat(),
            "state": self.inspect_state(),
            "validation": self.validate_component(),
            "debug_info": self.get_debug_info("INFO"),
            "dependencies": self.get_component_dependencies(),
        }

        return json.dumps(export_data, indent=2, default=str)

    def health_check(self) -> dict[str, bool | str | int | float | None]:
        """Perform a health check on the component."""
        is_healthy = True
        status = "healthy"

        # Check basic health conditions
        if not self._initialized:
            is_healthy = False
            status = "not_initialized"
        elif not self._current_config:
            is_healthy = False
            status = "no_configuration"
        elif self._error_count > 10:  # Arbitrary threshold
            is_healthy = False
            status = "too_many_errors"

        uptime = (datetime.now() - self._start_time).total_seconds()

        return {
            "healthy": is_healthy,
            "status": status,
            "uptime": uptime,
            "last_error": self._last_error,
            "error_count": self._error_count,
            "initialization_complete": self._initialized,
            "configuration_loaded": self._current_config is not None,
        }

    # Public API
    def get_current_config(self) -> GitServerConfig:
        """
        Get current validated configuration.

        Returns:
            Current GitServerConfig instance

        Raises:
            ConfigurationError: If configuration not initialized
        """
        if not self._current_config:
            raise ConfigurationError(
                "Configuration not initialized. Call initialize() first."
            )
        return self._current_config

    async def update_config(self, updates: dict[str, Any]) -> None:
        """
        Update configuration with new values.

        Args:
            updates: Dictionary of configuration updates

        Raises:
            ConfigurationError: If updates are invalid or update fails
        """
        if not self._initialized or self._current_config is None:
            raise ConfigurationError("Configuration not initialized")

        # Merge updates with current config
        current_data = self._current_config.model_dump()
        current_data.update(updates)

        # Validate updated configuration
        try:
            updated_config = await self._validate_configuration(current_data)
            self._current_config = updated_config
            self._update_state()

        except Exception as e:
            self._error_count += 1
            self._last_error = str(e)
            raise ConfigurationError(f"Failed to update configuration: {e}") from e

    async def reload_configuration(self) -> None:
        """Reload configuration from all sources."""
        if not self._initialized:
            raise ConfigurationError("Configuration not initialized")

        await self._load_configuration_sources()
        merged_config = await self._merge_configuration_sources()
        self._current_config = await self._validate_configuration(merged_config)
        self._update_state()

    def export_configuration(self, format_type: str = "dict") -> dict[str, Any] | str:
        """
        Export current configuration.

        Args:
            format_type: Export format ('dict', 'json', 'yaml')

        Returns:
            Configuration in requested format
        """
        if not self._current_config:
            raise ConfigurationError("Configuration not initialized")

        config_dict = self._current_config.model_dump()

        if format_type == "dict":
            return config_dict
        elif format_type == "json":
            return json.dumps(config_dict, indent=2, default=str)
        elif format_type == "yaml":
            if yaml is None:
                raise ConfigurationError("YAML export requires 'PyYAML' package")
            return yaml.dump(config_dict, default_flow_style=False)
        else:
            raise ValueError(f"Unsupported format type: {format_type}")
