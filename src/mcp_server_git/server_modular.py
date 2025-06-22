"""
Modular MCP Git Server - New structure that imports from existing server.py
This allows us to refactor incrementally while keeping the original working
"""

import logging
import time
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# Import everything from original server for now
from .server import (
    # Configuration and environment
    load_environment_variables,
    
    # GitHub functionality - will be replaced with modular imports
    github_get_pr_details,
    git_status,
    git_diff_unstaged,
    git_diff_staged,
    git_diff,
    git_commit,
    git_add,
    git_reset,
    git_log,
    git_create_branch,
    git_checkout,
    git_show,
    git_init,
    git_push,
    git_pull,
    git_diff_branches,
    git_rebase,
    git_merge,
    git_cherry_pick,
    git_abort,
    git_continue,
    
    # Security functionality
    validate_git_security_config,
    enforce_secure_git_config,
    
    # Models and enums
    GitTools,
    GitStatus as GitStatusModel,
    GitDiffUnstaged,
    GitDiffStaged,
    GitDiff,
    GitCommit,
    GitAdd,
    GitReset,
    GitLog,
    GitCreateBranch,
    GitCheckout,
    GitShow,
    GitInit,
    GitPush,
    GitPull,
    GitDiffBranches,
    GitRebase,
    GitMerge,
    GitCherryPick,
    GitAbort,
    GitContinue,
    GitHubGetPRChecks,
    GitHubGetFailingJobs,
    GitHubGetWorkflowRun,
    GitHubGetPRDetails,
    GitHubListPullRequests,
    GitHubGetPRStatus,
    GitHubGetPRFiles,
    GitSecurityValidate,
    GitSecurityEnforce,
)

# Try to import modular components, fall back to original if not available
try:
    from .github.api import (
        # Read operations
        github_get_pr_checks as modular_github_get_pr_checks,
        github_get_pr_details as modular_github_get_pr_details,
        github_get_failing_jobs as modular_github_get_failing_jobs,
        github_get_workflow_run as modular_github_get_workflow_run,
        github_list_pull_requests as modular_github_list_pull_requests,
        github_get_pr_status as modular_github_get_pr_status,
        github_get_pr_files as modular_github_get_pr_files,
    )
    print("✅ Using modular GitHub API functions")
    USE_MODULAR_GITHUB = True
except ImportError:
    print("⚠️ Modular GitHub API not available, using original functions")
    USE_MODULAR_GITHUB = False

try:
    from .git.operations import (
        git_status as modular_git_status,
        git_diff_unstaged as modular_git_diff_unstaged,
        git_diff_staged as modular_git_diff_staged,
        git_diff as modular_git_diff,
        git_commit as modular_git_commit,
        git_add as modular_git_add,
        git_reset as modular_git_reset,
        git_init as modular_git_init,
    )
    print("✅ Using modular Git operations")
    USE_MODULAR_GIT = True
except ImportError:
    print("⚠️ Modular Git operations not available, using original functions")
    USE_MODULAR_GIT = False

logger = logging.getLogger(__name__)


