"""Git operations for MCP Git Server"""

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

from git import (
    Repo,
    GitCommandError,
)  # Added Repo, GitCommandError, InvalidGitRepositoryError

logger = logging.getLogger(__name__)


def git_status(repo: Repo, porcelain: bool = False) -> str:
    """Get repository status in either human-readable or machine-readable format.

    Args:
        repo: Git repository object
        porcelain: If True, return porcelain (machine-readable) format

    Returns:
        Status output string
    """
    if porcelain:
        return repo.git.status("--porcelain")
    else:
        return repo.git.status()


def git_diff_unstaged(repo: Repo) -> str:
    """Get unstaged changes diff"""
    return repo.git.diff()


def git_diff_staged(repo: Repo) -> str:
    """Get staged changes diff"""
    return repo.git.diff("--cached")


def git_diff(repo: Repo, target: str) -> str:
    """Get diff against target ref"""
    return repo.git.diff(target)


def git_commit(
    repo: Repo,
    message: str,
    gpg_sign: bool = False,
    gpg_key_id: Optional[str] = None,
) -> str:
    """Commit staged changes with optional GPG signing and automatic security enforcement"""
    try:
        # Import security functions locally to avoid circular imports
        from .security import enforce_secure_git_config

        # 🔒 SECURITY: Enforce secure configuration before committing
        security_result = enforce_secure_git_config(repo, strict_mode=True)
        security_messages = []
        if "✅" in security_result:
            security_messages.append("🔒 Security configuration enforced")

        # Force GPG signing for all commits (SECURITY REQUIREMENT)
        force_gpg = True

        # Get GPG key from parameters, environment, or git config
        if gpg_key_id:
            force_key_id = gpg_key_id
        else:
            # Try environment variable first
            env_key = os.getenv("GPG_SIGNING_KEY")
            if env_key:
                force_key_id = env_key
            else:
                # Fall back to git config
                try:
                    config_key = repo.config_reader().get_value("user", "signingkey")
                    force_key_id = config_key
                except Exception:
                    return "❌ Could not determine GPG signing key. Please configure GPG_SIGNING_KEY env var"

        if force_gpg:
            # Use git command directly for GPG signing
            cmd = ["git", "commit"]
            cmd.append(f"--gpg-sign={force_key_id}")
            cmd.extend(["-m", message])

            result = subprocess.run(
                cmd, cwd=repo.working_dir, capture_output=True, text=True
            )
            if result.returncode == 0:
                # Get the commit hash from git log
                hash_result = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=repo.working_dir,
                    capture_output=True,
                    text=True,
                )
                commit_hash = (
                    hash_result.stdout.strip()[:8]
                    if hash_result.returncode == 0
                    else "unknown"
                )

                success_msg = (
                    f"✅ Commit {commit_hash} created with VERIFIED GPG signature"
                )
                if security_messages:
                    success_msg += f"\n{chr(10).join(security_messages)}"

                # Add security reminder
                success_msg += f"\n🔒 Enforced GPG signing with key {force_key_id}"
                success_msg += (
                    "\n⚠️  MCP Git Server used - no fallback to system git commands"
                )

                return success_msg
            else:
                return f"❌ Commit failed: {result.stderr}\n🔒 GPG signing was enforced but failed"
        else:
            # This path should never be reached due to force_gpg=True
            return "❌ SECURITY VIOLATION: Unsigned commits are not allowed by MCP Git Server"

    except GitCommandError as e:
        return f"❌ Commit failed: {str(e)}\n🔒 Security enforcement may have prevented insecure operation"
    except Exception as e:
        return f"❌ Commit error: {str(e)}\n🔒 Verify repository security configuration"


def git_add(repo: Repo, files: list[str]) -> str:
    """Add files to git staging area with robust error handling"""
    try:
        # Validate files exist
        repo_path = Path(repo.working_dir)
        missing_files = []
        for file in files:
            file_path = repo_path / file
            if not file_path.exists() and not file_path.is_symlink():
                missing_files.append(file)

        if missing_files:
            return f"❌ Files not found: {', '.join(missing_files)}"

        # Add files to staging area
        repo.index.add(files)

        # Verify files were added
        staged_files = [item.a_path for item in repo.index.diff("HEAD")]
        added_files = [f for f in files if f in staged_files]

        if added_files:
            return f"✅ Added {len(added_files)} file(s) to staging area: {', '.join(added_files)}"
        else:
            return "⚠️ No changes detected in specified files"

    except GitCommandError as e:
        return f"❌ Git add failed: {str(e)}"
    except Exception as e:
        return f"❌ Add error: {str(e)}"


