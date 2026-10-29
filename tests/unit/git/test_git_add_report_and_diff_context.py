"""Tests for git_add index-state reporting and diff context_lines (issue #321).

Real temporary repositories, no mocks at the git boundary.
"""

import os

import pytest

from mcp_server_git.git.operations import (
    git_add,
    git_diff,
    git_diff_staged,
    git_diff_unstaged,
)

pytest.importorskip("git")
from git import Repo  # noqa: E402

_BODY = "".join(f"line{i}\n" for i in range(1, 21))
_CHANGED = _BODY.replace("line10\n", "CHANGED\n")


def _init_repo(tmp_path, names=("a.txt",)):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    repo = Repo.init(repo_path)
    for name in names:
        (repo_path / name).write_text(_BODY)
    repo.index.add(list(names))
    repo.index.commit("initial")
    return repo, repo_path


def _hunk_body_lines(diff: str) -> list[str]:
    """Lines inside hunks that are neither headers nor +/- changes."""
    in_hunk = False
    context = []
    for line in diff.split("\n"):
        if line.startswith("@@"):
            in_hunk = True
        elif in_hunk and line.startswith(" "):
            context.append(line)
    return context


class TestGitAddReportsIndexState:
    def test_git_add_reports_already_staged_when_files_readded_unchanged(
        self, tmp_path
    ):
        repo, repo_path = _init_repo(tmp_path, ("a.txt", "b.txt"))
        (repo_path / "a.txt").write_text(_CHANGED)
        (repo_path / "b.txt").write_text(_CHANGED)
        git_add(repo, files=["a.txt", "b.txt"])

        result = git_add(repo, files=["a.txt", "b.txt"])

        assert result.startswith("✅ Already staged; index matches working tree")
        assert "a.txt" in result and "b.txt" in result
        assert "No changes detected" not in result

    def test_git_add_warns_when_requested_path_has_no_changes_and_nothing_staged(
        self, tmp_path
    ):
        repo, _ = _init_repo(tmp_path)

        result = git_add(repo, files=["a.txt"])

        assert result == "⚠️ No changes detected in specified files"

    def test_git_add_lists_already_staged_when_mixed_with_new_changes(self, tmp_path):
        repo, repo_path = _init_repo(tmp_path, ("a.txt", "b.txt"))
        (repo_path / "a.txt").write_text(_CHANGED)
        git_add(repo, files=["a.txt"])
        (repo_path / "b.txt").write_text(_CHANGED)

        result = git_add(repo, files=["a.txt", "b.txt"])

        assert result.startswith("✅ Added 1 file(s) to staging area: b.txt")
        assert "1 already staged: a.txt" in result

    @pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unsupported")
    def test_git_add_counts_typechanges_when_files_replaced_by_symlinks(self, tmp_path):
        names = ("a.txt", "b.txt", "c.txt", "d.txt")
        repo, repo_path = _init_repo(tmp_path, names)
        (repo_path / "target.txt").write_text("t\n")
        (repo_path / "a.txt").write_text(_CHANGED)
        for name in ("c.txt", "d.txt"):
            (repo_path / name).unlink()
            try:
                os.symlink("target.txt", repo_path / name)
            except OSError:
                pytest.skip("symlink creation not permitted")
        (repo_path / "b.txt").unlink()

        result = git_add(repo, files=list(names) + ["target.txt"])

        assert result.startswith("✅ Added 5 file(s) to staging area:")
        assert "c.txt (typechange)" in result
        assert "d.txt (typechange)" in result
        assert "b.txt (deleted)" in result


class TestDiffContextLines:
    def test_git_diff_unstaged_omits_context_when_context_lines_zero(self, tmp_path):
        repo, repo_path = _init_repo(tmp_path)
        (repo_path / "a.txt").write_text(_CHANGED)

        default = git_diff_unstaged(repo)
        zero = git_diff_unstaged(repo, context_lines=0)

        assert "@@" in zero
        assert _hunk_body_lines(default)
        assert _hunk_body_lines(zero) == []

    def test_git_diff_staged_omits_context_when_context_lines_zero(self, tmp_path):
        repo, repo_path = _init_repo(tmp_path)
        (repo_path / "a.txt").write_text(_CHANGED)
        repo.git.add("a.txt")

        zero = git_diff_staged(repo, context_lines=0)

        assert "@@" in zero
        assert _hunk_body_lines(zero) == []

    def test_git_diff_omits_context_when_context_lines_zero(self, tmp_path):
        repo, repo_path = _init_repo(tmp_path)
        (repo_path / "a.txt").write_text(_CHANGED)

        zero = git_diff(repo, context_lines=0)

        assert "@@" in zero
        assert _hunk_body_lines(zero) == []

    def test_git_diff_staged_widens_context_when_context_lines_large(self, tmp_path):
        repo, repo_path = _init_repo(tmp_path)
        (repo_path / "a.txt").write_text(_CHANGED)
        repo.git.add("a.txt")

        wide = git_diff_staged(repo, context_lines=5)

        assert len(_hunk_body_lines(wide)) == 10

    def test_git_diff_staged_composes_with_paths_and_max_lines_when_context_set(
        self, tmp_path
    ):
        repo, repo_path = _init_repo(tmp_path, ("a.txt", "b.txt"))
        (repo_path / "a.txt").write_text(_CHANGED)
        (repo_path / "b.txt").write_text(_CHANGED)
        repo.git.add("a.txt", "b.txt")

        result = git_diff_staged(repo, context_lines=0, paths=["a.txt"], max_lines=6)

        assert "a.txt" in result
        assert "b.txt" not in result

    def test_git_diff_staged_composes_with_name_only_when_context_set(self, tmp_path):
        repo, repo_path = _init_repo(tmp_path)
        (repo_path / "a.txt").write_text(_CHANGED)
        repo.git.add("a.txt")

        result = git_diff_staged(repo, context_lines=0, name_only=True)

        assert result == "Files with staged changes:\na.txt"

    @pytest.mark.parametrize("func", [git_diff_unstaged, git_diff_staged, git_diff])
    def test_diff_returns_validation_error_when_context_lines_negative(
        self, tmp_path, func
    ):
        repo, _ = _init_repo(tmp_path)

        result = func(repo, context_lines=-1)

        assert "context_lines must be an integer >= 0" in result
