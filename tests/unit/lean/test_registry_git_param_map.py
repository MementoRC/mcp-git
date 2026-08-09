"""Regression tests for the git_log schema/implementation param mismatch
(GitHub issue #196, defect 1).

The GitLog schema exposes a public ``format`` field (it can't be named
``format_str`` since that would leak an internal implementation detail into
the tool's public API), but the underlying ``git_log`` operation's parameter
is named ``format_str`` to avoid shadowing the ``format`` builtin. Without
the ``param_map={"format": "format_str"}`` rename in
``_register_git_tools``, calling the registered tool with ``format=...``
raised ``TypeError: git_log() got an unexpected keyword argument 'format'``.
"""

from unittest.mock import Mock, patch

import pytest

from mcp_server_git.git.models import GitLog
from mcp_server_git.lean.registry_git import _register_git_tools


class _StubInterface:
    """Minimal stand-in for GitLeanInterface.register_tool.

    Collects ToolDefinitions exactly as production's register_tool does,
    without the token-limiting/offloading wrapper, so tests can call
    tool_def.implementation directly and see the real registry wiring
    (including param_map) without needing a full GitLeanInterface.
    """

    def __init__(self):
        self.tool_registry = {}

    def register_tool(self, tool_def):
        self.tool_registry[tool_def.name] = tool_def


def _build_git_log_tool_def():
    interface = _StubInterface()
    _register_git_tools(interface, git_service=Mock())
    return interface.tool_registry["git_log"]


class TestGitLogRegistryParamMap:
    """Reproduce the exact reported failure via the real ToolDefinition."""

    def test_git_log_implementation_does_not_raise_when_called_with_schema_format_kwarg(
        self, tmp_path
    ):
        """Calling the registered git_log tool with the schema's ``format``
        keyword must not raise TypeError (issue #196 defect 1)."""
        # Arrange
        mock_repo_instance = Mock()
        mock_repo_instance.git.log.return_value = "abc123 G Alice Fix bug"

        with patch(
            "mcp_server_git.lean.registry_git.Repo", return_value=mock_repo_instance
        ):
            tool_def = _build_git_log_tool_def()

            # Act
            try:
                result = tool_def.implementation(
                    repo_path=str(tmp_path), format="%h %G? %GS", max_count=1
                )
            except TypeError as e:
                pytest.fail(
                    f"git_log tool raised TypeError for schema 'format' kwarg: {e}"
                )

        # Assert
        assert "unexpected keyword argument" not in str(result)
        args = mock_repo_instance.git.log.call_args[0]
        assert "--pretty=format:%h %G? %GS" in args

    def test_git_log_implementation_forwards_format_as_format_str_not_format(
        self, tmp_path
    ):
        """The underlying op must receive format_str, never the raw 'format'
        keyword, confirming param_map did the rename (issue #196 defect 1)."""
        # Arrange
        mock_repo_instance = Mock()
        mock_repo_instance.git.log.return_value = ""

        with (
            patch(
                "mcp_server_git.lean.registry_git.Repo",
                return_value=mock_repo_instance,
            ),
            patch("mcp_server_git.git.operations.git_log") as mock_git_log,
        ):
            mock_git_log.return_value = "abc123 - fix"
            tool_def = _build_git_log_tool_def()

            # Act
            tool_def.implementation(
                repo_path=str(tmp_path), format="%h - %s", max_count=1
            )

        # Assert
        _, call_kwargs = mock_git_log.call_args
        assert call_kwargs.get("format_str") == "%h - %s"
        assert "format" not in call_kwargs


class TestGitLogSchemaImplementationContract:
    """The schema's public parameter name must be a key the implementation
    actually accepts — this is the exact contract that broke in issue #196."""

    def test_git_log_schema_exposes_format_field(self):
        # Arrange / Act
        properties = GitLog.model_json_schema()["properties"]

        # Assert
        assert "format" in properties

    def test_git_log_registered_implementation_accepts_schema_format_key(
        self, tmp_path
    ):
        """The exact key exposed in GitLog's schema ('format') must be
        accepted by the registered implementation without raising."""
        # Arrange
        assert "format" in GitLog.model_json_schema()["properties"]
        mock_repo_instance = Mock()
        mock_repo_instance.git.log.return_value = ""

        with patch(
            "mcp_server_git.lean.registry_git.Repo", return_value=mock_repo_instance
        ):
            tool_def = _build_git_log_tool_def()

            # Act
            try:
                tool_def.implementation(repo_path=str(tmp_path), format="%h")
            except TypeError as e:
                pytest.fail(
                    f"schema key 'format' rejected by registered implementation: {e}"
                )
