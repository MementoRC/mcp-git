# Git Status Porcelain Format Enhancement

## Overview

Enhanced the `git_status` function in the MCP Git Server to support the `--porcelain` format, providing machine-readable output that matches the standard `git status --porcelain` format.

## Changes Made

### 1. Updated GitStatus Model
**File**: `src/mcp_server_git/server.py`

Added an optional `porcelain` boolean parameter to the `GitStatus` model:

```python
class GitStatus(BaseModel):
    repo_path: str
    porcelain: bool = False
```

### 2. Enhanced git_status Function

Modified the `git_status` function to handle the porcelain parameter:

```python
def git_status(repo: git.Repo, porcelain: bool = False) -> str:
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
```

### 3. Updated Tool Description

Modified the tool description to indicate porcelain format support:

```python
Tool(
    name=GitTools.STATUS,
    description="Shows the working tree status with optional porcelain (machine-readable) format",
    inputSchema=GitStatus.model_json_schema(),
),
```

### 4. Enhanced Call Handler

Updated the call_tool handler to properly handle both boolean and string values for the porcelain parameter:

```python
case GitTools.STATUS:
    porcelain_raw = arguments.get("porcelain", False)
    # Handle both boolean and string values for porcelain parameter
    porcelain = porcelain_raw if isinstance(porcelain_raw, bool) else str(porcelain_raw).lower() in ('true', '1', 'yes')
    status = git_status(repo, porcelain)
    prefix = "Repository status (porcelain):" if porcelain else "Repository status:"
    return [TextContent(
        type="text",
        text=f"{prefix}\n{status}"
    )]
```

## Porcelain Format Specification

The porcelain format provides machine-readable output where each line follows the pattern:

```
XY filename
```

Where:
- `X` = index status (staged changes)
- `Y` = worktree status (working directory changes)
- ` ` (space) = separator
- `filename` = path to the file

### Status Characters

- ` ` (space) = unmodified
- `M` = modified
- `A` = added
- `D` = deleted
- `R` = renamed
- `C` = copied
- `U` = unmerged
- `?` = untracked
- `!` = ignored

### Example Output

**Standard format**:
```
On branch master
Changes to be committed:
  (use "git restore --staged <file>..." to unstage)
	modified:   main.py

Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
	modified:   README.md

Untracked files:
  (use "git add <file>..." to include in what will be committed)
	new_file.txt
```

**Porcelain format**:
```
 M README.md
M  main.py
?? new_file.txt
```

## Usage

### MCP Tool Usage

```python
# Default (human-readable) format
mcp__git__git_status(repo_path="/path/to/repo")

# Porcelain (machine-readable) format
mcp__git__git_status(repo_path="/path/to/repo", porcelain=True)
```

### Direct Function Usage

```python
from mcp_server_git.server import git_status
import git

repo = git.Repo("/path/to/repo")

# Human-readable format
status = git_status(repo, porcelain=False)

# Machine-readable format
status = git_status(repo, porcelain=True)
```

## Testing

Added comprehensive tests in `tests/test_server.py`:

1. `test_git_status_default_format()` - Tests human-readable format
2. `test_git_status_porcelain_format()` - Tests machine-readable format
3. `test_git_status_porcelain_string_parameter()` - Tests parameter conversion

All tests verify:
- Correct format output
- Proper file detection
- Format-specific characteristics
- Parameter handling robustness

## Benefits

1. **Machine Parsing**: The porcelain format provides consistent, script-friendly output
2. **Backward Compatibility**: Default behavior remains unchanged
3. **Standard Compliance**: Matches Git's official `--porcelain` format
4. **Flexible Input**: Handles both boolean and string parameter values
5. **Comprehensive Testing**: Full test coverage ensures reliability

## Files Modified

- `src/mcp_server_git/server.py` - Main implementation
- `tests/test_server.py` - Added comprehensive tests

## Verification

The implementation has been thoroughly tested and verified to:
- Match standard Git porcelain format output
- Handle various file states correctly
- Maintain backward compatibility
- Work with both direct function calls and MCP tool interface