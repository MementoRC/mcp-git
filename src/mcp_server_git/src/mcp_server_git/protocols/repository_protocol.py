from abc import abstractmethod
from typing import Protocol, Any, List, Tuple, Optional, Union


class RepositoryProtocol(Protocol):
    """
    Protocol defining the interface for Git repository operations.

    This protocol specifies methods for interacting with a Git repository,
    including status checks, file operations, branch management, and direct
    Git command execution.
    """

    @abstractmethod
    async def get_status(self, repo_path: str) -> Any:
        """
        Asynchronously retrieves the current status of the Git repository.

        This method should provide information about modified, added, deleted,
        and untracked files, as well as the current branch and commit.

        Args:
            repo_path: The absolute path to the Git repository.

        Returns:
            Any: A detailed status object or dictionary representing the
                 repository's current state. (e.g., a Pydantic model like GitStatus)

        Raises:
            GitValidationError: If the provided path is not a valid Git repository.
        """
        ...

    @abstractmethod
    async def add(self, repo_path: str, paths: List[str]) -> None:
        """
        Asynchronously stages changes for the specified paths in the repository.

        Args:
            repo_path: The absolute path to the Git repository.
            paths: A list of file or directory paths to add to the staging area.
                   Use ['.'] to add all changes.

        Raises:
            GitValidationError: If the repository path is invalid or paths do not exist.
        """
        ...

    @abstractmethod
    async def commit(self, repo_path: str, message: str) -> str:
        """
        Asynchronously commits staged changes to the repository.

        Args:
            repo_path: The absolute path to the Git repository.
            message: The commit message.

        Returns:
            str: The hash of the newly created commit.

        Raises:
            GitValidationError: If no changes are staged or the repository is invalid.
        """
        ...

    @abstractmethod
    async def checkout(self, repo_path: str, ref: str) -> None:
        """
        Asynchronously checks out a specific branch, commit, or tag.

        Args:
            repo_path: The absolute path to the Git repository.
            ref: The branch name, commit hash, or tag to check out.

        Raises:
            GitValidationError: If the reference does not exist or checkout fails.
        """
        ...

    @abstractmethod
    async def create_branch(self, repo_path: str, branch_name: str, start_point: Optional[str] = None) -> None:
        """
        Asynchronously creates a new branch in the repository.

        Args:
            repo_path: The absolute path to the Git repository.
            branch_name: The name of the new branch to create.
            start_point: Optional. The commit or branch from which to start the new branch.
                         Defaults to the current HEAD.

        Raises:
            GitValidationError: If the branch already exists or the start_point is invalid.
        """
        ...

    @abstractmethod
    async def list_branches(self, repo_path: str) -> List[str]:
        """
        Asynchronously lists all local branches in the repository.

        Args:
            repo_path: The absolute path to the Git repository.

        Returns:
            List[str]: A list of branch names.

        Raises:
            GitValidationError: If the repository path is invalid.
        """
        ...

    @abstractmethod
    async def is_valid_path(self, repo_path: str, path: str) -> bool:
        """
        Asynchronously checks if a given path exists within the repository's working tree.

        Args:
            repo_path: The absolute path to the Git repository.
            path: The path to check, relative to the repository root.

        Returns:
            bool: True if the path exists and is within the repository, False otherwise.
        """
        ...

    @abstractmethod
    async def run_git_command(self, repo_path: str, command: List[str]) -> Tuple[int, str, str]:
        """
        Asynchronously executes an arbitrary Git command within the repository context.

        This method provides a low-level interface for executing Git commands
        that might not be covered by other specific methods.

        Args:
            repo_path: The absolute path to the Git repository.
            command: A list of strings representing the Git command and its arguments
                     (e.g., ['log', '--oneline']).

        Returns:
            Tuple[int, str, str]: A tuple containing the exit code, standard output,
                                  and standard error of the command.

        Raises:
            GitValidationError: If the repository path is invalid or the command fails.
        """
        ...

    @abstractmethod
    async def clone(self, repo_url: str, target_path: str) -> None:
        """
        Asynchronously clones a remote Git repository to a local path.

        Args:
            repo_url: The URL of the remote repository to clone.
            target_path: The local path where the repository should be cloned.

        Raises:
            GitValidationError: If cloning fails (e.g., invalid URL, permissions).
        """
        ...

    @abstractmethod
    async def pull(self, repo_path: str, remote: str = "origin", branch: Optional[str] = None) -> None:
        """
        Asynchronously pulls changes from a remote repository.

        Args:
            repo_path: The absolute path to the Git repository.
            remote: The name of the remote to pull from (default: 'origin').
            branch: Optional. The name of the branch to pull. If None, pulls the current branch.

        Raises:
            GitValidationError: If pulling fails (e.g., merge conflicts, network issues).
        """
        ...

    @abstractmethod
    async def push(self, repo_path: str, remote: str = "origin", branch: Optional[str] = None) -> None:
        """
        Asynchronously pushes changes to a remote repository.

        Args:
            repo_path: The absolute path to the Git repository.
            remote: The name of the remote to push to (default: 'origin').
            branch: Optional. The name of the branch to push. If None, pushes the current branch.

        Raises:
            GitValidationError: If pushing fails (e.g., authentication, non-fast-forward).
        """
        ...

    @abstractmethod
    async def get_file_content(self, repo_path: str, file_path: str, ref: str = "HEAD") -> str:
        """
        Asynchronously retrieves the content of a file at a specific reference.

        Args:
            repo_path: The absolute path to the Git repository.
            file_path: The path to the file within the repository.
            ref: The branch, commit hash, or tag from which to retrieve the file content.
                 Defaults to 'HEAD'.

        Returns:
            str: The content of the file as a string.

        Raises:
            GitValidationError: If the file or reference does not exist.
        """
        ...

    @abstractmethod
    async def write_file_content(self, repo_path: str, file_path: str, content: str) -> None:
        """
        Asynchronously writes content to a file within the repository's working tree.

        This method will create the file if it doesn't exist or overwrite it if it does.
        Note: This only writes to the working directory, it does not stage or commit.

        Args:
            repo_path: The absolute path to the Git repository.
            file_path: The path to the file within the repository to write to.
            content: The string content to write to the file.

        Raises:
            GitValidationError: If the repository path is invalid or writing fails.
        """
        ...

    @abstractmethod
    async def delete_file(self, repo_path: str, file_path: str) -> None:
        """
        Asynchronously deletes a file from the repository's working tree.

        Note: This only deletes from the working directory, it does not stage or commit.

        Args:
            repo_path: The absolute path to the Git repository.
            file_path: The path to the file within the repository to delete.

        Raises:
            GitValidationError: If the file does not exist or deletion fails.
        """
        ...