def git_reset(repo: Repo) -> str:
    """Reset all staged changes"""
    try:
        # Get list of staged files before reset
        staged_files = [item.a_path for item in repo.index.diff("HEAD")]

        if not staged_files:
            return "ℹ️ No staged changes to reset"

        # Reset the index
        repo.git.reset()

        return f"✅ Reset {len(staged_files)} staged file(s): {', '.join(staged_files)}"

    except GitCommandError as e:
        return f"❌ Reset failed: {str(e)}"
    except Exception as e:
        return f"❌ Reset error: {str(e)}"


def git_log(
    repo: Repo,
    max_count: int = 10,
    oneline: bool = False,
    graph: bool = False,
    format_str: Optional[str] = None,  # Renamed from 'format'
) -> str:
    """Get commit history with formatting options"""
    try:
        args = []

        if max_count:
            args.extend(["-n", str(max_count)])

        if oneline:
            args.append("--oneline")
        elif format_str:  # Use format_str
            args.extend(["--pretty=format:" + format_str])

        if graph:
            args.append("--graph")

        # Get commit log
        log_output = repo.git.log(*args)

        if not log_output.strip():
            return "No commits found in repository"

        return log_output

    except GitCommandError as e:
        return f"❌ Log failed: {str(e)}"
    except Exception as e:
        return f"❌ Log error: {str(e)}"


def git_create_branch(
    repo: Repo, branch_name: str, base_branch: Optional[str] = None
) -> str:
    """Create new branch from base"""
    try:
        # Check if branch already exists
        existing_branches = [branch.name for branch in repo.branches]
        if branch_name in existing_branches:
            return f"❌ Branch '{branch_name}' already exists"

        # Create new branch
        if base_branch:
            # Verify base branch exists
            if base_branch not in existing_branches and base_branch not in [
                branch.name for branch in repo.remote().refs
            ]:
                return f"❌ Base branch '{base_branch}' not found"

            repo.create_head(branch_name, base_branch)
        else:
            repo.create_head(branch_name)

        return f"✅ Created branch '{branch_name}'"

    except GitCommandError as e:
        return f"❌ Branch creation failed: {str(e)}"
    except Exception as e:
        return f"❌ Branch creation error: {str(e)}"


def git_checkout(repo: Repo, branch_name: str) -> str:
    """Switch to a branch"""
    try:
        # Check if branch exists locally
        local_branches = [branch.name for branch in repo.branches]

        if branch_name in local_branches:
            # Switch to local branch
            repo.git.checkout(branch_name)
            return f"✅ Switched to branch '{branch_name}'"
        else:
            # Check if branch exists on remote
            try:
                remote_branches = [
                    ref.name.split("/")[-1] for ref in repo.remote().refs
                ]
                if branch_name in remote_branches:
                    # Create local tracking branch
                    repo.git.checkout("-b", branch_name, f"origin/{branch_name}")
                    return f"✅ Created and switched to branch '{branch_name}' (tracking origin/{branch_name})"
                else:
                    return f"❌ Branch '{branch_name}' not found locally or on remote"
            except Exception:
                return f"❌ Branch '{branch_name}' not found"

    except GitCommandError as e:
        return f"❌ Checkout failed: {str(e)}"
    except Exception as e:
        return f"❌ Checkout error: {str(e)}"


def git_show(repo: Repo, revision: str) -> str:
    """Show commit details with diff"""
    try:
        # Get commit details
        show_output = repo.git.show(revision)
        return show_output

    except GitCommandError as e:
        return f"❌ Show failed: {str(e)}"
    except Exception as e:
        return f"❌ Show error: {str(e)}"


def git_init(repo_path: str) -> str:
    """Initialize new Git repository"""
    try:
        path = Path(repo_path)
        path.mkdir(parents=True, exist_ok=True)

        # Initialize repository
        Repo.init(path)

        return f"✅ Initialized empty Git repository in {repo_path}"

    except Exception as e:
        return f"❌ Init failed: {str(e)}"


