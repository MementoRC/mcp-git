"""git_commit author/date/reuse_message_from on a real, signing-capable repo (#283)."""

import pytest

from mcp_server_git.git._commit_ops import git_commit
from mcp_server_git.utils.tool_failure import ToolFailure


def _stage(repo, name="f.txt", text="x\n"):
    with open(f"{repo.working_dir}/{name}", "w") as handle:
        handle.write(text)
    repo.index.add([name])


def test_git_commit_sets_author_and_date_when_provided(signing_repo):
    _stage(signing_repo)

    result = git_commit(
        signing_repo,
        "with metadata",
        author="Ada Lovelace <ada@example.com>",
        date="2020-01-02T03:04:05+00:00",
    )

    assert result.startswith("✅"), result
    head = signing_repo.head.commit
    assert (head.author.name, head.author.email) == ("Ada Lovelace", "ada@example.com")
    assert head.authored_datetime.isoformat() == "2020-01-02T03:04:05+00:00"
    assert head.committer.name == "Test User"
    assert head.committed_datetime.year != 2020


def test_git_commit_signs_commit_when_metadata_options_used(signing_repo):
    _stage(signing_repo)

    git_commit(signing_repo, "signed", author="A B <a@b.c>")

    assert "gpgsig" in signing_repo.git.cat_file("-p", "HEAD")


def test_git_commit_reuses_message_when_reuse_message_from_given(signing_repo):
    signing_repo.index.commit("original message")
    original = signing_repo.head.commit.hexsha
    _stage(signing_repo)

    result = git_commit(signing_repo, reuse_message_from=original)

    assert result.startswith("✅"), result
    assert signing_repo.head.commit.message.strip() == "original message"
    assert signing_repo.head.commit.hexsha != original


@pytest.mark.parametrize(
    "author", ["no-email", "Name <>", "<a@b.c>", "Name <a@b.c> extra <x>"]
)
def test_git_commit_fails_when_author_malformed(signing_repo, author):
    _stage(signing_repo)
    before = signing_repo.head.commit.hexsha

    result = git_commit(signing_repo, "m", author=author)

    assert isinstance(result, ToolFailure)
    assert "Invalid author" in result
    assert signing_repo.head.commit.hexsha == before


def test_git_commit_fails_when_date_unparseable(signing_repo):
    _stage(signing_repo)

    result = git_commit(signing_repo, "m", date="last tuesday")

    assert isinstance(result, ToolFailure)
    assert "Invalid date" in result


def test_git_commit_fails_when_neither_message_nor_reuse_given(signing_repo):
    result = git_commit(signing_repo)

    assert isinstance(result, ToolFailure)
    assert "exactly one" in result


def test_git_commit_fails_when_both_message_and_reuse_given(signing_repo):
    result = git_commit(signing_repo, "m", reuse_message_from="HEAD")

    assert isinstance(result, ToolFailure)
    assert "exactly one" in result


def test_git_commit_fails_when_reuse_message_from_is_option_like(signing_repo):
    result = git_commit(signing_repo, reuse_message_from="--amend")

    assert isinstance(result, ToolFailure)
