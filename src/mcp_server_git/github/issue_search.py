"""GitHub Issue search, template, and bulk update operations."""

from __future__ import annotations

import logging
from typing import Any

from mcp_server_git.github.client import github_client_context
from mcp_server_git.github.issues import github_create_issue, github_update_issue

logger = logging.getLogger(__name__)


async def github_search_issues(
    repo_owner: str,
    repo_name: str,
    query: str,
    sort: str = "created",
    order: str = "desc",
    per_page: int = 30,
    page: int = 1,
) -> str:
    """Search issues using GitHub's advanced search API.

    Supports GitHub's search qualifiers like:
    - is:issue is:open author:username
    - label:bug label:"help wanted"
    - created:2023-01-01..2023-12-31
    - updated:>2023-06-01
    - milestone:"v1.0" assignee:username
    """
    logger.debug(f"🔍 Searching issues in {repo_owner}/{repo_name}: {query}")

    try:
        async with github_client_context() as client:
            # Add repository scope to query
            search_query = f"repo:{repo_owner}/{repo_name} is:issue {query}"

            params = {
                "q": search_query,
                "sort": sort,
                "order": order,
                "per_page": per_page,
                "page": page,
            }

            response = await client.get("/search/issues", params=params)

            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to search issues: {response.status} - {error_text}"

            data = await response.json()
            issues = data.get("items", [])
            total_count = data.get("total_count", 0)

            if not issues:
                return f"No issues found matching query: {query}"

            output = [f"Search Results for '{query}' in {repo_owner}/{repo_name}:\n"]
            output.append(f"Found {total_count} total issues (showing page {page})\n")

            for issue in issues:
                # Skip pull requests
                if issue.get("pull_request"):
                    continue

                state_emoji = {"open": "🟢", "closed": "🔴"}.get(
                    issue.get("state"), "❓"
                )
                output.append(f"{state_emoji} #{issue['number']}: {issue['title']}")
                output.append(f"   Author: {issue.get('user', {}).get('login', 'N/A')}")

                # Show labels
                if issue.get("labels"):
                    label_names = [label["name"] for label in issue["labels"]]
                    output.append(f"   Labels: {', '.join(label_names)}")

                # Show assignees
                if issue.get("assignees"):
                    assignee_names = [
                        assignee["login"] for assignee in issue["assignees"]
                    ]
                    output.append(f"   Assignees: {', '.join(assignee_names)}")

                # Show milestone
                if issue.get("milestone"):
                    output.append(f"   Milestone: {issue['milestone']['title']}")

                output.append(f"   Created: {issue.get('created_at', 'N/A')}")
                output.append(
                    f"   Score: {issue.get('score', 'N/A')}"
                )  # Search relevance score
                output.append("")

            # Add pagination info
            max_results = min(1000, total_count)  # GitHub limits search to 1000 results
            if total_count > len(issues):
                max_page = (max_results + per_page - 1) // per_page
                output.append(
                    f"📄 Page {page} of {max_page} (max {max_results} results from GitHub)"
                )

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error searching issues: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error searching issues: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error searching issues: {e}", exc_info=True)
        return f"❌ Error searching issues: {str(e)}"


