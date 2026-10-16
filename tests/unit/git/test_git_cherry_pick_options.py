"""git_cherry_pick signing and mainline on a real, signing-capable repo (#283)."""

import pytest

from mcp_server_git.git._rebase_ops import git_cherry_pick
from mcp_server_git.utils.tool_failure import ToolFailure, fail


def _commit_file(repo, name, text, message):
    with open(f"{repo.working_dir}/{name}", "w") as handle:
        handle.write(text)
    repo.index.add([name])
    return repo.index.commit(message)


@pytest.fixture
def repo_with_side_commit(signing_repo):
    signing_repo.git.checkout("-b", "side")
    picked = _commit_file(signing_repo, "side.txt", "s\n", "side work")
    signing_repo.git.checkout("main")
    return signing_repo, picked.hexsha


def test_git_cherry_pick_signs_commit_when_signing_enforced(repo_with_side_commit):
    repo, sha = repo_with_side_commit

    result = git_cherry_pick(repo, sha)

    assert result.startswith("✅"), result
    assert "gpgsig" in repo.git.cat_file("-p", "HEAD")
    assert repo.head.commit.message.strip() == "side work"


def test_git_cherry_pick_signs_commit_when_gpg_sign_false_but_enforced(
    repo_with_side_commit,
):
    repo, sha = repo_with_side_commit

    git_cherry_pick(repo, sha, gpg_sign=False)

    assert "gpgsig" in repo.git.cat_file("-p", "HEAD")


def test_git_cherry_pick_fails_when_no_signing_key_resolvable(
    repo_with_side_commit, monkeypatch
):
    repo, sha = repo_with_side_commit
    unresolved = (None, fail("❌ Could not determine GPG signing key"))
    monkeypatch.setattr(
        "mcp_server_git.git._rebase_ops.resolve_gpg_key", lambda *_: unresolved
    )
    before = repo.head.commit.hexsha

    result = git_cherry_pick(repo, sha)

    assert isinstance(result, ToolFailure)
    assert "GPG" in result
    assert repo.head.commit.hexsha == before


def test_git_cherry_pick_stages_without_commit_when_no_commit_true(
    repo_with_side_commit,
):
    repo, sha = repo_with_side_commit
    before = repo.head.commit.hexsha

    result = git_cherry_pick(repo, sha, no_commit=True)

    assert result.startswith("✅")
    assert repo.head.commit.hexsha == before


def test_git_cherry_pick_fails_when_merge_commit_picked_without_mainline(
    signing_repo,
):
    repo = signing_repo
    repo.git.checkout("-b", "topic")
    _commit_file(repo, "t.txt", "t\n", "topic work")
    repo.git.checkout("main")
    _commit_file(repo, "m.txt", "m\n", "main work")
    repo.git.merge("--no-ff", "topic", "-m", "merge topic")
    merge_sha = repo.head.commit.hexsha
    repo.git.checkout("-b", "target", "HEAD~1")

    result = git_cherry_pick(repo, merge_sha)

    assert isinstance(result, ToolFailure)
    assert "no -m option" in result


def test_git_cherry_pick_applies_merge_commit_when_mainline_given(signing_repo):
    repo = signing_repo
    base = repo.head.commit.hexsha
    repo.git.checkout("-b", "topic")
    _commit_file(repo, "t.txt", "t\n", "topic work")
    repo.git.checkout("main")
    _commit_file(repo, "m.txt", "m\n", "main work")
    repo.git.merge("--no-ff", "topic", "-m", "merge topic")
    merge_sha = repo.head.commit.hexsha
    repo.git.checkout("-b", "target", base)

    result = git_cherry_pick(repo, merge_sha, mainline=1)

    assert result.startswith("✅"), result
    assert "gpgsig" in repo.git.cat_file("-p", "HEAD")


def test_git_cherry_pick_fails_when_mainline_not_positive(repo_with_side_commit):
    repo, sha = repo_with_side_commit

    result = git_cherry_pick(repo, sha, mainline=0)

    assert isinstance(result, ToolFailure)
    assert "mainline" in result
