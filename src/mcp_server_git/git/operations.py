"""Git operations for MCP Git Server (re-export shim).

Decomposed for AG file-size policy. See _*_ops.py modules for implementations.
Public API preserved: tests and `git/__init__.py` continue to import from here.
"""

from ._diff_ops import (
    _apply_diff_size_limiting,
    _validate_commit_range,
    _validate_diff_parameters,
    git_diff,
    git_diff_branches,
    git_diff_staged,
    git_diff_unstaged,
)
from ._commit_ops import (
    git_blame,
    git_commit,
    git_log,
    git_show,
    git_status,
)
from ._staging_ops import git_add, git_reset
from ._branch_ops import (
    git_branch_list,
    git_checkout,
    git_create_branch,
    git_merge_base,
)
from ._init_ops import git_init
from ._remote_ops import (
    git_clone,
    git_fetch,
    git_pull,
    git_push,
    git_remote_add,
    git_remote_get_url,
    git_remote_list,
    git_remote_remove,
    git_remote_rename,
    git_remote_set_url,
)
from ._rebase_ops import (
    git_abort,
    git_cherry_pick,
    git_continue,
    git_merge,
    git_rebase,
)
from ._stash_ops import (
    git_stash_drop,
    git_stash_list,
    git_stash_pop,
    git_stash_push,
)
from ._tag_ops import git_tag_create, git_tag_delete, git_tag_list
from ._submodule_ops import (
    git_submodule_add,
    git_submodule_status,
    git_submodule_sync,
    git_submodule_update,
)
from ._config_ops import (
    _validate_config_file,
    _validate_config_key,
    git_config_get,
    git_config_list,
    git_config_set,
)

__all__ = [
    "git_clone",
    "git_status",
    "git_diff_unstaged",
    "git_diff_staged",
    "git_diff",
    "git_commit",
    "git_add",
    "git_reset",
    "git_log",
    "git_show",
    "git_init",
    "git_push",
    "git_pull",
    "git_create_branch",
    "git_checkout",
    "git_merge",
    "git_rebase",
    "git_cherry_pick",
    "git_abort",
    "git_continue",
    "git_fetch",
    "git_remote_add",
    "git_remote_remove",
    "git_remote_list",
    "git_remote_get_url",
    "git_remote_rename",
    "git_remote_set_url",
    "git_diff_branches",
    "git_stash_list",
    "git_stash_push",
    "git_stash_pop",
    "git_stash_drop",
    "git_tag_list",
    "git_tag_create",
    "git_tag_delete",
    "git_blame",
    "git_branch_list",
    "git_merge_base",
    "git_submodule_status",
    "git_submodule_add",
    "git_submodule_update",
    "git_submodule_sync",
    "git_config_get",
    "git_config_set",
    "git_config_list",
    # Private helpers re-exported for test compatibility
    "_apply_diff_size_limiting",
    "_validate_commit_range",
    "_validate_diff_parameters",
    "_validate_config_file",
    "_validate_config_key",
]
