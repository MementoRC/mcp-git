"""
Token limit configuration for MCP Git Server.

This module provides configuration management for token limits, client detection,
and content optimization settings. Configuration can be loaded from environment
variables, configuration files, or set programmatically.
"""

import logging
import os
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TokenLimitProfile(Enum):
    """Pre-defined token limit profiles for different use cases."""

    CONSERVATIVE = "conservative"  # Very safe limits
    BALANCED = "balanced"  # Good balance of functionality vs limits
    AGGRESSIVE = "aggressive"  # Maximum content preservation
    DEVELOPMENT = "development"  # High limits for development/testing


@dataclass
class TokenLimitSettings:
    """Token limit configuration settings."""

    # Core token limits
    llm_token_limit: int = 20000
    human_token_limit: int = 0  # 0 = unlimited
    unknown_token_limit: int = 25000

    # Feature toggles
    enable_content_optimization: bool = True
    enable_intelligent_truncation: bool = True
    enable_client_detection: bool = True
    add_truncation_warnings: bool = True

    # Performance settings
    max_processing_time_ms: int = 100
    enable_response_caching: bool = False

    # Client detection settings
    force_client_type: str = ""  # Force specific client type ("llm", "human", "")
    client_detection_headers: list[str] = field(
        default_factory=lambda: ["user-agent", "x-client-type"]
    )

    # Operation-specific overrides
    operation_limits: dict[str, int] = field(default_factory=dict)

    # Content optimization settings
    remove_emojis_for_llm: bool = True
    simplify_error_messages: bool = True
    add_structure_markers: bool = False
    include_content_summaries: bool = False

    def __post_init__(self):
        """Validate token limit settings after initialization."""
        # Validate core token limits
        if self.llm_token_limit < 0:
            raise ValueError("LLM token limit must be non-negative")
        if self.llm_token_limit > 1000000:  # Reasonable upper bound
            logger.warning(f"Very large LLM token limit: {self.llm_token_limit}")

        if self.human_token_limit < 0:
            raise ValueError("Human token limit must be non-negative")
        if (
            self.human_token_limit > 1000000 and self.human_token_limit != 0
        ):  # 0 = unlimited
            logger.warning(f"Very large human token limit: {self.human_token_limit}")

        if self.unknown_token_limit < 0:
            raise ValueError("Unknown client token limit must be non-negative")
        if self.unknown_token_limit > 1000000:
            logger.warning(
                f"Very large unknown client token limit: {self.unknown_token_limit}"
            )

        # Validate performance settings
        if self.max_processing_time_ms < 0:
            raise ValueError("Max processing time must be non-negative")
        if self.max_processing_time_ms > 10000:  # 10 seconds seems excessive
            logger.warning(
                f"Very large max processing time: {self.max_processing_time_ms}ms"
            )

        # Validate operation-specific limits
        for operation, limit in self.operation_limits.items():
            if limit < 0:
                raise ValueError(
                    f"Operation limit for '{operation}' must be non-negative"
                )
            if limit > 1000000:
                logger.warning(f"Very large operation limit for '{operation}': {limit}")

    @classmethod
    def from_profile(cls, profile: TokenLimitProfile) -> "TokenLimitSettings":
        """Create settings from a predefined profile."""
        profiles = {
            TokenLimitProfile.CONSERVATIVE: cls(
                llm_token_limit=15000,
                unknown_token_limit=18000,
                enable_content_optimization=True,
                enable_intelligent_truncation=True,
                add_truncation_warnings=True,
            ),
            TokenLimitProfile.BALANCED: cls(
                llm_token_limit=20000,
                unknown_token_limit=25000,
                enable_content_optimization=True,
                enable_intelligent_truncation=True,
            ),
            TokenLimitProfile.AGGRESSIVE: cls(
                llm_token_limit=30000,
                unknown_token_limit=35000,
                enable_content_optimization=False,
                enable_intelligent_truncation=True,
                add_truncation_warnings=False,
            ),
            TokenLimitProfile.DEVELOPMENT: cls(
                llm_token_limit=50000,
                unknown_token_limit=50000,
                enable_content_optimization=False,
                enable_intelligent_truncation=False,
                enable_response_caching=True,
            ),
        }

        return profiles.get(profile, cls())

    def to_dict(self) -> dict[str, Any]:
        """Convert settings to dictionary."""
        return {
            "llm_token_limit": self.llm_token_limit,
            "human_token_limit": self.human_token_limit,
            "unknown_token_limit": self.unknown_token_limit,
            "enable_content_optimization": self.enable_content_optimization,
            "enable_intelligent_truncation": self.enable_intelligent_truncation,
            "enable_client_detection": self.enable_client_detection,
            "add_truncation_warnings": self.add_truncation_warnings,
            "max_processing_time_ms": self.max_processing_time_ms,
            "enable_response_caching": self.enable_response_caching,
            "force_client_type": self.force_client_type,
            "client_detection_headers": self.client_detection_headers,
            "operation_limits": self.operation_limits,
            "remove_emojis_for_llm": self.remove_emojis_for_llm,
            "simplify_error_messages": self.simplify_error_messages,
            "add_structure_markers": self.add_structure_markers,
            "include_content_summaries": self.include_content_summaries,
        }


