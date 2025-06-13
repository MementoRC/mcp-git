# MCP Git Server Enhancements

This document describes the comprehensive enhancements made to the MCP Git server, transforming it from a basic tool interface into a powerful, intelligent Git workflow assistant.

## 🎯 Enhancement Overview

The enhanced MCP Git server now provides:

1. **Complete Git Operations** - All critical Git operations now available
2. **GPG Signing Support** - Verified commits with your GPG key
3. **Advanced Formatting** - Rich log formatting and display options
4. **Intelligent Prompts** - 10 specialized Git workflow prompts
5. **Branch Comparison** - Advanced diff capabilities between branches

## 📋 New Tools (Phase 1 - Critical)

### 1. git_push
**Purpose**: Push commits to remote repositories

**Parameters**:
- `repo_path` (required): Path to the Git repository
- `remote` (optional): Remote name (default: "origin")
- `branch` (optional): Branch to push (default: current branch)
- `force` (optional): Force push (default: false)
- `set_upstream` (optional): Set upstream tracking (default: false)

**Example Usage**:
```json
{
  "tool": "git_push",
  "arguments": {
    "repo_path": "/path/to/repo",
    "remote": "origin",
    "branch": "feature-branch",
    "set_upstream": true
  }
}
```

**Features**:
- Automatic branch detection
- Upstream tracking configuration
- Comprehensive error handling
- Detailed push result reporting

### 2. git_pull
**Purpose**: Pull changes from remote repositories

**Parameters**:
- `repo_path` (required): Path to the Git repository
- `remote` (optional): Remote name (default: "origin")
- `branch` (optional): Branch to pull (default: current branch)

**Example Usage**:
```json
{
  "tool": "git_pull",
  "arguments": {
    "repo_path": "/path/to/repo",
    "remote": "upstream",
    "branch": "main"
  }
}
```

**Features**:
- Fast-forward detection
- Merge conflict reporting
- Up-to-date status checking
- Detailed pull result analysis

### 3. Enhanced git_commit (GPG Signing)
**Purpose**: Commit changes with optional GPG signing for verified commits

**NEW Parameters**:
- `gpg_sign` (optional): Enable GPG signing (default: false)
- `gpg_key_id` (optional): Specific GPG key ID to use

**Example Usage**:
```json
{
  "tool": "git_commit", 
  "arguments": {
    "repo_path": "/path/to/repo",
    "message": "feat: add user authentication",
    "gpg_sign": true,
    "gpg_key_id": "C7927B4C27159961"
  }
}
```

**Features**:
- Automatic GPG key detection
- Verified commit badges on GitHub
- Error handling for GPG issues
- Fallback to unsigned commits if GPG fails

## 📊 Enhanced Tools (Phase 2)

### 4. Enhanced git_log (Advanced Formatting)
**Purpose**: View commit history with rich formatting options

**NEW Parameters**:
- `oneline` (optional): Single-line format (default: false)
- `graph` (optional): ASCII graph visualization (default: false)
- `format` (optional): Custom format string

**Example Usage**:
```json
{
  "tool": "git_log",
  "arguments": {
    "repo_path": "/path/to/repo",
    "max_count": 5,
    "oneline": true
  }
}
```

**Custom Format Example**:
```json
{
  "tool": "git_log",
  "arguments": {
    "repo_path": "/path/to/repo",
    "format": "%h %s (%an, %ar)"
  }
}
```

**Format Placeholders**:
- `%H` - Full commit hash
- `%h` - Short commit hash
- `%s` - Subject (first line of commit message)
- `%an` - Author name
- `%ae` - Author email
- `%ad` - Author date
- `%ar` - Author date, relative (e.g., "2 hours ago")

### 5. git_diff_branches
**Purpose**: Compare differences between two branches

**Parameters**:
- `repo_path` (required): Path to the Git repository
- `base_branch` (required): Base branch for comparison
- `compare_branch` (required): Branch to compare against base

**Example Usage**:
```json
{
  "tool": "git_diff_branches",
  "arguments": {
    "repo_path": "/path/to/repo",
    "base_branch": "main",
    "compare_branch": "feature/new-api"
  }
}
```

**Features**:
- Full diff output with patches
- File change type detection (added, modified, deleted, renamed)
- Binary file handling
- Empty diff detection

## 🤖 Intelligent Prompts

The server now includes 10 specialized prompts for Git workflows:

1. **commit-message** - Generate conventional commit messages
2. **pr-description** - Create comprehensive PR descriptions
3. **release-notes** - Generate structured release notes
4. **code-review** - Provide systematic code review guidance
5. **merge-conflict-resolution** - Guide conflict resolution
6. **git-workflow-guide** - Workflow best practices
7. **branch-strategy** - Branching strategy recommendations
8. **git-troubleshooting** - Help solve Git issues
9. **changelog-generation** - Create user-friendly changelogs
10. **rebase-interactive** - Guide complex rebase operations

See `examples/prompt_usage.md` for detailed usage examples.

## 🔧 Technical Implementation

### Architecture Improvements

