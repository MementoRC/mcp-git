"""Regression tests for git_update_index / git_ls_files (issue #236).

mcp-git had no way to set a file's executable bit in the git INDEX, and no
way to read the index mode back either. Agent-authored shell scripts land
100644 and fail at runtime with "Permission denied / status 126". These
tests exercise both tools against a REAL temporary git repository (no
mocked Repo) so the index state is checked independently of the code under
test, following the convention in tests/unit/git/test_git_add_modes.py.

The core regression (test 3 below) is that a plain working-tree chmod is
silently dropped when core.filemode=false, whereas `git update-index
--chmod` records the mode regardless -- this is why the issue asks for the
plumbing command specifically, not os.chmod.
"""

import pytest

from mcp_server_git.git.operations import git_ls_files, git_update_index

pytest.importorskip("git")
from git import Repo  # noqa: E402


def _mode_of(repo: Repo, path: str) -> str:
    """Real index mode for *path* via `git ls-files -s`, independent of the
    code under test."""
    output = repo.git.ls_files("-s", "--", path)
    # Format: "<mode> <oid> <stage>\t<path>"
    return output.split()[0]


def _init_repo_with_tracked_file(
    tmp_path, name: str = "script.sh"
) -> tuple[Repo, object]:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    repo = Repo.init(repo_path)
    (repo_path / name).write_text("#!/bin/sh\necho hi\n")
    repo.index.add([name])
    repo.index.commit("initial")
    return repo, repo_path


class TestGitUpdateIndexChmod:
    def test_sets_executable_bit_when_file_is_tracked_100644(self, tmp_path):
        # Arrange
        repo, _ = _init_repo_with_tracked_file(tmp_path)
        assert _mode_of(repo, "script.sh") == "100644"

        # Act
        result = git_update_index(repo, files=["script.sh"], chmod="+x")

        # Assert
        assert result.startswith("✅ ")
        assert _mode_of(repo, "script.sh") == "100755"

    def test_clears_executable_bit_when_file_is_tracked_100755(self, tmp_path):
        # Arrange
        repo, _ = _init_repo_with_tracked_file(tmp_path)
        repo.git.update_index("--chmod=+x", "--", "script.sh")
        assert _mode_of(repo, "script.sh") == "100755"

        # Act
        result = git_update_index(repo, files=["script.sh"], chmod="-x")

        # Assert
        assert result.startswith("✅ ")
        assert _mode_of(repo, "script.sh") == "100644"

    def test_sets_executable_bit_when_core_filemode_is_false(self, tmp_path):
        """Core regression: a plain working-tree chmod is silently dropped
        when core.filemode=false. --chmod must still flip the index mode."""
        # Arrange
        repo, _ = _init_repo_with_tracked_file(tmp_path)
        repo.git.config("core.filemode", "false")
        assert _mode_of(repo, "script.sh") == "100644"

        # Act
        result = git_update_index(repo, files=["script.sh"], chmod="+x")

        # Assert
        assert result.startswith("✅ ")
        assert _mode_of(repo, "script.sh") == "100755"

    def test_raises_no_exception_and_names_path_when_file_is_untracked(self, tmp_path):
        # Arrange
        repo, repo_path = _init_repo_with_tracked_file(tmp_path)
        (repo_path / "untracked.sh").write_text("#!/bin/sh\n")

        # Act
        result = git_update_index(repo, files=["untracked.sh"], chmod="+x")

        # Assert
        assert result.startswith("❌ ")
        assert "untracked.sh" in result

    def test_returns_error_without_raising_when_files_list_is_empty(self, tmp_path):
        # Arrange
        repo, _ = _init_repo_with_tracked_file(tmp_path)

        # Act
        result = git_update_index(repo, files=[], chmod="+x")

        # Assert
        assert result.startswith("❌ ")


class TestGitLsFilesStage:
    def test_surfaces_index_mode_when_stage_is_true(self, tmp_path):
        # Arrange
        repo, _ = _init_repo_with_tracked_file(tmp_path)
        repo.git.update_index("--chmod=+x", "--", "script.sh")

        # Act
        result = git_ls_files(repo, files=["script.sh"], stage=True)

        # Assert
        assert "100755" in result

    def test_does_not_surface_index_mode_when_stage_is_false(self, tmp_path):
        # Arrange
        repo, _ = _init_repo_with_tracked_file(tmp_path)
        repo.git.update_index("--chmod=+x", "--", "script.sh")

        # Act
        result = git_ls_files(repo, files=["script.sh"], stage=False)

        # Assert
        assert "100755" not in result
        assert "script.sh" in result

    def test_shows_each_own_mode_when_listing_mixed_permissions_in_one_call(
        self, tmp_path
    ):
        """Per-item rendering bug guard: a test with only one kind of item
        in the listing would hide a bug where every path gets the same
        (first or last) mode."""
        # Arrange
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        (repo_path / "dir").mkdir()
        repo = Repo.init(repo_path)
        (repo_path / "dir" / "exec.sh").write_text("#!/bin/sh\necho hi\n")
        (repo_path / "dir" / "plain.txt").write_text("just text\n")
        repo.index.add(["dir/exec.sh", "dir/plain.txt"])
        repo.index.commit("initial")
        repo.git.update_index("--chmod=+x", "--", "dir/exec.sh")
        assert _mode_of(repo, "dir/exec.sh") == "100755"
        assert _mode_of(repo, "dir/plain.txt") == "100644"

        # Act
        result = git_ls_files(repo, files=["dir"], stage=True)

        # Assert -- each path is shown with its OWN mode, not a shared one
        lines = {line.strip() for line in result.splitlines() if line.strip()}
        assert any("100755" in line and "dir/exec.sh" in line for line in lines)
        assert any("100644" in line and "dir/plain.txt" in line for line in lines)

    def test_returns_empty_result_message_when_nothing_matches(self, tmp_path):
        # Arrange
        repo, _ = _init_repo_with_tracked_file(tmp_path)

        # Act
        result = git_ls_files(repo, files=["nonexistent_dir"], stage=False)

        # Assert
        assert result.startswith("⚠️ ") or result.startswith("✅ ")
        assert "no" in result.lower() or "nothing" in result.lower()
