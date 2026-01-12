"""Tests for lean MCP interface main entry point."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner


class TestLeanMain:
    """Test lean interface main() function."""

    @patch("mcp_server_git.lean.__main__.load_dotenv")
    @patch("mcp_server_git.lean.__main__.create_git_lean_interface")
    def test_main_initializes_without_azure_config(
        self, mock_create_interface, _mock_load_dotenv
    ):
        """Test that main() initializes successfully without Azure configuration.

        This test verifies the fix for the TypeError that occurred when
        AzureClient was initialized without required arguments (token,
        organization, session).

        The fix ensures NullAzureService is always used in the lean interface,
        regardless of whether the azure.client module is importable.
        """
        # Setup: Mock the FastMCP app to prevent actual server startup
        mock_app = MagicMock()
        mock_create_interface.return_value = mock_app

        # Import main - this is where the bug would have occurred
        from mcp_server_git.lean.__main__ import main

        # Execute: Use CliRunner for click commands
        runner = CliRunner()
        runner.invoke(main, [])

        # Verify: Check that services were initialized correctly
        mock_create_interface.assert_called_once()
        call_kwargs = mock_create_interface.call_args.kwargs

        # Verify all three services are provided
        assert "git_service" in call_kwargs
        assert "github_service" in call_kwargs
        assert "azure_service" in call_kwargs

        # Verify azure_service is NullAzureService (not AzureClient)
        azure_service = call_kwargs["azure_service"]
        assert azure_service is not None
        # NullAzureService doesn't require any initialization arguments
        assert type(azure_service).__name__ == "NullAzureService"

    @patch("mcp_server_git.lean.__main__.load_dotenv")
    @patch("mcp_server_git.lean.__main__.create_git_lean_interface")
    def test_main_uses_null_azure_service(
        self, mock_create_interface, _mock_load_dotenv
    ):
        """Test that main() always uses NullAzureService.

        Even if azure.client.AzureClient is importable, the lean interface
        should use NullAzureService because Azure configuration (token,
        organization, session) is not set up by default.
        """
        # Setup
        mock_app = MagicMock()
        mock_create_interface.return_value = mock_app

        from mcp_server_git.lean.__main__ import main

        # Execute: Use CliRunner for click commands
        runner = CliRunner()
        runner.invoke(main, [])

        # Verify NullAzureService is used
        call_kwargs = mock_create_interface.call_args.kwargs
        azure_service = call_kwargs["azure_service"]

        # Should be NullAzureService, not AzureClient
        assert type(azure_service).__name__ == "NullAzureService"

        # NullAzureService should have stub methods that don't require config
        assert hasattr(azure_service, "azure_get_build_status")
        assert hasattr(azure_service, "azure_get_build_logs")

    @patch("mcp_server_git.lean.__main__.load_dotenv")
    @patch("mcp_server_git.lean.__main__.create_git_lean_interface")
    @patch("mcp_server_git.lean.__main__.logger")
    def test_main_logs_initialization(
        self, mock_logger, mock_create_interface, _mock_load_dotenv
    ):
        """Test that main() logs successful initialization."""
        # Setup
        mock_app = MagicMock()
        mock_create_interface.return_value = mock_app

        from mcp_server_git.lean.__main__ import main

        # Execute: Use CliRunner for click commands
        runner = CliRunner()
        runner.invoke(main, [])

        # Verify logging
        assert mock_logger.info.called
        log_messages = [call.args[0] for call in mock_logger.info.call_args_list]

        # Should log initialization messages
        assert any("Initializing" in msg for msg in log_messages)
        assert any("initialized successfully" in msg for msg in log_messages)
        assert any("3 meta-tools" in msg for msg in log_messages)
        assert any("51 tools" in msg for msg in log_messages)

    def test_main_shows_help(self):
        """Test that --help flag shows usage information."""
        from mcp_server_git.lean.__main__ import main

        runner = CliRunner()
        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "MCP Git Lean Server" in result.output
        assert "--repository" in result.output
        assert "--verbose" in result.output

    @patch("mcp_server_git.lean.__main__.load_dotenv")
    @patch("mcp_server_git.lean.__main__.create_git_lean_interface")
    def test_main_accepts_repository_arg(
        self, mock_create_interface, _mock_load_dotenv, tmp_path
    ):
        """Test that --repository argument is accepted."""
        # Setup: Create a fake git repo
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        mock_app = MagicMock()
        mock_create_interface.return_value = mock_app

        from mcp_server_git.lean.__main__ import main

        # Execute with repository argument
        runner = CliRunner()
        result = runner.invoke(main, ["--repository", str(tmp_path)])

        # Should not error on valid repo path
        assert result.exit_code == 0 or mock_create_interface.called

    @patch("mcp_server_git.lean.__main__.load_dotenv")
    @patch("mcp_server_git.lean.__main__.create_git_lean_interface")
    @patch("mcp_server_git.lean.__main__.logger")
    def test_main_warns_on_invalid_repository(
        self, mock_logger, mock_create_interface, _mock_load_dotenv, tmp_path
    ):
        """Test that invalid repository path logs a warning."""
        mock_app = MagicMock()
        mock_create_interface.return_value = mock_app

        from mcp_server_git.lean.__main__ import main

        # Execute with non-git directory
        runner = CliRunner()
        runner.invoke(main, ["--repository", str(tmp_path)])

        # Should warn about invalid repo
        warning_calls = [
            call.args[0] for call in mock_logger.warning.call_args_list
        ]
        assert any("not a git repository" in msg for msg in warning_calls)
