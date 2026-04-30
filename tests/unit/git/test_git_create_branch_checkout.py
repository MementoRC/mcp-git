"""
Unit tests for git_create_branch checkout behaviour (issue #162).

Verifies that HEAD switches on checkout=True (default) and stays put
on checkout=False. Uses a real in-process git repo via tempfile.
"""

import tempfile
from pathlib import Path

import pytest

from mcp_server_git.git.operations import git_create_branch
from mcp_server_git.utils.git_import import Repo


@pytest.fixture()
def tmp_repo():
    """Real git repo with one initial commit; configures dummy identity."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Repo.init(tmpdir)
        with repo.config_writer() as cfg:
            cfg.set_value("user", "name", "Test User")
            cfg.set_value("user", "email", "test@example.com")

        readme = Path(tmpdir) / "README.md"
        readme.write_text("init")
        repo.index.add(["README.md"])
        repo.index.commit("Initial commit")
        yield repo


def test_git_create_branch_default_checkout_switches_head(tmp_repo: Repo) -> None:
    result = git_create_branch(tmp_repo, "feature/new")

    assert tmp_repo.active_branch.name == "feature/new"
    assert "Created and switched" in result


def test_git_create_branch_checkout_false_preserves_head(tmp_repo: Repo) -> None:
    original_branch = tmp_repo.active_branch.name

    result = git_create_branch(tmp_repo, "feature/keep", checkout=False)

    assert tmp_repo.active_branch.name == original_branch
    branch_names = [h.name for h in tmp_repo.heads]
    assert "feature/keep" in branch_names
    assert "HEAD unchanged" in result


def test_git_create_branch_with_base_branch_points_at_base_commit(
    tmp_repo: Repo,
) -> None:
    tmp_repo.create_head("stable")
    stable_commit = tmp_repo.heads["stable"].commit

    result = git_create_branch(tmp_repo, "topic", base_branch="stable")

    assert tmp_repo.active_branch.name == "topic"
    assert tmp_repo.active_branch.commit == stable_commit
    assert "Created and switched" in result


def test_git_create_branch_already_exists_returns_error(tmp_repo: Repo) -> None:
    original_branch = tmp_repo.active_branch.name
    tmp_repo.create_head("existing")

    result = git_create_branch(tmp_repo, "existing")

    assert result.startswith("❌")
    assert "already exists" in result
    assert tmp_repo.active_branch.name == original_branch


def test_git_create_branch_checkout_false_does_not_switch_even_on_first_branch(
    tmp_repo: Repo,
) -> None:
    """checkout=False must not switch HEAD even when it is the first extra branch."""
    original_branch = tmp_repo.active_branch.name

    git_create_branch(tmp_repo, "side", checkout=False)
    git_create_branch(tmp_repo, "side2", checkout=False)

    assert tmp_repo.active_branch.name == original_branch