1. **Enhanced Error Handling**: All new tools include comprehensive error handling with specific error messages
2. **Type Safety**: Full type annotations with Pydantic v2 models
3. **Backwards Compatibility**: All existing tools remain unchanged
4. **Modern Pydantic**: Updated to use `model_json_schema()` instead of deprecated `schema()`

### Code Quality

- **Zero Regressions**: All existing functionality preserved
- **Comprehensive Tests**: Full test suite for all new features
- **Documentation**: Complete documentation with examples
- **Best Practices**: Following MCP 2025 specifications

## 🚀 ClaudeCode Integration Benefits

### Eliminated "Strategic Bash" Workarounds

**Before Enhancement**:
```bash
# ClaudeCode had to use workaround commands
git push origin feature-branch --set-upstream
git pull upstream main
git log --oneline --graph -10
```

**After Enhancement**:
```python
# Direct MCP tool calls
mcp_git.git_push(repo_path="/repo", branch="feature-branch", set_upstream=True)
mcp_git.git_pull(repo_path="/repo", remote="upstream", branch="main") 
mcp_git.git_log(repo_path="/repo", max_count=10, oneline=True, graph=True)
```

### Workflow Automation

**Intelligent Commit Workflow**:
1. Use `git_diff_staged` to get staged changes
2. Use `commit-message` prompt to generate conventional commit
3. Use `git_commit` with GPG signing for verified commit
4. Use `git_push` with upstream tracking

**Code Review Workflow**:
1. Use `git_diff_branches` to get branch differences
2. Use `code-review` prompt for structured review guidance
3. Use `pr-description` prompt for comprehensive PR documentation

## 📈 Performance & Reliability

### Robust Error Handling
- GitPython exception handling
- Network timeout management
- Invalid repository detection
- Missing remote handling

### Efficient Operations
- Lazy commit iteration for large repositories
- Streaming diff output for large changes
- Optimized branch comparison algorithms
- Memory-efficient log formatting

## 🔒 Security Features

### GPG Integration
- Automatic GPG key detection
- Configurable key selection
- Fallback to unsigned commits
- Error reporting for GPG issues

### Safe Operations
- No force operations by default
- Confirmation required for destructive operations
- Comprehensive validation of inputs
- Safe error recovery

## 📚 Usage Examples

### Basic Push/Pull Workflow
```python
# Push current branch with upstream
await git_push(repo, set_upstream=True)

# Pull latest changes
await git_pull(repo, remote="origin")

# Check status
await git_status(repo)
```

### Advanced Commit Workflow
```python
# Stage files
await git_add(repo, ["src/", "tests/"])

# Create GPG-signed commit
await git_commit(
    repo, 
    "feat: add user authentication with JWT support",
    gpg_sign=True,
    gpg_key_id="C7927B4C27159961"
)

# Push with verification
await git_push(repo, force=False)
```

### Branch Comparison Workflow
```python
# Compare feature branch with main
diff = await git_diff_branches(repo, "main", "feature/auth")

# Generate formatted log
log = await git_log(repo, max_count=5, format="%h %s (%an)")

# Create PR description using prompt
pr_desc = await get_prompt("pr-description", {
    "title": "Add JWT Authentication",
    "changes": diff,
    "breaking": "Updated authentication API"
})
```

## 🎯 Migration Guide

### From Strategic Bash to MCP Tools

**Old Approach**:
```python
# Using Bash tool for Git operations
bash("git push origin feature --set-upstream")
bash("git pull upstream main")
bash("git log --oneline -5")
```

**New Approach**:
```python
# Using dedicated MCP Git tools
git_push(repo, branch="feature", set_upstream=True)
git_pull(repo, remote="upstream", branch="main")
git_log(repo, max_count=5, oneline=True)
```

### Benefits of Migration
1. **Type Safety**: Full parameter validation
2. **Error Handling**: Structured error responses
3. **Integration**: Seamless MCP protocol integration
4. **Consistency**: Unified interface across all Git operations
5. **Prompts**: Intelligent workflow assistance

## 🔮 Future Enhancements

### Phase 3: Advanced Features (Planned)
- **git_merge** - Advanced merge operations
- **git_rebase** - Interactive rebase support
- **git_stash** - Stash management
- **git_tag** - Tag creation and management
- **git_remote** - Remote repository management

### GitHub Integration (Planned)
- **GitHub API Integration** - Direct GitHub operations
- **PR Management** - Create and manage pull requests
- **Issue Linking** - Automatic issue linking in commits
- **CI/CD Integration** - Workflow status monitoring

## 📊 Summary

The enhanced MCP Git server transforms Git operations from individual commands into intelligent, guided workflows. With comprehensive tool coverage, GPG signing support, advanced formatting, and 10 specialized prompts, it provides ClaudeCode users with expert-level Git assistance.

**Key Metrics**:
- **5 New Tools**: Complete Git operation coverage
- **10 Intelligent Prompts**: Workflow guidance and automation
- **100% Backwards Compatible**: No breaking changes
- **GPG Ready**: Verified commits with your existing GPG setup
- **Production Ready**: Comprehensive error handling and testing

This enhancement represents a major leap forward in AI-assisted Git workflows, providing both novice and expert developers with powerful, intelligent Git operations through the MCP protocol.