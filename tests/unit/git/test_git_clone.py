"""Tests for git_clone operation"""

import shutil
import tempfile
from pathlib import Path

import pytest

from src.mcp_server_git.utils.git_import import Repo


def _make_source_repo(
    path: Path, num_commits: int = 1, branch: str | None = None
) -> Repo:
    """Helper: initialise a bare-ish source repo with commits for use as a local remote."""
    repo = Repo.init(str(path))

    # Configure a minimal identity so commits work without system config
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Test User")
        cw.set_value("user", "email", "test@example.com")

    # Write and commit files
    for i in range(num_commits):
        dummy = path / f"file_{i}.txt"
        dummy.write_text(f"content {i}")
        repo.index.add([str(dummy)])
        repo.index.commit(f"commit {i}")

    if branch is not None:
        repo.create_head(branch)

    return repo


class TestGitClone:
    """Test git_clone function"""

    def setup_method(self):
        self._tmpdirs: list[str] = []

    def teardown_method(self):
        for d in self._tmpdirs:
            shutil.rmtree(d, ignore_errors=True)

    def _tmpdir(self) -> Path:
        d = tempfile.mkdtemp()
        self._tmpdirs.append(d)
        return Path(d)

    # ------------------------------------------------------------------
    # Happy-path tests
    # ------------------------------------------------------------------

    def test_clone_happy_path(self):
        """Clone a local source repo into a fresh empty target and verify success."""
        from src.mcp_server_git.git.operations import git_clone

        src = self._tmpdir()
        src_repo = _make_source_repo(src)
        expected_sha = src_repo.head.commit.hexsha

        target = self._tmpdir() / "cloned"

        result = git_clone(str(src), str(target))

        assert "✅" in result
        assert str(src) in result
        assert str(target) in result

        cloned_repo = Repo(str(target))
        assert cloned_repo.head.commit.hexsha == expected_sha

    def test_clone_with_branch(self):
        """Clone with branch= and verify active branch in cloned repo."""
        from src.mcp_server_git.git.operations import git_clone

        src = self._tmpdir()
        _make_source_repo(src, num_commits=1, branch="feature-x")

        target = self._tmpdir() / "cloned"

        result = git_clone(str(src), str(target), branch="feature-x")

        assert "✅" in result

        cloned_repo = Repo(str(target))
        assert cloned_repo.active_branch.name == "feature-x"

    def test_clone_with_depth(self):
        """Clone with depth=1 from a 3-commit repo and verify shallow history."""
        from src.mcp_server_git.git.operations import git_clone

        src = self._tmpdir()
        _make_source_repo(src, num_commits=3)

        target = self._tmpdir() / "cloned"

        result = git_clone(f"file://{src}", str(target), depth=1)

        assert "✅" in result

        cloned_repo = Repo(str(target))
        commit_count = cloned_repo.git.rev_list("--count", "HEAD")
        assert commit_count.strip() == "1"

    def test_clone_single_branch_flag(self):
        """Clone with single_branch=True succeeds."""
        from src.mcp_server_git.git.operations import git_clone

        src = self._tmpdir()
        _make_source_repo(src)

        target = self._tmpdir() / "cloned"

        result = git_clone(str(src), str(target), single_branch=True)

        assert "✅" in result

    # ------------------------------------------------------------------
    # Validation / rejection tests
    # ------------------------------------------------------------------

    def test_clone_rejects_existing_nonempty_target(self):
        """Raise ValueError when target directory already contains files."""
        from src.mcp_server_git.git.operations import git_clone

        src = self._tmpdir()
        _make_source_repo(src)

        target = self._tmpdir() / "nonempty"
        target.mkdir()
        (target / "existing.txt").write_text("not empty")

        with pytest.raises(ValueError, match="not empty"):
            git_clone(str(src), str(target))

    def test_clone_rejects_missing_parent(self):
        """Raise ValueError when the parent of target_path does not exist."""
        from src.mcp_server_git.git.operations import git_clone

        src = self._tmpdir()
        _make_source_repo(src)

        nonexistent_parent = self._tmpdir() / "ghost" / "cloned"

        with pytest.raises(ValueError, match="Parent directory does not exist"):
            git_clone(str(src), str(nonexistent_parent))

    # ------------------------------------------------------------------
    # Error-path tests
    # ------------------------------------------------------------------

    def test_clone_bad_url_returns_error_message(self):
        """Return a '❌' string when repo_url does not point to a valid repo."""
        from src.mcp_server_git.git.operations import git_clone

        target = self._tmpdir() / "cloned"

        # A path that does not exist is not a valid git repo; GitPython raises
        # GitCommandError which the implementation catches and returns as "❌ Clone failed: ..."
        bad_url = "/tmp/this_path_does_not_exist_at_all_xyz123"

        result = git_clone(bad_url, str(target))

        assert "❌" in result
