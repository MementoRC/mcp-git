"""Tests for null Azure service."""

import pytest

from mcp_server_git.lean.null_azure_service import NullAzureService


class TestNullAzureService:
    """Test null object pattern for Azure service."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = NullAzureService()

    def test_get_build_status(self):
        """Test get_build_status returns error."""
        result = self.service.azure_get_build_status(project="test", build_id=123)
        assert "error" in result
        assert "Azure DevOps client not available" in result["error"]
        assert result["requested_operation"] == "get_build_status"

    def test_get_build_logs(self):
        """Test get_build_logs returns error."""
        result = self.service.azure_get_build_logs(project="test", build_id=123)
        assert "error" in result
        assert result["requested_operation"] == "get_build_logs"

    def test_get_failing_jobs(self):
        """Test get_failing_jobs returns error."""
        result = self.service.azure_get_failing_jobs(project="test", build_id=123)
        assert "error" in result
        assert result["requested_operation"] == "get_failing_jobs"

    def test_list_builds(self):
        """Test list_builds returns error."""
        result = self.service.azure_list_builds(project="test")
        assert "error" in result
        assert result["requested_operation"] == "list_builds"

    def test_parameters_preserved_in_error(self):
        """Test that request parameters are preserved in error response."""
        params = {"project": "myproject", "build_id": 456}
        result = self.service.azure_get_build_status(**params)
        assert result["parameters"] == params
