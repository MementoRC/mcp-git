"""git_commit failure wording: hook rejections are not blamed on GPG (#332)."""

import os

from mcp_server_git.git._commit_ops import _commit_failure_hint, git_commit
from mcp_server_git.utils.tool_failure import ToolFailure

HOOK_HINT = "🪝 A pre-commit or commit-msg hook may have rejected the commit"
GPG_SUFFIX = "\n🔒 GPG signing was enforced but failed"


def test_git_commit_reports_hook_hint_without_gpg_when_pre_commit_hook_rejects(
    signing_repo,
):
    signing_repo.index.commit("base")
    hook = f"{signing_repo.git_dir}/hooks/pre-commit"
    with open(hook, "w") as handle:
        handle.write("#!/bin/sh\necho 'lint says no' >&2\nexit 1\n")
    os.chmod(hook, 0o755)
    with open(f"{signing_repo.working_dir}/f.txt", "w") as handle:
        handle.write("x\n")
    signing_repo.index.add(["f.txt"])

    result = git_commit(signing_repo, "blocked")

    assert isinstance(result, ToolFailure)
    assert HOOK_HINT in result
    assert "GPG" not in result


def test_commit_failure_hint_returns_gpg_suffix_when_stderr_shows_signing_failure():
    stderr = "error: gpg failed to sign the data\nfatal: failed to write commit object"

    result = _commit_failure_hint(stderr, no_verify=False)

    assert result == GPG_SUFFIX


def test_commit_failure_hint_returns_hook_hint_when_hook_rejects_without_no_verify():
    result = _commit_failure_hint("lint says no", no_verify=False)

    assert result.startswith("\n" + HOOK_HINT)
    assert "GPG" not in result


def test_commit_failure_hint_returns_empty_when_non_gpg_error_with_no_verify():
    assert _commit_failure_hint("nothing to commit", no_verify=True) == ""
