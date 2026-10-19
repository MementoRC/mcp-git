"""git_add force and git_update_index add/remove (issue #312).

Real temporary repositories with a conda-forge style `*` .gitignore.
"""

from pathlib import Path

import pytest

pytest.importorskip("git")
from git import Repo  # noqa: E402

from mcp_server_git.git.operations import git_add, git_update_index  # noqa: E402
from mcp_server_git.utils.tool_failure import ToolFailure  # noqa: E402


@pytest.fixture
def feedstock(tmp_path):
    repo = Repo.init(tmp_path)
    (tmp_path / ".gitignore").write_text("*\n!.gitignore\n")
    repo.git.add("-f", ".gitignore")
    repo.index.commit("init")
    return repo


def _write_ignored(repo, name="x.sh"):
    path = Path(repo.working_dir) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    return name


def _staged(repo) -> str:
    return repo.git.ls_files("-s")


def test_git_add_returns_staged_when_force_true_and_path_ignored(feedstock):
    name = _write_ignored(feedstock, ".github/scripts/x.sh")

    result = git_add(feedstock, files=[name], force=True)

    assert result.startswith("✅")
    assert name in _staged(feedstock)


def test_git_add_returns_failure_mentioning_force_when_path_ignored(feedstock):
    name = _write_ignored(feedstock)

    result = git_add(feedstock, files=[name])

    assert isinstance(result, ToolFailure)
    assert "force=True" in result
    assert name not in _staged(feedstock)


def test_git_add_returns_staged_when_force_true_with_patterns(feedstock):
    name = _write_ignored(feedstock)

    result = git_add(feedstock, patterns=["*.sh"], force=True)

    assert result.startswith("✅")
    assert name in _staged(feedstock)


def test_git_update_index_returns_success_when_add_true_on_ignored_file(feedstock):
    name = _write_ignored(feedstock)

    result = git_update_index(feedstock, files=[name], add=True)

    assert result.startswith("✅")
    assert name in _staged(feedstock)


def test_git_update_index_returns_success_when_chmod_only(feedstock):
    name = _write_ignored(feedstock)
    feedstock.git.add("-f", name)

    result = git_update_index(feedstock, files=[name], chmod="+x")

    assert result.startswith("✅")
    assert _staged(feedstock).split("\n")[-1].startswith("100755")


def test_git_update_index_returns_mode_755_when_add_and_chmod_combined(feedstock):
    name = _write_ignored(feedstock)

    result = git_update_index(feedstock, files=[name], add=True, chmod="+x")

    assert result.startswith("✅")
    line = [x for x in _staged(feedstock).split("\n") if name in x][0]
    assert line.startswith("100755")


def test_git_update_index_returns_success_when_remove_drops_deleted_file(feedstock):
    name = _write_ignored(feedstock)
    feedstock.git.add("-f", name)
    (Path(feedstock.working_dir) / name).unlink()

    result = git_update_index(feedstock, files=[name], remove=True)

    assert result.startswith("✅")
    assert name not in _staged(feedstock)


def test_git_update_index_returns_failure_when_no_operation_given(feedstock):
    name = _write_ignored(feedstock)

    result = git_update_index(feedstock, files=[name])

    assert isinstance(result, ToolFailure)
    assert "chmod, add, remove" in result


def test_git_update_index_returns_failure_when_chmod_invalid(feedstock):
    name = _write_ignored(feedstock)

    result = git_update_index(feedstock, files=[name], chmod="777", add=True)

    assert isinstance(result, ToolFailure)
