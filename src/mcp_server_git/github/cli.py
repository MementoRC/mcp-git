"""GitHub CLI operations for MCP Git Server"""

import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


def _run_gh_command(args: list[str], cwd: str) -> tuple[str, str, int]:
    """Run GitHub CLI command and return stdout, stderr, and return code"""
    try:
        result = subprocess.run(
            ["gh"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "Command timed out", 1
    except FileNotFoundError:
        return "", "GitHub CLI (gh) not found. Please install it from https://cli.github.com/", 1
    except Exception as e:
        return "", str(e), 1


def _validate_repo_path(repo_path: str) -> str:
    """Validate repository path and return error message if invalid"""
    if not os.path.exists(repo_path):
        return f"❌ Repository path does not exist: {repo_path}"
    
    git_dir = os.path.join(repo_path, ".git")
    if not os.path.exists(git_dir):
        return f"❌ Not a git repository: {repo_path}"
    
    return ""


def gh_create_pr(
    repo_path: str,
    title: str,
    body: Optional[str] = None,
    base: Optional[str] = None,
    head: Optional[str] = None,
    draft: bool = False,
    web: bool = False,
) -> str:
    """Create a pull request using GitHub CLI"""
    # Validate repository
    error = _validate_repo_path(repo_path)
    if error:
        return error
    
    try:
        # Build command
        args = ["pr", "create", "--title", title]
        
        if body:
            args.extend(["--body", body])
        
        if base:
            args.extend(["--base", base])
        
        if head:
            args.extend(["--head", head])
        
        if draft:
            args.append("--draft")
        
        if web:
            args.append("--web")
        
        # Run command
        stdout, stderr, returncode = _run_gh_command(args, repo_path)
        
        if returncode != 0:
            return f"❌ Failed to create PR: {stderr}"
        
        return f"✅ Pull request created successfully\n{stdout.strip()}"
    
    except Exception as e:
        return f"❌ Create PR error: {str(e)}"


def gh_edit_pr(
    repo_path: str,
    pr_number: int,
    title: Optional[str] = None,
    body: Optional[str] = None,
    base: Optional[str] = None,
    add_assignee: Optional[list[str]] = None,
    remove_assignee: Optional[list[str]] = None,
    add_label: Optional[list[str]] = None,
    remove_label: Optional[list[str]] = None,
    add_reviewer: Optional[list[str]] = None,
    remove_reviewer: Optional[list[str]] = None,
) -> str:
    """Edit a pull request using GitHub CLI"""
    # Validate repository
    error = _validate_repo_path(repo_path)
    if error:
        return error
    
    try:
        # Build command
        args = ["pr", "edit", str(pr_number)]
        
        if title:
            args.extend(["--title", title])
        
        if body:
            args.extend(["--body", body])
        
        if base:
            args.extend(["--base", base])
        
        if add_assignee:
            args.extend(["--add-assignee", ",".join(add_assignee)])
        
        if remove_assignee:
            args.extend(["--remove-assignee", ",".join(remove_assignee)])
        
        if add_label:
            args.extend(["--add-label", ",".join(add_label)])
        
        if remove_label:
            args.extend(["--remove-label", ",".join(remove_label)])
        
        if add_reviewer:
            args.extend(["--add-reviewer", ",".join(add_reviewer)])
        
        if remove_reviewer:
            args.extend(["--remove-reviewer", ",".join(remove_reviewer)])
        
        # Run command
        stdout, stderr, returncode = _run_gh_command(args, repo_path)
        
        if returncode != 0:
            return f"❌ Failed to edit PR: {stderr}"
        
        return f"✅ Pull request #{pr_number} edited successfully"
    
    except Exception as e:
        return f"❌ Edit PR error: {str(e)}"


def gh_merge_pr(
    repo_path: str,
    pr_number: int,
    merge_method: str = "merge",
    delete_branch: bool = False,
    auto: bool = False,
) -> str:
    """Merge a pull request using GitHub CLI"""
    # Validate repository
    error = _validate_repo_path(repo_path)
    if error:
        return error
    
    # Validate merge method
    valid_methods = ["merge", "squash", "rebase"]
    if merge_method not in valid_methods:
        return f"❌ Invalid merge method '{merge_method}'. Valid methods: {', '.join(valid_methods)}"
    
    try:
        # Build command
        args = ["pr", "merge", str(pr_number)]
        
        if merge_method == "squash":
            args.append("--squash")
        elif merge_method == "rebase":
            args.append("--rebase")
        # merge is default
        
        if delete_branch:
            args.append("--delete-branch")
        
        if auto:
            args.append("--auto")
        
        # Run command
        stdout, stderr, returncode = _run_gh_command(args, repo_path)
        
        if returncode != 0:
            return f"❌ Failed to merge PR: {stderr}"
        
        return f"✅ Pull request #{pr_number} merged successfully using {merge_method}\n{stdout.strip()}"
    
    except Exception as e:
        return f"❌ Merge PR error: {str(e)}"


def gh_close_pr(
    repo_path: str,
    pr_number: int,
    comment: Optional[str] = None,
) -> str:
    """Close a pull request using GitHub CLI"""
    # Validate repository
    error = _validate_repo_path(repo_path)
    if error:
        return error
    
    try:
        # Build command
        args = ["pr", "close", str(pr_number)]
        
        if comment:
            args.extend(["--comment", comment])
        
        # Run command
        stdout, stderr, returncode = _run_gh_command(args, repo_path)
        
        if returncode != 0:
            return f"❌ Failed to close PR: {stderr}"
        
        return f"✅ Pull request #{pr_number} closed successfully"
    
    except Exception as e:
        return f"❌ Close PR error: {str(e)}"


def gh_reopen_pr(
    repo_path: str,
    pr_number: int,
    comment: Optional[str] = None,
) -> str:
    """Reopen a pull request using GitHub CLI"""
    # Validate repository
    error = _validate_repo_path(repo_path)
    if error:
        return error
    
    try:
        # Build command
        args = ["pr", "reopen", str(pr_number)]
        
        if comment:
            args.extend(["--comment", comment])
        
        # Run command
        stdout, stderr, returncode = _run_gh_command(args, repo_path)
        
        if returncode != 0:
            return f"❌ Failed to reopen PR: {stderr}"
        
        return f"✅ Pull request #{pr_number} reopened successfully"
    
    except Exception as e:
        return f"❌ Reopen PR error: {str(e)}"


def gh_ready_pr(
    repo_path: str,
    pr_number: int,
) -> str:
    """Mark a pull request as ready for review using GitHub CLI"""
    # Validate repository
    error = _validate_repo_path(repo_path)
    if error:
        return error
    
    try:
        # Build command
        args = ["pr", "ready", str(pr_number)]
        
        # Run command
        stdout, stderr, returncode = _run_gh_command(args, repo_path)
        
        if returncode != 0:
            return f"❌ Failed to mark PR as ready: {stderr}"
        
        return f"✅ Pull request #{pr_number} marked as ready for review"
    
    except Exception as e:
        return f"❌ Ready PR error: {str(e)}"