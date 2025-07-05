"""
Repository protocol definitions for Git repository operations.

This module defines protocols for repository operations, path validation,
branch management, and Git command execution interfaces.
"""

from typing import Protocol, List, Optional, Dict, Any, Union, AsyncIterator
from abc import abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..types.git_types import (
    GitRepositoryPath,
    GitBranch,
    GitCommitHash,
    GitOperationResult,
    GitStatusResult,
    GitDiffResult,
    GitLogResult,
    GitCommitInfo,
    GitBranchInfo,
    GitRemoteInfo
    )
else:
    # Runtime imports - create type aliases to avoid import errors
    GitRepositoryPath = "GitRepositoryPath"
    GitBranch = "GitBranch" 
    GitCommitHash = "GitCommitHash"
    GitOperationResult = "GitOperationResult"
    GitStatusResult = "GitStatusResult"
    GitDiffResult = "GitDiffResult"
    GitLogResult = "GitLogResult"
    GitCommitInfo = "GitCommitInfo"
    GitBranchInfo = "GitBranchInfo"
    GitRemoteInfo = "GitRemoteInfo"


class RepositoryValidator(Protocol):
    """Protocol for repository path validation and verification."""
    
    @abstractmethod
    def validate_repository_path(self, path: Union[str, Path]) -> bool:
        """
        Validate if a path points to a valid Git repository.
        
        Args:
            path: Path to validate as a Git repository
            
        Returns:
            True if path is a valid Git repository, False otherwise
            
        Example:
            >>> validator = MyRepositoryValidator()
            >>> is_valid = validator.validate_repository_path("/path/to/repo")
        """
        ...
    
    @abstractmethod
    def get_repository_info(self, path: Union[str, Path]) -> Dict[str, Any]:
        """
        Get repository information and metadata.
        
        Args:
            path: Path to the Git repository
            
        Returns:
            Dictionary containing repository metadata (remote URLs, current branch, etc.)
            
        Example:
            >>> validator = MyRepositoryValidator()
            >>> info = validator.get_repository_info("/path/to/repo")
            >>> print(f"Current branch: {info['current_branch']}")
        """
        ...
    
    @abstractmethod
    def check_repository_health(self, path: Union[str, Path]) -> Dict[str, Union[bool, str, List[str]]]:
        """
        Check the health and integrity of a Git repository.
        
        Args:
            path: Path to the Git repository
            
        Returns:
            Dictionary with health status, issues, and recommendations
            
        Example:
            >>> validator = MyRepositoryValidator()
            >>> health = validator.check_repository_health("/path/to/repo")
            >>> if not health["healthy"]:
            ...     print(f"Issues: {health['issues']}")
        """
        ...


class BranchManager(Protocol):
    """Protocol for Git branch management operations."""
    
    @abstractmethod
    def list_branches(self, repo_path: GitRepositoryPath, remote: bool = False) -> List[GitBranchInfo]:
        """
        List all branches in the repository.
        
        Args:
            repo_path: Valid Git repository path
            remote: If True, include remote branches
            
        Returns:
            List of GitBranchInfo objects with branch details
            
        Example:
            >>> manager = MyBranchManager()
            >>> branches = manager.list_branches(repo_path, remote=True)
            >>> for branch in branches:
            ...     print(f"Branch: {branch.name}, current: {branch.current}")
        """
        ...
    
    @abstractmethod
    def create_branch(self, repo_path: GitRepositoryPath, branch_name: str, 
                     base_branch: Optional[str] = None) -> GitOperationResult:
        """
        Create a new branch.
        
        Args:
            repo_path: Valid Git repository path
            branch_name: Name for the new branch
            base_branch: Optional base branch to create from
            
        Returns:
            GitOperationResult indicating success or failure
            
        Example:
            >>> manager = MyBranchManager()
            >>> result = manager.create_branch(repo_path, "feature/new-feature")
            >>> if result.is_success():
            ...     print("Branch created successfully")
        """
        ...
    
    @abstractmethod
    def checkout_branch(self, repo_path: GitRepositoryPath, branch_name: str) -> GitOperationResult:
        """
        Switch to a different branch.
        
        Args:
            repo_path: Valid Git repository path
            branch_name: Name of branch to switch to
            
        Returns:
            GitOperationResult indicating success or failure
            
        Example:
            >>> manager = MyBranchManager()
            >>> result = manager.checkout_branch(repo_path, "main")
            >>> if result.is_error():
            ...     print(f"Checkout failed: {result.error}")
        """
        ...
    
    @abstractmethod
    def delete_branch(self, repo_path: GitRepositoryPath, branch_name: str, 
                     force: bool = False) -> GitOperationResult:
        """
        Delete a branch.
        
        Args:
            repo_path: Valid Git repository path
            branch_name: Name of branch to delete
            force: Force deletion even if not fully merged
            
        Returns:
            GitOperationResult indicating success or failure
        """
        ...
    
    @abstractmethod
    def merge_branch(self, repo_path: GitRepositoryPath, source_branch: str,
                    target_branch: Optional[str] = None) -> GitOperationResult:
        """
        Merge one branch into another.
        
        Args:
            repo_path: Valid Git repository path
            source_branch: Branch to merge from
            target_branch: Branch to merge into (current if None)
            
        Returns:
            GitOperationResult indicating success or failure
        """
        ...


