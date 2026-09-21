"""
Unit tests for git_push force handling on the raw refspec path (issue #237).

Before this fix the refspec branch of git_push returned early and forwarded
only ``--dry-run``, silently discarding ``force`` / ``force_with_lease`` /
``force_if_includes``. The non-fast-forward rejection message then advised
setting the very flags the caller had already set.

The implementation in _remote_ops.py is the source of truth.
"""

from unittest.mock import MagicMock

import pytest
from git import GitCommandError

from mcp_server_git.git.operations import git_push

NON_FAST_FORWARD_STDERR = (
    "! [rejected]        abc123 -> main (non-fast-forward)\n"
    "error: failed to push some refs to 'github.com:owner/repo.git'"
)

REFSPEC = "abc123:refs/heads/main"

# The pre-fix advice string. Correct when no force was requested, actively
# misleading when it was.
ADVICE = "Use force_with_lease=True (safe) or force=True"


@pytest.fixture()
def mock_repo() -> MagicMock:
    """Minimal repo mock: SSH remote URL bypasses GitHub HTTPS auth branch."""
    repo = MagicMock()
    repo.active_branch.name = "feature/x"
    repo.remote.return_value.url = "git@github.com:owner/repo.git"
    repo.git.push.return_value = ""
    return repo


def _reject(repo: MagicMock) -> None:
    """Make the next push fail the way a non-fast-forward rejection does."""
    repo.git.push.side_effect = GitCommandError(
        "git push", 1, stderr=NON_FAST_FORWARD_STDERR
    )


# ---------------------------------------------------------------------------
# Bug 1: force flags must reach the refspec path
# ---------------------------------------------------------------------------


def test_refspec_with_force_passes_force_flag(mock_repo: MagicMock) -> None:
    git_push(mock_repo, refspec=REFSPEC, force=True)

    args = mock_repo.git.push.call_args.args
    assert "--force" in args
    assert REFSPEC in args


def test_refspec_with_force_with_lease_passes_lease_flag(
    mock_repo: MagicMock,
) -> None:
    git_push(mock_repo, refspec=REFSPEC, force_with_lease=True)

    args = mock_repo.git.push.call_args.args
    assert "--force-with-lease" in args
    assert REFSPEC in args


def test_refspec_with_force_if_includes_passes_flag(mock_repo: MagicMock) -> None:
    git_push(mock_repo, refspec=REFSPEC, force_with_lease=True, force_if_includes=True)

    args = mock_repo.git.push.call_args.args
    assert "--force-with-lease" in args
    assert "--force-if-includes" in args


def test_refspec_lease_expect_colon_form_passes_through(
    mock_repo: MagicMock,
) -> None:
    git_push(
        mock_repo,
        refspec=REFSPEC,
        force_with_lease=True,
        force_with_lease_expect="refs/heads/main:cafebabe",
    )

    args = mock_repo.git.push.call_args.args
    assert "--force-with-lease=refs/heads/main:cafebabe" in args


def test_refspec_lease_expect_bare_sha_derives_refname_from_refspec_dst(
    mock_repo: MagicMock,
) -> None:
    """branch is None on the refspec path, so the destination ref is the
    only available source for the lease refname."""
    git_push(
        mock_repo,
        refspec=REFSPEC,
        force_with_lease=True,
        force_with_lease_expect="deadbeef",
    )

    args = mock_repo.git.push.call_args.args
    assert "--force-with-lease=refs/heads/main:deadbeef" in args


def test_refspec_without_colon_derives_lease_refname_from_whole_refspec(
    mock_repo: MagicMock,
) -> None:
    git_push(
        mock_repo,
        refspec="main",
        force_with_lease=True,
        force_with_lease_expect="deadbeef",
    )

    args = mock_repo.git.push.call_args.args
    assert "--force-with-lease=main:deadbeef" in args


def test_refspec_force_composes_with_dry_run(mock_repo: MagicMock) -> None:
    result = git_push(mock_repo, refspec=REFSPEC, force=True, dry_run=True)

    args = mock_repo.git.push.call_args.args
    assert "--force" in args
    assert "--dry-run" in args
    assert "dry-run" in result


def test_refspec_without_force_is_unchanged(mock_repo: MagicMock) -> None:
    """Regression guard: the no-force refspec call must keep its exact argv."""
    git_push(mock_repo, refspec=REFSPEC)

    mock_repo.git.push.assert_called_once_with("origin", REFSPEC)


def test_refspec_still_rejects_force_and_force_with_lease_combined(
    mock_repo: MagicMock,
) -> None:
    result = git_push(mock_repo, refspec=REFSPEC, force=True, force_with_lease=True)

    assert result.startswith("❌")
    assert "mutually exclusive" in result
    mock_repo.git.push.assert_not_called()


# ---------------------------------------------------------------------------
# Bug 2: the rejection message must not recommend flags already supplied
# ---------------------------------------------------------------------------


def test_rejection_message_keeps_advice_when_no_force_requested(
    mock_repo: MagicMock,
) -> None:
    """The original wording is correct in the only case it applies to."""
    _reject(mock_repo)

    result = git_push(mock_repo, branch="main")

    assert result.startswith("❌")
    assert ADVICE in result


def test_rejection_message_drops_advice_when_force_already_set(
    mock_repo: MagicMock,
) -> None:
    _reject(mock_repo)

    result = git_push(mock_repo, branch="main", force=True)

    assert result.startswith("❌")
    assert "non-fast-forward" in result
    assert ADVICE not in result


def test_rejection_message_drops_advice_when_lease_already_set(
    mock_repo: MagicMock,
) -> None:
    _reject(mock_repo)

    result = git_push(mock_repo, branch="main", force_with_lease=True)

    assert result.startswith("❌")
    assert ADVICE not in result


def test_rejection_message_on_refspec_path_drops_advice_when_force_set(
    mock_repo: MagicMock,
) -> None:
    """The exact path reported in issue #237: refspec + force, rejected,
    previously answered with 'use force=True'."""
    _reject(mock_repo)

    result = git_push(mock_repo, refspec=REFSPEC, force=True)

    assert result.startswith("❌")
    assert ADVICE not in result


def test_lease_rejection_explains_stale_ref_rather_than_repeating_flag(
    mock_repo: MagicMock,
) -> None:
    """A refused lease has a specific cause worth naming: the remote moved."""
    _reject(mock_repo)

    result = git_push(mock_repo, refspec=REFSPEC, force_with_lease=True)

    assert ADVICE not in result
    assert "fetch" in result.lower()
