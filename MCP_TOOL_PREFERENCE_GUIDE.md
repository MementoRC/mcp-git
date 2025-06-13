# MCP Tool Preference Guide for ClaudeCode

## 🚨 **CRITICAL: ALWAYS USE MCP TOOLS FIRST**

When working with Git repositories and GitHub operations, **ALWAYS prefer MCP tools over Bash commands**.

## 📋 **Direct Tool Mappings**

### **GitHub Operations**
| ❌ **DON'T USE (Bash)** | ✅ **USE (MCP Tool)** | **Purpose** |
|------------------------|----------------------|-------------|
| `Bash(gh pr checks 3 --repo ...)` | `github_get_pr_checks(repo_owner="...", repo_name="...", pr_number=3)` | Check CI status |
| `Bash(gh pr view 3 --repo ...)` | `github_get_pr_details(repo_owner="...", repo_name="...", pr_number=3)` | Get PR details |
| `Bash(gh pr checks --json ...)` | `github_get_failing_jobs(repo_owner="...", repo_name="...", pr_number=3, include_logs=True)` | Get failure details |

### **Git Operations**
| ❌ **DON'T USE (Bash)** | ✅ **USE (MCP Tool)** | **Purpose** |
|------------------------|----------------------|-------------|
| `Bash(git status)` | `mcp__git__git_status(repo_path=PROJECT_ROOT)` | Check repo status |
| `Bash(git add ...)` | `mcp__git__git_add(repo_path=PROJECT_ROOT, files=[...])` | Stage files |
| `Bash(git commit ...)` | `mcp__git__git_commit(repo_path=PROJECT_ROOT, message="...", gpg_sign=True)` | Commit changes |
| `Bash(git push ...)` | `mcp__git__git_push(repo_path=PROJECT_ROOT, remote="origin", branch="...")` | Push commits |
| `Bash(git pull ...)` | `mcp__git__git_pull(repo_path=PROJECT_ROOT, remote="origin", branch="...")` | Pull changes |

## 🎯 **Quick Reference Examples**

### **CI Status Check (Most Common)**
Instead of:
```bash
Bash(gh pr checks 3 --repo MementoRC/repo-name)
```

Use:
```python
github_get_pr_checks(
    repo_owner="MementoRC",
    repo_name="repo-name", 
    pr_number=3
)
```

### **CI Failure Analysis**
Instead of:
```bash
Bash(gh pr checks 3 --repo MementoRC/repo-name --json)
```

Use:
```python
github_get_failing_jobs(
    repo_owner="MementoRC",
    repo_name="repo-name",
    pr_number=3,
    include_logs=True,
    include_annotations=True
)
```

## 🔧 **Strategic Bash Usage (ONLY These Cases)**

✅ **Bash is ONLY allowed for**:
- Package manager commands: `pixi run test`, `poetry run lint`, `hatch run dev:pytest`
- Quality validation: `ruff check`, `pytest`, `pre-commit run`
- System operations: `sleep`, `echo`, environment variables

❌ **Bash is NEVER allowed for**:
- Any `git` commands
- Any `gh` commands
- Any GitHub API operations
- Any repository operations

## 🚀 **Benefits of MCP Tools**

1. **Type Safety**: Structured parameters prevent errors
2. **Better Error Handling**: Comprehensive error responses
3. **Enhanced Features**: GPG signing, detailed CI analysis
4. **Consistency**: Unified interface across all operations
5. **Intelligence**: Built-in failure analysis and smart prompts

## 💡 **When in Doubt**

**Rule of thumb**: If the operation involves Git or GitHub, there's almost certainly an MCP tool for it. Check the available MCP tools before falling back to Bash.

**Available MCP Tools**:
- All `mcp__git__*` tools for Git operations
- All `github_*` tools for GitHub operations  
- All `get_prompt()` tools for intelligent assistance

**Remember**: The goal is 95% MCP coverage, 5% strategic Bash. Most operations should use MCP tools!