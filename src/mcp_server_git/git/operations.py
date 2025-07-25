"""Git operations for MCP Git Server"""

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from git import Repo as GitRepo, GitCommandError
else:
    GitRepo = Any
    GitCommandError = Exception

# Handle git import gracefully to avoid conflicts with git redirectors
try:
    from git import (
        Repo,
        GitCommandError,
    )
except ImportError as e:
    # If GitPython fails to initialize due to git redirector or missing git,
    # provide fallback implementations
    Repo = None
    GitCommandError = Exception  # Fallback to base Exception
    import warnings

    warnings.warn(
        f"GitPython initialization failed in operations: {e}. Git operations may be limited.",
        UserWarning,
    )

logger = logging.getLogger(__name__)


def _apply_diff_size_limiting(
    diff_output: str,
    operation_name: str,
    stat_only: bool = False,
    max_lines: Optional[int] = None,
) -> str:
    """Apply size limiting to diff outputs with consistent formatting"""
    if not diff_output.strip():
        return f"No changes detected in {operation_name}"

    if stat_only:
        # This should be handled by the caller using --stat flag
        return diff_output

    # Apply line limit if specified
    if max_lines and max_lines > 0:
        lines = diff_output.split("\n")
        if len(lines) > max_lines:
            truncated_output = "\n".join(lines[:max_lines])
            truncated_output += (
                f"\n\n... [Truncated: showing {max_lines} of {len(lines)} lines]"
            )
            truncated_output += "\nUse stat_only=true for summary or increase max_lines for more content"
            return truncated_output

    # Check if output is extremely large and warn
    if len(diff_output) > 50000:  # 50KB threshold
        lines_count = len(diff_output.split("\n"))
        warning = f"⚠️  Large diff detected ({lines_count} lines, ~{len(diff_output) // 1000}KB)\n"
        warning += "Consider using stat_only=true for summary or max_lines parameter to limit output\n\n"
        return warning + diff_output

    return diff_output


def git_status(
    repo: "GitRepo",
    porcelain: bool = False,
    status_filter: Optional[str] = None,
    path_filter: Optional[str] = None,
    include_ignored: bool = False,
    include_untracked: bool = True,
) -> str:
    """Get repository status with advanced filtering options.

    Args:
        repo: Git repository object
        porcelain: If True, return porcelain (machine-readable) format
        status_filter: Filter by status (staged, unstaged, untracked, ignored)
        path_filter: Filter by file path pattern (glob-style)
        include_ignored: Include ignored files in output
        include_untracked: Include untracked files in output

    Returns:
        Status output string with applied filters
    """
    try:
        # Build git status command arguments
        args = []

        if porcelain:
            args.append("--porcelain")

        if include_ignored:
            args.append("--ignored")

        if not include_untracked:
            args.append("--untracked-files=no")

        # Get raw status output
        status_output = repo.git.status(*args)

        # Apply filters if specified
        if status_filter or path_filter:
            status_output = _apply_status_filters(
                status_output, status_filter, path_filter, porcelain
            )

        return (
            status_output
            if status_output.strip()
            else "No files match the specified filters"
        )

    except GitCommandError as e:
        return f"❌ Status failed: {str(e)}"
    except Exception as e:
        return f"❌ Status error: {str(e)}"


