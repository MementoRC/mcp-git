"""Git config operations for MCP Git Server."""

import logging
import re
from pathlib import Path

from ..utils.git_import import GitCommandError, Repo
from ..utils.tool_failure import fail
from .error_text import clean_git_error_text

logger = logging.getLogger(__name__)

__all__ = [
    "_build_config_scope_flags",
    "_validate_config_key",
    "_validate_config_file",
    "git_config_get",
    "git_config_set",
    "git_config_list",
]

_CONFIG_KEY_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9._/\\-]*[a-zA-Z0-9])?$")
_CONFIG_SCOPES = ("local", "global", "system", "worktree")


def _build_config_scope_flags(scope: str | None) -> list[str]:
    """Return the git CLI flag list (``--<scope>``) for a validated config scope."""
    if scope is None:
        return []
    if scope not in _CONFIG_SCOPES:
        raise ValueError(
            f"Invalid scope '{scope}'. Valid values: {', '.join(_CONFIG_SCOPES)}"
        )
    return [f"--{scope}"]


def _validate_config_key(key: str) -> None:
    """Raise ValueError if key contains characters that could cause injection."""
    if not _CONFIG_KEY_RE.match(key):
        raise ValueError(
            f"Invalid config key '{key}'. Keys must contain only alphanumeric characters, "
            "dots, dashes, and underscores (e.g., 'user.name', 'core.filemode')"
        )


def _validate_config_file(repo: Repo, file: str) -> None:
    """Raise ValueError if file path attempts to escape the repository directory."""
    # Reject any path that contains '..' components
    file_path = Path(file)
    if ".." in file_path.parts:
        raise ValueError(
            f"Invalid file path '{file}': path must not contain '..' components"
        )
    # Reject absolute paths that are outside the repo
    if file_path.is_absolute():
        try:
            file_path.relative_to(Path(repo.working_dir))
        except ValueError as e:
            raise ValueError(
                f"Invalid file path '{file}': absolute path must be within the repository"
            ) from e
    # Resolve to catch symlink escapes (belt-and-suspenders)
    repo_root = Path(repo.working_dir).resolve()
    resolved = (repo_root / file_path).resolve()
    if not str(resolved).startswith(str(repo_root)):
        raise ValueError(f"Config file path escapes repository: {file}")


def git_config_get(
    repo: Repo,
    key: str,
    file: str | None = None,
    scope: str | None = None,
) -> str:
    """Read a git config value.

    Args:
        repo: Git repository object
        key: Config key to read (e.g., 'user.name', 'core.filemode')
        file: Path to a specific config file (e.g., '.gitmodules')
        scope: Config scope: 'local' (default), 'global', or 'system'

    Returns:
        The config value or an error message
    """
    try:
        _validate_config_key(key)
        flags = _build_config_scope_flags(scope)
        if file:
            _validate_config_file(repo, file)
            value = repo.git.config(*flags, key, f=file)
        else:
            value = repo.git.config(*flags, key)
        return f"{key} = {value}"
    except ValueError as e:
        return fail(f"❌ {e}")
    except GitCommandError as e:
        return fail(f"❌ Config get failed: {clean_git_error_text(e.stderr, 'stderr')}")
    except Exception as e:
        return fail(f"❌ Config get error: {str(e)}")


def git_config_set(
    repo: Repo,
    key: str,
    value: str,
    file: str | None = None,
    scope: str | None = None,
) -> str:
    """Set a git config value.

    Args:
        repo: Git repository object
        key: Config key to set (e.g., 'user.name', 'core.filemode')
        value: Value to set
        file: Path to a specific config file (e.g., '.gitmodules')
        scope: Config scope: 'local' (default), 'global', or 'system'

    Returns:
        Success or error message
    """
    try:
        _validate_config_key(key)
        flags = _build_config_scope_flags(scope)
        if file:
            _validate_config_file(repo, file)
            repo.git.config(*flags, key, value, f=file)
        else:
            repo.git.config(*flags, key, value)
        scope_info = f" [{scope}]" if scope else ""
        file_info = f" in {file}" if file else ""
        return f"✅ Config set{scope_info}{file_info}: {key} = {value}"
    except ValueError as e:
        return fail(f"❌ {e}")
    except GitCommandError as e:
        return fail(f"❌ Config set failed: {clean_git_error_text(e.stderr, 'stderr')}")
    except Exception as e:
        return fail(f"❌ Config set error: {str(e)}")


def git_config_list(
    repo: Repo,
    file: str | None = None,
    scope: str | None = None,
) -> str:
    """List all git config entries.

    Args:
        repo: Git repository object
        file: Path to a specific config file to list (e.g., '.gitmodules')
        scope: Config scope: 'local' (default), 'global', or 'system'

    Returns:
        Formatted list of config entries or an error message
    """
    try:
        flags = _build_config_scope_flags(scope)
        if file:
            _validate_config_file(repo, file)
            output = repo.git.config(*flags, "--list", f=file)
        else:
            output = repo.git.config(*flags, "--list")
        if not output.strip():
            return "No config entries found"
        source = file if file else (scope or "local")
        return f"Git config [{source}]:\n{output}"
    except ValueError as e:
        return fail(f"❌ {e}")
    except GitCommandError as e:
        return fail(
            f"❌ Config list failed: {clean_git_error_text(e.stderr, 'stderr')}"
        )
    except Exception as e:
        return fail(f"❌ Config list error: {str(e)}")
