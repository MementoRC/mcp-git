# GitHub Repository Settings Management

This guide explains how to use mcp-git's GitHub Repository Settings Management tools to automate repository configuration.

## Prerequisites

1. **GitHub Token**: Set the `GITHUB_TOKEN` environment variable with a GitHub personal access token that has repository administration permissions.

2. **Repository Access**: Ensure your token has access to the repositories you want to configure.

## Available Tools

### 1. Repository Settings (`github_repo_settings`)

Configure basic repository settings like merge options and feature enablement.

**Example: Standard Organization Setup**
```python
await call_tool("github_repo_settings", {
    "repo_owner": "your-org",
    "repo_name": "your-repo",
    "has_issues": True,
    "has_projects": True,
    "has_wiki": False,
    "allow_squash_merge": True,
    "allow_merge_commit": False,
    "allow_rebase_merge": True,
    "delete_branch_on_merge": True,
    "allow_auto_merge": True,
    "squash_merge_commit_title": "PR_TITLE",
    "squash_merge_commit_message": "PR_BODY"
})
```

### 2. GitHub Actions Settings (`github_actions_settings`)

Configure GitHub Actions permissions and allowed actions.

**Example: Organization-Only Actions**
```python
await call_tool("github_actions_settings", {
    "repo_owner": "your-org",
    "repo_name": "your-repo",
    "enabled": True,
    "allowed_actions": "selected",
    "github_owned_allowed": True,
    "verified_allowed": True,
    "patterns_allowed": ["your-org/*", "actions/*"]
})
```

### 3. Workflow Permissions (`github_workflow_permissions`)

Configure default workflow permissions for GitHub Actions.

**Example: Enable PR Approval by Workflows**
```python
await call_tool("github_workflow_permissions", {
    "repo_owner": "your-org",
    "repo_name": "your-repo",
    "default_workflow_permissions": "write",
    "can_approve_pull_request_reviews": True
})
```

### 4. Branch Protection (`github_branch_protection`)

Set up branch protection rules for important branches.

**Example: Protect Main Branch**
```python
await call_tool("github_branch_protection", {
    "repo_owner": "your-org",
    "repo_name": "your-repo",
    "branch": "main",
    "required_status_checks": {
        "strict": True,
        "contexts": ["ci/build", "ci/test", "ci/lint"]
    },
    "enforce_admins": False,
    "required_pull_request_reviews": {
        "required_approving_review_count": 1,
        "dismiss_stale_reviews": True,
        "require_code_owner_reviews": False
    },
    "allow_force_pushes": False,
    "allow_deletions": False,
    "required_linear_history": True,
    "required_conversation_resolution": True
})
```

### 5. Security Settings (`github_security_settings`)

Configure repository security features.

**Example: Enable Security Features**
```python
await call_tool("github_security_settings", {
    "repo_owner": "your-org",
    "repo_name": "your-repo",
    "vulnerability_alerts": True,
    "automated_security_fixes": True,
    "security_and_analysis": {
        "secret_scanning": {"status": "enabled"},
        "secret_scanning_push_protection": {"status": "enabled"},
        "dependency_graph": {"status": "enabled"}
    }
})
```

## Common Use Cases

### 1. New Repository Setup

Automate the setup of a new repository with organization standards:

```python
# 1. Configure basic settings
await call_tool("github_repo_settings", {
    "repo_owner": "your-org",
    "repo_name": "new-repo",
    "has_issues": True,
    "has_wiki": False,
    "allow_squash_merge": True,
    "allow_merge_commit": False,
    "delete_branch_on_merge": True
})

# 2. Set up Actions
await call_tool("github_actions_settings", {
    "repo_owner": "your-org",
    "repo_name": "new-repo",
    "enabled": True,
    "allowed_actions": "selected",
    "github_owned_allowed": True,
    "patterns_allowed": ["your-org/*"]
})

# 3. Protect main branch
await call_tool("github_branch_protection", {
    "repo_owner": "your-org",
    "repo_name": "new-repo",
    "branch": "main",
    "required_pull_request_reviews": {
        "required_approving_review_count": 1
    },
    "allow_force_pushes": False
})

# 4. Enable security
await call_tool("github_security_settings", {
    "repo_owner": "your-org",
    "repo_name": "new-repo",
    "vulnerability_alerts": True,
    "automated_security_fixes": True
})
```

### 2. CI/CD Workflow Enablement

Enable workflows to create and approve pull requests:

```python
# Enable workflow PR permissions (solves the original issue)
await call_tool("github_workflow_permissions", {
    "repo_owner": "your-org",
    "repo_name": "your-repo",
    "default_workflow_permissions": "write",
    "can_approve_pull_request_reviews": True
})
```

### 3. Security Compliance Audit

Ensure all repositories meet security standards:

```python
# Enable all security features
await call_tool("github_security_settings", {
    "repo_owner": "your-org",
    "repo_name": "your-repo",
    "vulnerability_alerts": True,
    "automated_security_fixes": True,
    "security_and_analysis": {
        "secret_scanning": {"status": "enabled"},
        "secret_scanning_push_protection": {"status": "enabled"},
        "dependency_graph": {"status": "enabled"},
        "private_vulnerability_reporting": {"status": "enabled"}
    }
})
```

## Error Handling

All tools return descriptive error messages:

- `❌ GitHub token not configured` - Set GITHUB_TOKEN environment variable
- `❌ Failed to update repository settings: 404` - Repository not found or no access
- `❌ Failed to update branch protection: 403` - Insufficient permissions
- `❌ State must be 'open' or 'closed'` - Invalid parameter value

## Permissions Required

Your GitHub token needs the following permissions:

- **Repository administration** - For all settings changes
- **Actions** - For Actions and workflow permission changes  
- **Security events** - For security settings
- **Pull requests** - For branch protection rules

## Integration with CI/CD

These tools are designed to work with automation systems:

```yaml
# GitHub Actions example
- name: Configure Repository
  run: |
    python -c "
    import asyncio
    from mcp_server_git.core.handlers import CallToolHandler
    
    async def setup():
        handler = CallToolHandler()
        await handler.call_tool('github_repo_settings', {
            'repo_owner': '${{ github.repository_owner }}',
            'repo_name': '${{ github.event.repository.name }}',
            'allow_squash_merge': True,
            'delete_branch_on_merge': True
        })
    
    asyncio.run(setup())
    "
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## Related Documentation

- [GitHub REST API - Repository Settings](https://docs.github.com/en/rest/repos/repos)
- [GitHub REST API - Actions Permissions](https://docs.github.com/en/rest/actions/permissions)  
- [GitHub REST API - Branch Protection](https://docs.github.com/en/rest/branches/branch-protection)
- [Original Feature Request](https://github.com/MementoRC/mcp-git/issues/41)