def _apply_status_filters(
    status_output: str,
    status_filter: Optional[str] = None,
    path_filter: Optional[str] = None,
    porcelain: bool = False,
) -> str:
    """Apply status and path filters to git status output.

    Args:
        status_output: Raw git status output
        status_filter: Filter by status (staged, unstaged, untracked, ignored)
        path_filter: Filter by file path pattern (glob-style)
        porcelain: Whether output is in porcelain format

    Returns:
        Filtered status output
    """
    import fnmatch

    if not status_output.strip():
        return status_output

    lines = status_output.split("\n")
    filtered_lines = []

    if porcelain:
        # Porcelain format: XY filename
        # X = staged status, Y = unstaged status
        # Status codes: M=modified, A=added, D=deleted, R=renamed, C=copied, U=unmerged, ?=untracked, !=ignored
        for line in lines:
            if not line.strip():
                continue

            if len(line) < 3:
                continue

            staged_status = line[0]
            unstaged_status = line[1]
            filepath = line[3:]  # Skip XY and space

            # Apply status filter
            if status_filter:
                status_lower = status_filter.lower()
                include_line = False

                if status_lower == "staged" and staged_status not in [" ", "?"]:
                    include_line = True
                elif (
                    status_lower == "unstaged"
                    and unstaged_status not in [" ", "?"]
                    and staged_status != "?"
                ):
                    include_line = True
                elif (
                    status_lower == "untracked"
                    and staged_status == "?"
                    and unstaged_status == "?"
                ):
                    include_line = True
                elif (
                    status_lower == "ignored"
                    and staged_status == "!"
                    and unstaged_status == "!"
                ):
                    include_line = True
                elif status_lower == "modified" and (
                    staged_status == "M" or unstaged_status == "M"
                ):
                    include_line = True
                elif status_lower == "added" and staged_status == "A":
                    include_line = True
                elif status_lower == "deleted" and (
                    staged_status == "D" or unstaged_status == "D"
                ):
                    include_line = True

                if not include_line:
                    continue

            # Apply path filter
            if path_filter:
                if not fnmatch.fnmatch(filepath, path_filter):
                    continue

            filtered_lines.append(line)
    else:
        # Human-readable format - parse sections
        in_staged_section = False
        in_unstaged_section = False
        in_untracked_section = False
        in_ignored_section = False

        for line in lines:
            line_lower = line.lower()

            # Detect sections
            if "changes to be committed:" in line_lower:
                in_staged_section = True
                in_unstaged_section = False
                in_untracked_section = False
                in_ignored_section = False
                if not status_filter or status_filter.lower() == "staged":
                    filtered_lines.append(line)
                continue
            elif "changes not staged for commit:" in line_lower:
                in_staged_section = False
                in_unstaged_section = True
                in_untracked_section = False
                in_ignored_section = False
                if not status_filter or status_filter.lower() == "unstaged":
                    filtered_lines.append(line)
                continue
            elif "untracked files:" in line_lower:
                in_staged_section = False
                in_unstaged_section = False
                in_untracked_section = True
                in_ignored_section = False
                if not status_filter or status_filter.lower() == "untracked":
                    filtered_lines.append(line)
                continue
            elif "ignored files:" in line_lower:
                in_staged_section = False
                in_unstaged_section = False
                in_untracked_section = False
                in_ignored_section = True
                if not status_filter or status_filter.lower() == "ignored":
                    filtered_lines.append(line)
                continue

            # Process file lines based on current section
            if line.strip() and (line.startswith("\t") or line.startswith("  ")):
                # This is a file line
                filepath = line.strip()

                # Remove git status prefixes
                if filepath.startswith("modified:"):
                    filepath = filepath[9:].strip()
                elif filepath.startswith("new file:"):
                    filepath = filepath[9:].strip()
                elif filepath.startswith("deleted:"):
                    filepath = filepath[8:].strip()
                elif filepath.startswith("renamed:"):
                    filepath = filepath[8:].strip()
                elif filepath.startswith("copied:"):
                    filepath = filepath[7:].strip()

                # Apply status filter
                if status_filter:
                    status_lower = status_filter.lower()
                    include_line = False

                    if status_lower == "staged" and in_staged_section:
                        include_line = True
                    elif status_lower == "unstaged" and in_unstaged_section:
                        include_line = True
                    elif status_lower == "untracked" and in_untracked_section:
                        include_line = True
                    elif status_lower == "ignored" and in_ignored_section:
                        include_line = True

                    if not include_line:
                        continue

                # Apply path filter
                if path_filter:
                    if not fnmatch.fnmatch(filepath, path_filter):
                        continue

                filtered_lines.append(line)
            else:
                # Header lines, empty lines, etc.
                if not status_filter:
                    filtered_lines.append(line)
                elif line.strip() == "":
                    filtered_lines.append(line)

    return "\n".join(filtered_lines)