async def github_create_issue_from_template(
    repo_owner: str,
    repo_name: str,
    title: str,
    template_name: str = "bug_report",
    template_data: dict | None = None,
) -> str:
    """Create a GitHub issue using a predefined template.

    Templates include:
    - bug_report: Bug report with reproduction steps
    - feature_request: Feature request with use cases
    - question: Question or discussion starter
    - custom: Use template_data to define custom format
    """
    logger.debug(
        f"🚀 Creating issue from template '{template_name}' in {repo_owner}/{repo_name}"
    )

    templates = {
        "bug_report": {
            "body": f"""## Bug Report

**Describe the bug**
A clear and concise description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:
1. Go to '...'
2. Click on '....'
3. Scroll down to '....'
4. See error

**Expected behavior**
A clear and concise description of what you expected to happen.

**Additional context**
Add any other context about the problem here.

**Environment**
- OS: [e.g. iOS]
- Browser [e.g. chrome, safari]
- Version [e.g. 22]

{template_data.get("additional_info", "") if template_data else ""}
""",
            "labels": ["bug", "triage"],
        },
        "feature_request": {
            "body": f"""## Feature Request

**Is your feature request related to a problem? Please describe.**
A clear and concise description of what the problem is. Ex. I'm always frustrated when [...]

**Describe the solution you'd like**
A clear and concise description of what you want to happen.

**Describe alternatives you've considered**
A clear and concise description of any alternative solutions or features you've considered.

**Additional context**
Add any other context or screenshots about the feature request here.

{template_data.get("additional_info", "") if template_data else ""}
""",
            "labels": ["enhancement", "feature-request"],
        },
        "question": {
            "body": f"""## Question

**What would you like to know?**
Please describe your question clearly.

**Context**
Provide any relevant context that might help answer your question.

**What have you tried?**
Let us know what research or attempts you've already made.

{template_data.get("additional_info", "") if template_data else ""}
""",
            "labels": ["question"],
        },
    }

    if template_name == "custom" and template_data:
        template: dict[str, Any] = {
            "body": template_data.get("body", ""),
            "labels": template_data.get("labels", []),
        }
    else:
        template = templates.get(template_name)
        if not template:
            available = ", ".join(templates.keys()) + ", custom"
            return f"❌ Unknown template '{template_name}'. Available templates: {available}"

    # Apply template data customizations
    if template_data:
        if "labels" in template_data:
            template["labels"] = template["labels"] + template_data["labels"]
        if "assignees" in template_data:
            template["assignees"] = template_data["assignees"]
        if "milestone" in template_data:
            template["milestone"] = template_data["milestone"]

    # Create issue using template
    return await github_create_issue(
        repo_owner=repo_owner,
        repo_name=repo_name,
        title=title,
        body=template["body"],
        labels=template.get("labels"),
        assignees=template.get("assignees"),
        milestone=template.get("milestone"),
    )


async def github_bulk_update_issues(
    repo_owner: str,
    repo_name: str,
    issue_numbers: list[int],
    labels: list[str] | None = None,
    assignees: list[str] | None = None,
    milestone: int | None = None,
    state: str | None = None,
) -> str:
    """Bulk update multiple issues with common properties.

    Useful for:
    - Adding labels to multiple issues
    - Assigning multiple issues to same milestone
    - Bulk closing/reopening issues
    - Mass assignment operations
    """
    logger.debug(
        f"🚀 Bulk updating {len(issue_numbers)} issues in {repo_owner}/{repo_name}"
    )

    if not issue_numbers:
        return "⚠️ No issue numbers provided for bulk update"

    if not any([labels, assignees, milestone is not None, state]):
        return "⚠️ No update parameters provided. Specify labels, assignees, milestone, or state"

    results = []
    successful_updates = 0
    failed_updates = 0

    for issue_number in issue_numbers:
        try:
            result = await github_update_issue(
                repo_owner=repo_owner,
                repo_name=repo_name,
                issue_number=issue_number,
                labels=labels,
                assignees=assignees,
                milestone=milestone,
                state=state,
            )

            if result.startswith("✅"):
                successful_updates += 1
                results.append(f"✅ Issue #{issue_number}: Updated")
            else:
                failed_updates += 1
                results.append(f"❌ Issue #{issue_number}: {result}")

        except Exception as e:
            failed_updates += 1
            results.append(f"❌ Issue #{issue_number}: Error - {str(e)}")

    # Summary
    summary = [
        f"Bulk Update Results for {len(issue_numbers)} issues:",
        f"✅ Successful: {successful_updates}",
        f"❌ Failed: {failed_updates}",
        "",
    ]

    # Detailed results (limit to first 10 for readability)
    summary.append("Details:")
    for result in results[:10]:
        summary.append(f"  {result}")

    if len(results) > 10:
        summary.append(f"  ... and {len(results) - 10} more results")

    return "\n".join(summary)
