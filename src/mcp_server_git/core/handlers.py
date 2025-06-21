"""Tool call handlers for MCP Git Server"""

import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

import git
from mcp.types import TextContent

from .tools import GitToolRouter, ToolRegistry, ToolCategory

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
    
    def _get_git_handlers(self) -> Dict[str, Any]:
        """Get Git operation handlers (modular or original)"""
        try:
            from ..git.operations import (
                git_status, git_diff_unstaged, git_diff_staged, git_diff,
                git_commit, git_add, git_reset, git_log, git_create_branch,
                git_checkout, git_show, git_init, git_push, git_pull,
                git_diff_branches, git_rebase, git_merge, git_cherry_pick,
                git_abort, git_continue
            )
            logger.debug("Using modular Git operations")
            use_modular = True
        except ImportError:
            from ..server import (
                git_status, git_diff_unstaged, git_diff_staged, git_diff,
                git_commit, git_add, git_reset, git_log, git_create_branch,
                git_checkout, git_show, git_init, git_push, git_pull,
                git_diff_branches, git_rebase, git_merge, git_cherry_pick,
                git_abort, git_continue
            )
            logger.debug("Using original Git operations")
            use_modular = False
        
        return {
            "git_status": self._create_git_handler(git_status, requires_repo=True),
            "git_diff_unstaged": self._create_git_handler(git_diff_unstaged, requires_repo=True),
            "git_diff_staged": self._create_git_handler(git_diff_staged, requires_repo=True),
            "git_diff": self._create_git_handler(git_diff, requires_repo=True, extra_args=["target"]),
            "git_commit": self._create_git_handler(git_commit, requires_repo=True, extra_args=["message", "gpg_sign", "gpg_key_id"]),
            "git_add": self._create_git_handler(git_add, requires_repo=True, extra_args=["files"]),
            "git_reset": self._create_git_handler(git_reset, requires_repo=True),
            "git_log": self._create_git_handler(git_log, requires_repo=True, extra_args=["max_count", "oneline", "graph", "format"]),
            "git_create_branch": self._create_git_handler(git_create_branch, requires_repo=True, extra_args=["branch_name", "base_branch"]),
            "git_checkout": self._create_git_handler(git_checkout, requires_repo=True, extra_args=["branch_name"]),
            "git_show": self._create_git_handler(git_show, requires_repo=True, extra_args=["revision"]),
            "git_init": self._create_git_init_handler(git_init),
            "git_push": self._create_git_handler(git_push, requires_repo=True, extra_args=["remote", "branch", "set_upstream", "force"]),
            "git_pull": self._create_git_handler(git_pull, requires_repo=True, extra_args=["remote", "branch"]),
            "git_diff_branches": self._create_git_handler(git_diff_branches, requires_repo=True, extra_args=["base_branch", "compare_branch"]),
            "git_rebase": self._create_git_handler(git_rebase, requires_repo=True, extra_args=["target_branch", "interactive"]),
            "git_merge": self._create_git_handler(git_merge, requires_repo=True, extra_args=["source_branch", "strategy", "message"]),
            "git_cherry_pick": self._create_git_handler(git_cherry_pick, requires_repo=True, extra_args=["commit_hash", "no_commit"]),
            "git_abort": self._create_git_handler(git_abort, requires_repo=True, extra_args=["operation"]),
            "git_continue": self._create_git_handler(git_continue, requires_repo=True, extra_args=["operation"]),
        }
    
    def _get_github_handlers(self) -> Dict[str, Any]:
        """Get GitHub API handlers (modular or original)"""
        try:
            from ..github.api import (
                github_get_pr_checks, github_get_failing_jobs,
                github_get_workflow_run, github_get_pr_details,
                github_list_pull_requests, github_get_pr_status,
                github_get_pr_files
            )
            logger.debug("Using modular GitHub API")
            use_modular = True
        except ImportError:
            from ..server import (
                github_get_pr_checks, github_get_failing_jobs,
                github_get_workflow_run, github_get_pr_details,
                github_list_pull_requests, github_get_pr_status,
                github_get_pr_files
            )
            logger.debug("Using original GitHub API")
            use_modular = False
        
        return {
            "github_get_pr_checks": self._create_github_handler(github_get_pr_checks, ["repo_owner", "repo_name", "pr_number", "status", "conclusion"]),
            "github_get_failing_jobs": self._create_github_handler(github_get_failing_jobs, ["repo_owner", "repo_name", "pr_number", "include_logs", "include_annotations"]),
            "github_get_workflow_run": self._create_github_handler(github_get_workflow_run, ["repo_owner", "repo_name", "run_id", "include_logs"]),
            "github_get_pr_details": self._create_github_handler(github_get_pr_details, ["repo_owner", "repo_name", "pr_number", "include_files", "include_reviews"]),
            "github_list_pull_requests": self._create_github_handler(github_list_pull_requests, ["repo_owner", "repo_name", "state", "head", "base", "sort", "direction", "per_page", "page"]),
            "github_get_pr_status": self._create_github_handler(github_get_pr_status, ["repo_owner", "repo_name", "pr_number"]),
            "github_get_pr_files": self._create_github_handler(github_get_pr_files, ["repo_owner", "repo_name", "pr_number", "per_page", "page", "include_patch"]),
        }
    
    def _get_security_handlers(self) -> Dict[str, Any]:
        """Get security handlers (modular or original)"""
        try:
            from ..git.security import validate_git_security_config, enforce_secure_git_config
            logger.debug("Using modular security functions")
        except ImportError:
            from ..server import validate_git_security_config, enforce_secure_git_config
            logger.debug("Using original security functions")
        
        return {
            "git_security_validate": self._create_security_handler(validate_git_security_config),
            "git_security_enforce": self._create_security_handler(enforce_secure_git_config, extra_args=["strict_mode"]),
        }
    
    def _create_git_handler(self, func, requires_repo: bool = True, extra_args: Optional[List[str]] = None):
        """Create a wrapper for Git operation functions"""
        def handler(**kwargs):
            if requires_repo:
                repo_path = Path(kwargs["repo_path"])
                repo = git.Repo(repo_path)
                
                # Build arguments
                args = [repo]
                if extra_args:
                    for arg in extra_args:
                        if arg in kwargs:
                            args.append(kwargs[arg])
                        elif arg == "gpg_sign":
                            args.append(kwargs.get(arg, False))
                        elif arg == "gpg_key_id":
                            args.append(kwargs.get(arg, None))
                        elif arg in ["max_count", "per_page", "page"]:
                            args.append(kwargs.get(arg, 10 if arg == "max_count" else 30))
                        elif arg in ["oneline", "graph", "interactive", "set_upstream", "force", "no_commit"]:
                            args.append(kwargs.get(arg, False))
                        elif arg in ["remote"]:
                            args.append(kwargs.get(arg, "origin"))
                        elif arg in ["strategy"]:
                            args.append(kwargs.get(arg, "merge"))
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
    
    def _create_github_handler(self, func, arg_names: List[str]):
        """Create a wrapper for GitHub API functions"""
        async def handler(**kwargs):
            # Build arguments in the correct order
            args = []
            for arg_name in arg_names:
                if arg_name in kwargs:
                    args.append(kwargs[arg_name])
                elif arg_name in ["status", "conclusion", "head", "base", "branch", "message", "format"]:
                    args.append(kwargs.get(arg_name, None))
                elif arg_name in ["include_logs", "include_annotations", "include_files", "include_reviews", "include_patch"]:
                    args.append(kwargs.get(arg_name, False if "include" in arg_name else True))
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
    
    def _create_security_handler(self, func, extra_args: Optional[List[str]] = None):
        """Create a wrapper for security functions"""
        def handler(**kwargs):
            repo_path = Path(kwargs["repo_path"])
            repo = git.Repo(repo_path)
            
            args = [repo]
            if extra_args:
                for arg in extra_args:
                    if arg == "strict_mode":
                        args.append(kwargs.get(arg, True))
                    else:
                        args.append(kwargs.get(arg))
            
            result = func(*args)
            
            # Handle security validation results
            if isinstance(result, dict):
                # Format validation results
                status_emoji = "✅" if result["status"] == "secure" else "⚠️"
                result_text = f"{status_emoji} Git Security Validation Results\n\n"
                
                if result.get("warnings"):
                    result_text += "Security Warnings:\n"
                    for warning in result["warnings"]:
                        result_text += f"  - {warning}\n"
                    result_text += "\n"
                
                if result.get("recommendations"):
                    result_text += "Recommendations:\n"
                    for rec in result["recommendations"]:
                        result_text += f"  - {rec}\n"
                    result_text += "\n"
                
                result_text += f"Overall Status: {result['status']}"
                return result_text
            else:
                return result
        
        return handler
    
    async def call_tool(self, name: str, arguments: dict) -> List[TextContent]:
        """Main tool call entry point with improved logging and routing"""
        request_id = os.urandom(4).hex()
        logger.info(f"🔧 [{request_id}] Tool call: {name}")
        logger.debug(f"🔧 [{request_id}] Arguments: {arguments}")
        
        start_time = time.time()
        
        try:
            logger.debug(f"🔍 [{request_id}] Starting tool execution via router")
            result = await self.router.route_tool_call(name, arguments)
            
            duration = time.time() - start_time
            logger.debug(f"🔍 [{request_id}] Tool execution finished, result type: {type(result)}")
            if result and len(result) > 0:
                logger.debug(f"🔍 [{request_id}] Result[0] type: {type(result[0])}, content preview: {str(result[0])[:200]}")
            logger.info(f"✅ [{request_id}] Tool '{name}' completed in {duration:.2f}s")
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"❌ [{request_id}] Tool '{name}' failed after {duration:.2f}s: {e}", exc_info=True)
            return [TextContent(type="text", text=f"Error in {name}: {str(e)}")]