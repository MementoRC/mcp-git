"""git_checkout / git_merge refuse to clobber ignored files (issue #283).

Reproduces the reported scenario with a real repo: branch ``main`` stops
tracking ``secret.cfg`` (now ignored); branch ``legacy`` still tracks it.
"""

import pytest

from mcp_server_git.git._branch_ops import git_checkout
from mcp_server_git.git._ignored_guard import find_ignored_overwrites
from mcp_server_git.git._rebase_ops import git_merge
from mcp_server_git.utils.tool_failure import ToolFailure


def _write(repo, name, text):
    path = f"{repo.working_dir}/{name}"
    with open(path, "w") as handle:
        handle.write(text)
    return path


@pytest.fixture
def untracked_on_main(real_repo):
    """main ignores secret.cfg (local content); legacy tracks the committed one."""
    _write(real_repo, "secret.cfg", "committed\n")
    real_repo.index.add(["secret.cfg"])
    real_repo.index.commit("track secret")
    real_repo.create_head("legacy")
    real_repo.git.rm("--cached", "secret.cfg")
    _write(real_repo, ".gitignore", "secret.cfg\n")
    real_repo.index.add([".gitignore"])
    real_repo.index.commit("untrack secret")
    _write(real_repo, "secret.cfg", "LOCAL ONLY\n")
    return real_repo


def _read(repo, name):
    with open(f"{repo.working_dir}/{name}") as handle:
        return handle.read()


def test_git_checkout_refuses_switch_when_target_tracks_ignored_file(untracked_on_main):
    result = git_checkout(untracked_on_main, "legacy")

    assert isinstance(result, ToolFailure)
    assert "secret.cfg" in result
    assert "allow_overwrite_ignored" in result
    assert untracked_on_main.active_branch.name == "main"
    assert _read(untracked_on_main, "secret.cfg") == "LOCAL ONLY\n"


def test_git_checkout_overwrites_when_allow_overwrite_ignored_true(untracked_on_main):
    result = git_checkout(untracked_on_main, "legacy", allow_overwrite_ignored=True)

    assert result.startswith("✅")
    assert _read(untracked_on_main, "secret.cfg") == "committed\n"


def test_git_checkout_switches_when_no_ignored_file_at_risk(real_repo):
    real_repo.create_head("other")

    result = git_checkout(real_repo, "other")

    assert result.startswith("✅")


def test_git_checkout_switches_when_ignored_file_absent_from_target(untracked_on_main):
    _write(untracked_on_main, "scratch.log", "x")
    untracked_on_main.git.branch("clean")

    result = git_checkout(untracked_on_main, "clean")

    assert result.startswith("✅")
    assert _read(untracked_on_main, "secret.cfg") == "LOCAL ONLY\n"


def test_git_merge_refuses_when_source_changes_ignored_file(untracked_on_main):
    untracked_on_main.git.checkout("legacy")
    _write(untracked_on_main, "secret.cfg", "changed upstream\n")
    untracked_on_main.index.add(["secret.cfg"])
    untracked_on_main.index.commit("edit secret on legacy")
    untracked_on_main.git.checkout("main")
    _write(untracked_on_main, "secret.cfg", "LOCAL ONLY\n")

    result = git_merge(untracked_on_main, "legacy")

    assert isinstance(result, ToolFailure)
    assert "secret.cfg" in result
    assert _read(untracked_on_main, "secret.cfg") == "LOCAL ONLY\n"


def test_git_merge_proceeds_when_source_leaves_ignored_file_unchanged(
    untracked_on_main,
):
    untracked_on_main.git.checkout("legacy")
    _write(untracked_on_main, "other.txt", "x")
    untracked_on_main.index.add(["other.txt"])
    untracked_on_main.index.commit("unrelated change on legacy")
    untracked_on_main.git.checkout("main")
    _write(untracked_on_main, "secret.cfg", "LOCAL ONLY\n")

    result = git_merge(untracked_on_main, "legacy", message="merge legacy")

    assert not isinstance(result, ToolFailure), result
    assert _read(untracked_on_main, "secret.cfg") == "LOCAL ONLY\n"


def test_git_checkout_caps_listed_files_when_many_ignored_files_at_risk(real_repo):
    for i in range(12):
        _write(real_repo, f"gen{i:02}.out", "c")
    real_repo.index.add([f"gen{i:02}.out" for i in range(12)])
    real_repo.index.commit("track outputs")
    real_repo.create_head("outs")
    real_repo.git.rm("--cached", "-q", *[f"gen{i:02}.out" for i in range(12)])
    _write(real_repo, ".gitignore", "*.out\n")
    real_repo.index.add([".gitignore"])
    real_repo.index.commit("ignore outputs")

    found = find_ignored_overwrites(real_repo, "outs")
    result = git_checkout(real_repo, "outs")

    assert len(found) == 12
    assert isinstance(result, ToolFailure)
    assert "(+2 more)" in result
