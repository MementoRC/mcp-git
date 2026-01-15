# mcp-server-git: A git MCP server

<!-- CI Test - investigating workflow trigger issues -->

## Overview

A Model Context Protocol server for Git repository interaction and automation. This server provides tools to read, search, and manipulate Git repositories via Large Language Models.

Please note that mcp-server-git is currently in early development. The functionality and available tools are subject to change and expansion as we continue to develop and improve the server.

### Tools

1. `git_status`
   - Shows the working tree status
   - Input:
     - `repo_path` (string): Path to Git repository
   - Returns: Current status of working directory as text output

2. `git_diff_unstaged`
   - Shows changes in working directory not yet staged
   - Input:
     - `repo_path` (string): Path to Git repository
   - Returns: Diff output of unstaged changes

3. `git_diff_staged`
   - Shows changes that are staged for commit
   - Input:
     - `repo_path` (string): Path to Git repository
   - Returns: Diff output of staged changes

4. `git_diff`
   - Shows differences between branches or commits
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `target` (string): Target branch or commit to compare with
   - Returns: Diff output comparing current state with target

5. `git_commit`
   - Records changes to the repository
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `message` (string): Commit message
   - Returns: Confirmation with new commit hash

6. `git_add`
   - Adds file contents to the staging area with support for batch operations
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `files` (string[], optional): Array of file paths to stage
     - `add_all` (boolean, optional): Stage all changes including untracked files (git add -A)
     - `update_only` (boolean, optional): Stage only tracked file updates and deletions (git add -u)
     - `patterns` (string[], optional): Array of glob patterns to match files (e.g., ["*.py", "src/**/*.js"])
   - Returns: Confirmation of staged files
   - Note: Only one of files, add_all, update_only, or patterns should be specified

7. `git_reset`
   - Unstages all staged changes
   - Input:
     - `repo_path` (string): Path to Git repository
   - Returns: Confirmation of reset operation

8. `git_log`
   - Shows the commit logs with advanced filtering and formatting
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `max_count` (number, optional): Maximum number of commits to show (default: 10)
     - `oneline` (boolean, optional): Compact format showing hash and message only (default: false)
     - `graph` (boolean, optional): Show merge graph structure (default: false)
     - `format` (string, optional): Custom format string (e.g., "%h - %s (%an)")
     - `since` (string, optional): Show commits after date (e.g., "2024-01-01", "1 week ago")
     - `until` (string, optional): Show commits before date (e.g., "yesterday", "2024-12-31")
     - `author` (string, optional): Filter by author name or email
     - `grep` (string, optional): Search commit messages with regex pattern
     - `files` (string[], optional): Show only commits affecting these files
     - `branch` (string, optional): Show log for specific branch (default: current)
     - `reverse` (boolean, optional): Show commits in reverse chronological order (default: false)
     - `merges` (boolean, optional): Filter merge commits (null=all, true=only merges, false=no merges)
   - Returns: Formatted commit log matching specified criteria
   - Examples:
     - Find recent fix commits: `{repo_path: ".", max_count: 20, grep: "fix:", oneline: true}`
     - Changes by author: `{repo_path: ".", author: "john@example.com", since: "1 month ago"}`
     - File history: `{repo_path: ".", files: ["src/main.py"], max_count: 50}`

9. `git_create_branch`
   - Creates a new branch
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `branch_name` (string): Name of the new branch
     - `base_branch` (string, optional): Starting point for the new branch
   - Returns: Confirmation of branch creation
10. `git_checkout`
   - Switches branches
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `branch_name` (string): Name of branch to checkout
   - Returns: Confirmation of branch switch
11. `git_show`
   - Shows the contents of a commit
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `revision` (string): The revision (commit hash, branch name, tag) to show
   - Returns: Contents of the specified commit
12. `git_init`
   - Initializes a Git repository
   - Inputs:
     - `repo_path` (string): Path to directory to initialize git repo
   - Returns: Confirmation of repository initialization

### Azure DevOps Integration