class CommitManager(Protocol):
    """Protocol for Git commit operations."""
    
    @abstractmethod
    def get_commit_history(self, repo_path: GitRepositoryPath, 
                          max_count: int = 10, branch: Optional[str] = None) -> GitLogResult:
        """
        Get commit history for the repository.
        
        Args:
            repo_path: Valid Git repository path
            max_count: Maximum number of commits to retrieve
            branch: Specific branch to get history from
            
        Returns:
            GitLogResult with commit history
            
        Example:
            >>> manager = MyCommitManager()
            >>> history = manager.get_commit_history(repo_path, max_count=5)
            >>> for commit in history.commits:
            ...     print(f"{commit.hash.short()}: {commit.message}")
        """
        ...
    
    @abstractmethod
    def create_commit(self, repo_path: GitRepositoryPath, message: str,
                     files: Optional[List[str]] = None, 
                     author_name: Optional[str] = None,
                     author_email: Optional[str] = None) -> GitOperationResult:
        """
        Create a new commit.
        
        Args:
            repo_path: Valid Git repository path
            message: Commit message
            files: Optional list of files to commit (all staged if None)
            author_name: Optional author name override
            author_email: Optional author email override
            
        Returns:
            GitOperationResult with commit hash if successful
            
        Example:
            >>> manager = MyCommitManager()
            >>> result = manager.create_commit(repo_path, "Add new feature")
            >>> if result.is_success():
            ...     print(f"Committed: {result.output}")
        """
        ...
    
    @abstractmethod
    def get_commit_info(self, repo_path: GitRepositoryPath, 
                       commit_hash: Union[str, GitCommitHash]) -> GitCommitInfo:
        """
        Get detailed information about a specific commit.
        
        Args:
            repo_path: Valid Git repository path
            commit_hash: Hash of the commit to inspect
            
        Returns:
            GitCommitInfo with detailed commit information
            
        Example:
            >>> manager = MyCommitManager()
            >>> info = manager.get_commit_info(repo_path, "abc123")
            >>> print(f"Author: {info.author_name} <{info.author_email}>")
        """
        ...
    
    @abstractmethod
    def stage_files(self, repo_path: GitRepositoryPath, files: List[str]) -> GitOperationResult:
        """
        Stage files for commit.
        
        Args:
            repo_path: Valid Git repository path
            files: List of file paths to stage
            
        Returns:
            GitOperationResult indicating success or failure
        """
        ...
    
    @abstractmethod
    def unstage_files(self, repo_path: GitRepositoryPath, files: List[str]) -> GitOperationResult:
        """
        Unstage files from the staging area.
        
        Args:
            repo_path: Valid Git repository path
            files: List of file paths to unstage
            
        Returns:
            GitOperationResult indicating success or failure
        """
        ...


class DiffProvider(Protocol):
    """Protocol for Git diff operations."""
    
    @abstractmethod
    def get_working_diff(self, repo_path: GitRepositoryPath) -> GitDiffResult:
        """
        Get diff of working directory changes.
        
        Args:
            repo_path: Valid Git repository path
            
        Returns:
            GitDiffResult with working directory changes
        """
        ...
    
    @abstractmethod
    def get_staged_diff(self, repo_path: GitRepositoryPath) -> GitDiffResult:
        """
        Get diff of staged changes.
        
        Args:
            repo_path: Valid Git repository path
            
        Returns:
            GitDiffResult with staged changes
        """
        ...
    
    @abstractmethod
    def get_commit_diff(self, repo_path: GitRepositoryPath, 
                       commit_hash: Union[str, GitCommitHash]) -> GitDiffResult:
        """
        Get diff for a specific commit.
        
        Args:
            repo_path: Valid Git repository path
            commit_hash: Commit to get diff for
            
        Returns:
            GitDiffResult with commit changes
        """
        ...
    
    @abstractmethod
    def compare_branches(self, repo_path: GitRepositoryPath, 
                        base_branch: str, compare_branch: str) -> GitDiffResult:
        """
        Compare two branches and get differences.
        
        Args:
            repo_path: Valid Git repository path
            base_branch: Base branch for comparison
            compare_branch: Branch to compare against base
            
        Returns:
            GitDiffResult with branch differences
        """
        ...


