"""
Unit tests for GitHub repository creation functionality.

Tests the github_create_repo function including:
- Creating personal repositories
- Creating organization repositories
- Pydantic model validation for GitHubCreateRepo
- Error handling (repo exists, permission denied, org not found)
- Authentication and connection error handling
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from src.mcp_server_git.github.api import github_create_repo
from src.mcp_server_git.github.models import GitHubCreateRepo


class TestGitHubCreateRepoModel:
    """Test GitHubCreateRepo Pydantic model validation."""

    def test_valid_repo_name(self):
        """Test valid repository names are accepted."""
        valid_names = [
            "my-repo",
            "my_repo",
            "my.repo",
            "MyRepo123",
            "a",
            "repo-name-with-many-parts",
        ]
        for name in valid_names:
            model = GitHubCreateRepo(name=name)
            assert model.name == name

    def test_invalid_repo_name_empty(self):
        """Test empty repository name is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GitHubCreateRepo(name="")
        assert "cannot be empty" in str(exc_info.value)

    def test_invalid_repo_name_starts_with_period(self):
        """Test repository name starting with period is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GitHubCreateRepo(name=".hidden-repo")
        assert "cannot start with a period" in str(exc_info.value)

    def test_invalid_repo_name_special_chars(self):
        """Test repository name with invalid characters is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GitHubCreateRepo(name="repo/name")
        assert "alphanumeric" in str(exc_info.value)

    def test_invalid_repo_name_too_long(self):
        """Test repository name exceeding 100 characters is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GitHubCreateRepo(name="a" * 101)
        assert "too long" in str(exc_info.value)

    def test_valid_org_name(self):
        """Test valid organization names are accepted."""
        valid_orgs = [
            "my-org",
            "MyOrg123",
            "org",
            "my-org-name",
        ]
        for org in valid_orgs:
            model = GitHubCreateRepo(name="repo", org=org)
            assert model.org == org

    def test_org_name_none_is_valid(self):
        """Test None organization name is valid (personal repo)."""
        model = GitHubCreateRepo(name="repo", org=None)
        assert model.org is None

    def test_invalid_org_name_empty_string(self):
        """Test empty string organization name is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GitHubCreateRepo(name="repo", org="")
        assert "cannot be empty string" in str(exc_info.value)

    def test_invalid_org_name_starts_with_hyphen(self):
        """Test organization name starting with hyphen is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GitHubCreateRepo(name="repo", org="-invalid")
        assert "start/end with alphanumeric" in str(exc_info.value)

    def test_invalid_org_name_too_long(self):
        """Test organization name exceeding 39 characters is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GitHubCreateRepo(name="repo", org="a" * 40)
        assert "too long" in str(exc_info.value)

    def test_all_optional_fields(self):
        """Test model with all optional fields specified."""
        model = GitHubCreateRepo(
            name="my-repo",
            org="my-org",
            description="A test repository",
            private=True,
            auto_init=True,
            gitignore_template="Python",
            license_template="mit",
            has_issues=False,
            has_projects=False,
            has_wiki=False,
        )
        assert model.name == "my-repo"
        assert model.org == "my-org"
        assert model.description == "A test repository"
        assert model.private is True
        assert model.auto_init is True
        assert model.gitignore_template == "Python"
        assert model.license_template == "mit"
        assert model.has_issues is False