def git_push(
    repo: Repo,
    remote: str = "origin",
    branch: Optional[str] = None,
    set_upstream: bool = False,
    force: bool = False,
) -> str:
    """Push with comprehensive HTTPS/GitHub token authentication"""
    try:
        # Get current branch if not specified
        if not branch:
            try:
                branch = repo.active_branch.name
            except TypeError:  # Detached HEAD or no commits
                return "❌ No active branch found and no branch specified"

        # Build push arguments
        push_args = [remote]
        if branch:
            push_args.append(branch)

        if set_upstream:
            push_args.insert(0, "--set-upstream")
        if force:
            push_args.insert(0, "--force")

        # Get remote URL for GitHub authentication handling
        remote_url = ""
        try:
            remote_url = repo.remote(remote).url
            is_github = "github.com" in remote_url
        except Exception:
            is_github = False

        # GitHub HTTPS authentication handling
        if is_github and remote_url.startswith("https://"):
            github_token = os.getenv("GITHUB_TOKEN")
            if github_token:
                # Inject token into URL
                if "github.com" in remote_url:
                    # Format: https://token@github.com/user/repo.git
                    auth_url = remote_url.replace(
                        "https://", f"https://{github_token}@"
                    )

                    # Temporarily set remote URL with token
                    original_url = remote_url
                    repo.remote(remote).set_url(auth_url)

                    try:
                        # Attempt push with authenticated URL
                        repo.git.push(*push_args)
                        success_msg = f"✅ Successfully pushed {branch} to {remote}"
                        if set_upstream:
                            success_msg += " (set upstream tracking)"
                        success_msg += "\n🔐 Used GitHub token authentication"
                        return success_msg
                    finally:
                        # Restore original URL
                        repo.remote(remote).set_url(original_url)
            else:
                return "❌ GitHub HTTPS push requires GITHUB_TOKEN environment variable"

        # Regular push (SSH or authenticated HTTPS)
        repo.git.push(*push_args)
        success_msg = f"✅ Successfully pushed {branch} to {remote}"
        if set_upstream:
            success_msg += " (set upstream tracking)"
        return success_msg

    except GitCommandError as e:
        if "Authentication failed" in str(e) or "401" in str(e):
            return "❌ Authentication failed. For GitHub HTTPS, set GITHUB_TOKEN environment variable"
        elif "403" in str(e):
            return "❌ Permission denied. Check repository access permissions"
        elif "non-fast-forward" in str(e):
            return "❌ Push rejected (non-fast-forward). Use --force flag if needed"
        else:
            return f"❌ Push failed: {str(e)}"
    except Exception as e:
        return f"❌ Push error: {str(e)}"


def git_pull(repo: Repo, remote: str = "origin", branch: Optional[str] = None) -> str:
    """Pull changes from remote repository"""
    try:
        # Get current branch if not specified
        if not branch:
            try:
                branch = repo.active_branch.name
            except TypeError:  # Detached HEAD or no commits
                return "❌ No active branch found and no branch specified"

        # Perform pull
        if branch:
            result = repo.git.pull(remote, branch)
        else:
            result = repo.git.pull(remote)

        return f"✅ Successfully pulled from {remote}/{branch}\n{result}"

    except GitCommandError as e:
        if "Authentication failed" in str(e):
            return f"❌ Authentication failed. Check credentials for {remote}"
        elif "merge conflict" in str(e).lower():
            return "❌ Pull failed due to merge conflicts. Resolve conflicts and retry"
        else:
            return f"❌ Pull failed: {str(e)}"
    except Exception as e:
        return f"❌ Pull error: {str(e)}"


def git_diff_branches(repo: Repo, base_branch: str, compare_branch: str) -> str:
    """Show differences between two branches"""
    try:
        # Verify branches exist
        all_branches = [branch.name for branch in repo.branches] + [
            ref.name.split("/")[-1] for ref in repo.remote().refs
        ]

        if base_branch not in all_branches:
            return f"❌ Base branch '{base_branch}' not found"
        if compare_branch not in all_branches:
            return f"❌ Compare branch '{compare_branch}' not found"

        # Get diff between branches
        diff_output = repo.git.diff(f"{base_branch}...{compare_branch}")

        if not diff_output.strip():
            return f"No differences between {base_branch} and {compare_branch}"

        return diff_output

    except GitCommandError as e:
        return f"❌ Diff failed: {str(e)}"
    except Exception as e:
        return f"❌ Diff error: {str(e)}"


