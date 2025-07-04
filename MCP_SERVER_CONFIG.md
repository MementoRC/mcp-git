# MCP Git Server Configuration with Pixi

This document explains how to configure and run the MCP Git server using pixi package management.

## Overview

The MCP Git server now supports pixi-based execution, allowing for consistent environment management and easy integration with MCP clients like Claude Desktop.

## Running the MCP Server

### Basic Usage

To run the MCP server with pixi:

```bash
pixi run mcp-server
```

This will start the server in stdio mode, which is the standard mode for MCP servers.

### With Repository Path

To specify a particular Git repository:

```bash
pixi run mcp-server -- -r /path/to/your/repo
```

### With Verbose Logging

For debugging, you can enable verbose logging:

```bash
pixi run mcp-server -- -v  # Info level
pixi run mcp-server -- -vv # Debug level
```

### With File Logging

To enable logging to a file:

```bash
pixi run mcp-server -- --enable-file-logging
```

## Claude Desktop Configuration

To configure this server in Claude Desktop, add the following to your Claude configuration file:

### Example Configuration

```json
{
  "mcpServers": {
    "git": {
      "command": "pixi",
      "args": [
        "run",
        "--manifest-path",
        "/home/memento/ClaudeCode/Servers/git/worktrees/feat-llm-compliance",
        "mcp-server",
        "-r",
        "/path/to/your/git/repo"
      ],
      "cwd": "/home/memento/ClaudeCode/Servers/git/worktrees/feat-llm-compliance"
    }
  }
}
```

### Advanced Configuration with Multiple Repositories

You can configure multiple instances for different repositories:

```json
{
  "mcpServers": {
    "git-project1": {
      "command": "pixi",
      "args": [
        "run",
        "--manifest-path",
        "/home/memento/ClaudeCode/Servers/git/worktrees/feat-llm-compliance",
        "mcp-server",
        "-r",
        "/path/to/project1"
      ],
      "cwd": "/path/to/project1"
    },
    "git-project2": {
      "command": "pixi",
      "args": [
        "run",
        "--manifest-path",
        "/home/memento/ClaudeCode/Servers/git/worktrees/feat-llm-compliance",
        "mcp-server",
        "-r",
        "/path/to/project2"
      ],
      "cwd": "/path/to/project2"
    }
  }
}
```

## Environment Variables

The server supports loading environment variables from `.env` files in the following order:

1. Project-specific `.env` file (current working directory)
2. Repository-specific `.env` file (if repository path provided)
3. System environment variables

### GitHub Token Configuration

For GitHub API operations, ensure you have a valid `GITHUB_TOKEN` in your environment or `.env` file:

```env
GITHUB_TOKEN=your_github_personal_access_token
```

## Available Pixi Tasks

- `pixi run mcp-server` - Run the MCP server in stdio mode
- `pixi run serve` - Run the server (alternative command)
- `pixi run serve-simple` - Run the simplified server version
- `pixi run test` - Run tests
- `pixi run lint` - Run linting
- `pixi run quality` - Run full quality checks (test + lint + typecheck)

## Troubleshooting

### Server Not Starting

1. Ensure pixi is installed: `pixi --version`
2. Install dependencies: `pixi install`
3. Check for Python errors: `pixi run python -m mcp_server_git --help`

### Connection Issues

1. Enable verbose logging: `pixi run mcp-server -- -vv`
2. Check file logging: `pixi run mcp-server -- --enable-file-logging`
3. Verify the manifest path points to the correct project directory

### Environment Issues

1. Ensure PYTHONPATH includes src: The pixi task already sets this
2. Check `.env` file locations and permissions
3. Verify GitHub token is valid (if using GitHub features)

## Development

To modify the server while using pixi:

1. The package is installed in editable mode automatically
2. Changes to source files will be reflected immediately
3. Run `pixi install` after modifying dependencies

For more information about the MCP protocol, see: https://github.com/anthropics/mcp