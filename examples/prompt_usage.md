# MCP Git Server Prompt Usage Examples

This document demonstrates how to use the comprehensive Git workflow prompts available in the MCP Git server.

## Available Prompts

The MCP Git server provides 10 specialized prompts to help with common Git workflows:

1. **commit-message** - Generate conventional commit messages
2. **pr-description** - Create comprehensive pull request descriptions
3. **release-notes** - Generate release notes from commits
4. **code-review** - Assist with code reviews
5. **merge-conflict-resolution** - Guide conflict resolution
6. **git-workflow-guide** - Provide workflow best practices
7. **branch-strategy** - Recommend branching strategies
8. **git-troubleshooting** - Help solve Git issues
9. **changelog-generation** - Create changelogs from commits
10. **rebase-interactive** - Guide interactive rebase operations

## Usage Examples

### 1. Commit Message Generation

**Basic Usage:**
```json
{
  "prompt": "commit-message",
  "arguments": {
    "changes": "Added user authentication middleware with JWT support"
  }
}
```

**With Type and Scope:**
```json
{
  "prompt": "commit-message", 
  "arguments": {
    "changes": "Added user authentication middleware with JWT support",
    "type": "feat",
    "scope": "auth"
  }
}
```

### 2. Pull Request Description

```json
{
  "prompt": "pr-description",
  "arguments": {
    "title": "Add JWT Authentication Middleware",
    "changes": "- Implemented JWT token validation middleware\n- Added authentication error handling\n- Updated user session management\n- Added comprehensive test suite",
    "breaking": "Changed authentication API - clients must now include Authorization header"
  }
}
```

### 3. Release Notes Generation

```json
{
  "prompt": "release-notes",
  "arguments": {
    "version": "v2.1.0",
    "previous_version": "v2.0.0", 
    "commits": "feat(auth): add JWT middleware\nfix(api): resolve user session timeout\nfeat(ui): implement dark mode toggle\nfix(deps): update vulnerable packages\ndocs: update API documentation"
  }
}
```

### 4. Code Review Assistant

```json
{
  "prompt": "code-review",
  "arguments": {
    "diff": "@@ -45,6 +45,12 @@ class AuthMiddleware:\n+    def validate_token(self, token: str) -> bool:\n+        try:\n+            jwt.decode(token, self.secret_key, algorithms=['HS256'])\n+            return True\n+        except jwt.InvalidTokenError:\n+            return False\n+",
    "context": "Adding JWT token validation to authentication middleware for API security"
  }
}
```

### 5. Merge Conflict Resolution

```json
{
  "prompt": "merge-conflict-resolution",
  "arguments": {
    "conflicts": "<<<<<<< HEAD\n    def process_user(self, user_data):\n        return self.validate_user(user_data)\n=======\n    def process_user(self, user_info):\n        return self.authenticate_user(user_info)\n>>>>>>> feature/auth-refactor",
    "branch_info": "Merging feature/auth-refactor into main branch. Feature branch has authentication refactoring."
  }
}
```

### 6. Git Workflow Guide

```json
{
  "prompt": "git-workflow-guide",
  "arguments": {
    "workflow_type": "github-flow",
    "team_size": "5-10 developers"
  }
}
```

### 7. Branch Strategy Recommendation

```json
{
  "prompt": "branch-strategy",
  "arguments": {
    "project_type": "microservice",
    "deployment_frequency": "daily"
  }
}
```

### 8. Git Troubleshooting

```json
{
  "prompt": "git-troubleshooting", 
  "arguments": {
    "issue": "Cannot push to remote repository, getting 'non-fast-forward' error",
    "git_status": "On branch feature/new-api\nYour branch is ahead of 'origin/feature/new-api' by 3 commits.\nnothing to commit, working tree clean"
  }
}
```

### 9. Changelog Generation

```json
{
  "prompt": "changelog-generation",
  "arguments": {
    "commits": "feat: add user dashboard\nfix: resolve login timeout issue\nfeat: implement file upload\ndocs: update API documentation\nchore: update dependencies",
    "format": "keep-a-changelog"
  }
}
```

### 10. Interactive Rebase Guide

```json
{
  "prompt": "rebase-interactive",
  "arguments": {
    "commits": "abc123 feat: add user authentication\ndef456 fix: typo in auth middleware\nghi789 feat: add password validation\njkl012 fix: another typo fix\nmno345 feat: add user registration",
    "goal": "Clean up commit history by squashing typo fixes into their related feature commits"
  }
}
```

## ClaudeCode Integration

These prompts are designed to be used with ClaudeCode for enhanced Git workflows. They can be accessed through the MCP prompt interface, providing contextual assistance for common Git operations.

### Example ClaudeCode Workflow

1. **Before Committing:**
   Use the `commit-message` prompt with your staged changes to generate a conventional commit message.

2. **Before Creating PR:**
   Use the `pr-description` prompt to create a comprehensive pull request description.

3. **During Code Review:**
   Use the `code-review` prompt with diffs to get structured review guidance.

4. **When Facing Issues:**
   Use the `git-troubleshooting` prompt with error descriptions and git status output.

5. **For Release Planning:**
   Use the `release-notes` or `changelog-generation` prompts with commit history.

## Best Practices

1. **Provide Context:** Always include relevant context in prompt arguments for better guidance.

2. **Use Multiple Prompts:** Combine different prompts for comprehensive workflow support.

3. **Customize Arguments:** Include optional arguments for more specific guidance.

4. **Iterate and Refine:** Use prompt results as starting points and refine as needed.

5. **Team Consistency:** Establish team conventions for prompt usage to maintain consistency.

## Advanced Usage Patterns

### Automated Commit Messages
Combine Git tools with prompts:
1. Use `git_diff_staged` to get staged changes
2. Use `commit-message` prompt with the diff output
3. Use `git_commit` with the generated message

### PR Workflow
1. Use `git_log` to get recent commits
2. Use `pr-description` prompt with commit summary
3. Create PR with generated description

### Release Preparation
1. Use `git_log` with version range
2. Use both `release-notes` and `changelog-generation` prompts
3. Compare outputs for comprehensive release documentation

This prompt system transforms Git operations from individual commands into guided, intelligent workflows that help maintain consistency and best practices across your development team.