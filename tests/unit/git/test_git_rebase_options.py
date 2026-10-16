"""git_rebase --root/--rebase-merges/signing/date options on real repos (#283)."""

from pathlib import Path

import pytest

from mcp_server_git.git._rebase_ops import git_rebase
from mcp_server_git.git.models import GitRebase
from mcp_server_git.utils.tool_failure import ToolFailure


def _date(days):
    """Raw git date `days` after 2020-01-01 UTC, far from 'now'."""
    return f"{1577836800 + days * 86400} +0000"


def _commit_file(repo, name, text, message, date=None):
    with open(f"{repo.working_dir}/{name}", "w") as handle:
        handle.write(text)
    repo.index.add([name])
    kwargs = {"author_date": date} if date else {}
    return repo.index.commit(message, **kwargs)


def _all_shas(repo):
    return repo.git.rev_list("HEAD").split()


def _is_signed(repo, sha):
    return "gpgsig" in repo.git.cat_file("-p", sha)


@pytest.fixture
def merge_history(signing_repo):
    """root + 3 main commits, 2 side commits, a --no-ff merge, 3 more (10 total)."""
    repo = signing_repo
    for i in range(3):
        _commit_file(repo, f"m{i}.txt", "m\n", f"main {i}", _date(i))
    repo.git.checkout("-b", "side")
    for i in range(2):
        _commit_file(repo, f"s{i}.txt", "s\n", f"side {i}", _date(10 + i))
    repo.git.checkout("main")
    repo.git.merge("--no-ff", "-m", "merge side", "side")
    for i in range(3, 6):
        _commit_file(repo, f"m{i}.txt", "m\n", f"main {i}", _date(20 + i))
    return repo


def _merge_sha(repo):
    return repo.git.rev_list("--merges", "HEAD").split()[0]


def test_git_rebase_signs_every_commit_when_root_and_signing_enforced(merge_history):
    repo = merge_history
    assert not _is_signed(repo, repo.head.commit.hexsha)

    result = git_rebase(repo, root=True)

    assert result.startswith("✅"), result
    shas = _all_shas(repo)
    assert all(_is_signed(repo, sha) for sha in shas)
    assert len(shas) == 9  # merge flattened without --rebase-merges


def test_git_rebase_signs_commits_when_root_and_gpg_sign_false_but_enforced(
    signing_repo,
):
    _commit_file(signing_repo, "a.txt", "a\n", "a")

    git_rebase(signing_repo, root=True, gpg_sign=False)

    assert all(_is_signed(signing_repo, s) for s in _all_shas(signing_repo))


def test_git_rebase_preserves_merge_when_rebase_merges_true(merge_history):
    repo = merge_history

    result = git_rebase(repo, root=True, rebase_merges=True)

    assert result.startswith("✅"), result
    assert len(repo.commit(_merge_sha(repo)).parents) == 2


def test_git_rebase_flattens_merge_when_rebase_merges_false(merge_history):
    repo = merge_history

    git_rebase(repo, root=True)

    assert repo.git.rev_list("--merges", "HEAD").split() == []


def test_git_rebase_sets_committer_date_to_author_date_when_option_true(merge_history):
    repo = merge_history

    git_rebase(repo, root=True, committer_date_is_author_date=True)

    dated = repo.git.log(
        "--format=%ad|%cd|%s", "--date=raw", "--no-merges"
    ).splitlines()
    pairs = [line.split("|")[:2] for line in dated if "initial" not in line]
    assert pairs and all(author == committer for author, committer in pairs)


def test_git_rebase_resigns_whole_history_when_issue_283_reproduction(merge_history):
    repo = merge_history
    before = repo.git.log("--format=%s|%ad", "--date=raw", "--no-merges").splitlines()
    assert len(_all_shas(repo)) == 10

    result = git_rebase(
        repo, root=True, rebase_merges=True, committer_date_is_author_date=True
    )

    assert result.startswith("✅"), result
    shas = _all_shas(repo)
    assert len(shas) == 10
    assert all(_is_signed(repo, sha) for sha in shas)
    assert len(repo.commit(_merge_sha(repo)).parents) == 2
    after = repo.git.log("--format=%s|%ad", "--date=raw", "--no-merges").splitlines()
    assert sorted(after) == sorted(before)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"root": True, "target_branch": "main"},
        {"root": True, "onto": "main", "fork_point": "main"},
        {},
    ],
)
def test_git_rebase_rejects_options_when_combination_invalid(signing_repo, kwargs):
    before = signing_repo.head.commit.hexsha

    result = git_rebase(signing_repo, **kwargs)

    assert isinstance(result, ToolFailure)
    assert signing_repo.head.commit.hexsha == before


@pytest.mark.parametrize("field", ["target_branch", "branch", "onto", "fork_point"])
def test_git_rebase_rejects_value_when_it_starts_with_dash(signing_repo, field):
    kwargs = {"target_branch": "main", "onto": "main", "fork_point": "main"}
    kwargs[field] = "--exec=touch pwned"

    result = git_rebase(signing_repo, **kwargs)

    assert isinstance(result, ToolFailure)
    assert "must not start with '-'" in result
    assert not (Path(signing_repo.working_dir) / "pwned").exists()


def test_git_rebase_model_has_no_exec_like_field_when_schema_inspected():
    names = set(GitRebase.model_fields)

    assert not [n for n in names if "exec" in n or n in {"args", "strategy_option"}]
    assert names >= {
        "root",
        "rebase_merges",
        "gpg_sign",
        "committer_date_is_author_date",
    }


def test_git_rebase_reports_conflict_when_branches_diverge(signing_repo):
    repo = signing_repo
    repo.git.checkout("-b", "other")
    _commit_file(repo, "f.txt", "other\n", "other change")
    repo.git.checkout("main")
    _commit_file(repo, "f.txt", "main\n", "main change")
    repo.git.checkout("other")

    result = git_rebase(repo, "main")

    assert isinstance(result, ToolFailure)
    assert "conflicts" in result
    repo.git.rebase("--abort")


def test_git_rebase_does_not_open_editor_when_reword_editor_would_hang(
    merge_history, monkeypatch
):
    monkeypatch.setenv("GIT_EDITOR", "false")
    monkeypatch.setenv("GIT_SEQUENCE_EDITOR", "false")

    result = git_rebase(merge_history, root=True, rebase_merges=True)

    assert result.startswith("✅"), result
