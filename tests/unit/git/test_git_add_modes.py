"""Regression tests for git_add update_only/patterns reporting (issue #222).

update_only and patterns used to derive their report from the TOTAL staged
set (`git diff --cached --name-only`) rather than the delta this call
actually staged. That both under/over-counts when something was already
staged before the call, and — for patterns — can report SUCCESS when the
pattern matched nothing at all, as long as an earlier unrelated file was
already in the index. These tests exercise git_add against a REAL temporary
git repository (no mocked Repo) so the returned message is checked against
the actual index state. See tests/unit/git/test_git_add_pathspec.py (#218)
for the precedent this file follows.
"""

import pytest

from mcp_server_git.git.models import GitAdd
from mcp_server_git.git.operations import git_add

pytest.importorskip("git")
from git import Repo  # noqa: E402


def _staged_paths(repo: Repo) -> set:
    """Real staged-file names via git diff --cached, independent of the
    code under test."""
    output = repo.git.diff("--cached", "--name-only")
    return {line.strip() for line in output.split("\n") if line.strip()}


def _init_repo_with_tracked_file(tmp_path, name: str = "a.txt") -> tuple[Repo, object]:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    repo = Repo.init(repo_path)
    (repo_path / name).write_text("v1\n")
    repo.index.add([name])
    repo.index.commit("initial")
    return repo, repo_path


class TestGitAddUpdateOnly:
    def test_stages_tracked_modification_and_not_untracked_file(self, tmp_path):
        # Arrange
        repo, repo_path = _init_repo_with_tracked_file(tmp_path)
        (repo_path / "a.txt").write_text("v2\n")
        (repo_path / "untracked.txt").write_text("new\n")

        # Act
        result = git_add(repo, update_only=True)

        # Assert
        assert result == "✅ Added 1 file(s) to staging area (tracked updates)"
        assert _staged_paths(repo) == {"a.txt"}

    def test_reports_delta_not_total_when_file_already_staged(self, tmp_path):
        """Core bug: a file staged before this call must not inflate the
        count reported by this call."""
        # Arrange
        repo, repo_path = _init_repo_with_tracked_file(tmp_path)
        (repo_path / "b.txt").write_text("v1\n")
        repo.index.add(["b.txt"])
        repo.index.commit("add b")

        (repo_path / "b.txt").write_text("v2\n")
        repo.git.add("b.txt")  # pre-stage b.txt before the call under test

        (repo_path / "a.txt").write_text("v2\n")

        # Act
        result = git_add(repo, update_only=True)

        # Assert — only a.txt is newly staged by this call
        assert result == "✅ Added 1 file(s) to staging area (tracked updates)"
        assert _staged_paths(repo) == {"a.txt", "b.txt"}


class TestGitAddPatterns:
    def test_stages_matching_files_and_lists_files_not_patterns(self, tmp_path):
        # Arrange
        repo, repo_path = _init_repo_with_tracked_file(tmp_path, "keep.txt")
        (repo_path / "one.py").write_text("x\n")
        (repo_path / "two.py").write_text("x\n")

        # Act
        result = git_add(repo, patterns=["*.py"])

        # Assert — count and list both describe the actual staged files
        assert result.startswith("✅ Added 2 file(s) to staging area:")
        assert "one.py" in result
        assert "two.py" in result
        assert "matching *.py" in result
        assert _staged_paths(repo) == {"one.py", "two.py"}

    def test_no_delta_while_another_file_already_staged_reports_warning(self, tmp_path):
        """False-success bug: a pattern that stages nothing NEW must warn
        even if an unrelated file is already staged from before the call.

        `keep.txt` is committed and unchanged, so `git add keep.txt`
        succeeds without error but changes nothing in the index — the old
        code reported SUCCESS here because the pre-existing staged file
        made the TOTAL staged set non-empty.
        """
        # Arrange
        repo, repo_path = _init_repo_with_tracked_file(tmp_path, "keep.txt")
        (repo_path / "already_staged.txt").write_text("new\n")
        repo.git.add("already_staged.txt")  # pre-stage before the call

        # Act
        result = git_add(repo, patterns=["keep.txt"])

        # Assert
        assert result == "⚠️ No files matched patterns: keep.txt"
        # Nothing new staged by this call; pre-existing staged file untouched
        assert _staged_paths(repo) == {"already_staged.txt"}

    def test_rejects_shell_metacharacters(self, tmp_path):
        # Arrange
        repo, _ = _init_repo_with_tracked_file(tmp_path)

        # Act
        result = git_add(repo, patterns=["*.py; rm -rf /"])

        # Assert
        assert "❌ Invalid characters detected in pattern:" in result
        assert _staged_paths(repo) == set()


class TestGitAddModeValidation:
    def test_files_and_update_only_together_is_rejected(self, tmp_path):
        # Arrange
        repo, _ = _init_repo_with_tracked_file(tmp_path)

        # Act
        result = git_add(repo, files=["a.txt"], update_only=True)

        # Assert
        assert "❌ Conflicting parameters: files, update_only" in result
        assert _staged_paths(repo) == set()

    def test_no_mode_specified_returns_no_files_error(self, tmp_path):
        # Arrange
        repo, _ = _init_repo_with_tracked_file(tmp_path)

        # Act
        result = git_add(repo)

        # Assert
        assert (
            result == "❌ No files specified. Use files, update_only, or "
            "patterns parameter."
        )
        assert _staged_paths(repo) == set()


class TestGitAddSchema:
    def test_files_is_optional_so_update_only_alone_is_callable(self):
        schema = GitAdd.model_json_schema()
        assert schema.get("required") == ["repo_path"]
