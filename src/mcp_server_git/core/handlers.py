"""Tool call handlers for MCP Git Server"""

import logging
from pathlib import Path
from typing import Any


# Safe git import that handles ClaudeCode redirector conflicts
from ..utils.git_import import Repo, git
from .tools import GitToolRouter, ToolRegistry

logger = logging.getLogger(__name__)


class CallToolHandler:
    """Centralized tool call handler using the router system"""

    def __init__(self):
        self.registry = ToolRegistry()
        self.router = GitToolRouter(self.registry)
        self._setup_handlers()

    def _setup_handlers(self):
        """Set up all tool handlers"""
        self.registry.initialize_default_tools()

        # Try to use modular components, fall back to original
        git_handlers = self._get_git_handlers()
        github_handlers = self._get_github_handlers()
        security_handlers = self._get_security_handlers()

        self.router.set_handlers(git_handlers, github_handlers, security_handlers)

    def _get_git_handlers(self) -> dict[str, Any]:
        """Get Git operation handlers from modular implementation"""
        from ..git.operations import (
            git_abort,
            git_add,
            git_checkout,
            git_cherry_pick,
            git_commit,
            git_continue,
            git_create_branch,
            git_diff,
            git_diff_branches,
            git_diff_staged,
            git_diff_unstaged,
            git_init,
            git_log,
            git_merge,
            git_pull,
            git_push,
            git_rebase,
            git_reset,
            git_show,
            git_status,
        )

        logger.debug("Using modular Git operations")

        return {
            "git_status": self._create_git_handler(git_status, requires_repo=True),
            "git_diff_unstaged": self._create_git_handler(
                git_diff_unstaged,
                requires_repo=True,
                extra_args=["stat_only", "max_lines", "name_only", "paths"],
            ),
            "git_diff_staged": self._create_git_handler(
                git_diff_staged,
                requires_repo=True,
                extra_args=["stat_only", "max_lines", "name_only", "paths"],
            ),
            "git_diff": self._create_git_handler(
                git_diff,
                requires_repo=True,
                extra_args=["target", "stat_only", "max_lines", "name_only", "paths"],
            ),
            "git_commit": self._create_git_handler(
                git_commit,
                requires_repo=True,
                extra_args=["message", "gpg_sign", "gpg_key_id"],
            ),
            "git_add": self._create_git_handler(
                git_add, requires_repo=True, extra_args=["files"]
            ),
            "git_reset": self._create_git_handler(git_reset, requires_repo=True),
            "git_log": self._create_git_handler(
                git_log,
                requires_repo=True,
                extra_args=["max_count", "oneline", "graph", "format"],
            ),
            "git_create_branch": self._create_git_handler(
                git_create_branch,
                requires_repo=True,
                extra_args=["branch_name", "base_branch"],
            ),
            "git_checkout": self._create_git_handler(
                git_checkout, requires_repo=True, extra_args=["branch_name"]
            ),
            "git_show": self._create_git_handler(
                git_show, requires_repo=True, extra_args=["revision"]
            ),
            "git_init": self._create_git_init_handler(git_init),
            "git_push": self._create_git_handler(
                git_push,
                requires_repo=True,
                extra_args=["remote", "branch", "set_upstream", "force"],
            ),
            "git_pull": self._create_git_handler(
                git_pull, requires_repo=True, extra_args=["remote", "branch"]
            ),
            "git_diff_branches": self._create_git_handler(
                git_diff_branches,
                requires_repo=True,
                extra_args=["base_branch", "compare_branch"],
            ),
            "git_rebase": self._create_git_handler(
                git_rebase,
                requires_repo=True,
                extra_args=["target_branch"],
            ),
            "git_merge": self._create_git_handler(
                git_merge,
                requires_repo=True,
                extra_args=["source_branch", "strategy", "message"],
            ),
            "git_cherry_pick": self._create_git_handler(
                git_cherry_pick,
                requires_repo=True,
                extra_args=["commit_hash", "no_commit"],
            ),
            "git_abort": self._create_git_handler(
                git_abort, requires_repo=True, extra_args=["operation"]
            ),
            "git_continue": self._create_git_handler(
                git_continue, requires_repo=True, extra_args=["operation"]
            ),
        }

    def _get_github_handlers(self) -> dict[str, Any]:
        """Get GitHub API handlers from modular implementation"""
        # Import all GitHub API functions from modular implementation
        try:
            from ..github.api import (
                github_bulk_update_issues,
                github_create_issue,
                github_create_issue_from_template,
                github_edit_pr_description,
                github_get_failing_jobs,
                github_get_pr_checks,
                github_get_pr_details,
                github_get_pr_files,
                github_get_pr_status,
                github_get_workflow_run,
                github_list_workflow_runs,
                github_list_issues,
                github_list_pull_requests,
                github_search_issues,
                github_update_issue,
            )

            logger.debug("Using modular GitHub API")
        except ImportError:
            logger.warning("GitHub API module not available, using fallback")

            # Define fallback function for when GitHub API is not available
            async def fallback_github_function(*args, **kwargs):
                return "❌ GitHub API not available"

            # Use fallback for all functions
            (
                github_bulk_update_issues,
                github_create_issue,
                github_create_issue_from_template,
                github_edit_pr_description,
                github_get_failing_jobs,
                github_get_pr_checks,
                github_get_pr_details,
                github_get_pr_files,
                github_get_pr_status,
                github_get_workflow_run,
                github_list_workflow_runs,
                github_list_issues,
                github_list_pull_requests,
                github_search_issues,
                github_update_issue,
            ) = [fallback_github_function] * 15

        return {
            "github_get_pr_checks": self._create_github_handler(
                github_get_pr_checks,
                ["repo_owner", "repo_name", "pr_number", "status", "conclusion"],
            ),
            "github_get_failing_jobs": self._create_github_handler(
                github_get_failing_jobs,
                [
                    "repo_owner",
                    "repo_name",
                    "pr_number",
                    "include_logs",
                    "include_annotations",
                ],
            ),
            "github_get_workflow_run": self._create_github_handler(
                github_get_workflow_run,
                ["repo_owner", "repo_name", "run_id", "include_logs"],
            ),
            "github_list_workflow_runs": self._create_github_handler(
                github_list_workflow_runs,
                [
                    "repo_owner",
                    "repo_name",
                    "workflow_id",
                    "actor",
                    "branch",
                    "event",
                    "status",
                    "conclusion",
                    "per_page",
                    "page",
                    "created",
                    "exclude_pull_requests",
                    "check_suite_id",
                    "head_sha",
                ],
            ),
            "github_get_pr_details": self._create_github_handler(
                github_get_pr_details,
                [
                    "repo_owner",
                    "repo_name",
                    "pr_number",
                    "include_files",
                    "include_reviews",
                ],
            ),
            "github_list_pull_requests": self._create_github_handler(
                github_list_pull_requests,
                [
                    "repo_owner",
                    "repo_name",
                    "state",
                    "head",
                    "base",
                    "sort",
                    "direction",
                    "per_page",
                    "page",
                ],
            ),
            "github_get_pr_status": self._create_github_handler(
                github_get_pr_status, ["repo_owner", "repo_name", "pr_number"]
            ),
            "github_get_pr_files": self._create_github_handler(
                github_get_pr_files,
                [
                    "repo_owner",
                    "repo_name",
                    "pr_number",
                    "per_page",
                    "page",
                    "include_patch",
                ],
            ),
            "github_create_issue": self._create_github_handler(
                github_create_issue,
                [
                    "repo_owner",
                    "repo_name",
                    "title",
                    "body",
                    "labels",
                    "assignees",
                    "milestone",
                ],
            ),
            "github_list_issues": self._create_github_handler(
                github_list_issues,
                [
                    "repo_owner",
                    "repo_name",
                    "state",
                    "labels",
                    "assignee",
                    "creator",
                    "mentioned",
                    "milestone",
                    "sort",
                    "direction",
                    "since",
                    "per_page",
                    "page",
                ],
            ),
            "github_update_issue": self._create_github_handler(
                github_update_issue,
                [
                    "repo_owner",
                    "repo_name",
                    "issue_number",
                    "title",
                    "body",
                    "state",
                    "labels",
                    "assignees",
                    "milestone",
                ],
            ),
            "github_edit_pr_description": self._create_github_handler(
                github_edit_pr_description,
                ["repo_owner", "repo_name", "pr_number", "description"],
            ),
            "github_search_issues": self._create_github_handler(
                github_search_issues,
                [
                    "repo_owner",
                    "repo_name",
                    "query",
                    "sort",
                    "order",
                    "per_page",
                    "page",
                ],
            ),
            "github_create_issue_from_template": self._create_github_handler(
                github_create_issue_from_template,
                [
                    "repo_owner",
                    "repo_name",
                    "title",
                    "template_name",
                    "template_data",
                ],
            ),
            "github_bulk_update_issues": self._create_github_handler(
                github_bulk_update_issues,
                [
                    "repo_owner",
                    "repo_name",
                    "issue_numbers",
                    "labels",
                    "assignees",
                    "milestone",
                    "state",
                ],
            ),
        }

    def _get_security_handlers(self) -> dict[str, Any]:
        """Get security handlers (modular or original)"""
        from ..git.security import (
            enforce_secure_git_config,
            validate_git_security_config,
        )

        logger.debug("Using modular security functions")

        return {
            "git_security_validate": self._create_security_handler(
                validate_git_security_config
            ),
            "git_security_enforce": self._create_security_handler(
                enforce_secure_git_config, extra_args=["strict_mode"]
            ),
        }

    def _create_git_handler(
        self, func, requires_repo: bool = True, extra_args: list[str] | None = None
    ):
        """Create a wrapper for Git operation functions"""

        def handler(**kwargs):
            if requires_repo:
                repo_path = Path(kwargs["repo_path"])
                repo: Repo = git.Repo(repo_path)

                # Build arguments
                args: list[Any] = [repo]
                if extra_args:
                    for arg in extra_args:
                        if arg in kwargs:
                            args.append(kwargs[arg])
                        elif arg == "gpg_sign":
                            args.append(kwargs.get(arg, False))
                        elif arg == "gpg_key_id":
                            args.append(kwargs.get(arg, None))
                        elif arg in ["max_count", "per_page", "page"]:
                            args.append(
                                kwargs.get(arg, 10 if arg == "max_count" else 30)
                            )
                        elif arg in [
                            "oneline",
                            "graph",
                            "set_upstream",
                            "force",
                            "no_commit",
                            "stat_only",
                            "name_only",
                        ]:
                            args.append(kwargs.get(arg, False))
                        elif arg in ["remote"]:
                            args.append(kwargs.get(arg, "origin"))
                        elif arg in ["strategy"]:
                            args.append(kwargs.get(arg, "merge"))
                        elif arg == "base_branch":
                            # Use base_branch parameter directly for git operations
                            args.append(kwargs.get(arg))
                        else:
                            args.append(kwargs.get(arg))

                return func(*args)
            else:
                return func(**kwargs)

        return handler

    def _create_git_init_handler(self, func):
        """Special handler for git_init which doesn't need a repo object"""

        def handler(**kwargs):
            repo_path = kwargs["repo_path"]
            return func(repo_path)

        return handler

    def _create_github_handler(self, func, arg_names: list[str]):
        """Create a wrapper for GitHub API functions"""

        async def handler(**kwargs):
            # Build arguments in the correct order
            args = []
            for arg_name in arg_names:
                if arg_name in kwargs:
                    args.append(kwargs[arg_name])
                elif arg_name in [
                    "status",
                    "conclusion",
                    "head",
                    "base",
                    "branch",
                    "message",
                    "format",
                ]:
                    args.append(kwargs.get(arg_name, None))
                elif arg_name in [
                    "include_logs",
                    "include_annotations",
                    "include_files",
                    "include_reviews",
                    "include_patch",
                ]:
                    args.append(
                        kwargs.get(arg_name, False if "include" in arg_name else True)
                    )
                elif arg_name in ["per_page"]:
                    args.append(kwargs.get(arg_name, 30))
                elif arg_name in ["page"]:
                    args.append(kwargs.get(arg_name, 1))
                elif arg_name == "state":
                    args.append(kwargs.get(arg_name, "open"))
                elif arg_name == "sort":
                    args.append(kwargs.get(arg_name, "created"))
                elif arg_name == "direction":
                    args.append(kwargs.get(arg_name, "desc"))
                else:
                    args.append(kwargs.get(arg_name))

            return await func(*args)

        return handler

    def _create_security_handler(self, func, extra_args: list[str] | None = None):
        """Create a wrapper for security functions"""

        def handler(**kwargs):
            args = []
            if extra_args:
                for arg in extra_args:
                    if arg == "strict_mode":
                        args.append(kwargs.get(arg, False))
                    else:
                        args.append(kwargs.get(arg))

            return func(*args) if args else func()

        return handler
