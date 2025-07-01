# GitHub Actions Integration Usage Guide

This guide demonstrates how to use the powerful GitHub Actions integration in the MCP Git server to analyze failing CI/CD workflows and get intelligent assistance for your development workflow.

## 🔧 Setup

### Environment Configuration

Set your GitHub token as an environment variable:

```bash
export GITHUB_TOKEN="ghp_your_token_here"
```

**Token Permissions Required:**
- `repo` - Repository access
- `actions:read` - Read GitHub Actions
- `checks:read` - Read check runs
- `pull_requests:read` - Read pull requests

### Get Your Token
1. Go to GitHub Settings → Developer settings → Personal access tokens
2. Create a new token with the required permissions
3. Set it as `GITHUB_TOKEN` environment variable

## 🎯 Core GitHub Actions Tools

### 1. github_get_pr_checks
**Get all check runs for a pull request**

```json
{
  "tool": "github_get_pr_checks",
  "arguments": {
    "repo_owner": "anthropic",
    "repo_name": "claude-code",
    "pr_number": 123
  }
}
```

**With Filtering:**
```json
{
  "tool": "github_get_pr_checks",
  "arguments": {
    "repo_owner": "anthropic",
    "repo_name": "claude-code",
    "pr_number": 123,
    "status": "completed",
    "conclusion": "failure"
  }
}
```

**Example Output:**
```
Check runs for PR #123 (commit a1b2c3d4):

❌ CI / Test Suite
   Status: completed
   Conclusion: failure
   Started: 2025-01-15T10:30:00Z
   Completed: 2025-01-15T10:35:00Z
   URL: https://github.com/owner/repo/actions/runs/123456

✅ CI / Lint
   Status: completed
   Conclusion: success
   Started: 2025-01-15T10:30:00Z
   Completed: 2025-01-15T10:32:00Z
```

### 2. github_get_failing_jobs
**Get detailed failing job information (your specific request!)**

```json
{
  "tool": "github_get_failing_jobs",
  "arguments": {
    "repo_owner": "anthropic",
    "repo_name": "claude-code",
    "pr_number": 123,
    "include_logs": true,
    "include_annotations": true
  }
}
```

**Example Output:**
```
Failing jobs for PR #123:

❌ Test Suite
   Conclusion: failure
   Started: 2025-01-15T10:30:00Z
   Completed: 2025-01-15T10:35:00Z
   Annotations:
     • Test failed: test_user_authentication
       File: tests/test_auth.py (line 45)
     • AssertionError: Expected 200, got 401
       File: tests/test_auth.py (line 47)
   Details: https://github.com/owner/repo/actions/runs/123456

❌ Integration Tests
   Conclusion: failure
   Started: 2025-01-15T10:30:00Z
   Completed: 2025-01-15T10:40:00Z
   Annotations:
     • Connection timeout: Database unreachable
       File: tests/integration/test_db.py (line 23)
   Details: https://github.com/owner/repo/actions/runs/123457
```

### 3. github_get_workflow_run
**Get detailed workflow run information**

```json
{
  "tool": "github_get_workflow_run",
  "arguments": {
    "repo_owner": "anthropic",
    "repo_name": "claude-code",
    "run_id": 123456,
    "include_logs": false
  }
}
```

### 4. github_get_pr_details
**Get comprehensive PR information**

```json
{
  "tool": "github_get_pr_details",
  "arguments": {
    "repo_owner": "anthropic",
    "repo_name": "claude-code",
    "pr_number": 123,
    "include_files": true,
    "include_reviews": true
  }
}
```

## 🤖 GitHub Actions Failure Analysis Prompts

### 1. github-actions-failure-analysis
**Comprehensive failure analysis with actionable solutions**

```json
{
  "prompt": "github-actions-failure-analysis",
  "arguments": {
    "failure_logs": "Error: Test failed - test_user_authentication\nAssertionError: Expected status 200, got 401\n  at tests/test_auth.py:47\n  at AuthTestCase.test_login_success:45",
    "workflow_file": "name: CI\non: [push, pull_request]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v3\n      - name: Setup Python\n        uses: actions/setup-python@v4\n        with:\n          python-version: '3.11'\n      - name: Run tests\n        run: pytest tests/",
    "changed_files": "src/auth/middleware.py\ntests/test_auth.py\nREADME.md"
  }
}
```

**Generated Response Example:**
```markdown
## Root Cause Analysis
The authentication test is failing because the login endpoint is returning 401 (Unauthorized) instead of the expected 200 (OK). This suggests:
1. Authentication middleware changes in `src/auth/middleware.py` may have broken the login flow
2. Test setup might not be properly configuring authentication credentials
3. Database seeding might be missing required user data

## Immediate Fixes
1. **Check middleware changes:**
   ```python
   # In src/auth/middleware.py - ensure proper token validation
   def validate_token(self, token):
       if not token:
           return False
       # Add proper validation logic
   ```

2. **Fix test setup:**
   ```python
   # In tests/test_auth.py
   def setUp(self):
       self.client = TestClient()
       self.test_user = create_test_user()  # Ensure user exists
       self.auth_token = generate_test_token(self.test_user)
   ```

## Testing Plan
1. Run failing test in isolation: `pytest tests/test_auth.py::AuthTestCase::test_login_success -v`
2. Add debug logging to middleware
3. Verify test database has required user data
4. Check token generation in test setup
```