class TestGitHubCreateRepoPersonal:
    """Test github_create_repo for personal repositories."""

    @pytest.mark.asyncio
    async def test_create_personal_repo_success(self):
        """Test successfully creating a personal repository."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 201
        mock_response.json = AsyncMock(
            return_value={
                "full_name": "user/my-repo",
                "html_url": "https://github.com/user/my-repo",
                "clone_url": "https://github.com/user/my-repo.git",
                "ssh_url": "git@github.com:user/my-repo.git",
                "private": False,
            }
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_create_repo(name="my-repo")

            assert "Successfully created repository: user/my-repo" in result
            assert "https://github.com/user/my-repo" in result
            assert "Clone (HTTPS):" in result
            assert "Clone (SSH):" in result
            assert "Visibility: Public" in result
            mock_client.post.assert_called_once_with(
                "/user/repos",
                json={
                    "name": "my-repo",
                    "private": False,
                    "auto_init": False,
                    "has_issues": True,
                    "has_projects": True,
                    "has_wiki": True,
                },
            )

    @pytest.mark.asyncio
    async def test_create_private_repo_success(self):
        """Test successfully creating a private repository."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 201
        mock_response.json = AsyncMock(
            return_value={
                "full_name": "user/private-repo",
                "html_url": "https://github.com/user/private-repo",
                "clone_url": "https://github.com/user/private-repo.git",
                "ssh_url": "git@github.com:user/private-repo.git",
                "private": True,
            }
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_create_repo(name="private-repo", private=True)

            assert "Successfully created repository" in result
            assert "Visibility: Private" in result

    @pytest.mark.asyncio
    async def test_create_repo_with_auto_init(self):
        """Test creating a repository with README initialization."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 201
        mock_response.json = AsyncMock(
            return_value={
                "full_name": "user/initialized-repo",
                "html_url": "https://github.com/user/initialized-repo",
                "clone_url": "https://github.com/user/initialized-repo.git",
                "ssh_url": "git@github.com:user/initialized-repo.git",
                "private": False,
            }
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_create_repo(name="initialized-repo", auto_init=True)

            assert "Initialized with README" in result


class TestGitHubCreateRepoOrganization:
    """Test github_create_repo for organization repositories."""

    @pytest.mark.asyncio
    async def test_create_org_repo_success(self):
        """Test successfully creating an organization repository."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 201
        mock_response.json = AsyncMock(
            return_value={
                "full_name": "my-org/team-repo",
                "html_url": "https://github.com/my-org/team-repo",
                "clone_url": "https://github.com/my-org/team-repo.git",
                "ssh_url": "git@github.com:my-org/team-repo.git",
                "private": True,
            }
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_create_repo(
                name="team-repo",
                org="my-org",
                private=True,
                description="Team repository",
            )

            assert "Successfully created repository: my-org/team-repo" in result
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[0][0] == "/orgs/my-org/repos"
            assert call_args[1]["json"]["description"] == "Team repository"

    @pytest.mark.asyncio
    async def test_create_org_repo_not_found(self):
        """Test creating repository in non-existent organization."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 404
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_create_repo(name="repo", org="nonexistent-org")

            assert "Error:" in result
            assert "nonexistent-org" in result
            assert "not found" in result


class TestGitHubCreateRepoErrors:
    """Test error handling for github_create_repo."""

    @pytest.mark.asyncio
    async def test_repo_already_exists(self):
        """Test error when repository already exists."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 422
        mock_response.json = AsyncMock(
            return_value={
                "message": "Validation Failed",
                "errors": [{"message": "name already exists on this account"}],
            }
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_create_repo(name="existing-repo")

            assert "Error:" in result
            assert "already exists" in result

    @pytest.mark.asyncio
    async def test_permission_denied(self):
        """Test error when permission is denied."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 403
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_create_repo(name="repo")

            assert "Error: Permission denied" in result
            assert "'repo' scope" in result

    @pytest.mark.asyncio
    async def test_validation_error_generic(self):
        """Test generic validation error from GitHub API."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 422
        mock_response.json = AsyncMock(
            return_value={
                "message": "Repository creation failed",
                "errors": [],
            }
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_create_repo(name="repo")

            assert "Validation error" in result
            assert "Repository creation failed" in result

    @pytest.mark.asyncio
    async def test_authentication_error(self):
        """Test error when authentication fails."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ValueError(
                "GitHub token not configured"
            )

            result = await github_create_repo(name="repo")

            assert "Error:" in result
            assert "token" in result.lower()

    @pytest.mark.asyncio
    async def test_connection_error(self):
        """Test error when network connection fails."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ConnectionError(
                "Network unreachable"
            )

            result = await github_create_repo(name="repo")

            assert "Error:" in result
            assert "Network connection failed" in result

    @pytest.mark.asyncio
    async def test_unexpected_error(self):
        """Test handling of unexpected errors."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = RuntimeError(
                "Unexpected failure"
            )

            result = await github_create_repo(name="repo")

            assert "Error:" in result
            assert "Unexpected failure" in result

    @pytest.mark.asyncio
    async def test_unknown_status_code(self):
        """Test handling of unknown HTTP status codes."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_create_repo(name="repo")

            assert "Error:" in result
            assert "500" in result


class TestGitHubCreateRepoOptions:
    """Test github_create_repo with various options."""

    @pytest.mark.asyncio
    async def test_create_repo_with_gitignore_template(self):
        """Test creating repository with gitignore template."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 201
        mock_response.json = AsyncMock(
            return_value={
                "full_name": "user/python-project",
                "html_url": "https://github.com/user/python-project",
                "clone_url": "https://github.com/user/python-project.git",
                "ssh_url": "git@github.com:user/python-project.git",
                "private": False,
            }
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            await github_create_repo(
                name="python-project",
                gitignore_template="Python",
            )

            call_args = mock_client.post.call_args
            assert call_args[1]["json"]["gitignore_template"] == "Python"

    @pytest.mark.asyncio
    async def test_create_repo_with_license_template(self):
        """Test creating repository with license template."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 201
        mock_response.json = AsyncMock(
            return_value={
                "full_name": "user/mit-project",
                "html_url": "https://github.com/user/mit-project",
                "clone_url": "https://github.com/user/mit-project.git",
                "ssh_url": "git@github.com:user/mit-project.git",
                "private": False,
            }
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            await github_create_repo(
                name="mit-project",
                license_template="mit",
            )

            call_args = mock_client.post.call_args
            assert call_args[1]["json"]["license_template"] == "mit"

    @pytest.mark.asyncio
    async def test_create_repo_disable_features(self):
        """Test creating repository with features disabled."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 201
        mock_response.json = AsyncMock(
            return_value={
                "full_name": "user/minimal-repo",
                "html_url": "https://github.com/user/minimal-repo",
                "clone_url": "https://github.com/user/minimal-repo.git",
                "ssh_url": "git@github.com:user/minimal-repo.git",
                "private": False,
            }
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            await github_create_repo(
                name="minimal-repo",
                has_issues=False,
                has_projects=False,
                has_wiki=False,
            )

            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            assert payload["has_issues"] is False
            assert payload["has_projects"] is False
            assert payload["has_wiki"] is False
