"""Bundle tool definitions for the git domain (issue #283).

Kept apart from ``registry_git.py`` (size budget). ``wrap_repo_op`` is the
wrapper defined inside ``_register_git_tools`` and is passed in so these tools
share its Repo resolution and error shaping. Bundles only read the repository,
so neither tool is ``mutates_index``.

The #283 history filter (``git_filter_paths``, which takes the bundle backup
first) is defined in ``registry_git_filter.py`` and appended here, so the
oversized ``registry_git.py`` needs no new lines.
"""

from collections.abc import Callable
from typing import Any

from ..git._bundle_ops import git_bundle_create, git_bundle_verify
from ..git.models_bundle import GitBundleCreate, GitBundleVerify
from .interface import ToolDefinition
from .registry_git_filter import filter_tool_definitions
from .registry_git_maintenance import maintenance_tool_definitions


def bundle_tool_definitions(wrap_repo_op: Callable[..., Any]) -> list[ToolDefinition]:
    """ToolDefinitions for the bundle tools and git_filter_paths (#283)."""
    return [
        *filter_tool_definitions(wrap_repo_op),
        *maintenance_tool_definitions(wrap_repo_op),
        ToolDefinition(
            name="git_bundle_create",
            implementation=wrap_repo_op(git_bundle_create),
            description=(
                "Create a git bundle backup file (default all refs); refuses to "
                "overwrite an existing file unless overwrite=True"
            ),
            schema=GitBundleCreate.model_json_schema(),
            domain="git",
            complexity="focused",
        ),
        ToolDefinition(
            name="git_bundle_verify",
            implementation=wrap_repo_op(git_bundle_verify),
            description="Verify a git bundle file is valid and applicable to the repository",
            schema=GitBundleVerify.model_json_schema(),
            domain="git",
            complexity="focused",
        ),
    ]