def git_rebase(repo: Repo, target_branch: str, interactive: bool = False) -> str:
    """Rebase current branch onto target branch"""
    try:
        # Get current branch
        current_branch = repo.active_branch.name

        # Check if target branch exists
        all_branches = [branch.name for branch in repo.branches]
        
        # Add remote branches if remotes exist
        try:
            if repo.remotes:
                for remote in repo.remotes:
                    all_branches.extend([ref.name.split("/")[-1] for ref in remote.refs])
        except Exception:
            # Ignore remote access errors (e.g., no remotes configured)
            pass
        if target_branch not in all_branches:
            return f"❌ Target branch '{target_branch}' not found"

        # Build rebase command
        rebase_args = [target_branch]
        if interactive:
            rebase_args.insert(0, "--interactive")

        # Perform rebase
        result = repo.git.rebase(*rebase_args)

        return (
            f"✅ Successfully rebased {current_branch} onto {target_branch}\n{result}"
        )

    except GitCommandError as e:
        if "conflict" in str(e).lower():
            return "❌ Rebase failed due to conflicts. Resolve conflicts and run 'git rebase --continue'"
        else:
            return f"❌ Rebase failed: {str(e)}"
    except Exception as e:
        return f"❌ Rebase error: {str(e)}"


def git_merge(
    repo: Repo,
    source_branch: str,
    strategy: str = "merge",
    message: Optional[str] = None,
) -> str:
    """Merge source branch with strategy options"""
    try:
        # Get current branch
        current_branch = repo.active_branch.name

        # Check if source branch exists
        all_branches = [branch.name for branch in repo.branches]
        
        # Add remote branches if remotes exist
        try:
            if repo.remotes:
                for remote in repo.remotes:
                    all_branches.extend([ref.name.split("/")[-1] for ref in remote.refs])
        except Exception:
            # Ignore remote access errors (e.g., no remotes configured)
            pass
        if source_branch not in all_branches:
            return f"❌ Source branch '{source_branch}' not found"

        # Build merge command
        merge_args = [source_branch]
        if message:
            merge_args.extend(["-m", message])

        # Perform merge
        result = repo.git.merge(*merge_args)

        return f"✅ Successfully merged {source_branch} into {current_branch}\n{result}"

    except GitCommandError as e:
        if "conflict" in str(e).lower():
            return "❌ Merge failed due to conflicts. Resolve conflicts and commit"
        else:
            return f"❌ Merge failed: {str(e)}"
    except Exception as e:
        return f"❌ Merge error: {str(e)}"


def git_cherry_pick(repo: Repo, commit_hash: str, no_commit: bool = False) -> str:
    """Cherry-pick commits"""
    try:
        # Build cherry-pick command
        cp_args = [commit_hash]
        if no_commit:
            cp_args.insert(0, "--no-commit")

        # Perform cherry-pick
        result = repo.git.cherry_pick(*cp_args)

        action = "staged" if no_commit else "cherry-picked"
        return f"✅ Successfully {action} commit {commit_hash[:8]}\n{result}"

    except GitCommandError as e:
        if "conflict" in str(e).lower():
            return (
                "❌ Cherry-pick failed due to conflicts. Resolve conflicts and continue"
            )
        else:
            return f"❌ Cherry-pick failed: {str(e)}"
    except Exception as e:
        return f"❌ Cherry-pick error: {str(e)}"


def git_abort(repo: Repo, operation: str) -> str:
    """Abort ongoing operations (rebase, merge, cherry-pick)"""
    try:
        valid_operations = ["rebase", "merge", "cherry-pick"]
        if operation not in valid_operations:
            return f"❌ Invalid operation '{operation}'. Valid operations: {', '.join(valid_operations)}"

        # Perform abort
        repo.git.execute(["git", f"{operation}", "--abort"])

        return f"✅ Successfully aborted {operation}"

    except GitCommandError as e:
        return f"❌ Abort {operation} failed: {str(e)}"
    except Exception as e:
        return f"❌ Abort error: {str(e)}"


def git_continue(repo: Repo, operation: str) -> str:
    """Continue operations after resolving conflicts"""
    try:
        valid_operations = ["rebase", "merge", "cherry-pick"]
        if operation not in valid_operations:
            return f"❌ Invalid operation '{operation}'. Valid operations: {', '.join(valid_operations)}"

        # Perform continue
        repo.git.execute(["git", f"{operation}", "--continue"])

        return f"✅ Successfully continued {operation}"

    except GitCommandError as e:
        return f"❌ Continue {operation} failed: {str(e)}"
    except Exception as e:
        return f"❌ Continue error: {str(e)}"