def git_diff_unstaged(
    repo: "GitRepo", stat_only: bool = False, max_lines: Optional[int] = None
) -> str:
    """Get unstaged changes diff with size limiting options"""
    try:
        if stat_only:
            diff_output = repo.git.diff("--stat")
            return (
                f"Unstaged changes summary:\n{diff_output}"
                if diff_output.strip()
                else "No unstaged changes"
            )

        diff_output = repo.git.diff()
        return _apply_diff_size_limiting(
            diff_output, "unstaged changes", stat_only, max_lines
        )

    except GitCommandError as e:
        return f"❌ Diff unstaged failed: {str(e)}"
    except Exception as e:
        return f"❌ Diff unstaged error: {str(e)}"


def git_diff_staged(
    repo: "GitRepo", stat_only: bool = False, max_lines: Optional[int] = None
) -> str:
    """Get staged changes diff with size limiting options"""
    try:
        if stat_only:
            diff_output = repo.git.diff("--cached", "--stat")
            return (
                f"Staged changes summary:\n{diff_output}"
                if diff_output.strip()
                else "No staged changes"
            )

        diff_output = repo.git.diff("--cached")
        return _apply_diff_size_limiting(
            diff_output, "staged changes", stat_only, max_lines
        )

    except GitCommandError as e:
        return f"❌ Diff staged failed: {str(e)}"
    except Exception as e:
        return f"❌ Diff staged error: {str(e)}"


def git_diff(
    repo: "GitRepo",
    target: str,
    stat_only: bool = False,
    max_lines: Optional[int] = None,
) -> str:
    """Get diff against target ref with size limiting options"""
    try:
        if stat_only:
            diff_output = repo.git.diff("--stat", target)
            return (
                f"Diff against {target} summary:\n{diff_output}"
                if diff_output.strip()
                else f"No differences against {target}"
            )

        diff_output = repo.git.diff(target)
        return _apply_diff_size_limiting(
            diff_output, f"diff against {target}", stat_only, max_lines
        )

    except GitCommandError as e:
        return f"❌ Diff failed: {str(e)}"
    except Exception as e:
        return f"❌ Diff error: {str(e)}"


