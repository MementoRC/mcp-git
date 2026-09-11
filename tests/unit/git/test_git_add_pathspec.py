"""Regression tests for git_add pathspec reporting (issue #218).

git_add used to compare the literal input pathspec strings against the
list of staged filenames to decide what to report. That works for an
explicit file list but silently fails for "." or a directory pathspec,
since neither ever equals a staged filename — even though the underlying
`git add` staged everything correctly. These tests exercise git_add
against a REAL temporary git repository (no mocked Repo) so the returned
message is checked against the actual index state, not a mock's
expectations. See issue #214 for the precedent of a fully-mocked suite
passing against a 100%-broken tool.
"""

import pytest

from mcp_server_git.git.operations import git_add

pytest.importorskip("git")
from git import Repo  # noqa: E402


def _staged_paths(repo: Repo) -> set:
    """Real staged-file names via git diff --cached, independent of the
    code under test."""
    output = repo.git.diff("--cached", "--name-only")
    return {line.strip() for line in output.split("\n") if line.strip()}


class TestGitAddPathspecReporting:
    def test_returns_success_with_dot_pathspec_when_tracked_files_modified(
        self, tmp_path
    ):
        # Arrange: a real repo with 3 tracked, modified files
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        repo = Repo.init(repo_path)
        (repo_path / "a.txt").write_text("v1\n")
        (repo_path / "b.txt").write_text("v1\n")
        sub = repo_path / "sub"
        sub.mkdir()
        (sub / "c.txt").write_text("v1\n")
        repo.index.add(["a.txt", "b.txt", "sub/c.txt"])
        repo.index.commit("initial")

        (repo_path / "a.txt").write_text("v2\n")
        (repo_path / "b.txt").write_text("v2\n")
        (sub / "c.txt").write_text("v2\n")

        # Act
        result = git_add(repo, files=["."])

        # Assert — message reflects the actual index state
        assert result.startswith("✅ Added 3 file(s) to staging area:")
        staged = _staged_paths(repo)
        assert staged == {"a.txt", "b.txt", "sub/c.txt"}

    def test_explicit_file_list_still_reports_correctly(self, tmp_path):
        # Arrange
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        repo = Repo.init(repo_path)
        (repo_path / "a.txt").write_text("v1\n")
        (repo_path / "b.txt").write_text("v1\n")
        sub = repo_path / "sub"
        sub.mkdir()
        (sub / "c.txt").write_text("v1\n")
        repo.index.add(["a.txt", "b.txt", "sub/c.txt"])
        repo.index.commit("initial")

        (repo_path / "a.txt").write_text("v2\n")
        (repo_path / "b.txt").write_text("v2\n")
        (sub / "c.txt").write_text("v2\n")

        # Act
        result = git_add(repo, files=["a.txt", "b.txt", "sub/c.txt"])

        # Assert
        assert result.startswith("✅ Added 3 file(s) to staging area:")
        assert _staged_paths(repo) == {"a.txt", "b.txt", "sub/c.txt"}

    def test_returns_success_with_dot_pathspec_for_new_untracked_file(self, tmp_path):
        # Arrange: a repo with an initial commit and one new untracked file
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        repo = Repo.init(repo_path)
        (repo_path / "README.md").write_text("init\n")
        repo.index.add(["README.md"])
        repo.index.commit("initial")

        (repo_path / "new_file.txt").write_text("brand new\n")

        # Act
        result = git_add(repo, files=["."])

        # Assert
        assert result.startswith("✅ Added 1 file(s) to staging area:")
        assert "new_file.txt" in result
        assert _staged_paths(repo) == {"new_file.txt"}

    def test_returns_success_with_dot_pathspec_for_mixed_modified_and_untracked(
        self, tmp_path
    ):
        # Arrange
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        repo = Repo.init(repo_path)
        (repo_path / "a.txt").write_text("v1\n")
        repo.index.add(["a.txt"])
        repo.index.commit("initial")

        (repo_path / "a.txt").write_text("v2\n")
        (repo_path / "new_file.txt").write_text("brand new\n")

        # Act
        result = git_add(repo, files=["."])

        # Assert
        assert result.startswith("✅ Added 2 file(s) to staging area:")
        assert _staged_paths(repo) == {"a.txt", "new_file.txt"}

    def test_dot_pathspec_on_clean_tree_reports_no_changes_and_stages_nothing(
        self, tmp_path
    ):
        # Arrange: a clean repo — the true negative case
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        repo = Repo.init(repo_path)
        (repo_path / "a.txt").write_text("v1\n")
        repo.index.add(["a.txt"])
        repo.index.commit("initial")

        # Act
        result = git_add(repo, files=["."])

        # Assert
        assert result == "⚠️ No changes detected in specified files"
        assert _staged_paths(repo) == set()

    def test_already_staged_unchanged_file_is_not_double_counted(self, tmp_path):
        """A file staged before the call, with content unchanged since,
        must not appear as newly staged."""
        # Arrange
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        repo = Repo.init(repo_path)
        (repo_path / "a.txt").write_text("v1\n")
        repo.index.add(["a.txt"])
        repo.index.commit("initial")

        (repo_path / "a.txt").write_text("v2\n")
        (repo_path / "b.txt").write_text("new\n")
        repo.git.add("a.txt")  # pre-stage a.txt before the call under test

        # Act
        result = git_add(repo, files=["."])

        # Assert — only b.txt is newly staged by this call
        assert result.startswith("✅ Added 1 file(s) to staging area:")
        assert "b.txt" in result
        assert "a.txt" not in result
        assert _staged_paths(repo) == {"a.txt", "b.txt"}

    def test_dot_pathspec_with_no_initial_commit_handles_missing_head(self, tmp_path):
        """A repo with no HEAD yet: `git diff --cached` has nothing to
        diff against. git_add must not raise and must report accurately."""
        # Arrange
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        repo = Repo.init(repo_path)
        (repo_path / "a.txt").write_text("v1\n")
        (repo_path / "b.txt").write_text("v1\n")

        # Act
        result = git_add(repo, files=["."])

        # Assert
        assert result.startswith("✅ Added 2 file(s) to staging area:")
        assert _staged_paths(repo) == {"a.txt", "b.txt"}

    def test_large_file_list_is_capped_with_and_n_more(self, tmp_path):
        # Arrange: 25 new tracked-directory files staged via "."
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        repo = Repo.init(repo_path)
        (repo_path / "README.md").write_text("init\n")
        repo.index.add(["README.md"])
        repo.index.commit("initial")

        for i in range(25):
            (repo_path / f"file_{i:02d}.txt").write_text("x\n")

        # Act
        result = git_add(repo, files=["."])

        # Assert
        assert result.startswith("✅ Added 25 file(s) to staging area:")
        assert "(and 5 more)" in result
        assert len(_staged_paths(repo)) == 25
