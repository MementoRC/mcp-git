"""
Real-repo tests for git_reflog (no mocks).

The mocked tests in test_git_reflog.py could not catch a raw NUL byte in the
--format argv element, which the OS rejects. These run real git.
"""

import re

import git
import pytest

from mcp_server_git.git.operations import git_reflog


@pytest.fixture
def repo(tmp_path):
    r = git.Repo.init(tmp_path)
    with r.config_writer() as cw:
        cw.set_value("user", "name", "Test")
        cw.set_value("user", "email", "test@example.com")
        cw.set_value("commit", "gpgsign", "false")
    for i in range(3):
        (tmp_path / f"f{i}.txt").write_text(str(i))
        r.index.add([f"f{i}.txt"])
        r.index.commit(f"commit {i}")
    r.git.checkout("-b", "feature")
    return r


def test_git_reflog_returns_entry_dicts_when_real_repo(repo):
    result = git_reflog(repo)

    assert isinstance(result, list), result
    assert len(result) >= 4
    for n, entry in enumerate(result):
        assert re.fullmatch(r"[0-9a-f]{40}", entry["new_sha"])
        assert entry["label"] == f"HEAD@{{{n}}}"
        assert entry["action"]
        assert entry["message"]


def test_git_reflog_parses_actions_when_commit_and_checkout_entries(repo):
    result = git_reflog(repo)

    assert isinstance(result, list), result
    assert result[0]["action"] == "checkout"
    assert "feature" in result[0]["message"]
    assert result[1]["action"] == "commit"
    assert result[1]["message"].endswith("commit 2")


def test_git_reflog_links_old_sha_to_next_new_sha_when_real_repo(repo):
    result = git_reflog(repo)

    assert isinstance(result, list), result
    for i in range(len(result) - 1):
        assert result[i]["old_sha"] == result[i + 1]["new_sha"]
    assert "old_sha" not in result[-1]


def test_git_reflog_limits_entries_when_max_count_given(repo):
    result = git_reflog(repo, max_count=2)

    assert isinstance(result, list), result
    assert len(result) == 2


def test_git_reflog_works_when_ref_is_branch_name(repo):
    result = git_reflog(repo, ref="feature")

    assert isinstance(result, list), result
    assert len(result) >= 1
    assert re.fullmatch(r"[0-9a-f]{40}", result[0]["new_sha"])


def test_git_reflog_omits_old_sha_when_all_true(repo):
    result = git_reflog(repo, all=True)

    assert isinstance(result, list), result
    assert len(result) >= 1
    assert all("old_sha" not in e for e in result)
