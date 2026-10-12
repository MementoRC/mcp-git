"""Characterization tests pinning every branch of git_merge_file (issue #255).

Real temporary repositories exercise the merge; mocks are used only to reach
the non-conflict merge-file failure and the OS/unexpected-error branches.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from mcp_server_git.git.merge_ops import git_merge_file
from mcp_server_git.text_limits import MAX_CHARS_FOR_LLM
from mcp_server_git.utils.tool_failure import ToolFailure

pytest.importorskip("git")
from git import GitCommandError, Repo  # noqa: E402

SEP = "-" * 60


def _commit(r, root, name, text):
    (root / name).write_text(text)
    r.git.add(name)
    r.git.commit("-m", f"c-{name}-{len(text)}")
    return r.git.rev_parse("HEAD")


@pytest.fixture
def repo(tmp_path):
    r = Repo.init(tmp_path)
    with r.config_writer() as cw:
        cw.set_value("user", "name", "T")
        cw.set_value("user", "email", "t@example.com")
        cw.set_value("commit", "gpgsign", "false")
    return r


@pytest.fixture
def revs(repo, tmp_path):
    """base, clean-ours (edits line 1), clean-theirs (edits line 3), conflict."""
    base = _commit(repo, tmp_path, "f.txt", "a\nb\nc\n")
    ours = _commit(repo, tmp_path, "f.txt", "A\nb\nc\n")
    repo.git.checkout(base)
    theirs = _commit(repo, tmp_path, "f.txt", "a\nb\nC\n")
    clash = _commit(repo, tmp_path, "f.txt", "X\nb\nC\n")
    return {"base": base, "ours": ours, "theirs": theirs, "clash": clash}


def _merge(repo, revs, **kw):
    return git_merge_file(
        repo, "f.txt", revs["base"], revs["ours"], revs["theirs"], **kw
    )


@pytest.mark.parametrize("field", ["base_rev", "ours_rev", "theirs_rev", "path"])
def test_git_merge_file_returns_invalid_chars_when_argument_dangerous(
    repo, revs, field
):
    args = {
        "path": "f.txt",
        "base_rev": revs["base"],
        "ours_rev": revs["ours"],
        "theirs_rev": revs["theirs"],
    }
    args[field] = "bad;x"
    result = git_merge_file(repo, **args)
    assert result == f"❌ Invalid characters detected in {field}: 'bad;x'"
    assert isinstance(result, ToolFailure)


def test_git_merge_file_validates_base_before_ours_before_theirs(repo, revs):
    result = git_merge_file(repo, "p;", "b;", "o;", "t;")
    assert result == "❌ Invalid characters detected in base_rev: 'b;'"


def test_git_merge_file_returns_label_count_error_when_labels_not_three(repo, revs):
    result = _merge(repo, revs, labels=["a", "b"])
    assert result == (
        "❌ labels must be exactly three entries (ours, base, theirs), got 2"
    )
    assert isinstance(result, ToolFailure)


def test_git_merge_file_returns_invalid_chars_when_label_dangerous(repo, revs):
    result = _merge(repo, revs, labels=["a", "b$", "c"])
    assert result == "❌ Invalid characters detected in labels[1]: 'b$'"
    assert isinstance(result, ToolFailure)


def test_git_merge_file_returns_missing_error_when_path_absent_everywhere(repo, revs):
    result = git_merge_file(
        repo, "nope.txt", revs["base"], revs["ours"], revs["theirs"]
    )
    assert result == (
        f"❌ nope.txt does not exist in any of {revs['ours']}, "
        f"{revs['base']}, {revs['theirs']}"
    )
    assert isinstance(result, ToolFailure)


def test_git_merge_file_returns_clean_merge_when_edits_do_not_overlap(repo, revs):
    result = _merge(repo, revs)
    assert result == "\n".join(
        [
            "🔀 Merged f.txt",
            f"   ours:   {revs['ours']}",
            f"   base:   {revs['base']}",
            f"   theirs: {revs['theirs']}",
            "✅ Clean merge (0 conflicts)",
            "📊 Total: 3 lines / 5 bytes | Truncated: no",
            "\n📄 Merged content (ours / base / theirs):",
            SEP,
            "A\nb\nC",
            SEP,
        ]
    )
    assert not isinstance(result, ToolFailure)


def test_git_merge_file_returns_conflict_markers_when_edits_overlap(repo, revs):
    result = git_merge_file(
        repo,
        "f.txt",
        revs["base"],
        revs["ours"],
        revs["clash"],
        labels=["L1", "L2", "L3"],
    )
    assert "⚠️ 1 conflict region(s) — markers included in the content below" in result
    assert "<<<<<<< L1" in result
    assert "||||||| L2" not in result  # merge-file -p defaults to non-diff3
    assert ">>>>>>> L3" in result
    assert "📄 Merged content (L1 / L2 / L3):" in result
    assert not isinstance(result, ToolFailure)


def test_git_merge_file_marks_side_absent_when_path_missing_in_one_revision(
    repo, revs, tmp_path
):
    repo.git.checkout(revs["base"])
    (tmp_path / "g.txt").write_text("only\n")
    repo.git.add("g.txt")
    repo.git.commit("-m", "add g")
    added = repo.git.rev_parse("HEAD")
    result = git_merge_file(repo, "g.txt", revs["base"], added, revs["base"])
    assert f"   ours:   {added}\n" in result
    assert f"   base:   {revs['base']}  (absent)\n" in result
    assert f"   theirs: {revs['base']}  (absent)\n" in result
    assert "✅ Clean merge (0 conflicts)" in result


def test_git_merge_file_truncates_inline_content_when_merge_exceeds_limit(
    repo, tmp_path
):
    big = "x" * (MAX_CHARS_FOR_LLM + 500) + "\n"
    rev = _commit(repo, tmp_path, "big.txt", big)
    result = git_merge_file(repo, "big.txt", rev, rev, rev)
    assert "Truncated: yes" in result
    assert (
        "⚠️ Truncated for LLM context (chars: exceeded 100KB limit) — "
        "pass output_path=<absolute path> for the complete result"
    ) in result


def test_git_merge_file_writes_file_when_output_path_absolute(repo, revs, tmp_path):
    out = tmp_path / "out" / "merged.txt"
    result = _merge(repo, revs, output_path=str(out))
    assert result == "\n".join(
        [
            "🔀 Merged f.txt",
            f"   ours:   {revs['ours']}",
            f"   base:   {revs['base']}",
            f"   theirs: {revs['theirs']}",
            "✅ Clean merge (0 conflicts)",
            f"💾 Full merge result written to {out}",
            "📊 Total: 3 lines / 5 bytes | Returned: written to disk | Truncated: no",
        ]
    )
    assert out.read_text() == "A\nb\nC"
    assert not isinstance(result, ToolFailure)


def test_git_merge_file_returns_error_when_output_path_relative(repo, revs):
    result = _merge(repo, revs, output_path="rel/out.txt")
    assert result == "❌ output_path must be an absolute path, got: rel/out.txt"
    assert isinstance(result, ToolFailure)


def test_git_merge_file_returns_error_when_output_path_unwritable(repo, revs, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("file")
    out = blocker / "sub" / "merged.txt"
    result = _merge(repo, revs, output_path=str(out))
    assert result.startswith(f"❌ Failed to write merge result to {out}: ")
    assert isinstance(result, ToolFailure)


def _failing_merge_repo(repo, err):
    """Real blob reads, but ``git merge-file`` raises *err*."""
    return SimpleNamespace(
        git=SimpleNamespace(show=repo.git.show, merge_file=Mock(side_effect=err))
    )


def test_git_merge_file_returns_failure_when_merge_file_exits_non_conflict(repo, revs):
    err = GitCommandError(["merge-file"], 255, stderr="fatal: boom", stdout="")
    result = _merge(_failing_merge_repo(repo, err), revs)
    assert result == "❌ Merge-file failed: fatal: boom"
    assert isinstance(result, ToolFailure)


def test_git_merge_file_falls_back_to_stdout_when_failure_stderr_empty(repo, revs):
    err = GitCommandError(["merge-file"], 255, stderr="", stdout="out text")
    result = _merge(_failing_merge_repo(repo, err), revs)
    assert result == "❌ Merge-file failed: out text"
    assert isinstance(result, ToolFailure)


def test_git_merge_file_returns_error_when_preparing_inputs_raises_oserror(repo, revs):
    with patch.object(Path, "write_text", side_effect=OSError("disk full")):
        result = _merge(repo, revs)
    assert result == "❌ Error preparing merge inputs: disk full"
    assert isinstance(result, ToolFailure)


def test_git_merge_file_returns_error_when_unexpected_exception_raised(repo, revs):
    with patch.object(Path, "write_text", side_effect=RuntimeError("boom")):
        result = _merge(repo, revs)
    assert result == "❌ Error during merge-file: boom"
    assert isinstance(result, ToolFailure)