The server provides Azure DevOps integration for monitoring and analyzing Azure Pipelines builds:

1. `azure_get_build_status`
   - Get status of an Azure DevOps build/pipeline run
   - Inputs:
     - `project` (string): The project name or ID
     - `build_id` (integer): The build ID
   - Returns: Formatted build status information including definition, status, result, branch, and timing

2. `azure_get_build_logs`
   - Get logs from an Azure DevOps build
   - Inputs:
     - `project` (string): The project name or ID
     - `build_id` (integer): The build ID
     - `log_id` (integer, optional): Specific log ID to retrieve. If omitted, lists all logs
   - Returns: Log content or list of available logs

3. `azure_get_failing_jobs`
   - Get detailed information about failing jobs in an Azure DevOps build
   - Inputs:
     - `project` (string): The project name or ID
     - `build_id` (integer): The build ID
     - `include_logs` (boolean, optional): Whether to include log excerpts (default: true)
   - Returns: Detailed failure information including error messages and log excerpts

4. `azure_list_builds`
   - List builds for an Azure DevOps project with filtering
   - Inputs:
     - `project` (string): The project name or ID
     - `repository_id` (string, optional): Filter by repository ID
     - `branch_name` (string, optional): Filter by branch name (e.g., 'refs/heads/main')
     - `status` (string, optional): Filter by status (notStarted, inProgress, completed, etc.)
     - `result` (string, optional): Filter by result (succeeded, failed, canceled, etc.)
     - `top` (integer, optional): Maximum number of builds to return (default: 30)
     - `continuation_token` (string, optional): Token for pagination
   - Returns: List of builds with status, result, and metadata

**Configuration**: Azure DevOps integration requires setting `AZURE_DEVOPS_TOKEN` and `AZURE_DEVOPS_ORG` environment variables. See the Environment Variables section for details.

### Lean MCP Interface (Context-Optimized)

The server provides an alternative **lean interface** that reduces context consumption by ~97% (from ~30k tokens to ~900 tokens). Instead of exposing all 51 tools upfront, it uses a 3-meta-tool pattern:

| Meta-Tool | Purpose |
|-----------|---------|
| `discover_tools(pattern)` | List available tools with optional filtering |
| `get_tool_spec(tool_name)` | Get full schema for a specific tool on-demand |
| `execute_tool(tool_name, params)` | Execute any tool dynamically |

**Tool Coverage**: All 51 tools remain accessible (25 git, 22 GitHub, 4 Azure DevOps).

**Usage Example**:
```python
# 1. Discover available tools (optional filtering)
discover_tools("pr")  # Returns 11 PR-related tools

# 2. Get schema when needed
get_tool_spec("github_create_pr")  # Returns full parameter schema

# 3. Execute the tool
execute_tool("github_create_pr", {
    "repo_owner": "owner",
    "repo_name": "repo",
    "title": "feat: new feature",
    "head": "feature-branch",
    "base": "main"
})
```

**Configuration**: Use the `mcp-git-lean` entry point:
```json
"mcpServers": {
  "git-lean": {
    "command": "pixi",
    "args": ["run", "-m", "mcp-git-lean", "--repository", "path/to/repo"]
  }
}
```

### Important: Repository Path Resolution

The `repo_path` parameter in all git tools supports the following behaviors:

- **Absolute paths**: Always used directly (e.g., `/home/user/my-repo`)
- **"." (current directory)**: Resolves to the bound repository when the server is started with the `--repository` parameter. If no repository is bound, the operation will fail with a clear error message.
- **Relative paths**: Converted to absolute paths relative to the current working directory. For best reliability, use absolute paths or bind a repository with `--repository`.

**Recommended Usage**:
- When starting the server, use the `--repository` parameter to bind to a specific repository
- In tool calls, use `repo_path: "."` to reference the bound repository
- For operations on different repositories, provide absolute paths

**Example**:
```bash
# Start server bound to a repository
mcp-server-git --repository /path/to/my-repo

# Then use "." in tool calls to reference the bound repository
# This prevents cross-repository contamination
```

