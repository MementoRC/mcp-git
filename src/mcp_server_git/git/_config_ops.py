"""Git config operations for MCP Git Server."""

import logging
import re
from pathlib import Path

from ..utils.git_import import GitCommandError, Repo

logger = logging.getLogger(__name__)

__all__ = [
    "_build_config_scope_kwargs",
    "_validate_config_key",
    "_validate_config_file",
    "git_config_get",
    "git_config_set",
    "git_config_list",
]

_CONFIG_KEY_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9._/\\-]*[a-zA-Z0-9])?$")
_CONFIG_SCOPE_MAP = {
    "local": {},
    "global": {"_global": True},
    "system": {"system": True},
}


def _build_config_scope_kwargs(scope: str | None) -> dict:
    """Return GitPython keyword arguments for the requested config scope."""
    if scope is None or scope == "local":
        return {}
    if scope not in _CONFIG_SCOPE_MAP:
        raise ValueError(
            f"Invalid scope '{scope}'. Valid values: local, global, system"
        )
    return _CONFIG_SCOPE_MAP[scope]


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
        scope_kwargs = _build_config_scope_kwargs(scope)
        if file:
            _validate_config_file(repo, file)
            value = repo.git.config(key, f=file, **scope_kwargs)
        else:
            value = repo.git.config(key, **scope_kwargs)
        return f"{key} = {value}"
    except ValueError as e:
        return f"❌ {e}"
    except GitCommandError as e:
        return f"❌ Config get failed: {str(e)}"
    except Exception as e:
        return f"❌ Config get error: {str(e)}"


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
        scope_kwargs = _build_config_scope_kwargs(scope)
        if file:
            _validate_config_file(repo, file)
            repo.git.config(key, value, f=file, **scope_kwargs)
        else:
            repo.git.config(key, value, **scope_kwargs)
        scope_info = f" [{scope}]" if scope else ""
        file_info = f" in {file}" if file else ""
        return f"✅ Config set{scope_info}{file_info}: {key} = {value}"
    except ValueError as e:
        return f"❌ {e}"
    except GitCommandError as e:
        return f"❌ Config set failed: {str(e)}"
    except Exception as e:
        return f"❌ Config set error: {str(e)}"


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
        scope_kwargs = _build_config_scope_kwargs(scope)
        if file:
            _validate_config_file(repo, file)
            output = repo.git.config("--list", f=file, **scope_kwargs)
        else:
            output = repo.git.config("--list", **scope_kwargs)
        if not output.strip():
            return "No config entries found"
        source = file if file else (scope or "local")
        return f"Git config [{source}]:\n{output}"
    except ValueError as e:
        return f"❌ {e}"
    except GitCommandError as e:
        return f"❌ Config list failed: {str(e)}"
    except Exception as e:
        return f"❌ Config list error: {str(e)}"
