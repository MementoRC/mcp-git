"""git_filter_paths tool definition for the git domain (issue #283).

Kept apart from ``registry_git.py`` (size budget), like
``registry_git_bundle.py``. ``wrap_repo_op`` is the wrapper defined inside
``_register_git_tools``. The rewrite checks out the new history, so the tool
is ``mutates_index``.
"""

from collections.abc import Callable
from typing import Any

from ..git._filter_ops import git_filter_paths
from ..git.models_filter import GitFilterPaths
from .interface import ToolDefinition


def filter_tool_definitions(wrap_repo_op: Callable[..., Any]) -> list[ToolDefinition]:
    """ToolDefinition for git_filter_paths."""
    return [
        ToolDefinition(
            name="git_filter_paths",
            implementation=wrap_repo_op(git_filter_paths, mutates_index=True),
            description=(
                "Rewrite history to remove paths (or keep only them with "
                "invert=True) via git filter-branch. Refuses on a dirty tree, "
                "configured remotes (unless allow_with_remote), an operation in "
                "progress or leftover refs/original/. Writes and verifies a "
                "bundle backup first; signs while signing is enforced; "
                "dry_run=True only reports. Never pushes. With all_refs, "
                "annotated signed tags lose their signatures"
            ),
            schema=GitFilterPaths.model_json_schema(),
            domain="git",
            complexity="advanced",
        ),
    ]