## Installation

### Using uv (recommended)

When using [`uv`](https://docs.astral.sh/uv/) no specific installation is needed. We will
use [`uvx`](https://docs.astral.sh/uv/guides/tools/) to directly run *mcp-server-git*.

### Using PIP

Alternatively you can install `mcp-server-git` via pip:

```
pip install mcp-server-git
```

Note: For development, use `pixi install` instead of pip for proper dependency management.

After installation, you can run it as a script using:

```
python -m mcp_server_git
```

## Configuration

### Environment Variables

The server supports loading environment variables from `.env` files with the following precedence order:

1. **Project-specific .env file** - `.env` file in the current working directory
2. **Repository-specific .env file** - `.env` file in the repository directory (when using `--repository` argument)
3. **ClaudeCode working directory .env file** - `.env` file in ClaudeCode workspace root (automatically detected)
4. **System environment variables** - Standard environment variables

#### Example .env file

Create a `.env` file in your project directory or ClaudeCode workspace:

```bash
# GitHub API Token for GitHub integration features
# Get your token from: https://github.com/settings/tokens
GITHUB_TOKEN=your_github_token_here

# Optional: Custom GitHub API base URL (for GitHub Enterprise)
# GITHUB_API_BASE_URL=https://api.github.com

# Azure DevOps Configuration
# Get your Personal Access Token from: https://dev.azure.com/{organization}/_usersSettings/tokens
# The token should have 'Build (Read)' scope at minimum
AZURE_DEVOPS_TOKEN=your_azure_devops_pat_token_here
AZURE_DEVOPS_ORG=your_organization_name

# Optional: Log level for debugging
# LOG_LEVEL=INFO
```

**Note**: The `.env` file is loaded automatically when the server starts. The server intelligently detects ClaudeCode workspace directories by traversing up from both the current working directory and the repository path (if provided via `--repository` argument). If no `.env` files are found, the server will use system environment variables.

**For ClaudeCode users**: If you have your `.env` file in your ClaudeCode workspace root (e.g., `/home/memento/ClaudeCode/.env`), it will be automatically detected and loaded when running the MCP server from any subdirectory within that workspace.

### Usage with Claude Desktop

Add this to your `claude_desktop_config.json`:

<details>
<summary>Using uvx</summary>

```json
"mcpServers": {
  "git": {
    "command": "uvx",
    "args": ["mcp-server-git", "--repository", "path/to/git/repo"]
  }
}
```
</details>

<details>
<summary>Using docker</summary>

* Note: replace '/Users/username' with the a path that you want to be accessible by this tool

```json
"mcpServers": {
  "git": {
    "command": "docker",
    "args": ["run", "--rm", "-i", "--mount", "type=bind,src=/Users/username,dst=/Users/username", "mcp/git"]
  }
}
```
</details>

<details>
<summary>Using pip installation</summary>

```json
"mcpServers": {
  "git": {
    "command": "python",
    "args": ["-m", "mcp_server_git", "--repository", "path/to/git/repo"]
  }
}
```
</details>

### Usage with VS Code

For quick installation, use one of the one-click install buttons below...

[![Install with UV in VS Code](https://img.shields.io/badge/VS_Code-UV-0098FF?style=flat-square&logo=visualstudiocode&logoColor=white)](https://insiders.vscode.dev/redirect/mcp/install?name=git&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22mcp-server-git%22%5D%7D) [![Install with UV in VS Code Insiders](https://img.shields.io/badge/VS_Code_Insiders-UV-24bfa5?style=flat-square&logo=visualstudiocode&logoColor=white)](https://insiders.vscode.dev/redirect/mcp/install?name=git&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22mcp-server-git%22%5D%7D&quality=insiders)

[![Install with Docker in VS Code](https://img.shields.io/badge/VS_Code-Docker-0098FF?style=flat-square&logo=visualstudiocode&logoColor=white)](https://insiders.vscode.dev/redirect/mcp/install?name=git&config=%7B%22command%22%3A%22docker%22%2C%22args%22%3A%5B%22run%22%2C%22--rm%22%2C%22-i%22%2C%22--mount%22%2C%22type%3Dbind%2Csrc%3D%24%7BworkspaceFolder%7D%2Cdst%3D%2Fworkspace%22%2C%22mcp%2Fgit%22%5D%7D) [![Install with Docker in VS Code Insiders](https://img.shields.io/badge/VS_Code_Insiders-Docker-24bfa5?style=flat-square&logo=visualstudiocode&logoColor=white)](https://insiders.vscode.dev/redirect/mcp/install?name=git&config=%7B%22command%22%3A%22docker%22%2C%22args%22%3A%5B%22run%22%2C%22--rm%22%2C%22-i%22%2C%22--mount%22%2C%22type%3Dbind%2Csrc%3D%24%7BworkspaceFolder%7D%2Cdst%3D%2Fworkspace%22%2C%22mcp%2Fgit%22%5D%7D&quality=insiders)

For manual installation, add the following JSON block to your User Settings (JSON) file in VS Code. You can do this by pressing `Ctrl + Shift + P` and typing `Preferences: Open Settings (JSON)`.

Optionally, you can add it to a file called `.vscode/mcp.json` in your workspace. This will allow you to share the configuration with others.

> Note that the `mcp` key is not needed in the `.vscode/mcp.json` file.

```json
{
  "mcp": {
    "servers": {
      "git": {
        "command": "uvx",
        "args": ["mcp-server-git"]
      }
    }
  }
}
```

For Docker installation:

```json
{
  "mcp": {
    "servers": {
      "git": {
        "command": "docker",
        "args": [
          "run",
          "--rm",
          "-i",
          "--mount", "type=bind,src=${workspaceFolder},dst=/workspace",
          "mcp/git"
        ]
      }
    }
  }
}
```

### Usage with [Zed](https://github.com/zed-industries/zed)

Add to your Zed settings.json:

<details>
<summary>Using uvx</summary>

```json
"context_servers": [
  "mcp-server-git": {
    "command": {
      "path": "uvx",
      "args": ["mcp-server-git"]
    }
  }
],
```
</details>

<details>
<summary>Using pip installation</summary>

```json
"context_servers": {
  "mcp-server-git": {
    "command": {
      "path": "python",
      "args": ["-m", "mcp_server_git"]
    }
  }
},
```
</details>

## Debugging

You can use the MCP inspector to debug the server. For uvx installations:

```
npx @modelcontextprotocol/inspector uvx mcp-server-git
```

Or if you've installed the package in a specific directory or are developing on it:

```
cd path/to/servers/src/git
npx @modelcontextprotocol/inspector uv run mcp-server-git
```

Running `tail -n 20 -f ~/Library/Logs/Claude/mcp*.log` will show the logs from the server and may
help you debug any issues.

## Development

If you are doing local development, there are two ways to test your changes:

1. Run the MCP inspector to test your changes. See [Debugging](#debugging) for run instructions.

2. Test using the Claude desktop app. Add the following to your `claude_desktop_config.json`:

### Docker

```json
{
  "mcpServers": {
    "git": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--mount", "type=bind,src=/Users/username/Desktop,dst=/projects/Desktop",
        "--mount", "type=bind,src=/path/to/other/allowed/dir,dst=/projects/other/allowed/dir,ro",
        "--mount", "type=bind,src=/path/to/file.txt,dst=/projects/path/to/file.txt",
        "mcp/git"
      ]
    }
  }
}
```

### UVX
```json
{
"mcpServers": {
  "git": {
    "command": "uv",
    "args": [
      "--directory",
      "/<path to mcp-servers>/mcp-servers/src/git",
      "run",
      "mcp-server-git"
    ]
  }
}
```

## Build

Docker build:

```bash
cd src/git
docker build -t mcp/git .
```

## License

This MCP server is licensed under the MIT License. This means you are free to use, modify, and distribute the software, subject to the terms and conditions of the MIT License. For more details, please see the LICENSE file in the project repository.