def git_commit(
    repo: "GitRepo",
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
                    force_key_id = str(config_key)
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


def git_add(repo: "GitRepo", files: list[str]) -> str:
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


def git_reset(
    repo: "GitRepo",
    mode: Optional[str] = None,
    target: Optional[str] = None,
    files: Optional[list[str]] = None,
) -> str:
    """Reset repository with advanced options (--soft, --mixed, --hard)"""
    try:
        # Validate reset mode
        valid_modes = ["soft", "mixed", "hard"]
        if mode and mode not in valid_modes:
            return (
                f"❌ Invalid reset mode '{mode}'. Valid modes: {', '.join(valid_modes)}"
            )

        # Build git reset command
        reset_args = []

        # Add mode flag if specified
        if mode:
            reset_args.append(f"--{mode}")

        # Add target if specified
        if target:
            # Validate target exists
            try:
                repo.git.rev_parse(target)
            except GitCommandError:
                return f"❌ Target '{target}' does not exist"
            reset_args.append(target)

        # Add files if specified
        if files:
            # Validate files exist
            for file in files:
                if not os.path.exists(os.path.join(repo.working_dir, file)):
                    return f"❌ File '{file}' does not exist"
            reset_args.extend(files)

        # Special handling for file-specific reset
        if files and not mode and not target:
            # Default to mixed reset for files
            reset_args.insert(0, "HEAD")

        # Get status before reset for informative message
        status_before = ""
        if mode in ["mixed", "hard"] or not mode:
            try:
                staged_files = [
                    item.a_path for item in repo.index.diff("HEAD") if item.a_path
                ]
                if staged_files:
                    status_before = f"staged files: {', '.join(staged_files[:5])}"
                    if len(staged_files) > 5:
                        status_before += f" (and {len(staged_files) - 5} more)"
            except Exception:
                pass

        if mode == "hard":
            try:
                modified_files = [
                    item.a_path for item in repo.index.diff(None) if item.a_path
                ]
                if modified_files:
                    mod_status = f"modified files: {', '.join(modified_files[:5])}"
                    if len(modified_files) > 5:
                        mod_status += f" (and {len(modified_files) - 5} more)"
                    status_before = (
                        f"{status_before}, {mod_status}"
                        if status_before
                        else mod_status
                    )
            except Exception:
                pass

        # Execute reset
        if reset_args:
            repo.git.reset(*reset_args)
        else:
            repo.git.reset()

        # Build success message
        if files:
            return f"✅ Reset {len(files)} file(s): {', '.join(files)}"
        elif mode == "soft":
            return f"✅ Soft reset to {target if target else 'HEAD'} - keeping changes in index"
        elif mode == "mixed" or not mode:
            target_msg = f" to {target}" if target else ""
            return f"✅ Mixed reset{target_msg} - {status_before if status_before else 'no staged changes'}"
        elif mode == "hard":
            target_msg = f" to {target}" if target else ""
            return f"✅ Hard reset{target_msg} - {status_before if status_before else 'no changes'} discarded"
        else:
            # Fallback return (should not reach here)
            return "✅ Reset completed"

    except GitCommandError as e:
        return f"❌ Reset failed: {str(e)}"
    except Exception as e:
        return f"❌ Reset error: {str(e)}"


def git_log(
    repo: "GitRepo",
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
    repo: "GitRepo", branch_name: str, base_branch: Optional[str] = None
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


def git_checkout(repo: "GitRepo", branch_name: str) -> str:
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


def git_show(
    repo: "GitRepo",
    revision: str,
    stat_only: bool = False,
    max_lines: Optional[int] = None,
) -> str:
    """Show commit details with diff and size limiting options"""
    try:
        if stat_only:
            # Return only commit info and file statistics
            show_output = repo.git.show("--stat", revision)
            return f"Commit details for {revision}:\n{show_output}"

        # Get full commit details
        show_output = repo.git.show(revision)

        # Apply line limit if specified
        if max_lines and max_lines > 0:
            lines = show_output.split("\n")
            if len(lines) > max_lines:
                truncated_output = "\n".join(lines[:max_lines])
                truncated_output += (
                    f"\n\n... [Truncated: showing {max_lines} of {len(lines)} lines]"
                )
                truncated_output += "\nUse stat_only=true for summary or increase max_lines for more content"
                return truncated_output

        # Check if output is extremely large and warn
        if len(show_output) > 50000:  # 50KB threshold
            lines_count = len(show_output.split("\n"))
            warning = f"⚠️  Large commit detected ({lines_count} lines, ~{len(show_output) // 1000}KB)\n"
            warning += "Consider using stat_only=true for summary or max_lines parameter to limit output\n\n"
            return warning + show_output

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
        if Repo:
            Repo.init(path)
        else:
            # Fallback to subprocess if GitPython unavailable
            subprocess.run(["git", "init"], cwd=path, check=True)

        return f"✅ Initialized empty Git repository in {repo_path}"

    except Exception as e:
        return f"❌ Init failed: {str(e)}"


def git_push(
    repo: "GitRepo",
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


def git_pull(
    repo: "GitRepo", remote: str = "origin", branch: Optional[str] = None
) -> str:
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


def git_diff_branches(
    repo: "GitRepo",
    base_branch: str,
    compare_branch: str,
    stat_only: bool = False,
    max_lines: Optional[int] = None,
) -> str:
    """Show differences between two branches with size limiting options"""
    try:
        # Verify branches exist
        all_branches = [branch.name for branch in repo.branches] + [
            ref.name.split("/")[-1] for ref in repo.remote().refs
        ]

        if base_branch not in all_branches:
            return f"❌ Base branch '{base_branch}' not found"
        if compare_branch not in all_branches:
            return f"❌ Compare branch '{compare_branch}' not found"

        # Build diff command arguments
        diff_range = f"{base_branch}...{compare_branch}"

        if stat_only:
            # Return only file statistics
            diff_output = repo.git.diff("--stat", diff_range)
            if not diff_output.strip():
                return f"No differences between {base_branch} and {compare_branch}"
            return f"Diff statistics between {base_branch} and {compare_branch}:\n{diff_output}"

        # Get full diff
        diff_output = repo.git.diff(diff_range)

        if not diff_output.strip():
            return f"No differences between {base_branch} and {compare_branch}"

        # Apply line limit if specified
        if max_lines and max_lines > 0:
            lines = diff_output.split("\n")
            if len(lines) > max_lines:
                truncated_output = "\n".join(lines[:max_lines])
                truncated_output += (
                    f"\n\n... [Truncated: showing {max_lines} of {len(lines)} lines]"
                )
                truncated_output += "\nUse --stat flag for summary or increase max_lines for more content"
                return truncated_output

        # Check if output is extremely large and warn
        if len(diff_output) > 50000:  # 50KB threshold
            lines_count = len(diff_output.split("\n"))
            warning = f"⚠️  Large diff detected ({lines_count} lines, ~{len(diff_output) // 1000}KB)\n"
            warning += "Consider using stat_only=true for summary or max_lines parameter to limit output\n\n"
            return warning + diff_output

        return diff_output

    except GitCommandError as e:
        return f"❌ Diff failed: {str(e)}"
    except Exception as e:
        return f"❌ Diff error: {str(e)}"


def git_rebase(repo: "GitRepo", target_branch: str) -> str:
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
                    all_branches.extend(
                        [ref.name.split("/")[-1] for ref in remote.refs]
                    )
        except Exception:
            # Ignore remote access errors (e.g., no remotes configured)
            pass
        if target_branch not in all_branches:
            return f"❌ Target branch '{target_branch}' not found"

        # Perform rebase (non-interactive only)
        result = repo.git.rebase(target_branch)

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
    repo: "GitRepo",
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
                    all_branches.extend(
                        [ref.name.split("/")[-1] for ref in remote.refs]
                    )
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


def git_cherry_pick(repo: "GitRepo", commit_hash: str, no_commit: bool = False) -> str:
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


def git_abort(repo: "GitRepo", operation: str) -> str:
    """Abort ongoing operations (rebase, merge, cherry-pick)"""
    try:
        valid_operations = ["rebase", "merge", "cherry-pick"]
        if operation not in valid_operations:
            return f"❌ Invalid operation '{operation}'. Valid operations: {', '.join(valid_operations)}"

        # Perform abort using the same pattern as other operations
        if operation == "rebase":
            repo.git.rebase("--abort")
        elif operation == "merge":
            repo.git.merge("--abort")
        elif operation == "cherry-pick":
            repo.git.cherry_pick("--abort")

        return f"✅ Successfully aborted {operation}"

    except GitCommandError as e:
        return f"❌ Abort {operation} failed: {str(e)}"
    except Exception as e:
        return f"❌ Abort error: {str(e)}"


def git_continue(repo: "GitRepo", operation: str) -> str:
    """Continue operations after resolving conflicts"""
    try:
        valid_operations = ["rebase", "merge", "cherry-pick"]
        if operation not in valid_operations:
            return f"❌ Invalid operation '{operation}'. Valid operations: {', '.join(valid_operations)}"

        # Perform continue using the same pattern as other operations
        if operation == "rebase":
            repo.git.rebase("--continue")
        elif operation == "merge":
            repo.git.merge("--continue")
        elif operation == "cherry-pick":
            repo.git.cherry_pick("--continue")

        return f"✅ Successfully continued {operation}"

    except GitCommandError as e:
        return f"❌ Continue {operation} failed: {str(e)}"
    except Exception as e:
        return f"❌ Continue error: {str(e)}"


def git_remote_list(repo: "GitRepo", verbose: bool = False) -> str:
    """List all remote repositories"""
    try:
        if verbose:
            return repo.git.remote("-v")
        else:
            return repo.git.remote()
    except GitCommandError as e:
        return f"❌ Remote list failed: {str(e)}"
    except Exception as e:
        return f"❌ Remote list error: {str(e)}"


def git_remote_add(repo: "GitRepo", name: str, url: str) -> str:
    """Add a new remote repository"""
    try:
        repo.git.remote("add", name, url)
        return f"✅ Successfully added remote '{name}' -> {url}"
    except GitCommandError as e:
        return f"❌ Remote add failed: {str(e)}"
    except Exception as e:
        return f"❌ Remote add error: {str(e)}"


def git_remote_remove(repo: "GitRepo", name: str) -> str:
    """Remove a remote repository"""
    try:
        repo.git.remote("remove", name)
        return f"✅ Successfully removed remote '{name}'"
    except GitCommandError as e:
        return f"❌ Remote remove failed: {str(e)}"
    except Exception as e:
        return f"❌ Remote remove error: {str(e)}"


def git_remote_rename(repo: "GitRepo", old_name: str, new_name: str) -> str:
    """Rename a remote repository"""
    try:
        repo.git.remote("rename", old_name, new_name)
        return f"✅ Successfully renamed remote '{old_name}' to '{new_name}'"
    except GitCommandError as e:
        return f"❌ Remote rename failed: {str(e)}"
    except Exception as e:
        return f"❌ Remote rename error: {str(e)}"


def git_remote_set_url(repo: "GitRepo", name: str, url: str) -> str:
    """Set URL for a remote repository"""
    try:
        repo.git.remote("set-url", name, url)
        return f"✅ Successfully set URL for remote '{name}' -> {url}"
    except GitCommandError as e:
        return f"❌ Remote set-url failed: {str(e)}"
    except Exception as e:
        return f"❌ Remote set-url error: {str(e)}"


def git_remote_get_url(repo: "GitRepo", name: str) -> str:
    """Get URL for a remote repository"""
    try:
        url = repo.git.remote("get-url", name)
        return f"Remote '{name}' URL: {url}"
    except GitCommandError as e:
        return f"❌ Remote get-url failed: {str(e)}"
    except Exception as e:
        return f"❌ Remote get-url error: {str(e)}"


def git_fetch(
    repo: "GitRepo",
    remote: str = "origin",
    branch: Optional[str] = None,
    prune: bool = False,
) -> str:
    """Fetch changes from remote repository"""
    try:
        args = [remote]
        if branch:
            args.append(branch)
        if prune:
            args.append("--prune")

        repo.git.fetch(*args)

        if branch:
            return f"✅ Successfully fetched {remote}/{branch}" + (
                " (with prune)" if prune else ""
            )
        else:
            return f"✅ Successfully fetched from {remote}" + (
                " (with prune)" if prune else ""
            )
    except GitCommandError as e:
        return f"❌ Fetch failed: {str(e)}"
    except Exception as e:
        return f"❌ Fetch error: {str(e)}"


def git_stash_list(repo: "GitRepo") -> str:
    """List all stashes"""
    try:
        stash_list = repo.git.stash("list")
        if not stash_list.strip():
            return "No stashes found"
        return f"Stash list:\n{stash_list}"
    except GitCommandError as e:
        return f"❌ Stash list failed: {str(e)}"
    except Exception as e:
        return f"❌ Stash list error: {str(e)}"


def git_stash_push(
    repo: "GitRepo", message: Optional[str] = None, include_untracked: bool = False
) -> str:
    """Create a new stash"""
    try:
        args = ["push"]
        if include_untracked:
            args.append("--include-untracked")
        if message:
            args.extend(["-m", message])

        repo.git.stash(*args)
        return "✅ Successfully created stash" + (f": {message}" if message else "")
    except GitCommandError as e:
        return f"❌ Stash push failed: {str(e)}"
    except Exception as e:
        return f"❌ Stash push error: {str(e)}"


def git_stash_pop(repo: "GitRepo", stash_id: Optional[str] = None) -> str:
    """Apply and remove a stash"""
    try:
        if stash_id:
            repo.git.stash("pop", stash_id)
            return f"✅ Successfully popped stash {stash_id}"
        else:
            repo.git.stash("pop")
            return "✅ Successfully popped latest stash"
    except GitCommandError as e:
        return f"❌ Stash pop failed: {str(e)}"
    except Exception as e:
        return f"❌ Stash pop error: {str(e)}"


def git_stash_drop(repo: "GitRepo", stash_id: Optional[str] = None) -> str:
    """Remove a stash without applying it"""
    try:
        if stash_id:
            repo.git.stash("drop", stash_id)
            return f"✅ Successfully dropped stash {stash_id}"
        else:
            repo.git.stash("drop")
            return "✅ Successfully dropped latest stash"
    except GitCommandError as e:
        return f"❌ Stash drop failed: {str(e)}"
    except Exception as e:
        return f"❌ Stash drop error: {str(e)}"


def git_tag_list(repo: "GitRepo") -> str:
    """List all tags"""
    try:
        tag_list = repo.git.tag("-l")
        if not tag_list.strip():
            return "No tags found"
        return f"Tags:\n{tag_list}"
    except GitCommandError as e:
        return f"❌ Tag list failed: {str(e)}"
    except Exception as e:
        return f"❌ Tag list error: {str(e)}"


def git_tag_create(
    repo: "GitRepo",
    tag_name: str,
    message: Optional[str] = None,
    commit: Optional[str] = None,
) -> str:
    """Create a new tag"""
    try:
        args = [tag_name]
        if message:
            args.extend(["-m", message])
        if commit:
            args.append(commit)

        repo.git.tag(*args)
        return f"✅ Successfully created tag '{tag_name}'" + (
            f" on {commit}" if commit else ""
        )
    except GitCommandError as e:
        return f"❌ Tag create failed: {str(e)}"
    except Exception as e:
        return f"❌ Tag create error: {str(e)}"


def git_tag_delete(repo: "GitRepo", tag_name: str) -> str:
    """Delete a tag"""
    try:
        repo.git.tag("-d", tag_name)
        return f"✅ Successfully deleted tag '{tag_name}'"
    except GitCommandError as e:
        return f"❌ Tag delete failed: {str(e)}"
    except Exception as e:
        return f"❌ Tag delete error: {str(e)}"


def git_blame(
    repo: "GitRepo",
    file_path: str,
    line_start: Optional[int] = None,
    line_end: Optional[int] = None,
) -> str:
    """Show blame information for a file"""
    try:
        args = [file_path]
        if line_start and line_end:
            args.extend(["-L", f"{line_start},{line_end}"])
        elif line_start:
            args.extend(["-L", f"{line_start},+1"])

        blame_output = repo.git.blame(*args)
        return f"Blame for {file_path}:\n{blame_output}"
    except GitCommandError as e:
        return f"❌ Blame failed: {str(e)}"
    except Exception as e:
        return f"❌ Blame error: {str(e)}"


def git_clean(
    repo: "GitRepo",
    dry_run: bool = True,
    force: bool = False,
    directories: bool = False,
    ignored: bool = False,
    exclude_pattern: Optional[str] = None,
    include_pattern: Optional[str] = None,
) -> str:
    """Clean untracked files and directories with safety controls.

    Args:
        repo: Git repository object
        dry_run: If True, show what would be removed without actually removing (safety default)
        force: Force removal of files and directories (required for __pycache__ dirs)
        directories: Remove untracked directories in addition to files
        ignored: Remove ignored files (files matching patterns in .gitignore)
        exclude_pattern: Pattern to exclude from cleaning (e.g., "*.log")
        include_pattern: Pattern to include in cleaning (e.g., "__pycache__")

    Returns:
        Status message with cleaned files/directories or dry-run preview
    """
    try:
        # Build git clean command arguments
        args = []

        # Safety: Always start with dry run info if not explicitly disabled
        if dry_run:
            args.append("-n")  # Dry run - show what would be removed

        # Force flag - required for directories like __pycache__
        if force:
            args.append("-f")

        # Remove directories flag
        if directories:
            args.append("-d")

        # Remove ignored files flag
        if ignored:
            args.append("-x")

        # Add pattern exclusions/inclusions
        if exclude_pattern:
            args.extend(["-e", exclude_pattern])

        # Git clean doesn't have native include patterns, but we can simulate
        # by using path specification at the end
        if include_pattern:
            args.append(include_pattern)

        # Safety check: Ensure we have either dry_run OR force for actual removal
        if not dry_run and not force:
            return "❌ Safety check failed: git clean requires either dry_run=True or force=True for actual removal"

        # Execute git clean command
        clean_output = repo.git.clean(*args)

        # Format output based on operation type
        if dry_run:
            if clean_output.strip():
                return f"🔍 Dry run - Files/directories that would be removed:\n{clean_output}"
            else:
                return "✅ Dry run - No untracked files to clean"
        else:
            if clean_output.strip():
                return f"✅ Successfully cleaned untracked files:\n{clean_output}"
            else:
                return "✅ No untracked files found to clean"

    except GitCommandError as e:
        # Provide helpful error context
        error_msg = str(e)
        if "not removing" in error_msg.lower():
            return (
                f"❌ Clean failed - Use force=True for directory removal: {error_msg}"
            )
        elif "clean.requireForce" in error_msg:
            return f"❌ Clean failed - Repository requires force=True: {error_msg}"
        else:
            return f"❌ Git clean failed: {error_msg}"
    except Exception as e:
        return f"❌ Clean operation error: {str(e)}"
