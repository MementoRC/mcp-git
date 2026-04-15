"""Git domain tool registration for lean MCP interface."""

import logging
from typing import Any

from ..git import operations as git_ops
from ..git.models import (
    GitAbort,
    GitAdd,
    GitBranchUpdate,
    GitCheckout,
    GitCherryPick,
    GitCommit,
    GitConfigGet,
    GitConfigList,
    GitConfigSet,
    GitContinue,
    GitCreateBranch,
    GitDiff,
    GitDiffBranches,
    GitDiffStaged,
    GitDiffUnstaged,
    GitInit,
    GitLog,
    GitMerge,
    GitMergeBase,
    GitMergeTree,
    GitPull,
    GitPush,
    GitRebase,
    GitReset,
    GitRestore,
    GitShow,
    GitStatus,
    GitSubmoduleAdd,
    GitSubmoduleStatus,
    GitSubmoduleSync,
    GitSubmoduleUpdate,
    GitWorktreeList,
    GitWorktreeRemove,
)
from ..git.operations_extended import (
    git_branch_update,
    git_merge_tree,
    git_restore,
    git_worktree_list,
    git_worktree_remove,
)
from ..utils.git_import import Repo
from .interface import ToolDefinition

logger = logging.getLogger(__name__)


def _register_git_tools(interface: Any, git_service: Any):
    """Register all Git domain tools."""

    # Create wrapper functions that convert repo_path to Repo object
    # The underlying operations expect Repo objects, not path strings
    def wrap_repo_op(op_func):
        """Wrap a git operation that takes Repo as first argument."""

        def wrapper(repo_path: str, **kwargs):
            repo = Repo(repo_path)
            return op_func(repo, **kwargs)

        return wrapper

    git_tools = [
        ToolDefinition(
            name="git_status",
            implementation=wrap_repo_op(git_ops.git_status),
            description="Shows the working tree status",
            schema=GitStatus.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_diff_unstaged",
            implementation=wrap_repo_op(git_ops.git_diff_unstaged),
            description="Shows changes in the working directory that are not yet staged",
            schema=GitDiffUnstaged.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_diff_staged",
            implementation=wrap_repo_op(git_ops.git_diff_staged),
            description="Shows changes that are staged for commit",
            schema=GitDiffStaged.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_diff",
            implementation=wrap_repo_op(git_ops.git_diff),
            description="Shows differences between branches or commits",
            schema=GitDiff.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_commit",
            implementation=wrap_repo_op(git_ops.git_commit),
            description="Records changes to the repository",
            schema=GitCommit.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_add",
            implementation=wrap_repo_op(git_ops.git_add),
            description="Adds file contents to the staging area",
            schema=GitAdd.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_reset",
            implementation=wrap_repo_op(git_ops.git_reset),
            description="Reset repository with advanced options (--soft, --mixed, --hard)",
            schema=GitReset.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_log",
            implementation=wrap_repo_op(git_ops.git_log),
            description="Shows the commit logs",
            schema=GitLog.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_create_branch",
            implementation=wrap_repo_op(git_ops.git_create_branch),
            description="Creates a new branch from an optional base branch",
            schema=GitCreateBranch.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_checkout",
            implementation=wrap_repo_op(git_ops.git_checkout),
            description="Switches branches",
            schema=GitCheckout.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_show",
            implementation=wrap_repo_op(git_ops.git_show),
            description="Shows the contents of a commit",
            schema=GitShow.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_init",
            implementation=git_ops.git_init,  # git_init takes path directly, not Repo
            description="Initialize a new Git repository",
            schema=GitInit.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_push",
            implementation=wrap_repo_op(git_ops.git_push),
            description="Push commits to remote repository",
            schema=GitPush.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_pull",
            implementation=wrap_repo_op(git_ops.git_pull),
            description="Pull changes from remote repository",
            schema=GitPull.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_diff_branches",
            implementation=wrap_repo_op(git_ops.git_diff_branches),
            description="Show differences between two branches",
            schema=GitDiffBranches.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_rebase",
            implementation=wrap_repo_op(git_ops.git_rebase),
            description="Rebase current branch onto another branch",
            schema=GitRebase.model_json_schema(),
            domain="git",
            complexity="advanced",
        ),
        ToolDefinition(
            name="git_merge",
            implementation=wrap_repo_op(git_ops.git_merge),
            description="Merge a branch into the current branch",
            schema=GitMerge.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_cherry_pick",
            implementation=wrap_repo_op(git_ops.git_cherry_pick),
            description="Apply a commit from another branch to current branch",
            schema=GitCherryPick.model_json_schema(),
            domain="git",
            complexity="advanced",
        ),
        ToolDefinition(
            name="git_abort",
            implementation=wrap_repo_op(git_ops.git_abort),
            description="Abort an in-progress git operation (rebase, merge, cherry-pick)",
            schema=GitAbort.model_json_schema(),
            domain="git",
            complexity="advanced",
        ),
        ToolDefinition(
            name="git_continue",
            implementation=wrap_repo_op(git_ops.git_continue),
            description="Continue an in-progress git operation after resolving conflicts",
            schema=GitContinue.model_json_schema(),
            domain="git",
            complexity="advanced",
        ),
        # Remote operations
        ToolDefinition(
            name="git_fetch",
            implementation=wrap_repo_op(git_ops.git_fetch),
            description="Fetch changes from remote repository",
            schema={
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "remote": {"type": "string"},
                },
            },
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_remote_add",
            implementation=wrap_repo_op(git_ops.git_remote_add),
            description="Add a remote repository",
            schema={
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "name": {"type": "string"},
                    "url": {"type": "string"},
                },
            },
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_remote_remove",
            implementation=wrap_repo_op(git_ops.git_remote_remove),
            description="Remove a remote repository",
            schema={
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "name": {"type": "string"},
                },
            },
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_remote_list",
            implementation=wrap_repo_op(git_ops.git_remote_list),
            description="List remote repositories",
            schema={"type": "object", "properties": {"repo_path": {"type": "string"}}},
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_remote_get_url",
            implementation=wrap_repo_op(git_ops.git_remote_get_url),
            description="Get URL of a remote repository",
            schema={
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "name": {"type": "string"},
                },
            },
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_merge_base",
            implementation=wrap_repo_op(git_ops.git_merge_base),
            description="Find the common ancestor (merge-base) of two references",
            schema=GitMergeBase.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        # Stash operations
        ToolDefinition(
            name="git_stash_list",
            implementation=wrap_repo_op(git_ops.git_stash_list),
            description="List all stashes in the repository",
            schema={
                "type": "object",
                "properties": {"repo_path": {"type": "string"}},
                "required": ["repo_path"],
            },
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_stash_push",
            implementation=wrap_repo_op(git_ops.git_stash_push),
            description="Create a new stash with optional message",
            schema={
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "message": {
                        "type": "string",
                        "description": "Optional stash message",
                    },
                    "include_untracked": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include untracked files",
                    },
                },
                "required": ["repo_path"],
            },
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_stash_pop",
            implementation=wrap_repo_op(git_ops.git_stash_pop),
            description="Apply and remove a stash (defaults to latest)",
            schema={
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "stash_id": {
                        "type": "string",
                        "description": "Stash ID (e.g., stash@{0}), defaults to latest",
                    },
                },
                "required": ["repo_path"],
            },
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_stash_drop",
            implementation=wrap_repo_op(git_ops.git_stash_drop),
            description="Remove a stash without applying it",
            schema={
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "stash_id": {
                        "type": "string",
                        "description": "Stash ID (e.g., stash@{0}), defaults to latest",
                    },
                },
                "required": ["repo_path"],
            },
            domain="git",
            complexity="core",
        ),
        # Submodule operations
        ToolDefinition(
            name="git_submodule_status",
            implementation=wrap_repo_op(git_ops.git_submodule_status),
            description="List submodules and their current status (paths, SHAs, branches)",
            schema=GitSubmoduleStatus.model_json_schema(),
            domain="git",
            complexity="focused",
        ),
        ToolDefinition(
            name="git_submodule_add",
            implementation=wrap_repo_op(git_ops.git_submodule_add),
            description="Add a new submodule to the repository",
            schema=GitSubmoduleAdd.model_json_schema(),
            domain="git",
            complexity="focused",
        ),
        ToolDefinition(
            name="git_submodule_update",
            implementation=wrap_repo_op(git_ops.git_submodule_update),
            description="Update submodules (init, recursive, or from remote)",
            schema=GitSubmoduleUpdate.model_json_schema(),
            domain="git",
            complexity="focused",
        ),
        ToolDefinition(
            name="git_submodule_sync",
            implementation=wrap_repo_op(git_ops.git_submodule_sync),
            description="Sync submodule URLs from .gitmodules to .git/config",
            schema=GitSubmoduleSync.model_json_schema(),
            domain="git",
            complexity="focused",
        ),
        # Config operations
        ToolDefinition(
            name="git_config_get",
            implementation=wrap_repo_op(git_ops.git_config_get),
            description="Read a git config value by key",
            schema=GitConfigGet.model_json_schema(),
            domain="git",
            complexity="focused",
        ),
        ToolDefinition(
            name="git_config_set",
            implementation=wrap_repo_op(git_ops.git_config_set),
            description="Set a git config value (key/value, optional scope or file)",
            schema=GitConfigSet.model_json_schema(),
            domain="git",
            complexity="focused",
        ),
        ToolDefinition(
            name="git_config_list",
            implementation=wrap_repo_op(git_ops.git_config_list),
            description="List all git config entries (optionally scoped or from a specific file)",
            schema=GitConfigList.model_json_schema(),
            domain="git",
            complexity="focused",
        ),
        ToolDefinition(
            name="git_restore",
            implementation=wrap_repo_op(git_restore),
            description="Restore working tree files or unstage files (git restore / git restore --staged)",
            schema=GitRestore.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_branch_update",
            implementation=wrap_repo_op(git_branch_update),
            description="Force-update a branch ref or delete a branch",
            schema=GitBranchUpdate.model_json_schema(),
            domain="git",
            complexity="focused",
        ),
        ToolDefinition(
            name="git_worktree_list",
            implementation=wrap_repo_op(git_worktree_list),
            description="List all worktrees in the repository",
            schema=GitWorktreeList.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_worktree_remove",
            implementation=wrap_repo_op(git_worktree_remove),
            description="Remove a worktree (with optional force for modified worktrees)",
            schema=GitWorktreeRemove.model_json_schema(),
            domain="git",
            complexity="focused",
        ),
        ToolDefinition(
            name="git_merge_tree",
            implementation=wrap_repo_op(git_merge_tree),
            description="Dry-run merge conflict detection without modifying working tree",
            schema=GitMergeTree.model_json_schema(),
            domain="git",
            complexity="focused",
        ),
    ]

    for tool in git_tools:
        interface.register_tool(tool)

    logger.info(f"Registered {len(git_tools)} Git tools")
