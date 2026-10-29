"""git_merge commit-ish sources / no_commit / no_ff / ff_only and git_pull ff_only (#321).

Real temporary repositories throughout; no mocks at the git boundary.
"""

import pytest

from mcp_server_git.git.operations import git_merge, git_pull

pytest.importorskip("git")
from git import Repo  # noqa: E402


def _commit(repo: Repo, name: str, content: str, msg: str) -> str:
    path = f"{repo.working_dir}/{name}"
    with open(path, "w") as handle:
        handle.write(content)
    repo.index.add([name])
    return repo.index.commit(msg).hexsha


def _init(tmp_path) -> Repo:
    path = tmp_path / "repo"
    path.mkdir()
    repo = Repo.init(path, initial_branch="main")
    repo.config_writer().set_value("commit", "gpgsign", "false").release()
    _commit(repo, "base.txt", "base\n", "initial")
    return repo


def _feature_branch(repo: Repo, name: str = "feature") -> str:
    repo.git.checkout("-b", name)
    sha = _commit(repo, f"{name}.txt", "f\n", f"add {name}")
    repo.git.checkout("main")
    return sha


def _diverge(repo: Repo) -> None:
    _feature_branch(repo)
    _commit(repo, "main.txt", "m\n", "main moves")


class TestGitMergeSource:
    def test_merges_by_sha_when_source_is_commit_hash(self, tmp_path):
        repo = _init(tmp_path)
        sha = _feature_branch(repo)

        result = git_merge(repo, sha[:10])

        assert result.startswith("✅")
        assert (tmp_path / "repo" / "feature.txt").exists()

    def test_merges_by_tag_when_source_is_tag(self, tmp_path):
        repo = _init(tmp_path)
        _feature_branch(repo)
        repo.create_tag("v1", ref="feature")
        repo.git.branch("-D", "feature")

        result = git_merge(repo, source="v1")

        assert result.startswith("✅")
        assert (tmp_path / "repo" / "feature.txt").exists()

    def test_returns_error_when_source_unknown(self, tmp_path):
        repo = _init(tmp_path)

        assert "not found" in git_merge(repo, "nope")

    def test_returns_error_when_source_aliases_differ(self, tmp_path):
        repo = _init(tmp_path)
        _feature_branch(repo)

        result = git_merge(repo, source_branch="feature", source="other")

        assert "differ" in result

    def test_accepts_both_aliases_when_equal(self, tmp_path):
        repo = _init(tmp_path)
        _feature_branch(repo)

        assert git_merge(repo, source_branch="feature", source="feature").startswith(
            "✅"
        )


class TestGitMergeModes:
    def test_leaves_merge_head_and_no_commit_when_no_commit(self, tmp_path):
        repo = _init(tmp_path)
        _diverge(repo)
        head = repo.head.commit.hexsha

        result = git_merge(repo, "feature", no_commit=True)

        assert "staged and uncommitted" in result
        assert repo.head.commit.hexsha == head
        assert (tmp_path / "repo" / ".git" / "MERGE_HEAD").exists()

    def test_stages_without_fast_forward_when_no_commit_on_ff_branch(self, tmp_path):
        repo = _init(tmp_path)
        _feature_branch(repo)
        head = repo.head.commit.hexsha

        git_merge(repo, "feature", no_commit=True)

        assert repo.head.commit.hexsha == head
        assert (tmp_path / "repo" / ".git" / "MERGE_HEAD").exists()

    def test_creates_merge_commit_when_no_ff_on_fast_forwardable_branch(self, tmp_path):
        repo = _init(tmp_path)
        _feature_branch(repo)

        result = git_merge(repo, "feature", no_ff=True, message="merge it")

        assert result.startswith("✅")
        assert len(repo.head.commit.parents) == 2
        assert "UNSIGNED" in result

    def test_fast_forwards_when_ff_only_and_fast_forwardable(self, tmp_path):
        repo = _init(tmp_path)
        sha = _feature_branch(repo)

        result = git_merge(repo, "feature", ff_only=True)

        assert result.startswith("✅")
        assert repo.head.commit.hexsha == sha

    def test_fails_when_ff_only_on_diverged_branches(self, tmp_path):
        repo = _init(tmp_path)
        _diverge(repo)
        head = repo.head.commit.hexsha

        result = git_merge(repo, "feature", ff_only=True)

        assert result.startswith("❌")
        assert repo.head.commit.hexsha == head

    def test_returns_error_when_ff_only_with_no_ff(self, tmp_path):
        repo = _init(tmp_path)
        _feature_branch(repo)

        result = git_merge(repo, "feature", ff_only=True, no_ff=True)

        assert "mutually exclusive" in result

    def test_reports_no_signature_line_when_fast_forward(self, tmp_path):
        repo = _init(tmp_path)
        _feature_branch(repo)

        result = git_merge(repo, "feature")

        assert "GPG" not in result


class TestGitPullFfOnly:
    def _clone_pair(self, tmp_path):
        origin = tmp_path / "origin.git"
        Repo.init(origin, bare=True, initial_branch="main")
        seed = Repo.init(tmp_path / "seed", initial_branch="main")
        seed.config_writer().set_value("commit", "gpgsign", "false").release()
        _commit(seed, "a.txt", "a\n", "seed")
        seed.create_remote("origin", str(origin))
        seed.git.push("origin", "main")
        clone = Repo.clone_from(str(origin), tmp_path / "clone", branch="main")
        clone.config_writer().set_value("commit", "gpgsign", "false").release()
        clone.config_writer().set_value("user", "name", "t").release()
        clone.config_writer().set_value("user", "email", "t@e.x").release()
        return seed, clone

    def test_pulls_when_ff_only_and_fast_forwardable(self, tmp_path):
        seed, clone = self._clone_pair(tmp_path)
        sha = _commit(seed, "b.txt", "b\n", "upstream")
        seed.git.push("origin", "main")

        result = git_pull(clone, "origin", "main", ff_only=True)

        assert result.startswith("✅")
        assert clone.head.commit.hexsha == sha

    def test_fails_when_ff_only_and_local_diverged(self, tmp_path):
        seed, clone = self._clone_pair(tmp_path)
        _commit(seed, "b.txt", "b\n", "upstream")
        seed.git.push("origin", "main")
        local = _commit(clone, "c.txt", "c\n", "local")

        result = git_pull(clone, "origin", "main", ff_only=True)

        assert result.startswith("❌")
        assert clone.head.commit.hexsha == local
