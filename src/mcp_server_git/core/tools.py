"""Tool registry and routing system for MCP Git Server"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Callable, Any

from mcp.types import Tool, TextContent
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class GitTools(str, Enum):
    """Enumeration of all available Git tools"""
    # Git operations
    STATUS = "git_status"
    DIFF_UNSTAGED = "git_diff_unstaged"
    DIFF_STAGED = "git_diff_staged"
    DIFF = "git_diff"
    COMMIT = "git_commit"
    ADD = "git_add"
    RESET = "git_reset"
    LOG = "git_log"
    CREATE_BRANCH = "git_create_branch"
    CHECKOUT = "git_checkout"
    SHOW = "git_show"
    INIT = "git_init"
    PUSH = "git_push"
    PULL = "git_pull"
    DIFF_BRANCHES = "git_diff_branches"
    REBASE = "git_rebase"
    MERGE = "git_merge"
    CHERRY_PICK = "git_cherry_pick"
    ABORT = "git_abort"
    CONTINUE = "git_continue"
    
    # GitHub API tools
    GITHUB_GET_PR_CHECKS = "github_get_pr_checks"
    GITHUB_GET_FAILING_JOBS = "github_get_failing_jobs"
    GITHUB_GET_WORKFLOW_RUN = "github_get_workflow_run"
    GITHUB_GET_PR_DETAILS = "github_get_pr_details"
    GITHUB_LIST_PULL_REQUESTS = "github_list_pull_requests"
    GITHUB_GET_PR_STATUS = "github_get_pr_status"
    GITHUB_GET_PR_FILES = "github_get_pr_files"
    
    # Security tools
    GIT_SECURITY_VALIDATE = "git_security_validate"
    GIT_SECURITY_ENFORCE = "git_security_enforce"


class ToolCategory(str, Enum):
    """Tool categories for organization and routing"""
    GIT = "git"
    GITHUB = "github"
    SECURITY = "security"


@dataclass
class ToolDefinition:
    """Complete tool definition with metadata"""
    name: str
    category: ToolCategory
    description: str
    schema: BaseModel
    handler: Callable
    requires_repo: bool = True
    requires_github_token: bool = False


class ToolRegistry:
    """Central registry for all MCP Git Server tools"""
    
    def __init__(self):
        self.tools: Dict[str, ToolDefinition] = {}
        self._initialized = False
    
    def register(self, tool_def: ToolDefinition):
        """Register a tool in the registry"""
        self.tools[tool_def.name] = tool_def
        logger.debug(f"Registered tool: {tool_def.name} ({tool_def.category})")
    
    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Get tool definition by name"""
        return self.tools.get(name)
    
    def list_tools(self) -> List[Tool]:
        """Get all tools as MCP Tool objects"""
        return [
            Tool(
                name=tool_def.name,
                description=tool_def.description,
                inputSchema=tool_def.schema.model_json_schema()
            )
            for tool_def in self.tools.values()
        ]
    
    def get_tools_by_category(self, category: ToolCategory) -> List[ToolDefinition]:
        """Get all tools in a specific category"""
        return [
            tool_def for tool_def in self.tools.values()
            if tool_def.category == category
        ]
    
    def initialize_default_tools(self):
        """Initialize registry with default Git server tools"""
        if self._initialized:
            return
        
        # Import models and handlers
        from ..git.models import (
            GitStatus, GitDiffUnstaged, GitDiffStaged, GitDiff, GitCommit,
            GitAdd, GitReset, GitLog, GitCreateBranch, GitCheckout, GitShow,
            GitInit, GitPush, GitPull, GitDiffBranches, GitRebase, GitMerge,
            GitCherryPick, GitAbort, GitContinue, GitSecurityValidate,
            GitSecurityEnforce
        )
        from ..github.models import (
            GitHubGetPRChecks, GitHubGetFailingJobs, GitHubGetWorkflowRun,
            GitHubGetPRDetails, GitHubListPullRequests, GitHubGetPRStatus,
            GitHubGetPRFiles
        )
        
        # Import handlers (will be set by the router)
        placeholder_handler = lambda *args, **kwargs: "Handler not set"
        
        # Register Git tools
        git_tools = [
            ToolDefinition(
                name=GitTools.STATUS,
                category=ToolCategory.GIT,
                description="Show the working tree status",
                schema=GitStatus,
                handler=placeholder_handler,
                requires_repo=True
            ),
            ToolDefinition(
                name=GitTools.DIFF_UNSTAGED,
                category=ToolCategory.GIT,
                description="Show changes in the working directory that are not yet staged",
                schema=GitDiffUnstaged,
                handler=placeholder_handler,
                requires_repo=True
            ),
            ToolDefinition(
                name=GitTools.DIFF_STAGED,
                category=ToolCategory.GIT,
                description="Show changes that are staged for commit",
                schema=GitDiffStaged,
                handler=placeholder_handler,
                requires_repo=True
            ),
            ToolDefinition(
                name=GitTools.DIFF,
                category=ToolCategory.GIT,
                description="Show differences between branches or commits",
                schema=GitDiff,
                handler=placeholder_handler,
                requires_repo=True
            ),
            ToolDefinition(
                name=GitTools.COMMIT,
                category=ToolCategory.GIT,
                description="Record changes to the repository",
                schema=GitCommit,
                handler=placeholder_handler,
                requires_repo=True
            ),
            ToolDefinition(
                name=GitTools.ADD,
                category=ToolCategory.GIT,
                description="Add file contents to the staging area",
                schema=GitAdd,
                handler=placeholder_handler,
                requires_repo=True
            ),
            ToolDefinition(
                name=GitTools.RESET,
                category=ToolCategory.GIT,
                description="Unstage all staged changes",
                schema=GitReset,
                handler=placeholder_handler,
                requires_repo=True
            ),
            ToolDefinition(
                name=GitTools.LOG,
                category=ToolCategory.GIT,
                description="Show the commit logs",
                schema=GitLog,
                handler=placeholder_handler,
                requires_repo=True
            ),
            ToolDefinition(
                name=GitTools.CREATE_BRANCH,
                category=ToolCategory.GIT,
                description="Create a new branch from an optional base branch",
                schema=GitCreateBranch,
                handler=placeholder_handler,
                requires_repo=True
            ),
            ToolDefinition(
                name=GitTools.CHECKOUT,
                category=ToolCategory.GIT,
                description="Switch branches",
                schema=GitCheckout,
                handler=placeholder_handler,
                requires_repo=True
            ),
            ToolDefinition(
                name=GitTools.SHOW,
                category=ToolCategory.GIT,
                description="Show the contents of a commit",
                schema=GitShow,
                handler=placeholder_handler,
                requires_repo=True
            ),
            ToolDefinition(
                name=GitTools.INIT,
                category=ToolCategory.GIT,
                description="Initialize a new Git repository",
                schema=GitInit,
                handler=placeholder_handler,
                requires_repo=False  # Special case
            ),
            ToolDefinition(
                name=GitTools.PUSH,
                category=ToolCategory.GIT,
                description="Push commits to remote repository",
                schema=GitPush,
                handler=placeholder_handler,
                requires_repo=True
            ),
            ToolDefinition(
                name=GitTools.PULL,
                category=ToolCategory.GIT,
                description="Pull changes from remote repository",
                schema=GitPull,
                handler=placeholder_handler,
                requires_repo=True
            ),
            ToolDefinition(
                name=GitTools.DIFF_BRANCHES,
                category=ToolCategory.GIT,
                description="Show differences between two branches",
                schema=GitDiffBranches,
                handler=placeholder_handler,
                requires_repo=True
            ),
            ToolDefinition(
                name=GitTools.REBASE,
                category=ToolCategory.GIT,
                description="Rebase current branch onto target branch",
                schema=GitRebase,
                handler=placeholder_handler,
                requires_repo=True
            ),
            ToolDefinition(
                name=GitTools.MERGE,
                category=ToolCategory.GIT,
                description="Merge source branch into current branch",
                schema=GitMerge,
                handler=placeholder_handler,
                requires_repo=True
            ),
            ToolDefinition(
                name=GitTools.CHERRY_PICK,
                category=ToolCategory.GIT,
                description="Cherry-pick a commit onto current branch",
                schema=GitCherryPick,
                handler=placeholder_handler,
                requires_repo=True
            ),
            ToolDefinition(
                name=GitTools.ABORT,
                category=ToolCategory.GIT,
                description="Abort an ongoing git operation",
                schema=GitAbort,
                handler=placeholder_handler,
                requires_repo=True
            ),
            ToolDefinition(
                name=GitTools.CONTINUE,
                category=ToolCategory.GIT,
                description="Continue an ongoing git operation after resolving conflicts",
                schema=GitContinue,
                handler=placeholder_handler,
                requires_repo=True
            ),
        ]
        
        # Register GitHub API tools
        github_tools = [
            ToolDefinition(
                name=GitTools.GITHUB_GET_PR_CHECKS,
                category=ToolCategory.GITHUB,
                description="Get check runs for a pull request",
                schema=GitHubGetPRChecks,
                handler=placeholder_handler,
                requires_repo=False,
                requires_github_token=True
            ),
            ToolDefinition(
                name=GitTools.GITHUB_GET_FAILING_JOBS,
                category=ToolCategory.GITHUB,
                description="Get detailed information about failing jobs in a PR",
                schema=GitHubGetFailingJobs,
                handler=placeholder_handler,
                requires_repo=False,
                requires_github_token=True
            ),
            ToolDefinition(
                name=GitTools.GITHUB_GET_WORKFLOW_RUN,
                category=ToolCategory.GITHUB,
                description="Get detailed workflow run information",
                schema=GitHubGetWorkflowRun,
                handler=placeholder_handler,
                requires_repo=False,
                requires_github_token=True
            ),
            ToolDefinition(
                name=GitTools.GITHUB_GET_PR_DETAILS,
                category=ToolCategory.GITHUB,
                description="Get comprehensive PR details",
                schema=GitHubGetPRDetails,
                handler=placeholder_handler,
                requires_repo=False,
                requires_github_token=True
            ),
            ToolDefinition(
                name=GitTools.GITHUB_LIST_PULL_REQUESTS,
                category=ToolCategory.GITHUB,
                description="List pull requests for a repository",
                schema=GitHubListPullRequests,
                handler=placeholder_handler,
                requires_repo=False,
                requires_github_token=True
            ),
            ToolDefinition(
                name=GitTools.GITHUB_GET_PR_STATUS,
                category=ToolCategory.GITHUB,
                description="Get the status and check runs for a pull request",
                schema=GitHubGetPRStatus,
                handler=placeholder_handler,
                requires_repo=False,
                requires_github_token=True
            ),
            ToolDefinition(
                name=GitTools.GITHUB_GET_PR_FILES,
                category=ToolCategory.GITHUB,
                description="Get files changed in a pull request",
                schema=GitHubGetPRFiles,
                handler=placeholder_handler,
                requires_repo=False,
                requires_github_token=True
            ),
        ]
        
        # Register Security tools
        security_tools = [
            ToolDefinition(
                name=GitTools.GIT_SECURITY_VALIDATE,
                category=ToolCategory.SECURITY,
                description="Validate Git security configuration for the repository",
                schema=GitSecurityValidate,
                handler=placeholder_handler,
                requires_repo=True
            ),
            ToolDefinition(
                name=GitTools.GIT_SECURITY_ENFORCE,
                category=ToolCategory.SECURITY,
                description="Enforce secure Git configuration",
                schema=GitSecurityEnforce,
                handler=placeholder_handler,
                requires_repo=True
            ),
        ]
        
        # Register all tools
        for tool in git_tools + github_tools + security_tools:
            self.register(tool)
        
        self._initialized = True
        logger.info(f"Initialized tool registry with {len(self.tools)} tools")