async def serve_modular(repository: Path | None = None):
    """Serve the MCP Git Server with modular structure"""
    
    start_time = time.time()
    logger.info("🚀 Starting Modular MCP Git Server...")
    
    # Load environment variables
    load_environment_variables(repository)
    
    # Create server
    server = Server("mcp-git")
    
    @server.list_tools()
    async def list_tools():
        """List all available tools"""
        return [
            # Git tools
            Tool(
                name=GitTools.STATUS,
                description="Show the working tree status",
                inputSchema=GitStatusModel.model_json_schema()
            ),
            Tool(
                name=GitTools.DIFF_UNSTAGED,
                description="Show changes in the working directory that are not yet staged",
                inputSchema=GitDiffUnstaged.model_json_schema()
            ),
            Tool(
                name=GitTools.DIFF_STAGED,
                description="Show changes that are staged for commit",
                inputSchema=GitDiffStaged.model_json_schema()
            ),
            Tool(
                name=GitTools.DIFF,
                description="Show differences between branches or commits",
                inputSchema=GitDiff.model_json_schema()
            ),
            Tool(
                name=GitTools.COMMIT,
                description="Record changes to the repository",
                inputSchema=GitCommit.model_json_schema()
            ),
            Tool(
                name=GitTools.ADD,
                description="Add file contents to the staging area",
                inputSchema=GitAdd.model_json_schema()
            ),
            Tool(
                name=GitTools.RESET,
                description="Unstage all staged changes",
                inputSchema=GitReset.model_json_schema()
            ),
            Tool(
                name=GitTools.LOG,
                description="Show the commit logs",
                inputSchema=GitLog.model_json_schema()
            ),
            Tool(
                name=GitTools.CREATE_BRANCH,
                description="Create a new branch from an optional base branch",
                inputSchema=GitCreateBranch.model_json_schema()
            ),
            Tool(
                name=GitTools.CHECKOUT,
                description="Switch branches",
                inputSchema=GitCheckout.model_json_schema()
            ),
            Tool(
                name=GitTools.SHOW,
                description="Show the contents of a commit",
                inputSchema=GitShow.model_json_schema()
            ),
            Tool(
                name=GitTools.INIT,
                description="Initialize a new Git repository",
                inputSchema=GitInit.model_json_schema()
            ),
            Tool(
                name=GitTools.PUSH,
                description="Push commits to remote repository",
                inputSchema=GitPush.model_json_schema()
            ),
            Tool(
                name=GitTools.PULL,
                description="Pull changes from remote repository",
                inputSchema=GitPull.model_json_schema()
            ),
            Tool(
                name=GitTools.DIFF_BRANCHES,
                description="Show differences between two branches",
                inputSchema=GitDiffBranches.model_json_schema()
            ),
            Tool(
                name=GitTools.REBASE,
                description="Rebase current branch onto target branch",
                inputSchema=GitRebase.model_json_schema()
            ),
            Tool(
                name=GitTools.MERGE,
                description="Merge source branch into current branch",
                inputSchema=GitMerge.model_json_schema()
            ),
            Tool(
                name=GitTools.CHERRY_PICK,
                description="Cherry-pick a commit onto current branch",
                inputSchema=GitCherryPick.model_json_schema()
            ),
            Tool(
                name=GitTools.ABORT,
                description="Abort an ongoing git operation",
                inputSchema=GitAbort.model_json_schema()
            ),
            Tool(
                name=GitTools.CONTINUE,
                description="Continue an ongoing git operation after resolving conflicts",
                inputSchema=GitContinue.model_json_schema()
            ),
            
            # GitHub API tools
            Tool(
                name=GitTools.GITHUB_GET_PR_CHECKS,
                description="Get check runs for a pull request",
                inputSchema=GitHubGetPRChecks.model_json_schema()
            ),
            Tool(
                name=GitTools.GITHUB_GET_FAILING_JOBS,
                description="Get detailed information about failing jobs in a PR",
                inputSchema=GitHubGetFailingJobs.model_json_schema()
            ),
            Tool(
                name=GitTools.GITHUB_GET_WORKFLOW_RUN,
                description="Get detailed workflow run information",
                inputSchema=GitHubGetWorkflowRun.model_json_schema()
            ),
            Tool(
                name=GitTools.GITHUB_GET_PR_DETAILS,
                description="Get comprehensive PR details",
                inputSchema=GitHubGetPRDetails.model_json_schema()
            ),
            Tool(
                name=GitTools.GITHUB_LIST_PULL_REQUESTS,
                description="List pull requests for a repository",
                inputSchema=GitHubListPullRequests.model_json_schema()
            ),
            Tool(
                name=GitTools.GITHUB_GET_PR_STATUS,
                description="Get the status and check runs for a pull request",
                inputSchema=GitHubGetPRStatus.model_json_schema()
            ),
            Tool(
                name=GitTools.GITHUB_GET_PR_FILES,
                description="Get files changed in a pull request",
                inputSchema=GitHubGetPRFiles.model_json_schema()
            ),
            
            # Security tools
            Tool(
                name=GitTools.GIT_SECURITY_VALIDATE,
                description="Validate Git security configuration for the repository",
                inputSchema=GitSecurityValidate.model_json_schema()
            ),
            Tool(
                name=GitTools.GIT_SECURITY_ENFORCE,
                description="Enforce secure Git configuration",
                inputSchema=GitSecurityEnforce.model_json_schema()
            ),
        ]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        """Call a tool with improved routing"""
        import os
        import time
        
        request_id = os.urandom(4).hex()
        logger.info(f"🔧 [{request_id}] Tool call: {name}")
        logger.debug(f"🔧 [{request_id}] Arguments: {arguments}")
        
        start_time = time.time()
        result = None
        
        try:
            logger.debug(f"🔍 [{request_id}] Starting tool execution")
            
            # GitHub API tools don't need repo_path - they're handled separately
            if name not in [GitTools.GITHUB_GET_PR_CHECKS, GitTools.GITHUB_GET_FAILING_JOBS, 
                           GitTools.GITHUB_GET_WORKFLOW_RUN, GitTools.GITHUB_GET_PR_DETAILS,
                           GitTools.GITHUB_LIST_PULL_REQUESTS, GitTools.GITHUB_GET_PR_STATUS,
                           GitTools.GITHUB_GET_PR_FILES]:
                
                # All non-GitHub tools require repo_path
                repo_path = Path(arguments["repo_path"])
                
                # Handle git init separately since it doesn't require an existing repo
                if name == GitTools.INIT:
                    if USE_MODULAR_GIT:
                        result = modular_git_init(str(repo_path))
                    else:
                        result = git_init(str(repo_path))
                    result = [TextContent(type="text", text=result)]
                    duration = time.time() - start_time  
                    logger.info(f"✅ [{request_id}] Tool '{name}' completed in {duration:.2f}s")
                    return result  # Early return for INIT
                
                # For all other commands, we need an existing repo
                import git
                repo = git.Repo(repo_path)
                
                # Route to Git operations (use modular or original)
                match name:
                    case GitTools.STATUS:
                        porcelain_raw = arguments.get("porcelain", False)
                        porcelain = porcelain_raw if isinstance(porcelain_raw, bool) else str(porcelain_raw).lower() in ('true', '1', 'yes')
                        if USE_MODULAR_GIT:
                            status = modular_git_status(repo, porcelain)
                        else:
                            status = git_status(repo, porcelain)
                        prefix = "Repository status (porcelain):" if porcelain else "Repository status:"
                        result = [TextContent(type="text", text=f"{prefix}\n{status}")]
                    
                    case GitTools.DIFF_UNSTAGED:
                        diff = (modular_git_diff_unstaged(repo) if USE_MODULAR_GIT else git_diff_unstaged(repo))
                        result = [TextContent(type="text", text=f"Unstaged changes:\n{diff}")]
                    
                    case GitTools.DIFF_STAGED:
                        diff = (modular_git_diff_staged(repo) if USE_MODULAR_GIT else git_diff_staged(repo))
                        result = [TextContent(type="text", text=f"Staged changes:\n{diff}")]
                    
                    case GitTools.DIFF:
                        diff = (modular_git_diff(repo, arguments["target"]) if USE_MODULAR_GIT else git_diff(repo, arguments["target"]))
                        result = [TextContent(type="text", text=f"Diff with {arguments['target']}:\n{diff}")]
                    
                    case GitTools.COMMIT:
                        commit_result = (modular_git_commit(repo, arguments["message"], arguments.get("gpg_sign", False), arguments.get("gpg_key_id")) if USE_MODULAR_GIT else git_commit(repo, arguments["message"], arguments.get("gpg_sign", False), arguments.get("gpg_key_id")))
                        result = [TextContent(type="text", text=commit_result)]
                    
                    case GitTools.ADD:
                        add_result = (modular_git_add(repo, arguments["files"]) if USE_MODULAR_GIT else git_add(repo, arguments["files"]))
                        result = [TextContent(type="text", text=add_result)]
                    
                    case GitTools.RESET:
                        reset_result = (modular_git_reset(repo) if USE_MODULAR_GIT else git_reset(repo))
                        result = [TextContent(type="text", text=reset_result)]
                    
                    case GitTools.LOG:
                        log_result = git_log(
                            repo,
                            arguments.get("max_count", 10),
                            arguments.get("oneline", False),
                            arguments.get("graph", False),
                            arguments.get("format")
                        )
                        result = [TextContent(type="text", text=f"Commit log:\n{log_result}")]
                    
                    case GitTools.CREATE_BRANCH:
                        branch_result = git_create_branch(repo, arguments["branch_name"], arguments.get("base_branch"))
                        result = [TextContent(type="text", text=branch_result)]
                    
                    case GitTools.CHECKOUT:
                        checkout_result = git_checkout(repo, arguments["branch_name"])
                        result = [TextContent(type="text", text=checkout_result)]
                    
                    case GitTools.SHOW:
                        show_result = git_show(repo, arguments["revision"])
                        result = [TextContent(type="text", text=f"Commit details:\n{show_result}")]
                    
                    case GitTools.PUSH:
                        push_result = git_push(
                            repo,
                            arguments.get("remote", "origin"),
                            arguments.get("branch"),
                            arguments.get("set_upstream", False),
                            arguments.get("force", False)
                        )
                        result = [TextContent(type="text", text=push_result)]
                    
                    case GitTools.PULL:
                        pull_result = git_pull(repo, arguments.get("remote", "origin"), arguments.get("branch"))
                        result = [TextContent(type="text", text=pull_result)]
                    
                    case GitTools.DIFF_BRANCHES:
                        branches_diff = git_diff_branches(repo, arguments["base_branch"], arguments["compare_branch"])
                        result = [TextContent(type="text", text=f"Diff between branches:\n{branches_diff}")]
                    
                    case GitTools.REBASE:
                        rebase_result = git_rebase(repo, arguments["target_branch"], arguments.get("interactive", False))
                        result = [TextContent(type="text", text=rebase_result)]
                    
                    case GitTools.MERGE:
                        merge_result = git_merge(repo, arguments["source_branch"], arguments.get("strategy", "merge"), arguments.get("message"))
                        result = [TextContent(type="text", text=merge_result)]
                    
                    case GitTools.CHERRY_PICK:
                        cherry_pick_result = git_cherry_pick(repo, arguments["commit_hash"], arguments.get("no_commit", False))
                        result = [TextContent(type="text", text=cherry_pick_result)]
                    
                    case GitTools.ABORT:
                        abort_result = git_abort(repo, arguments["operation"])
                        result = [TextContent(type="text", text=abort_result)]
                    
                    case GitTools.CONTINUE:
                        continue_result = git_continue(repo, arguments["operation"])
                        result = [TextContent(type="text", text=continue_result)]
                    
                    # Security tools
                    case GitTools.GIT_SECURITY_VALIDATE:
                        validation_result = validate_git_security_config(repo)
                        status_emoji = "✅" if validation_result["status"] == "secure" else "⚠️"
                        result_text = f"{status_emoji} Git Security Validation Results\n\n"
                        
                        if validation_result["warnings"]:
                            result_text += "Security Warnings:\n"
                            for warning in validation_result["warnings"]:
                                result_text += f"  - {warning}\n"
                            result_text += "\n"
                        
                        if validation_result["recommendations"]:
                            result_text += "Recommendations:\n"
                            for rec in validation_result["recommendations"]:
                                result_text += f"  - {rec}\n"
                            result_text += "\n"
                        
                        result_text += f"Overall Status: {validation_result['status']}"
                        result = [TextContent(type="text", text=result_text)]
                    
                    case GitTools.GIT_SECURITY_ENFORCE:
                        strict_mode = arguments.get("strict_mode", True)
                        enforce_result = enforce_secure_git_config(repo, strict_mode)
                        result = [TextContent(type="text", text=enforce_result)]
                    
                    case _:
                        logger.error(f"❌ [{request_id}] Unknown tool: {name}")
                        raise ValueError(f"Unknown tool: {name}")
            
            else:
                # Handle GitHub API tools that don't require repo_path
                logger.debug(f"🔍 [{request_id}] Tool is GitHub API tool, processing...")
                
                # Choose between modular or original implementation
                if USE_MODULAR_GITHUB:
                    # Use modular GitHub API functions
                    match name:
                        case GitTools.GITHUB_GET_PR_DETAILS:
                            pr_details_result = await modular_github_get_pr_details(
                                arguments.get("repo_owner"),
                                arguments.get("repo_name"),
                                arguments["pr_number"],
                                arguments.get("include_files", False),
                                arguments.get("include_reviews", False)
                            )
                            result = [TextContent(type="text", text=pr_details_result)]
                        
                        case GitTools.GITHUB_GET_PR_CHECKS:
                            pr_checks_result = await modular_github_get_pr_checks(
                                arguments.get("repo_owner"),
                                arguments.get("repo_name"),
                                arguments["pr_number"],
                                arguments.get("status"),
                                arguments.get("conclusion")
                            )
                            result = [TextContent(type="text", text=pr_checks_result)]
                        
                        case GitTools.GITHUB_GET_FAILING_JOBS:
                            failing_jobs_result = await modular_github_get_failing_jobs(
                                arguments.get("repo_owner"),
                                arguments.get("repo_name"),
                                arguments["pr_number"],
                                arguments.get("include_logs", True),
                                arguments.get("include_annotations", True)
                            )
                            result = [TextContent(type="text", text=failing_jobs_result)]
                        
                        case GitTools.GITHUB_GET_WORKFLOW_RUN:
                            workflow_run_result = await modular_github_get_workflow_run(
                                arguments.get("repo_owner"),
                                arguments.get("repo_name"),
                                arguments["run_id"],
                                arguments.get("include_logs", False)
                            )
                            result = [TextContent(type="text", text=workflow_run_result)]
                        
                        case GitTools.GITHUB_LIST_PULL_REQUESTS:
                            list_prs_result = await modular_github_list_pull_requests(
                                arguments.get("repo_owner"),
                                arguments.get("repo_name"),
                                arguments.get("state", "open"),
                                arguments.get("head"),
                                arguments.get("base"),
                                arguments.get("sort", "created"),
                                arguments.get("direction", "desc"),
                                arguments.get("per_page", 30),
                                arguments.get("page", 1)
                            )
                            result = [TextContent(type="text", text=list_prs_result)]
                        
                        case GitTools.GITHUB_GET_PR_STATUS:
                            pr_status_result = await modular_github_get_pr_status(
                                arguments.get("repo_owner"),
                                arguments.get("repo_name"),
                                arguments["pr_number"]
                            )
                            result = [TextContent(type="text", text=pr_status_result)]
                        
                        case GitTools.GITHUB_GET_PR_FILES:
                            pr_files_result = await modular_github_get_pr_files(
                                arguments.get("repo_owner"),
                                arguments.get("repo_name"),
                                arguments["pr_number"],
                                arguments.get("per_page", 30),
                                arguments.get("page", 1),
                                arguments.get("include_patch", False)
                            )
                            result = [TextContent(type="text", text=pr_files_result)]
                        
                        case _:
                            logger.error(f"❌ [{request_id}] Unknown GitHub API tool: {name}")
                            raise ValueError(f"Unknown GitHub API tool: {name}")
                else:
                    # Fall back to original GitHub API functions
                    match name:
                        case GitTools.GITHUB_GET_PR_DETAILS:
                            repo_owner = arguments.get("repo_owner")
                            repo_name = arguments.get("repo_name")
                            if not repo_owner or not repo_name:
                                result = [TextContent(type="text", text="❌ repo_owner and repo_name parameters are required for GitHub API tools")]
                            else:
                                pr_details_result = await github_get_pr_details(
                                    repo_owner,
                                    repo_name,
                                    arguments["pr_number"],
                                    arguments.get("include_files", False),
                                    arguments.get("include_reviews", False)
                                )
                                result = [TextContent(type="text", text=pr_details_result)]
                        
                        # Add other original GitHub functions as needed...
                        case _:
                            result = [TextContent(type="text", text=f"❌ Original GitHub tool '{name}' not implemented in modular fallback")]
        
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"❌ [{request_id}] Tool '{name}' failed after {duration:.2f}s: {e}", exc_info=True)
            return [TextContent(type="text", text=f"Error in {name}: {str(e)}")]
        
        duration = time.time() - start_time
        logger.debug(f"🔍 [{request_id}] Tool execution finished, result type: {type(result)}")
        if result and len(result) > 0:
            logger.debug(f"🔍 [{request_id}] Result[0] type: {type(result[0])}, content preview: {str(result[0])[:200]}")
        logger.info(f"✅ [{request_id}] Tool '{name}' completed in {duration:.2f}s")
        return result
    
    # Server initialization
    logger.info("🎯 Modular MCP Git Server initialized and ready to listen...")
    initialization_time = time.time() - start_time
    logger.info(f"📡 Server listening (startup took {initialization_time:.2f}s)")
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, raise_exceptions=False)