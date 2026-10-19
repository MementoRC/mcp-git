"""git_reflog_expire and git_gc tool definitions for the git domain (issue #283).

Kept apart from ``registry_git.py`` (size budget). ``wrap_repo_op`` is the
wrapper defined inside ``_register_git_tools``. Neither tool writes the index,
so neither is ``mutates_index`` (the flag only gates the index.lock reaper).
"""

from collections.abc import Callable
from typing import Any

from ..git._maintenance_ops import git_gc, git_reflog_expire
from ..git.models_maintenance import GitGc, GitReflogExpire
from .interface import ToolDefinition


def maintenance_tool_definitions(
    wrap_repo_op: Callable[..., Any],
) -> list[ToolDefinition]:
    """ToolDefinitions for git_reflog_expire and git_gc."""
    return [
        ToolDefinition(
            name="git_reflog_expire",
            implementation=wrap_repo_op(git_reflog_expire),
            description=(
                "DESTRUCTIVE when dry_run=false: permanently removes reflog "
                "entries of HEAD and every ref (dry_run defaults to true). "
                "refs/stash is excluded by default (include_stash=true to "
                "expire it; the stash is shared across worktrees). Run after "
                "git_filter_paths, then git_gc, so removed content is "
                "unreachable"
            ),
            schema=GitReflogExpire.model_json_schema(),
            domain="git",
            complexity="advanced",
        ),
        ToolDefinition(
            name="git_gc",
            implementation=wrap_repo_op(git_gc),
            description=(
                "DESTRUCTIVE when dry_run=false: permanently removes "
                "unreachable objects via git gc --prune (dry_run defaults to "
                "true and only reports object counts and what would be "
                "pruned). Never expires reflogs. prune defaults to "
                "2.weeks.ago; to finish a scrub run git_reflog_expire first, "
                "then pass prune='now', only when no other process or "
                "session is using the repository"
            ),
            schema=GitGc.model_json_schema(),
            domain="git",
            complexity="advanced",
        ),
    ]
