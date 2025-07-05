"""
Intelligent prompts for MCP Git Server
Centralized prompt management for AI-assisted Git and GitHub workflows
"""

from mcp.types import GetPromptResult, PromptMessage, TextContent


def get_prompt(name: str, args: dict) -> GetPromptResult:
    """Get an intelligent prompt by name with provided arguments"""

    match name:
        case "commit-message":
            changes = args.get("changes", "")
            type_ = args.get("type", "feat")
            scope = args.get("scope", "")
            description = args.get("description", "")

            scope_section = f"({scope})" if scope else ""
            changes_section = f"\n\n**Changes:**\n{changes}" if changes else ""

            prompt_text = f"""Generate a conventional commit message based on the provided information.

**Commit Type:** {type_}
**Scope:** {scope or "not specified"}
**Description:** {description or "not provided"}
{changes_section}

Create a commit message following the Conventional Commits specification:
- Format: `type{scope_section}: description`
- Type should be one of: feat, fix, docs, style, refactor, test, chore
- Description should be imperative mood, lowercase, no period
- Include a body if changes are complex
- Include breaking change notice if applicable

Example formats:
- `feat(auth): add user authentication`
- `fix: resolve memory leak in parser`
- `docs: update API documentation`

Provide just the commit message, ready to use."""

            return GetPromptResult(
                description="Conventional commit message generator",
                messages=[
                    PromptMessage(
                        role="user", content=TextContent(type="text", text=prompt_text)
                    )
                ],
            )

        case "pr-description":
            title = args.get("title", "")
            changes = args.get("changes", "")
            breaking = args.get("breaking", "")

            breaking_section = (
                f"\n\n## ⚠️ Breaking Changes\n{breaking}" if breaking else ""
            )

            prompt_text = f"""Generate a comprehensive GitHub Pull Request description.

**PR Title:** {title}

**Changes Made:**
{changes}
{breaking_section}

Create a well-structured PR description with:

## Summary
Brief overview of what this PR accomplishes

## Changes Made
- Bulleted list of specific changes
- Focus on user-facing changes
- Include technical details where relevant

## Testing
- How these changes were tested
- Any new test cases added
- Manual testing performed

## Related Issues
- Link any related issues (e.g., "Closes #123")
- Reference discussions or requirements

## Screenshots/Demo
- Placeholder for visual changes
- Include before/after if UI changes

## Checklist
- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] Breaking changes documented

Make it professional, clear, and comprehensive."""

            return GetPromptResult(
                description="GitHub PR description generator",
                messages=[
                    PromptMessage(
                        role="user", content=TextContent(type="text", text=prompt_text)
                    )
                ],
            )

        case "code-review":
            diff = args.get("diff", "")
            context = args.get("context", "")

            context_section = f"\n**Context:**\n{context}\n" if context else ""

            prompt_text = f"""Perform a thorough code review of the provided diff.

**Code Changes:**
```diff
{diff}
```
{context_section}
Review the code for:

1. **Functionality**
   - Logic correctness
   - Edge case handling
   - Performance implications
   - Security considerations

2. **Code Quality**
   - Readability and clarity
   - Naming conventions
   - Code organization
   - Documentation/comments

3. **Best Practices**
   - Design patterns
   - Error handling
   - Testing considerations
   - Maintainability

4. **Potential Issues**
   - Bugs or logic errors
   - Performance bottlenecks
   - Security vulnerabilities
   - Breaking changes

Provide constructive feedback with specific suggestions for improvement. Format as actionable items."""

            return GetPromptResult(
                description="Code review assistant",
                messages=[
                    PromptMessage(
                        role="user", content=TextContent(type="text", text=prompt_text)
                    )
                ],
            )

        case "merge-conflict-resolution":
            conflicts = args.get("conflicts", "")
            branch_info = args.get("branch_info", "")

            branch_section = (
                f"\n**Branch Information:**\n{branch_info}" if branch_info else ""
            )

            prompt_text = f"""Help resolve Git merge conflicts systematically.

**Conflict Details:**
```
{conflicts}
```
{branch_section}
Provide a step-by-step resolution strategy:

1. **Conflict Analysis**
   - Identify the nature of conflicts
   - Understand what each side is trying to accomplish
   - Assess the impact of different resolution approaches

2. **Resolution Strategy**
   - Recommend which changes to keep, modify, or combine
   - Explain the reasoning for each decision
   - Consider the intent of both branches

3. **Implementation Steps**
   - Specific commands to resolve conflicts
   - How to test the resolution
   - Verification steps

4. **Prevention**
   - Suggestions to avoid similar conflicts
   - Workflow improvements
   - Communication strategies

Focus on preserving the intent of both branches while ensuring functionality."""

            return GetPromptResult(
                description="Merge conflict resolution guide",
                messages=[
                    PromptMessage(
                        role="user", content=TextContent(type="text", text=prompt_text)
                    )
                ],
            )

        case "git-workflow-guide":
            workflow_type = args.get("workflow_type", "feature-branch")
            team_size = args.get("team_size", "small")

            prompt_text = f"""Provide comprehensive Git workflow guidance.

**Workflow Type:** {workflow_type}
**Team Size:** {team_size}

Create a detailed workflow guide covering:

1. **Branch Strategy**
   - Main branch naming and purpose
   - Feature branch conventions
   - Release branch strategy
   - Hotfix procedures

2. **Development Process**
   - Creating feature branches
   - Commit message standards
   - Code review process
   - Merge strategies

3. **Collaboration Guidelines**
   - Pull request workflow
   - Review requirements
   - Conflict resolution
   - Communication protocols

4. **Quality Gates**
   - Pre-commit requirements
   - CI/CD integration
   - Testing standards
   - Documentation requirements

5. **Common Commands**
   - Daily workflow commands
   - Troubleshooting commands
   - Advanced operations

Tailor recommendations to the specified team size and workflow type."""

            return GetPromptResult(
                description="Git workflow guide generator",
                messages=[
                    PromptMessage(
                        role="user", content=TextContent(type="text", text=prompt_text)
                    )
                ],
            )

        case "branch-strategy":
            project_type = args.get("project_type", "web-application")
            deployment_frequency = args.get("deployment_frequency", "weekly")

            prompt_text = f"""Recommend an optimal Git branching strategy.

**Project Type:** {project_type}
**Deployment Frequency:** {deployment_frequency}

Analyze and recommend:

1. **Branching Model**
   - Suitable branching strategy (Git Flow, GitHub Flow, GitLab Flow, etc.)
   - Reasoning for the recommendation
   - Alternative approaches and trade-offs

2. **Branch Structure**
   - Main/master branch role
   - Development branch usage
   - Feature branch naming
   - Release branch strategy
   - Hotfix procedures

3. **Workflow Integration**
   - How branches align with development phases
   - CI/CD pipeline integration
   - Testing strategy per branch
   - Deployment process

4. **Team Considerations**
   - Collaboration patterns
   - Review requirements
   - Merge policies
   - Access controls

5. **Implementation Plan**
   - Migration steps if changing strategies
   - Team training requirements
   - Tool configuration
   - Success metrics

Provide specific, actionable recommendations based on the project characteristics."""

            return GetPromptResult(
                description="Git branching strategy advisor",
                messages=[
                    PromptMessage(
                        role="user", content=TextContent(type="text", text=prompt_text)
                    )
                ],
            )

        case "git-troubleshooting":
            issue = args.get("issue", "")
            git_status = args.get("git_status", "")

            status_section = (
                f"\n**Git Status:**\n```\n{git_status}\n```" if git_status else ""
            )

            prompt_text = f"""Help troubleshoot a Git issue.

**Issue Description:**
{issue}
{status_section}

Provide systematic troubleshooting:

1. **Problem Diagnosis**
   - Analyze the described issue
   - Identify potential root causes
   - Assess the severity and impact

2. **Immediate Solutions**
   - Quick fixes if available
   - Commands to resolve the issue
   - Safety considerations

3. **Investigation Steps**
   - Commands to gather more information
   - Logs or status to check
   - Diagnostic procedures

4. **Resolution Options**
   - Multiple approaches to fix the issue
   - Pros and cons of each approach
   - Risk assessment

5. **Prevention**
   - How to avoid this issue in the future
   - Best practices
   - Workflow improvements

Include exact Git commands and explain what each command does."""

            return GetPromptResult(
                description="Git troubleshooting assistant",
                messages=[
                    PromptMessage(
                        role="user", content=TextContent(type="text", text=prompt_text)
                    )
                ],
            )

        case "release-notes":
            version = args.get("version", "")
            commits = args.get("commits", "")
            previous_version = args.get("previous_version", "")

            prev_section = f" (since {previous_version})" if previous_version else ""

            prompt_text = f"""Generate release notes for version {version}{prev_section}.

**Commit History:**
```
{commits}
```

Create comprehensive release notes with:

## {version} Release Notes

### 🚀 New Features
- List major new features added
- Focus on user-visible enhancements

### 🐛 Bug Fixes
- Critical bugs resolved
- Performance improvements
- Stability enhancements

### 🔧 Improvements
- Developer experience improvements
- Code quality enhancements
- Documentation updates

### 🔄 Changes
- Breaking changes (if any)
- Deprecations
- API changes

### 📚 Technical Details
- Infrastructure updates
- Dependency changes
- Build system improvements

### 🙏 Contributors
- Acknowledge contributors
- Special thanks

Format for user consumption, highlighting impact and benefits."""

            return GetPromptResult(
                description="Release notes generator",
                messages=[
                    PromptMessage(
                        role="user", content=TextContent(type="text", text=prompt_text)
                    )
                ],
            )

        case "changelog-generation":
            commits = args.get("commits", "")
            format = args.get("format", "keepachangelog")

            prompt_text = f"""Generate a changelog from commit history.

**Commit History:**
```
{commits}
```

**Format:** {format}

Generate a changelog following the {format} format:

1. **Parse Commits**
   - Extract meaningful changes from commit messages
   - Categorize by change type
   - Filter out trivial commits

2. **Format Output**
   - Follow the specified format conventions
   - Use appropriate categorization
   - Include dates and version information

3. **Content Organization**
   - Group related changes
   - Prioritize user-facing changes
   - Include breaking changes prominently

4. **Quality Checks**
   - Ensure clarity and readability
   - Remove duplicate information
   - Maintain chronological order

Provide a well-structured changelog ready for publication."""

            return GetPromptResult(
                description="Changelog generator",
                messages=[
                    PromptMessage(
                        role="user", content=TextContent(type="text", text=prompt_text)
                    )
                ],
            )

        case "github-actions-failure-analysis":
            failure_logs = args.get("failure_logs", "")
            workflow_file = args.get("workflow_file", "")
            changed_files = args.get("changed_files", "")

            workflow_section = (
                f"\n**Workflow File:**\n```yaml\n{workflow_file}\n```\n"
                if workflow_file
                else ""
            )
            files_section = (
                f"\n**Changed Files:**\n{changed_files}\n" if changed_files else ""
            )

            prompt_text = f"""Analyze GitHub Actions failure and provide solutions.

**Failure Logs:**
```
{failure_logs}
```
{workflow_section}{files_section}
Perform comprehensive failure analysis:

1. **Error Classification**
   - Type of failure (build, test, deployment, etc.)
   - Severity and impact assessment
   - Root cause identification

2. **Failure Analysis**
   - Parse error messages and stack traces
   - Identify problematic code or configuration
   - Determine if it's environmental or code-related

3. **Solution Strategies**
   - Immediate fixes for quick resolution
   - Long-term improvements for stability
   - Alternative approaches if needed

4. **Implementation Steps**
   - Specific changes to make
   - Commands to run
   - Configuration updates needed

5. **Prevention Measures**
   - CI/CD improvements
   - Additional test cases needed
   - Regression prevention

Focus on actionable, specific solutions with code examples where applicable."""

            return GetPromptResult(
                description="GitHub Actions failure analysis",
                messages=[
                    PromptMessage(
                        role="user", content=TextContent(type="text", text=prompt_text)
                    )
                ],
            )

        case "ci-failure-root-cause":
            error_message = args.get("error_message", "")
            stack_trace = args.get("stack_trace", "")
            environment_info = args.get("environment_info", "")

            stack_section = (
                f"\n**Stack Trace:**\n```\n{stack_trace}\n```\n" if stack_trace else ""
            )
            env_section = (
                f"\n**Environment:**\n{environment_info}\n" if environment_info else ""
            )

            prompt_text = f"""Identify the root cause of this CI failure and provide solutions:

**Error Message:**
```
{error_message}
```
{stack_section}{env_section}
Provide comprehensive analysis:

1. **Error Classification**
   - Type of error (compilation, runtime, test, dependency, etc.)
   - Severity level and impact
   - Frequency (new vs recurring)

2. **Root Cause Investigation**
   - Primary cause identification
   - Contributing factors
   - Underlying system issues

3. **Solution Strategy**
   - Immediate hotfix (if applicable)
   - Proper long-term solution
   - Alternative approaches

4. **Implementation Steps**
   - Exact code changes needed
   - Configuration modifications
   - Deployment considerations

5. **Verification Process**
   - How to test the fix
   - Success criteria
   - Rollback plan if needed

6. **Prevention Measures**
   - Code quality improvements
   - Better testing strategies
   - Monitoring enhancements

Be specific about technical solutions and include code examples."""

            return GetPromptResult(
                description="CI failure root cause analysis",
                messages=[
                    PromptMessage(
                        role="user", content=TextContent(type="text", text=prompt_text)
                    )
                ],
            )

        case "pr-readiness-assessment":
            pr_details = args.get("pr_details", "")
            ci_status = args.get("ci_status", "")
            review_comments = args.get("review_comments", "")

            ci_section = f"\n**CI Status:**\n{ci_status}\n" if ci_status else ""
            reviews_section = (
                f"\n**Review Comments:**\n{review_comments}\n"
                if review_comments
                else ""
            )

            prompt_text = f"""Assess this pull request's readiness for review and merge:

**PR Details:**
{pr_details}
{ci_section}{reviews_section}
Provide comprehensive readiness assessment:

1. **Code Quality Assessment**
   - Code style and conventions
   - Architecture and design patterns
   - Performance considerations
   - Security implications

2. **Completeness Check**
   - Feature implementation completeness
   - Edge cases coverage
   - Error handling adequacy
   - Documentation updates

3. **Testing Evaluation**
   - Test coverage assessment
   - Test quality and effectiveness
   - Integration test coverage
   - Manual testing requirements

4. **CI/CD Status**
   - Build and test results
   - Static analysis findings
   - Security scans results
   - Deployment readiness

5. **Review Readiness**
   - PR description quality
   - Commit message standards
   - Change scope appropriateness
   - Reviewer assignment suggestions

6. **Merge Readiness**
   - Branch protection compliance
   - Merge strategy recommendation
   - Post-merge considerations
   - Rollback planning

7. **Action Items**
   - Issues that must be resolved
   - Nice-to-have improvements
   - Follow-up tasks

Provide specific, actionable recommendations for each area."""

            return GetPromptResult(
                description="PR readiness assessment",
                messages=[
                    PromptMessage(
                        role="user", content=TextContent(type="text", text=prompt_text)
                    )
                ],
            )

        case "github-pr-creation":
            branch_name = args.get("branch_name", "")
            changes_summary = args.get("changes_summary", "")
            breaking_changes = args.get("breaking_changes", "")
            target_audience = args.get("target_audience", "developers")
            urgency = args.get("urgency", "medium")

            breaking_section = (
                f"\n**Breaking Changes:**\n{breaking_changes}\n"
                if breaking_changes
                else ""
            )

            prompt_text = f"""Generate comprehensive content for a new GitHub Pull Request.

**Context:**
- **Source Branch:** `{branch_name}`
- **Urgency:** {urgency.capitalize()}
- **Target Audience:** {target_audience}

**Summary of Changes:**
```
{changes_summary}
```
{breaking_section}**Request:**

Based on the provided context and changes, generate the following components for the `github_create_pr` tool:

1.  **PR Title:**
    - A concise, descriptive title following Conventional Commits format (e.g., `feat(api): Add user authentication endpoint`).
    - The title should be clear and immediately understandable.

2.  **PR Body (in Markdown):**
    - **Description:** A detailed explanation of *what* was changed and *why*.
    - **Changes Made:** A bulleted list of specific changes.
    - **Testing Strategy:** How these changes have been tested (e.g., unit tests, integration tests, manual testing).
    - **Related Issues:** A section to link any related issues (e.g., `Closes #123`).
    - **Screenshots/GIFs:** Placeholders for visual evidence, if applicable.
    - **Checklist:** A self-review checklist for the author.

3.  **Suggested Labels (as a comma-separated list):**
    - Suggest relevant labels from this list: `feature`, `bug`, `documentation`, `refactor`, `tests`, `ci`, `breaking-change`, `needs-review`, `wip`.
    - Consider the changes summary and urgency.

4.  **Suggested Reviewers (as a comma-separated list of GitHub usernames):**
    - Based on the `target_audience` and type of changes, suggest 1-3 potential reviewers (use placeholder usernames like `dev-lead`, `qa-specialist`, `security-expert`).

**Example Output Format:**

**Title:**
feat(auth): Implement password reset functionality

**Body:**
## Description
This PR implements a comprehensive password reset system that allows users to securely reset their passwords via email verification.

## Changes Made
- Added password reset request endpoint
- Implemented secure token generation and validation
- Created email notification system
- Added rate limiting for security

## Testing Strategy
- Unit tests for all new functions (95% coverage)
- Integration tests for the complete flow
- Manual testing with various email providers
- Security testing for token validation

## Related Issues
Closes #456

## Checklist
- [x] Code follows project style guidelines
- [x] Self-review completed
- [x] Tests added and passing
- [x] Documentation updated

**Labels:**
feature, security, needs-review

**Reviewers:**
security-expert, backend-lead

Generate content in this format, tailored to the provided changes and context."""

            return GetPromptResult(
                description="GitHub PR creation content generator",
                messages=[
                    PromptMessage(
                        role="user", content=TextContent(type="text", text=prompt_text)
                    )
                ],
            )

        case "github-pr-comment-generation":
            diff_content = args.get("diff_content", "")
            comment_type = args.get("comment_type", "review")
            specific_focus = args.get("specific_focus", "general")
            tone = args.get("tone", "constructive")

            prompt_text = f"""Generate a high-quality, professional comment for a GitHub Pull Request review.

**Context:**
- **Comment Type:** {comment_type}
- **Specific Focus:** {specific_focus}
- **Desired Tone:** {tone}

**Code Snippet / Diff to Review:**
```diff
{diff_content}
```

**Request:**

Based on the provided code and context, generate a comment for the `github_add_pr_comment` tool.

**Guidelines for the comment:**
1.  **Be Specific:** Refer to specific lines or logic in the provided diff.
2.  **Explain the "Why":** Don't just say something is wrong; explain *why* it's a concern and what the impact is (e.g., performance, security, maintainability).
3.  **Offer Solutions:** When possible, suggest concrete improvements or alternative approaches. Use GitHub's suggestion syntax for code changes.
4.  **Use the Right Tone:** The comment should be `{tone}`. Frame feedback as questions or suggestions to foster collaboration (e.g., "Have you considered...?" or "What do you think about...?").
5.  **Structure based on `comment_type`:**
    - **review:** A general review comment pointing out a specific issue or area for improvement.
    - **suggestion:** A direct code suggestion using GitHub's suggestion syntax (```suggestion\n...code...\n```).
    - **approval:** A positive comment confirming that the code looks good, perhaps with minor nits.
    - **request_changes:** A clear, non-blocking comment that explains what changes are needed before approval.

**Example for a 'suggestion' comment:**

This logic for fetching the user seems a bit inefficient as it could make multiple database calls in a loop.

What do you think about fetching all users in a single batch request outside the loop to improve performance?

```suggestion
const userIds = items.map(item => item.userId);
const users = await db.users.getByIds(userIds);
const userMap = new Map(users.map(u => [u.id, u]));

for (const item of items) {{
  const user = userMap.get(item.userId);
  // ...
}}
```
This approach should be more performant, especially with a large number of items. Let me know your thoughts!

Generate a comment following these guidelines and tailored to the specific code and context provided."""

            return GetPromptResult(
                description="GitHub PR comment generator",
                messages=[
                    PromptMessage(
                        role="user", content=TextContent(type="text", text=prompt_text)
                    )
                ],
            )

        case "github-merge-strategy-recommendation":
            pr_details = args.get("pr_details", "")
            commit_history = args.get("commit_history", "")
            team_preferences = args.get("team_preferences", "no preference")
            risk_level = args.get("risk_level", "medium")

            prompt_text = f"""Analyze the provided Pull Request information and recommend the best merge strategy.

**PR Context:**
- **PR Details:** {pr_details}
- **Commit History:**
```
{commit_history}
```
- **Team Preferences:** {team_preferences}
- **Risk Level:** {risk_level}

**Request:**

Recommend a merge strategy for the `github_merge_pr` tool. The options are `merge`, `squash`, or `rebase`.

Provide a structured recommendation including:

1.  **Recommended Strategy:** State the recommended strategy clearly (e.g., "Recommended Strategy: `squash`").
2.  **Rationale:** Provide a detailed justification for your recommendation. Consider the following factors:
    - **Commit History Clarity:** Is the commit history messy with many small, incremental, or "fixup" commits? (Favors `squash` or `rebase`).
    - **Feature Atomicity:** Does the PR represent a single, atomic feature? (Favors `squash`).
    - **Historical Record:** Is it important to preserve the detailed development history of this branch? (Favors `merge` or `rebase`).
    - **Risk and Rollback:** How does the strategy affect the ease of identifying and reverting changes?
    - **Team Workflow:** How does the recommendation align with the team's preferences?
3.  **`github_merge_pr` Parameters:**
    - **`merge_method`**: The recommended strategy (`merge`, `squash`, or `rebase`).
    - **`commit_title`**: A well-crafted commit title for the merge. For `squash`, this will be the title of the squashed commit.
    - **`commit_message`**: A detailed commit message. For `squash`, this should summarize the changes from the PR.

**Example Output:**

**Recommended Strategy:** `squash`

**Rationale:**
The commit history for this PR contains several small, incremental commits (e.g., "fix typo", "wip"). Squashing these into a single, atomic commit will create a cleaner and more readable history on the `main` branch. Since the PR represents a single feature ("Add User Profile Page"), a single commit accurately reflects the change. This aligns with the team's preference for a linear history.

**`github_merge_pr` Parameters:**
- **`merge_method`**: `squash`
- **`commit_title`**: `feat(profile): Add user profile page`
- **`commit_message`**:
  - Implements a new user profile page accessible at `/profile/:username`.
  - Displays user information, recent activity, and profile settings.
  - Includes backend API endpoints to fetch user data.
  - Closes #78.

Generate a recommendation following this structure, tailored to the specific PR context provided."""

            return GetPromptResult(
                description="GitHub merge strategy recommendation",
                messages=[
                    PromptMessage(
                        role="user", content=TextContent(type="text", text=prompt_text)
                    )
                ],
            )

        case "github-pr-update-guidance":
            review_feedback = args.get("review_feedback", "")
            current_pr_state = args.get("current_pr_state", "")
            priority_issues = args.get("priority_issues", "")
            timeline = args.get("timeline", "not specified")

            priority_section = (
                f"\n**High-Priority Issues:**\n{priority_issues}\n"
                if priority_issues
                else ""
            )
            timeline_section = f"\n**Timeline:** {timeline}\n" if timeline else ""

            prompt_text = f"""Generate a systematic plan to update a GitHub Pull Request based on review feedback.

**Context:**
- **Current PR State:**
```
{current_pr_state}
```
- **Review Feedback Received:**
```
{review_feedback}
```
{priority_section}{timeline_section}**Request:**

Create a structured action plan for updating the PR. The plan should help the developer use tools like `git_add`, `git_commit`, and `git_push` effectively.

The output should be a clear, actionable checklist in Markdown format.

**The plan should include:**
1.  **Feedback Triage:**
    - Group related feedback items.
    - Prioritize changes, starting with blocking issues or those identified as high-priority.
    - Acknowledge all feedback points, even if no change is made (with a justification).

2.  **Actionable Checklist:**
    - Create a task list (`- [ ]`) for each required code change, test update, or documentation adjustment.
    - For each task, specify the file(s) to be modified.
    - Suggest logical commit points. For example, group related changes into a single commit.

3.  **Communication Plan:**
    - Suggest how to communicate progress to the reviewers.
    - Recommend pushing changes and then re-requesting a review.
    - Provide a template for a summary comment to post on the PR after updates are pushed, explaining what was changed.

**Example Output:**

### PR Update Action Plan

Here is a plan to address the review feedback for your PR.

#### 1. Feedback Triage & Prioritization

**High-Priority (Blocking):**
- Security vulnerability in `auth.py` (user input validation)
- Failing unit test in `test_user_model.py`

**Medium-Priority (Should Fix):**
- Code clarity in `utils.py` (break down complex function)
- Missing documentation for `get_data` function

**Low-Priority (Nice-to-Have):**
- Variable naming consistency in `helpers.py`

#### 2. Actionable Checklist

**Commit 1: Address Security and Test Issues**
- [ ] **Security Fix:** In `src/auth.py`, replace the use of `eval()` with a safer data parsing method.
- [ ] **Commit 1:** Create a commit for the security fix: `git commit -m "fix(auth): Remove insecure use of eval()"`
- [ ] **Test Fix:** In `tests/test_user_model.py`, correct the assertion to match the expected output.
- [ ] **Refactor:** In `src/utils.py`, break down the `calculate_stats` function into smaller, helper functions.
- [ ] **Documentation:** Add OpenAPI-compliant docstrings to the `get_data` function in `src/api.py`.
- [ ] **Commit 2:** Group the test fix, refactor, and documentation changes into a single commit: `git commit -m "refactor(stats): Improve readability and add docs"`
- [ ] **Push Changes:** Push both new commits to your branch: `git push`

#### 3. Communication with Reviewers
After pushing your changes, post the following summary comment on the PR and re-request a review:

> Thanks for the feedback! I've pushed updates to address the points raised:
> - The security vulnerability in `auth.py` has been resolved.
> - The failing unit test is now passing.
> - I've refactored `calculate_stats` and added the missing API documentation.
>
> Ready for another look!

Generate a plan following this structure, tailored to the specific feedback and PR state provided."""

            return GetPromptResult(
                description="GitHub PR update guidance generator",
                messages=[
                    PromptMessage(
                        role="user", content=TextContent(type="text", text=prompt_text)
                    )
                ],
            )

        case _:
            raise ValueError(f"Unknown prompt: {name}")
