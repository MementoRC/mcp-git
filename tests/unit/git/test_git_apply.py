"""git_apply: apply a unified-diff patch to the working tree (#334).

Real temporary repositories throughout; no mocks at the git boundary.
"""

from pathlib import Path

import pytest

from mcp_server_git.git.operations import git_apply

pytest.importorskip("git")
from git import Repo  # noqa: E402

_PATCH = (
    "diff --git a/base.txt b/base.txt\n"
    "--- a/base.txt\n"
    "+++ b/base.txt\n"
    "@@ -1 +1,2 @@\n"
    " base\n"
    "+added\n"
)
_STALE = _PATCH.replace(" base\n", " other\n")
_NEW_FILE = (
    "diff --git a/new.txt b/new.txt\n"
    "new file mode 100644\n"
    "--- /dev/null\n"
    "+++ b/new.txt\n"
    "@@ -0,0 +1 @@\n"
    "+hello\n"
)


@pytest.fixture
def repo(tmp_path) -> Repo:
    path = tmp_path / "repo"
    path.mkdir()
    repo = Repo.init(path, initial_branch="main")
    with repo.config_writer() as config:
        config.set_value("commit", "gpgsign", "false")
        config.set_value("user", "name", "Test User")
        config.set_value("user", "email", "test@example.com")
    (path / "base.txt").write_text("base\n")
    repo.git.add("base.txt")  # real git add keeps the index stat data fresh
    repo.git.commit("-m", "initial")
    return repo


def _base(repo: Repo) -> str:
    return (Path(repo.working_dir) / "base.txt").read_text()


def _patch_file(tmp_path, text: str) -> str:
    path = tmp_path / "change.patch"
    path.write_text(text)
    return str(path)


class TestGitApply:
    def test_git_apply_returns_success_when_patch_path_is_clean(self, repo, tmp_path):
        result = git_apply(repo, patch_path=_patch_file(tmp_path, _PATCH))

        assert result.startswith("✅ Applied patch to 1 file(s)")
        assert "  +1 -0 base.txt" in result
        assert _base(repo) == "base\nadded\n"
        assert "base.txt" in repo.git.diff("--name-only")

    def test_git_apply_applies_inline_text_when_no_file_on_disk(self, repo):
        result = git_apply(repo, patch_text=_PATCH.rstrip("\n"))

        assert result.startswith("✅ Applied patch to 1 file(s)")
        assert _base(repo) == "base\nadded\n"
        assert not list(Path(repo.working_dir).glob("*.patch"))

    def test_git_apply_reports_counts_when_check_on_clean_patch(self, repo):
        result = git_apply(repo, patch_text=_PATCH, check=True)

        assert result.startswith("✅ Patch applies cleanly (check only")
        assert "1 file(s)" in result
        assert "  +1 -0 base.txt" in result
        assert _base(repo) == "base\n"

    def test_git_apply_reports_failing_file_when_check_on_stale_patch(self, repo):
        result = git_apply(repo, patch_text=_STALE, check=True)

        assert result.startswith("❌ Patch does not apply")
        assert "base.txt" in result
        assert _base(repo) == "base\n"

    def test_git_apply_fails_and_leaves_tree_when_patch_is_stale(self, repo):
        result = git_apply(repo, patch_text=_STALE)

        assert result.startswith("❌ Patch does not apply")
        assert _base(repo) == "base\n"
        assert not repo.git.status("--porcelain")

    def test_git_apply_stages_change_when_index_true(self, repo):
        result = git_apply(repo, patch_text=_PATCH, index=True)

        assert "(index updated)" in result
        assert repo.git.diff("--cached", "--name-only") == "base.txt"

    def test_git_apply_leaves_index_untouched_when_index_false(self, repo):
        git_apply(repo, patch_text=_PATCH)

        assert repo.git.diff("--cached", "--name-only") == ""

    def test_git_apply_undoes_patch_when_reverse_true(self, repo):
        git_apply(repo, patch_text=_PATCH)

        result = git_apply(repo, patch_text=_PATCH, reverse=True)

        assert "(reversed)" in result
        assert _base(repo) == "base\n"

    def test_git_apply_fails_when_both_patch_args_given(self, repo, tmp_path):
        result = git_apply(
            repo, patch_path=_patch_file(tmp_path, _PATCH), patch_text=_PATCH
        )

        assert result.startswith("❌")
        assert _base(repo) == "base\n"

    def test_git_apply_fails_when_no_patch_arg_given(self, repo):
        assert git_apply(repo).startswith("❌")

    def test_git_apply_fails_when_patch_path_missing(self, repo, tmp_path):
        result = git_apply(repo, patch_path=str(tmp_path / "nope.patch"))

        assert result.startswith("❌")
        assert "not found" in result

    def test_git_apply_fails_when_patch_path_is_directory(self, repo, tmp_path):
        assert git_apply(repo, patch_path=str(tmp_path)).startswith("❌")

    def test_git_apply_rejects_option_like_path_when_path_starts_with_dash(self, repo):
        result = git_apply(repo, patch_path="--stat")

        assert result.startswith("❌")
        assert "'-'" in result

    def test_git_apply_resolves_relative_path_when_against_working_tree(self, repo):
        (Path(repo.working_dir) / "rel.patch").write_text(_PATCH)

        result = git_apply(repo, patch_path="rel.patch")

        assert result.startswith("✅ Applied")

    def test_git_apply_creates_file_when_patch_adds_new_file(self, repo):
        result = git_apply(repo, patch_text=_NEW_FILE)

        assert result.startswith("✅ Applied patch to 1 file(s)")
        assert "  +1 -0 new.txt" in result
        assert (Path(repo.working_dir) / "new.txt").read_text() == "hello\n"
