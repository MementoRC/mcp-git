"""Real-repo builders and probes shared by the git_filter_paths tests (#283).

No ``test_`` prefix, so pytest does not collect it. ``isolated_git_home`` is
an autouse fixture: importing it into a test module applies it there, so the
developer's global git config (signing key, commit.gpgSign) never leaks in.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from git import Repo

SECRETS = [".mcp.json", ".claude/", ".serena"]


@pytest.fixture(autouse=True)
def isolated_git_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point HOME/XDG at an empty dir and drop GPG_SIGNING_KEY."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("GPG_SIGNING_KEY", raising=False)


def _date(month: int, day: int) -> str:
    return f"2020-{month:02d}-{day:02d}T12:00:00+0000"


def write(repo: Repo, files: dict[str, str]) -> None:
    root = Path(repo.working_tree_dir)
    for name, content in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)


def commit(repo: Repo, files: dict[str, str], message: str, day: int) -> str:
    """Commit *files* with author date 2020-01-<day> and committer 2020-02-<day>."""
    write(repo, files)
    env = {
        "GIT_LITERAL_PATHSPECS": "1",
        "GIT_AUTHOR_DATE": _date(1, day),
        "GIT_COMMITTER_DATE": _date(2, day),
    }
    with repo.git.custom_environment(**env):
        repo.git.add("--", *files)
        repo.git.commit("-m", message)
    return repo.head.commit.hexsha


def merge(repo: Repo, branch: str, message: str, day: int) -> None:
    env = {"GIT_AUTHOR_DATE": _date(1, day), "GIT_COMMITTER_DATE": _date(2, day)}
    with repo.git.custom_environment(**env):
        repo.git.merge("--no-ff", "-m", message, branch)


def build_283_history(repo: Repo) -> None:
    """~10 commits and one merge with .mcp.json/.claude/.serena committed throughout."""
    commit(
        repo,
        {
            "README.md": "readme",
            ".mcp.json": "{}",
            ".claude/settings.json": "{}",
            ".serena/project.yml": "a",
        },
        "c1 add project",
        1,
    )
    commit(repo, {"src/app.py": "1", ".mcp.json": "{1}"}, "c2", 2)
    commit(repo, {"src/app.py": "2", ".claude/settings.json": "{2}"}, "c3", 3)
    repo.git.checkout("-b", "side")
    commit(repo, {"src/side.py": "s1", ".serena/project.yml": "b"}, "s1 side", 4)
    commit(repo, {"src/side.py": "s2", ".claude/notes.md": "n"}, "s2 side", 5)
    repo.git.checkout("main")
    commit(repo, {"src/app.py": "3", ".mcp.json": "{3}"}, "c4", 6)
    merge(repo, "side", "m1 merge side", 7)
    for day in range(8, 12):
        commit(
            repo, {"src/app.py": f"{day}", ".mcp.json": f"{{{day}}}"}, f"c{day}", day
        )


def ref_shas(repo: Repo) -> dict[str, str]:
    out = repo.git.for_each_ref("--format=%(refname) %(objectname)")
    return dict(line.split(" ", 1) for line in out.splitlines())


def bundles_near(repo: Repo) -> list[Path]:
    """Bundle files next to the repository (where the default backup goes)."""
    return sorted(Path(repo.working_tree_dir).parent.glob("*.bundle"))


def all_commits(repo: Repo, *revs: str) -> list[str]:
    return repo.git.rev_list(*(revs or ("--all",))).split()


def tree_paths(repo: Repo, sha: str) -> list[str]:
    out = repo.git.ls_tree("-r", "-z", "--name-only", sha)
    return [name for name in out.split("\0") if name]


def dates_by_subject(repo: Repo) -> dict[str, str]:
    out = repo.git.log("--all", "--format=%s|%ad|%cd", "--date=raw")
    return dict(line.split("|", 1) for line in out.splitlines())


def is_signed(repo: Repo, sha: str) -> bool:
    return "\ngpgsig " in repo.git.cat_file("commit", sha)


def add_bare_remote(repo: Repo, tmp_path: Path) -> Repo:
    bare = Repo.init(tmp_path / "remote.git", bare=True)
    repo.create_remote("origin", str(tmp_path / "remote.git"))
    repo.git.push("origin", "--all")
    return bare
