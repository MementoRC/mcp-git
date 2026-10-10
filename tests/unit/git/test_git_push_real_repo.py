"""
Characterization tests for git_push against real repositories (issue #255).

Pins the regular (non-GitHub-HTTPS) push outcomes using a working repo and a
bare remote reached through a file path URL, so no boundary is mocked.
"""

from pathlib import Path

import git
import pytest

from mcp_server_git.git.operations import git_push


def _commit(repo: git.Repo, name: str) -> None:
    path = Path(repo.working_dir) / name
    path.write_text(name)
    repo.index.add([name])
    repo.index.commit(f"add {name}")


@pytest.fixture()
def bare_remote(tmp_path: Path) -> Path:
    path = tmp_path / "remote.git"
    git.Repo.init(path, bare=True)
    return path


@pytest.fixture()
def work_repo(tmp_path: Path, bare_remote: Path) -> git.Repo:
    repo = git.Repo.init(tmp_path / "work", initial_branch="main")
    with repo.config_writer() as cfg:
        cfg.set_value("user", "name", "Test")
        cfg.set_value("user", "email", "test@example.com")
    _commit(repo, "a.txt")
    repo.create_remote("origin", str(bare_remote))
    return repo


def _diverge(work_repo: git.Repo, bare_remote: Path, tmp_path: Path) -> None:
    """Push a commit to the remote from another clone, then fetch it here."""
    work_repo.git.push("origin", "main")
    other = git.Repo.clone_from(str(bare_remote), tmp_path / "other", branch="main")
    with other.config_writer() as cfg:
        cfg.set_value("user", "name", "Other")
        cfg.set_value("user", "email", "other@example.com")
    _commit(other, "other.txt")
    other.git.push("origin", "main")
    work_repo.git.fetch("origin")
    _commit(work_repo, "local.txt")


def test_git_push_returns_success_when_remote_accepts_branch(
    work_repo: git.Repo,
) -> None:
    result = git_push(work_repo)

    assert result == "✅ Successfully pushed main to origin"


def test_git_push_returns_upstream_suffix_when_set_upstream_requested(
    work_repo: git.Repo,
) -> None:
    result = git_push(work_repo, set_upstream=True)

    assert result == "✅ Successfully pushed main to origin (set upstream tracking)"


def test_git_push_returns_dry_run_suffix_when_dry_run_requested(
    work_repo: git.Repo, bare_remote: Path
) -> None:
    result = git_push(work_repo, dry_run=True)

    assert result == (
        "✅ Successfully pushed main to origin (dry-run; no remote state modified)"
    )
    assert git.Repo(bare_remote).heads == []


def test_git_push_returns_all_suffixes_when_upstream_and_dry_run_requested(
    work_repo: git.Repo,
) -> None:
    result = git_push(work_repo, set_upstream=True, dry_run=True)

    assert result == (
        "✅ Successfully pushed main to origin (set upstream tracking)"
        " (dry-run; no remote state modified)"
    )


def test_git_push_returns_no_active_branch_when_head_detached(
    work_repo: git.Repo,
) -> None:
    work_repo.git.checkout("--detach")

    result = git_push(work_repo)

    assert result == "❌ No active branch found and no branch specified"


def test_git_push_returns_failure_with_exit_code_when_remote_missing(
    work_repo: git.Repo,
) -> None:
    result = git_push(work_repo, remote="nowhere")

    assert result.startswith("❌ Push failed (exit 128): ")
    assert "nowhere" in result


def test_git_push_returns_failure_with_exit_code_when_branch_unknown(
    work_repo: git.Repo,
) -> None:
    result = git_push(work_repo, branch="no-such-branch")

    assert result.startswith("❌ Push failed (exit 1): ")


def test_git_push_returns_rejected_hint_when_non_fast_forward(
    work_repo: git.Repo, bare_remote: Path, tmp_path: Path
) -> None:
    _diverge(work_repo, bare_remote, tmp_path)

    result = git_push(work_repo)

    assert result == (
        "❌ Push rejected (non-fast-forward). "
        "Use force_with_lease=True (safe) or force=True (unconditional)"
    )


def test_git_push_returns_force_rejected_when_remote_denies_forced_update(
    work_repo: git.Repo, bare_remote: Path, tmp_path: Path
) -> None:
    git.Repo(bare_remote).git.config("receive.denyNonFastForwards", "true")
    _diverge(work_repo, bare_remote, tmp_path)

    result = git_push(work_repo, force=True)

    assert result.startswith(
        "❌ Push rejected (non-fast-forward) even though force=True. "
    )


def test_git_push_returns_lease_rejected_when_remote_denies_leased_update(
    work_repo: git.Repo, bare_remote: Path, tmp_path: Path
) -> None:
    git.Repo(bare_remote).git.config("receive.denyNonFastForwards", "true")
    _diverge(work_repo, bare_remote, tmp_path)

    result = git_push(work_repo, force_with_lease=True)

    assert result.startswith(
        "❌ Push rejected (non-fast-forward) even though force_with_lease=True. "
    )