### 2. ci-failure-root-cause
**Specific error analysis**

```json
{
  "prompt": "ci-failure-root-cause",
  "arguments": {
    "error_message": "ModuleNotFoundError: No module named 'jwt'",
    "stack_trace": "Traceback (most recent call last):\n  File 'src/auth/middleware.py', line 3, in <module>\n    import jwt\nModuleNotFoundError: No module named 'jwt'",
    "environment_info": "Python 3.11.0, Ubuntu 22.04, GitHub Actions runner"
  }
}
```

### 3. pr-readiness-assessment
**Comprehensive PR evaluation**

```json
{
  "prompt": "pr-readiness-assessment",
  "arguments": {
    "pr_details": "Title: Add JWT Authentication\nAuthor: developer123\nChanges: +150 -25\nFiles: 8 changed\nDescription: Implements JWT-based authentication system",
    "ci_status": "2 checks failing, 3 checks passing",
    "review_comments": "Review 1: LGTM, minor style issues\nReview 2: Security concerns about token storage"
  }
}
```

## 🔥 ClaudeCode Workflow Examples

### Scenario 1: PR Failing - Quick Diagnosis

**ClaudeCode Automated Workflow:**
```python
# 1. Get failing jobs for a PR
failing_jobs = github_get_failing_jobs("owner", "repo", 123)

# 2. Analyze failures with AI
analysis = get_prompt("github-actions-failure-analysis", {
    "failure_logs": failing_jobs,
    "changed_files": git_diff_branches("main", "feature")
})

# 3. Apply suggested fixes and rerun
```

### Scenario 2: CI Debugging Session

**ClaudeCode Steps:**
```python
# 1. Get PR details and CI status
pr_info = github_get_pr_details("owner", "repo", 123, include_files=True)
checks = github_get_pr_checks("owner", "repo", 123, conclusion="failure")

# 2. Get specific workflow run details
workflow_details = github_get_workflow_run("owner", "repo", run_id)

# 3. Root cause analysis
root_cause = get_prompt("ci-failure-root-cause", {
    "error_message": extract_error_from_logs(workflow_details),
    "environment_info": extract_env_info(workflow_details)
})

# 4. Apply fixes and validate
```

### Scenario 3: PR Review Automation

**ClaudeCode Workflow:**
```python
# 1. Comprehensive PR assessment
pr_details = github_get_pr_details("owner", "repo", 123,
                                   include_files=True,
                                   include_reviews=True)
ci_status = github_get_pr_checks("owner", "repo", 123)

# 2. Readiness evaluation
assessment = get_prompt("pr-readiness-assessment", {
    "pr_details": pr_details,
    "ci_status": ci_status
})

# 3. Automated feedback and suggestions
```

## 🚀 Advanced Integration Ideas

### 1. Auto-Healing CI
```python
# ClaudeCode could automatically:
1. Detect failing CI → github_get_failing_jobs()
2. Analyze failure → github-actions-failure-analysis prompt
3. Apply common fixes → git_commit() with fixes
4. Monitor results → github_get_pr_checks()
```

### 2. Smart PR Management
```python
# ClaudeCode could:
1. Monitor PR status → github_get_pr_details()
2. Assess readiness → pr-readiness-assessment prompt
3. Suggest improvements → Update PR description
4. Coordinate reviews → Suggest reviewers based on changes
```

### 3. Continuous Learning
```python
# ClaudeCode could learn:
1. Track failure patterns across PRs
2. Build knowledge base of common fixes
3. Improve suggestion accuracy over time
4. Predict likely failure points
```

## 🔒 Security & Best Practices

### Token Security
- Use minimal required permissions
- Rotate tokens regularly
- Never commit tokens to repositories
- Use environment variables or secure secret management

### Rate Limiting
- GitHub API has rate limits (5000 requests/hour for authenticated requests)
- The tools implement proper error handling for rate limit scenarios
- Consider caching results for frequently accessed data

### Error Handling
- All tools include comprehensive error handling
- Network timeouts are handled gracefully
- Invalid repositories/PRs return helpful error messages

## 📊 Power User Tips

### 1. Batch Operations
```python
# Get comprehensive failure analysis
pr_checks = github_get_pr_checks("owner", "repo", 123, conclusion="failure")
failing_jobs = github_get_failing_jobs("owner", "repo", 123)
pr_details = github_get_pr_details("owner", "repo", 123, include_files=True)

# Single prompt with all context
analysis = get_prompt("github-actions-failure-analysis", {
    "failure_logs": failing_jobs,
    "changed_files": pr_details
})
```

### 2. Workflow Automation
```python
# Create automated CI monitoring
1. Set up periodic checks for PR status
2. Auto-analyze failures when they occur
3. Generate reports for team review
4. Alert on critical failures
```

### 3. Team Integration
```python
# Integrate with team workflows
1. Auto-comment on PRs with failure analysis
2. Generate daily CI health reports
3. Track team productivity metrics
4. Identify recurring failure patterns
```

This GitHub Actions integration transforms ClaudeCode from a basic Git assistant into a comprehensive CI/CD workflow intelligence system, providing expert-level analysis and automation for modern development teams.