class TokenLimitConfigManager:
    """Manages token limit configuration from multiple sources."""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.TokenLimitConfigManager")
        self._settings: TokenLimitSettings | None = None
        self._config_file_path: Path | None = None
        self._lock = threading.Lock()

    def load_configuration(
        self,
        config_file: str | None = None,
        profile: TokenLimitProfile | None = None,
        **overrides,
    ) -> TokenLimitSettings:
        """
        Load configuration from multiple sources.

        Args:
            config_file: Path to configuration file
            profile: Predefined profile to use as base
            **overrides: Direct setting overrides

        Returns:
            Loaded TokenLimitSettings
        """
        # Start with profile or default settings
        if profile:
            settings = TokenLimitSettings.from_profile(profile)
        else:
            settings = TokenLimitSettings()

        # Load from configuration file if provided
        if config_file:
            file_settings = self._load_from_file(config_file)
            settings = self._merge_settings(settings, file_settings)

        # Load from environment variables
        env_settings = self._load_from_environment()
        settings = self._merge_settings(settings, env_settings)

        # Apply direct overrides
        for key, value in overrides.items():
            if hasattr(settings, key):
                setattr(settings, key, value)

        self._settings = settings
        self._log_configuration(settings)

        return settings

    def _load_from_file(self, config_file: str) -> dict[str, Any]:
        """Load configuration from JSON or YAML file."""
        try:
            config_path = Path(config_file)
            if not config_path.exists():
                self.logger.warning(f"Config file not found: {config_file}")
                return {}

            if config_path.suffix.lower() == ".json":
                import json

                with open(config_path) as f:
                    return json.load(f).get("token_limits", {})

            elif config_path.suffix.lower() in [".yml", ".yaml"]:
                try:
                    import yaml

                    with open(config_path) as f:
                        return yaml.safe_load(f).get("token_limits", {})
                except ImportError:
                    self.logger.error("PyYAML required for YAML config files")
                    return {}

            else:
                self.logger.error(
                    f"Unsupported config file format: {config_path.suffix}"
                )
                return {}

        except Exception as e:
            self.logger.error(f"Error loading config file {config_file}: {e}")
            return {}

    def _load_from_environment(self) -> dict[str, Any]:
        """Load configuration from environment variables."""
        env_settings = {}

        # Define environment variable mappings
        env_mappings = {
            "MCP_GIT_LLM_TOKEN_LIMIT": ("llm_token_limit", int),
            "MCP_GIT_HUMAN_TOKEN_LIMIT": ("human_token_limit", int),
            "MCP_GIT_UNKNOWN_TOKEN_LIMIT": ("unknown_token_limit", int),
            "MCP_GIT_ENABLE_OPTIMIZATION": (
                "enable_content_optimization",
                self._parse_bool,
            ),
            "MCP_GIT_ENABLE_TRUNCATION": (
                "enable_intelligent_truncation",
                self._parse_bool,
            ),
            "MCP_GIT_ENABLE_CLIENT_DETECTION": (
                "enable_client_detection",
                self._parse_bool,
            ),
            "MCP_GIT_ADD_TRUNCATION_WARNINGS": (
                "add_truncation_warnings",
                self._parse_bool,
            ),
            "MCP_GIT_MAX_PROCESSING_TIME_MS": ("max_processing_time_ms", int),
            "MCP_GIT_FORCE_CLIENT_TYPE": ("force_client_type", str),
            "MCP_GIT_REMOVE_EMOJIS": ("remove_emojis_for_llm", self._parse_bool),
            "MCP_GIT_SIMPLIFY_ERRORS": ("simplify_error_messages", self._parse_bool),
        }

        for env_var, (setting_name, type_converter) in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None:
                try:
                    env_settings[setting_name] = type_converter(value)
                except (ValueError, TypeError) as e:
                    self.logger.error(f"Invalid value for {env_var}: {value} ({e})")

        # Handle operation-specific limits
        for env_var, value in os.environ.items():
            if env_var.startswith("MCP_GIT_OPERATION_LIMIT_"):
                operation = env_var.replace("MCP_GIT_OPERATION_LIMIT_", "").lower()
                try:
                    if "operation_limits" not in env_settings:
                        env_settings["operation_limits"] = {}
                    env_settings["operation_limits"][operation] = int(value)
                except ValueError as e:
                    self.logger.error(
                        f"Invalid operation limit for {operation}: {value} ({e})"
                    )

        return env_settings

    def _merge_settings(
        self, base: TokenLimitSettings, overrides: dict[str, Any]
    ) -> TokenLimitSettings:
        """Merge override settings into base settings."""
        for key, value in overrides.items():
            if hasattr(base, key):
                # Handle special cases for nested dictionaries
                if key == "operation_limits" and hasattr(base, "operation_limits"):
                    base.operation_limits.update(value)
                elif key == "client_detection_headers" and isinstance(value, str):
                    base.client_detection_headers = [
                        h.strip() for h in value.split(",")
                    ]
                else:
                    setattr(base, key, value)
            else:
                self.logger.warning(f"Unknown configuration key: {key}")

        return base

    def _parse_bool(self, value: str) -> bool:
        """Parse boolean value from string."""
        return value.lower() in ("true", "1", "yes", "on", "enabled")

    def _log_configuration(self, settings: TokenLimitSettings) -> None:
        """Log the current configuration."""
        self.logger.info("Token limit configuration loaded:")
        self.logger.info(f"  LLM token limit: {settings.llm_token_limit}")
        self.logger.info(
            f"  Human token limit: {settings.human_token_limit or 'unlimited'}"
        )
        self.logger.info(f"  Unknown token limit: {settings.unknown_token_limit}")
        self.logger.info(
            f"  Content optimization: {settings.enable_content_optimization}"
        )
        self.logger.info(
            f"  Intelligent truncation: {settings.enable_intelligent_truncation}"
        )
        self.logger.info(f"  Client detection: {settings.enable_client_detection}")

        if settings.operation_limits:
            self.logger.info(
                f"  Operation-specific limits: {settings.operation_limits}"
            )

    def get_current_settings(self) -> TokenLimitSettings:
        """Get the currently loaded settings with thread safety."""
        # Double-checked locking pattern for thread safety
        if self._settings is None:
            with self._lock:
                # Check again after acquiring lock
                if self._settings is None:
                    self._settings = self.load_configuration()
        return self._settings

    def update_setting(self, key: str, value: Any) -> bool:
        """Update a specific setting."""
        if self._settings is None:
            self._settings = TokenLimitSettings()

        if hasattr(self._settings, key):
            setattr(self._settings, key, value)
            self.logger.info(f"Updated setting {key} = {value}")
            return True
        else:
            self.logger.error(f"Unknown setting: {key}")
            return False


# Global configuration manager instance
config_manager = TokenLimitConfigManager()
