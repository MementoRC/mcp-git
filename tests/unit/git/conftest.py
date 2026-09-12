"""Shared fixtures for tests/unit/git/.

Six defects (#214-#222) all survived a green suite that mocked the exact
boundary where the bug lived. Tests that need to prove a *real* git failure
(or success) renders correctly should use the ``real_repo`` fixture below
instead of a mocked ``Repo`` -- see ``test_git_add_modes.py`` (#222) and
``test_git_add_pathspec.py`` (#218) for the precedent this follows.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("git")
from git import Repo  # noqa: E402

_INITIAL_BRANCH = "main"
_USER_NAME = "Test User"
_USER_EMAIL = "test@example.com"


@pytest.fixture
def real_repo(tmp_path: Path) -> Repo:
    """A real, initialized git repository with one initial commit.

    Identity and branch name are pinned explicitly so git's default-branch
    warning and version-dependent default name, and any dependency on
    ambient/global ``user.name``/``user.email`` config, can't leak into
    assertions made against this repo's output.
    """
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    repo = Repo.init(repo_path, initial_branch=_INITIAL_BRANCH)
    with repo.config_writer() as config:
        config.set_value("user", "name", _USER_NAME)
        config.set_value("user", "email", _USER_EMAIL)
    repo.index.commit("initial commit")
    return repo