class GitToolRouter:
    """Router for dispatching tool calls to appropriate handlers"""
    
    def __init__(self, registry: ToolRegistry):
        self.registry = registry
        self._handlers_initialized = False
    
    def set_handlers(self, git_handlers: Dict[str, Callable], github_handlers: Dict[str, Callable], security_handlers: Dict[str, Callable]):
        """Set up actual tool handlers"""
        
        # Update Git tool handlers
        for tool_name, handler in git_handlers.items():
            if tool_name in self.registry.tools:
                self.registry.tools[tool_name].handler = handler
        
        # Update GitHub tool handlers  
        for tool_name, handler in github_handlers.items():
            if tool_name in self.registry.tools:
                self.registry.tools[tool_name].handler = handler
        
        # Update Security tool handlers
        for tool_name, handler in security_handlers.items():
            if tool_name in self.registry.tools:
                self.registry.tools[tool_name].handler = handler
        
        self._handlers_initialized = True
        logger.info("Tool handlers initialized")
    
    async def route_tool_call(self, name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        """Route a tool call to the appropriate handler"""
        
        if not self._handlers_initialized:
            return [TextContent(type="text", text="❌ Tool handlers not initialized")]
        
        tool_def = self.registry.get_tool(name)
        if not tool_def:
            return [TextContent(type="text", text=f"❌ Unknown tool: {name}")]
        
        try:
            # Validate required parameters
            if tool_def.requires_repo and "repo_path" not in arguments:
                return [TextContent(type="text", text="❌ repo_path parameter required for this tool")]
            
            if tool_def.requires_github_token:
                if not arguments.get("repo_owner") or not arguments.get("repo_name"):
                    return [TextContent(type="text", text="❌ repo_owner and repo_name parameters required for GitHub API tools")]
            
            # Call the handler
            if tool_def.category == ToolCategory.GITHUB:
                # GitHub tools are async
                result = await tool_def.handler(**arguments)
            else:
                # Git and security tools are sync
                result = tool_def.handler(**arguments)
            
            return [TextContent(type="text", text=result)]
            
        except Exception as e:
            logger.error(f"Tool call failed for {name}: {e}", exc_info=True)
            return [TextContent(type="text", text=f"❌ Tool execution failed: {str(e)}")]