class RemoteManager(Protocol):
    """Protocol for Git remote operations."""
    
    @abstractmethod
    def list_remotes(self, repo_path: GitRepositoryPath) -> List[GitRemoteInfo]:
        """
        List all configured remotes.
        
        Args:
            repo_path: Valid Git repository path
            
        Returns:
            List of GitRemoteInfo objects
        """
        ...
    
    @abstractmethod
    def add_remote(self, repo_path: GitRepositoryPath, name: str, url: str) -> GitOperationResult:
        """
        Add a new remote.
        
        Args:
            repo_path: Valid Git repository path
            name: Name for the remote
            url: URL of the remote repository
            
        Returns:
            GitOperationResult indicating success or failure
        """
        ...
    
    @abstractmethod
    def fetch_remote(self, repo_path: GitRepositoryPath, 
                    remote_name: str = "origin") -> GitOperationResult:
        """
        Fetch changes from a remote.
        
        Args:
            repo_path: Valid Git repository path
            remote_name: Name of remote to fetch from
            
        Returns:
            GitOperationResult indicating success or failure
        """
        ...
    
    @abstractmethod
    def push_to_remote(self, repo_path: GitRepositoryPath, 
                      remote_name: str = "origin", 
                      branch_name: Optional[str] = None,
                      force: bool = False) -> GitOperationResult:
        """
        Push changes to a remote.
        
        Args:
            repo_path: Valid Git repository path
            remote_name: Name of remote to push to
            branch_name: Branch to push (current if None)
            force: Force push
            
        Returns:
            GitOperationResult indicating success or failure
        """
        ...


class RepositoryOperations(Protocol):
    """
    Comprehensive protocol for Git repository operations.
    
    This protocol combines all repository management capabilities into a single
    interface for components that need full Git functionality.
    """
    
    @abstractmethod
    def get_repository_status(self, repo_path: GitRepositoryPath) -> GitStatusResult:
        """
        Get current repository status.
        
        Args:
            repo_path: Valid Git repository path
            
        Returns:
            GitStatusResult with comprehensive status information
            
        Example:
            >>> ops = MyRepositoryOperations()
            >>> status = ops.get_repository_status(repo_path)
            >>> if status.has_no_changes():
            ...     print("Repository is clean")
            >>> else:
            ...     print(f"Modified files: {len(status.modified_files)}")
        """
        ...
    
    @abstractmethod
    def initialize_repository(self, path: Union[str, Path], bare: bool = False) -> GitOperationResult:
        """
        Initialize a new Git repository.
        
        Args:
            path: Path where to initialize the repository
            bare: Create a bare repository
            
        Returns:
            GitOperationResult indicating success or failure
            
        Example:
            >>> ops = MyRepositoryOperations()
            >>> result = ops.initialize_repository("/path/to/new/repo")
            >>> if result.is_success():
            ...     print("Repository initialized successfully")
        """
        ...
    
    @abstractmethod
    def clone_repository(self, url: str, destination: Union[str, Path],
                        branch: Optional[str] = None) -> GitOperationResult:
        """
        Clone a remote repository.
        
        Args:
            url: URL of repository to clone
            destination: Local path for cloned repository
            branch: Specific branch to clone
            
        Returns:
            GitOperationResult indicating success or failure
        """
        ...
    
    # Include all sub-protocol capabilities
    validator: RepositoryValidator
    branch_manager: BranchManager
    commit_manager: CommitManager
    diff_provider: DiffProvider
    remote_manager: RemoteManager


class AsyncRepositoryOperations(Protocol):
    """Protocol for asynchronous repository operations."""
    
    @abstractmethod
    async def get_repository_status_async(self, repo_path: GitRepositoryPath) -> GitStatusResult:
        """Async version of get_repository_status."""
        ...
    
    @abstractmethod
    async def clone_repository_async(self, url: str, destination: Union[str, Path],
                                   progress_callback: Optional[callable] = None) -> GitOperationResult:
        """
        Async clone with progress reporting.
        
        Args:
            url: URL of repository to clone
            destination: Local path for cloned repository
            progress_callback: Optional callback for progress updates
            
        Returns:
            GitOperationResult indicating success or failure
        """
        ...
    
    @abstractmethod
    async def fetch_with_progress(self, repo_path: GitRepositoryPath, 
                                 remote_name: str = "origin") -> AsyncIterator[str]:
        """
        Fetch with real-time progress updates.
        
        Args:
            repo_path: Valid Git repository path
            remote_name: Name of remote to fetch from
            
        Yields:
            Progress messages during fetch operation
        """
        ...