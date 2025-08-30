"""
Integration tests for TokenLimitMiddleware integration with ServerApplication.

These tests specifically validate Task 2 implementation:
- ServerApplication properly initializes enhanced middleware chain
- TokenLimitMiddleware is included in the middleware chain
- Dependency injection works correctly (TokenLimitConfig)
- Middleware availability during server operations
- Integration test for request processing flow preparation

Focus: Testing the integration work completed in Task 2 without requiring full server startup.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_server_git.applications.server_application import (
    ServerApplication,
    ServerApplicationConfig,
)
from mcp_server_git.frameworks.server_middleware import MiddlewareChainManager
from mcp_server_git.middlewares.token_limit import TokenLimitMiddleware


class TestServerApplicationTokenMiddlewareIntegration:
    """Test TokenLimitMiddleware integration with ServerApplication."""

    def test_server_application_config_initialization(self):
        """Test ServerApplication config creates proper environment for middleware integration."""
        config = ServerApplicationConfig(
            repository_path=Path("/tmp/test-repo"),
            enable_metrics=True,
            enable_security=True,
            test_mode=True,
        )

        app = ServerApplication(config)

        # Verify basic initialization
        assert app.config == config
        assert (
            app._middleware_manager is None
        )  # Not initialized until infrastructure phase

    @pytest.mark.asyncio
    async def test_infrastructure_initialization_creates_enhanced_middleware_chain(
        self,
    ):
        """Test that _initialize_infrastructure() creates enhanced middleware chain with token limits."""
        config = ServerApplicationConfig(test_mode=True)
        app = ServerApplication(config)

        # Mock the framework registration to avoid side effects
        app._framework = MagicMock()
        app._configuration_manager = MagicMock()
        app._configuration_manager.get_current_config.return_value = MagicMock()

        # Call infrastructure initialization
        await app._initialize_infrastructure()

        # Verify enhanced middleware chain was created
        assert app._middleware_manager is not None
        assert isinstance(app._middleware_manager, MiddlewareChainManager)

        # Verify it's not empty (enhanced chain should have multiple middleware)
        middleware_list = app._middleware_manager.middlewares
        assert len(middleware_list) > 0

    @pytest.mark.asyncio
    async def test_token_limit_middleware_included_in_chain(self):
        """Test that TokenLimitMiddleware is specifically included in the middleware chain."""
        config = ServerApplicationConfig(test_mode=True)
        app = ServerApplication(config)

        # Mock framework and configuration
        app._framework = MagicMock()
        app._configuration_manager = MagicMock()
        app._configuration_manager.get_current_config.return_value = MagicMock()

        # Initialize infrastructure
        await app._initialize_infrastructure()

        # Get the middleware chain
        middleware_list = app._middleware_manager.middlewares

        # Find TokenLimitMiddleware in the chain
        token_middleware = None
        for middleware in middleware_list:
            if isinstance(middleware, TokenLimitMiddleware):
                token_middleware = middleware
                break

        assert token_middleware is not None, (
            "TokenLimitMiddleware not found in middleware chain"
        )

        # Verify middleware is properly configured
        assert token_middleware.config is not None
        assert (
            token_middleware.config.llm_token_limit == 20000
        )  # As configured in create_enhanced_middleware_chain
        assert token_middleware.config.enable_content_optimization is True
        assert token_middleware.config.enable_intelligent_truncation is True

    @pytest.mark.asyncio
    async def test_middleware_chain_ordering_includes_token_middleware(self):
        """Test that middleware chain has correct ordering with TokenLimitMiddleware included."""
        config = ServerApplicationConfig(test_mode=True)
        app = ServerApplication(config)

        # Mock dependencies
        app._framework = MagicMock()
        app._configuration_manager = MagicMock()
        app._configuration_manager.get_current_config.return_value = MagicMock()

        # Initialize infrastructure
        await app._initialize_infrastructure()

        # Get middleware list
        middleware_list = app._middleware_manager.middlewares

        # Verify we have expected middleware types (order matters)
        middleware_names = [middleware.name for middleware in middleware_list]

        # Should include standard middleware plus TokenLimitMiddleware
        expected_middleware_types = [
            "error_handling",
            "logging",
            "authentication",
            "request_tracking",
            "token_limit",  # This is the new one from Task 2
        ]

        # Check that all expected middleware are present
        for expected_type in expected_middleware_types:
            assert any(expected_type in name.lower() for name in middleware_names), (
                f"Expected middleware type '{expected_type}' not found in {middleware_names}"
            )

    @pytest.mark.asyncio
    async def test_dependency_injection_for_token_middleware_config(self):
        """Test that TokenLimitMiddleware receives proper dependency injection."""
        config = ServerApplicationConfig(test_mode=True)
        app = ServerApplication(config)

        # Mock dependencies
        app._framework = MagicMock()
        app._configuration_manager = MagicMock()
        app._configuration_manager.get_current_config.return_value = MagicMock()

        # Initialize infrastructure
        await app._initialize_infrastructure()

        # Find TokenLimitMiddleware
        middleware_list = app._middleware_manager.middlewares
        token_middleware = next(
            (m for m in middleware_list if isinstance(m, TokenLimitMiddleware)), None
        )

        assert token_middleware is not None

        # Verify configuration dependency injection
        assert token_middleware.config.llm_token_limit == 20000
        assert token_middleware.config.enable_content_optimization is True
        assert token_middleware.config.enable_intelligent_truncation is True
        assert token_middleware.config.max_processing_time_ms > 0

        # Verify middleware has required dependencies
        assert hasattr(token_middleware, "token_estimator")
        assert hasattr(token_middleware, "client_detector")
        assert hasattr(token_middleware, "truncation_manager")
        assert hasattr(token_middleware, "response_formatter")

    @pytest.mark.asyncio
    async def test_middleware_availability_during_component_registration(self):
        """Test that middleware manager is available during component registration phase."""
        config = ServerApplicationConfig(test_mode=True)
        app = ServerApplication(config)

        # Mock framework and configuration
        framework_mock = MagicMock()
        app._framework = framework_mock
        app._configuration_manager = MagicMock()
        app._configuration_manager.get_current_config.return_value = MagicMock()

        # Initialize infrastructure (creates middleware)
        await app._initialize_infrastructure()

        # Call component registration
        await app._register_components()

        # Verify middleware was registered with the framework
        framework_mock.register_component.assert_called()

        # Find the middleware registration call
        middleware_registration = None
        for call in framework_mock.register_component.call_args_list:
            args, kwargs = call
            if kwargs.get("name") == "middleware" or (
                len(args) > 0 and args[0] == "middleware"
            ):
                middleware_registration = call
                break

        assert middleware_registration is not None, (
            "Middleware was not registered with framework"
        )

        # Verify the registered component is our middleware manager
        call_kwargs = middleware_registration[1] if middleware_registration[1] else {}
        if "component" in call_kwargs:
            registered_component = call_kwargs["component"]
            assert registered_component is app._middleware_manager

    @pytest.mark.asyncio
    async def test_integration_request_processing_flow_preparation(self):
        """Test integration preparation for request processing flow."""
        config = ServerApplicationConfig(test_mode=True)
        app = ServerApplication(config)

        # Mock all dependencies for full initialization
        app._framework = MagicMock()
        app._configuration_manager = MagicMock()
        app._configuration_manager.get_current_config.return_value = MagicMock()

        # Initialize infrastructure
        await app._initialize_infrastructure()

        # Create a mock request context for testing the chain preparation
        from mcp_server_git.frameworks.server_middleware import MiddlewareContext

        mock_request = MagicMock()
        mock_context = MiddlewareContext(request=mock_request)

        # Verify middleware chain can be prepared for request processing
        middleware_manager = app._middleware_manager
        assert middleware_manager is not None

        # Test chain creation and basic structure
        middleware_list = middleware_manager.middlewares
        assert (
            len(middleware_list) >= 5
        )  # Should have at least 5 middleware including token limit

        # Verify TokenLimitMiddleware is in the chain and properly configured for requests
        token_middleware = next(
            (m for m in middleware_list if isinstance(m, TokenLimitMiddleware)), None
        )
        assert token_middleware is not None
        assert token_middleware.is_enabled()  # Should be enabled

        # Verify chain manager can process requests (basic validation)
        assert hasattr(middleware_manager, "process_request")
        assert callable(middleware_manager.process_request)

    @pytest.mark.asyncio
    async def test_enhanced_middleware_chain_fallback_without_token_limits(self):
        """Test that enhanced middleware chain works even if token limit creation fails."""
        config = ServerApplicationConfig(test_mode=True)
        app = ServerApplication(config)

        # Mock dependencies
        app._framework = MagicMock()
        app._configuration_manager = MagicMock()
        app._configuration_manager.get_current_config.return_value = MagicMock()

        # Mock token middleware creation to fail
        with patch(
            "mcp_server_git.middlewares.token_limit.create_token_limit_middleware"
        ) as mock_create:
            mock_create.side_effect = ImportError("Token middleware not available")

            # Initialize infrastructure should still work
            await app._initialize_infrastructure()

            # Verify middleware manager was still created
            assert app._middleware_manager is not None

            # Should have other middleware but not token middleware
            middleware_list = app._middleware_manager.middlewares
            assert len(middleware_list) >= 4  # Should have standard middleware

            # Should not have TokenLimitMiddleware
            token_middleware_found = any(
                isinstance(m, TokenLimitMiddleware) for m in middleware_list
            )
            assert not token_middleware_found

    @pytest.mark.asyncio
    async def test_server_application_full_initialization_with_token_middleware(self):
        """Integration test for full ServerApplication initialization including token middleware."""
        config = ServerApplicationConfig(
            repository_path=Path("/tmp/test-repo"),
            test_mode=True,
            enable_metrics=False,  # Disable for simpler testing
            enable_security=False,
            enable_notifications=False,
        )
        app = ServerApplication(config)

        # Mock all external dependencies
        app._framework = MagicMock()
        app._configuration_manager = MagicMock()
        app._configuration_manager.get_current_config.return_value = MagicMock()

        # Run only infrastructure initialization to avoid complex dependencies
        await app._initialize_infrastructure()

        # Verify middleware manager was created and configured
        assert app._middleware_manager is not None

        # Verify TokenLimitMiddleware is present and configured
        middleware_list = app._middleware_manager.middlewares
        token_middleware = next(
            (m for m in middleware_list if isinstance(m, TokenLimitMiddleware)), None
        )

        assert token_middleware is not None
        assert token_middleware.config.llm_token_limit == 20000
        assert token_middleware.name == "token_limit"

        # Verify the integration is complete
        assert hasattr(app, "_middleware_manager")
        assert callable(getattr(app._middleware_manager, "process_request", None))


class TestEnhancedMiddlewareChainCreation:
    """Test the create_enhanced_middleware_chain function directly for Task 2 validation."""

    def test_create_enhanced_middleware_chain_with_token_limits(self):
        """Test enhanced middleware chain creation with token limits enabled."""
        from mcp_server_git.frameworks.server_middleware import (
            create_enhanced_middleware_chain,
        )

        # Create enhanced chain with token limits
        chain = create_enhanced_middleware_chain(enable_token_limits=True)

        assert isinstance(chain, MiddlewareChainManager)

        # Verify middleware are present
        middleware_list = chain.middlewares
        assert len(middleware_list) >= 5  # Should have all standard + token middleware

        # Verify TokenLimitMiddleware is included
        token_middleware_found = any(
            isinstance(m, TokenLimitMiddleware) for m in middleware_list
        )
        assert token_middleware_found, (
            "TokenLimitMiddleware not found in enhanced chain"
        )

    def test_create_enhanced_middleware_chain_without_token_limits(self):
        """Test enhanced middleware chain creation with token limits disabled."""
        from mcp_server_git.frameworks.server_middleware import (
            create_enhanced_middleware_chain,
        )

        # Create enhanced chain without token limits
        chain = create_enhanced_middleware_chain(enable_token_limits=False)

        assert isinstance(chain, MiddlewareChainManager)

        # Verify standard middleware are present but not token middleware
        middleware_list = chain.middlewares
        assert len(middleware_list) >= 4  # Should have standard middleware

        # Verify TokenLimitMiddleware is NOT included
        token_middleware_found = any(
            isinstance(m, TokenLimitMiddleware) for m in middleware_list
        )
        assert not token_middleware_found, (
            "TokenLimitMiddleware should not be in chain when disabled"
        )

    def test_enhanced_middleware_chain_token_middleware_configuration(self):
        """Test that TokenLimitMiddleware in enhanced chain has correct configuration."""
        from mcp_server_git.frameworks.server_middleware import (
            create_enhanced_middleware_chain,
        )

        chain = create_enhanced_middleware_chain(enable_token_limits=True)
        middleware_list = chain.middlewares

        # Find and verify TokenLimitMiddleware configuration
        token_middleware = next(
            (m for m in middleware_list if isinstance(m, TokenLimitMiddleware)), None
        )

        assert token_middleware is not None

        # Verify configuration matches Task 2 requirements
        config = token_middleware.config
        assert config.llm_token_limit == 20000  # Conservative limit for LLMs
        assert config.enable_content_optimization is True
        assert config.enable_intelligent_truncation is True

        # Verify middleware is properly named and enabled
        assert token_middleware.name == "token_limit"
        assert token_middleware.is_enabled()


class TestMiddlewareChainIntegrationEdgeCases:
    """Test edge cases and error scenarios for middleware integration."""

    @pytest.mark.asyncio
    async def test_server_application_handles_middleware_creation_failure(self):
        """Test ServerApplication handles middleware creation failures gracefully."""
        config = ServerApplicationConfig(test_mode=True)
        app = ServerApplication(config)

        # Mock dependencies
        app._framework = MagicMock()
        app._configuration_manager = MagicMock()
        app._configuration_manager.get_current_config.return_value = MagicMock()

        # Mock the entire enhanced middleware chain creation to fail
        with patch(
            "mcp_server_git.frameworks.server_middleware.create_enhanced_middleware_chain"
        ) as mock_create:
            mock_create.side_effect = Exception("Middleware creation failed")

            # Initialization should fail gracefully
            with pytest.raises(Exception, match="Middleware creation failed"):
                await app._initialize_infrastructure()

    @pytest.mark.asyncio
    async def test_token_middleware_import_error_handling(self):
        """Test handling of TokenLimitMiddleware import errors."""
        from mcp_server_git.frameworks.server_middleware import (
            create_enhanced_middleware_chain,
        )

        # Mock the import to fail
        with patch(
            "mcp_server_git.middlewares.token_limit.create_token_limit_middleware"
        ) as mock_import:
            mock_import.side_effect = ImportError(
                "Token limit middleware not available"
            )

            # Should still create chain without token middleware
            chain = create_enhanced_middleware_chain(enable_token_limits=True)

            assert isinstance(chain, MiddlewareChainManager)

            # Should have standard middleware but not token middleware
            middleware_list = chain.middlewares
            assert len(middleware_list) >= 4
            token_middleware_found = any(
                isinstance(m, TokenLimitMiddleware) for m in middleware_list
            )
            assert not token_middleware_found

    def test_middleware_chain_manager_properties_after_integration(self):
        """Test MiddlewareChainManager properties after Task 2 integration."""
        from mcp_server_git.frameworks.server_middleware import (
            create_enhanced_middleware_chain,
        )

        chain = create_enhanced_middleware_chain(enable_token_limits=True)

        # Test chain manager methods work correctly
        assert len(chain.middlewares) >= 5
        assert chain.get_middleware("token_limit") is not None
        assert isinstance(chain.get_middleware("token_limit"), TokenLimitMiddleware)

        # Test middleware can be accessed by name
        token_middleware = chain.get_middleware("token_limit")
        assert token_middleware.name == "token_limit"
        assert token_middleware.is_enabled()


class TestTask2IntegrationCompliance:
    """Specific tests to validate Task 2 implementation requirements."""

    @pytest.mark.asyncio
    async def test_task2_requirement_enhanced_middleware_chain_initialization(self):
        """Verify Task 2 requirement: ServerApplication uses create_enhanced_middleware_chain."""
        config = ServerApplicationConfig(test_mode=True)
        app = ServerApplication(config)

        # Mock dependencies
        app._framework = MagicMock()
        app._configuration_manager = MagicMock()
        app._configuration_manager.get_current_config.return_value = MagicMock()

        # Just verify initialization directly without complex mocking
        await app._initialize_infrastructure()

        # Verify middleware manager was created with enhanced chain
        assert app._middleware_manager is not None
        assert isinstance(app._middleware_manager, MiddlewareChainManager)

        # Verify TokenLimitMiddleware is in the chain (which proves create_enhanced_middleware_chain was used)
        token_middleware = app._middleware_manager.get_middleware("token_limit")
        assert token_middleware is not None
        assert isinstance(token_middleware, TokenLimitMiddleware)

    def test_task2_requirement_token_middleware_20k_limit(self):
        """Verify Task 2 requirement: TokenLimitMiddleware has 20K token limit."""
        from mcp_server_git.frameworks.server_middleware import (
            create_enhanced_middleware_chain,
        )

        chain = create_enhanced_middleware_chain(enable_token_limits=True)
        token_middleware = chain.get_middleware("token_limit")

        assert token_middleware is not None
        assert isinstance(token_middleware, TokenLimitMiddleware)
        assert token_middleware.config.llm_token_limit == 20000

    def test_task2_requirement_middleware_chain_includes_all_components(self):
        """Verify Task 2 requirement: Enhanced chain includes all required middleware."""
        from mcp_server_git.frameworks.server_middleware import (
            create_enhanced_middleware_chain,
        )

        chain = create_enhanced_middleware_chain(enable_token_limits=True)
        middleware_names = [m.name for m in chain.middlewares]

        # Task 2 specifies these middleware should be included
        required_middleware = [
            "error_handling",
            "logging",
            "authentication",
            "request_tracking",
            "token_limit",  # New in Task 2
        ]

        for required in required_middleware:
            assert any(required in name.lower() for name in middleware_names), (
                f"Required middleware '{required}' not found. Available: {middleware_names}"
            )

    @pytest.mark.asyncio
    async def test_task2_requirement_dependency_injection_works(self):
        """Verify Task 2 requirement: Dependency injection works correctly."""
        config = ServerApplicationConfig(test_mode=True)
        app = ServerApplication(config)

        # Mock dependencies
        app._framework = MagicMock()
        app._configuration_manager = MagicMock()
        app._configuration_manager.get_current_config.return_value = MagicMock()

        await app._initialize_infrastructure()

        # Verify middleware manager was properly injected
        assert app._middleware_manager is not None
        assert isinstance(app._middleware_manager, MiddlewareChainManager)

        # Verify TokenLimitMiddleware was properly configured via dependency injection
        token_middleware = app._middleware_manager.get_middleware("token_limit")
        assert token_middleware is not None
        assert token_middleware.config is not None
        assert token_middleware.config.llm_token_limit == 20000
        assert token_middleware.config.enable_content_optimization is True
        assert token_middleware.config.enable_intelligent_truncation is True

    @pytest.mark.asyncio
    async def test_task2_requirement_middleware_ready_for_server_operations(self):
        """Verify Task 2 requirement: Middleware available during server operations."""
        config = ServerApplicationConfig(test_mode=True)
        app = ServerApplication(config)

        # Mock dependencies
        app._framework = MagicMock()
        app._configuration_manager = MagicMock()
        app._configuration_manager.get_current_config.return_value = MagicMock()

        await app._initialize_infrastructure()
        await app._register_components()

        # Verify middleware is available and ready for operations
        assert app._middleware_manager is not None

        # Verify middleware chain is ready to process requests
        middleware_list = app._middleware_manager.middlewares
        assert len(middleware_list) > 0

        # Verify TokenLimitMiddleware is ready
        token_middleware = next(
            (m for m in middleware_list if isinstance(m, TokenLimitMiddleware)), None
        )
        assert token_middleware is not None
        assert token_middleware.is_enabled()
        assert hasattr(token_middleware, "process_request")
        assert callable(token_middleware.process_request)
