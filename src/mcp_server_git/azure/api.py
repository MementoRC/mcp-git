"""Azure DevOps API operations for MCP Git Server"""

import logging
from contextlib import asynccontextmanager

from .client import get_azure_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def azure_client_context():
    """Async context manager for Azure DevOps client with guaranteed
    resource cleanup."""
    client = None
    try:
        client = get_azure_client()
        if not client:
            raise ValueError(
                "Azure DevOps not configured. "
                "Set AZURE_DEVOPS_TOKEN and AZURE_DEVOPS_ORG "
                "environment variables."
            )
        yield client
    finally:
        if client and client.session:
            try:
                await client.session.close()
            except Exception as cleanup_error:
                logger.warning(f"Error during Azure client cleanup: {cleanup_error}")


async def azure_get_build_status(project: str, build_id: int) -> str:
    """Get status of an Azure DevOps build/pipeline run

    Args:
        project: The project name or ID
        build_id: The build ID

    Returns:
        Formatted string with build status information
    """
    try:
        async with azure_client_context() as client:
            # Get build details
            # API: GET https://dev.azure.com/{organization}/{project}/_apis/build/builds/{buildId}?api-version=7.1
            response = await client.get(
                f"{project}/_apis/build/builds/{build_id}?api-version=7.1"
            )

            if response.status != 200:
                error_text = await response.text()
                return (
                    f"❌ Failed to get build #{build_id}: "
                    f"{response.status} - {error_text}"
                )

            build_data = await response.json()

            # Format the output
            output = [f"Azure DevOps Build #{build_id} ({project}):\n"]
            definition_name = build_data.get("definition", {}).get("name", "N/A")
            output.append(f"Definition: {definition_name}")
            output.append(f"Status: {build_data.get('status', 'N/A')}")
            output.append(f"Result: {build_data.get('result', 'N/A')}")
            source_branch = build_data.get("sourceBranch", "N/A")
            output.append(f"Source Branch: {source_branch}")
            source_version = build_data.get("sourceVersion", "N/A")[:8]
            output.append(f"Source Version: {source_version}")

            if build_data.get("queueTime"):
                output.append(f"Queued: {build_data['queueTime']}")
            if build_data.get("startTime"):
                output.append(f"Started: {build_data['startTime']}")
            if build_data.get("finishTime"):
                output.append(f"Finished: {build_data['finishTime']}")

            if build_data.get("requestedFor"):
                requester = build_data["requestedFor"]
                output.append(f"Requested By: {requester.get('displayName', 'N/A')}")

            if build_data.get("_links", {}).get("web", {}).get("href"):
                output.append(f"\nURL: {build_data['_links']['web']['href']}")

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error getting build status: {auth_error}")
        return f"❌ {str(auth_error)}"
    except Exception as e:
        logger.error(
            f"Error getting build status for build #{build_id}: {e}", exc_info=True
        )
        return f"❌ Error getting build status: {str(e)}"


async def azure_get_build_logs(
    project: str, build_id: int, log_id: int | None = None
) -> str:
    """Get logs from an Azure DevOps build

    Args:
        project: The project name or ID
        build_id: The build ID
        log_id: Optional specific log ID to retrieve. If None, lists all logs.

    Returns:
        Formatted string with log information or content
    """
    try:
        async with azure_client_context() as client:
            if log_id is None:
                # List all logs for the build
                # API: GET https://dev.azure.com/{organization}/{project}/_apis/build/builds/{buildId}/logs?api-version=7.1
                response = await client.get(
                    f"{project}/_apis/build/builds/{build_id}/logs?api-version=7.1"
                )

                if response.status != 200:
                    error_text = await response.text()
                    return (
                        f"❌ Failed to get build logs: {response.status} - {error_text}"
                    )

                logs_data = await response.json()
                logs = logs_data.get("value", [])

                if not logs:
                    return f"No logs found for build #{build_id}"

                output = [f"Logs for Build #{build_id}:\n"]
                for log in logs:
                    log_type = log.get("type", "N/A")
                    line_count = log.get("lineCount", 0)
                    output.append(f"Log #{log['id']}: {log_type} ({line_count} lines)")
                    if log.get("url"):
                        output.append(f"  URL: {log['url']}")

                return "\n".join(output)
            else:
                # Get specific log content
                # API: GET https://dev.azure.com/{organization}/{project}/_apis/build/builds/{buildId}/logs/{logId}?api-version=7.1
                response = await client.get(
                    f"{project}/_apis/build/builds/{build_id}/logs/{log_id}?api-version=7.1"
                )

                if response.status != 200:
                    error_text = await response.text()
                    return (
                        f"❌ Failed to get log #{log_id}: "
                        f"{response.status} - {error_text}"
                    )

                log_content = await response.text()

                # Truncate if too long (similar to GitHub implementation)
                max_length = 10000
                if len(log_content) > max_length:
                    truncated_chars = len(log_content) - max_length
                    log_content = (
                        log_content[:max_length]
                        + f"\n... [truncated {truncated_chars} chars]"
                    )

                return f"Log #{log_id} for Build #{build_id}:\n\n{log_content}"

    except ValueError as auth_error:
        logger.error(f"Authentication error getting build logs: {auth_error}")
        return f"❌ {str(auth_error)}"
    except Exception as e:
        logger.error(
            f"Error getting build logs for build #{build_id}: {e}", exc_info=True
        )
        return f"❌ Error getting build logs: {str(e)}"


async def azure_get_failing_jobs(
    project: str, build_id: int, include_logs: bool = True
) -> str:
    """Get detailed information about failing jobs in a build

    Args:
        project: The project name or ID
        build_id: The build ID
        include_logs: Whether to include log excerpts from failing jobs

    Returns:
        Formatted string with failing job information
    """
    try:
        async with azure_client_context() as client:
            # First get build status to check if it failed
            build_response = await client.get(
                f"{project}/_apis/build/builds/{build_id}?api-version=7.1"
            )

            if build_response.status != 200:
                error_text = await build_response.text()
                return (
                    f"❌ Failed to get build #{build_id}: "
                    f"{build_response.status} - {error_text}"
                )

            build_data = await build_response.json()

            result = build_data.get("result", "N/A")
            if result not in ["failed", "partiallySucceeded", "canceled"]:
                return (
                    f"Build #{build_id} has result '{result}' - no failures to report"
                )

            # Get timeline data which contains job information
            # API: GET https://dev.azure.com/{organization}/{project}/_apis/build/builds/{buildId}/timeline?api-version=7.1
            timeline_response = await client.get(
                f"{project}/_apis/build/builds/{build_id}/timeline?api-version=7.1"
            )

            if timeline_response.status != 200:
                error_text = await timeline_response.text()
                return (
                    f"❌ Failed to get build timeline: "
                    f"{timeline_response.status} - {error_text}"
                )

            timeline_data = await timeline_response.json()
            records = timeline_data.get("records", [])

            # Filter for failed jobs/tasks
            failed_records = [
                record
                for record in records
                if record.get("result") in ["failed", "canceled", "abandoned"]
                and record.get("type") in ["Job", "Task", "Phase"]
            ]

            if not failed_records:
                return f"No failed jobs found for build #{build_id}"

            output = [f"Failed Jobs for Build #{build_id}:\n"]

            for record in failed_records:
                record_type = record.get("type", "Unknown")
                status_emoji = {"failed": "❌", "canceled": "🚫", "abandoned": "⚠️"}.get(
                    record.get("result", ""), "❓"
                )

                record_name = record.get("name", "N/A")
                output.append(f"{status_emoji} {record_type}: {record_name}")
                output.append(f"   Result: {record.get('result', 'N/A')}")
                output.append(f"   State: {record.get('state', 'N/A')}")

                if record.get("startTime"):
                    output.append(f"   Started: {record['startTime']}")
                if record.get("finishTime"):
                    output.append(f"   Finished: {record['finishTime']}")

                # Get error messages from issues
                if record.get("issues"):
                    output.append("   Issues:")
                    for issue in record["issues"][:5]:  # Limit to 5 issues
                        issue_type = issue.get("type", "unknown")
                        message = issue.get("message", "No message")
                        output.append(f"     [{issue_type}] {message}")

                # Include log excerpt if requested
                if include_logs and record.get("log", {}).get("id"):
                    log_id = record["log"]["id"]
                    try:
                        log_response = await client.get(
                            f"{project}/_apis/build/builds/{build_id}/logs/{log_id}?api-version=7.1"
                        )
                        if log_response.status == 200:
                            log_content = await log_response.text()
                            # Get last 20 lines
                            lines = log_content.strip().split("\n")
                            if len(lines) > 20:
                                excerpt = "\n".join(lines[-20:])
                            else:
                                excerpt = log_content
                            output.append("   Log excerpt (last 20 lines):")
                            output.append("   ```")
                            output.append(f"   {excerpt}")
                            output.append("   ```")
                    except Exception as log_error:
                        logger.warning(f"Failed to get log {log_id}: {log_error}")

                output.append("")  # Empty line between records

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error getting failing jobs: {auth_error}")
        return f"❌ {str(auth_error)}"
    except Exception as e:
        logger.error(
            f"Error getting failing jobs for build #{build_id}: {e}", exc_info=True
        )
        return f"❌ Error getting failing jobs: {str(e)}"


async def azure_list_builds(
    project: str,
    repository_id: str | None = None,
    branch_name: str | None = None,
    status: str | None = None,
    result: str | None = None,
    top: int = 30,
    continuation_token: str | None = None,
) -> str:
    """List builds for an Azure DevOps project

    Args:
        project: The project name or ID
        repository_id: Optional repository ID to filter builds
        branch_name: Optional branch name to filter builds (e.g., 'refs/heads/main')
        status: Optional status filter (notStarted, inProgress, completed, etc.)
        result: Optional result filter (succeeded, failed, canceled, etc.)
        top: Maximum number of builds to return (default 30)
        continuation_token: Token for pagination

    Returns:
        Formatted string with list of builds
    """
    try:
        async with azure_client_context() as client:
            # Build query parameters
            params = {
                "api-version": "7.1",
                "$top": top,
            }

            if repository_id:
                params["repositoryId"] = repository_id
            if branch_name:
                params["branchName"] = branch_name
            if status:
                params["statusFilter"] = status
            if result:
                params["resultFilter"] = result
            if continuation_token:
                params["continuationToken"] = continuation_token

            # API: GET https://dev.azure.com/{organization}/{project}/_apis/build/builds?api-version=7.1
            response = await client.get(f"{project}/_apis/build/builds", params=params)

            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to list builds: {response.status} - {error_text}"

            builds_data = await response.json()
            builds = builds_data.get("value", [])

            if not builds:
                return f"No builds found for project '{project}'"

            output = [f"Builds for project '{project}':\n"]

            for build in builds:
                status_emoji = {
                    "completed": "✅" if build.get("result") == "succeeded" else "❌",
                    "inProgress": "🔄",
                    "notStarted": "⏳",
                }.get(build.get("status", ""), "❓")

                build_number = build.get("buildNumber", "N/A")
                definition = build.get("definition", {}).get("name", "N/A")
                result = build.get("result", "N/A")
                source_branch = build.get("sourceBranch", "N/A")
                build_id_display = build.get("id", "N/A")
                output.append(
                    f"{status_emoji} Build #{build_id_display}: {build_number}"
                )
                output.append(f"   Definition: {definition}")
                output.append(f"   Status: {build.get('status', 'N/A')}")
                output.append(f"   Result: {result}")
                output.append(f"   Branch: {source_branch}")

                if build.get("queueTime"):
                    output.append(f"   Queued: {build['queueTime']}")

                if build.get("_links", {}).get("web", {}).get("href"):
                    output.append(f"   URL: {build['_links']['web']['href']}")

                output.append("")  # Empty line between builds

            # Check if there are more results
            if "x-ms-continuationtoken" in response.headers:
                continuation_token = response.headers["x-ms-continuationtoken"]
                output.append(
                    f"\nMore results available. "
                    f"Use continuation token: {continuation_token}"
                )

            return "\n".join(output)

    except ValueError as auth_error:
        logger.error(f"Authentication error listing builds: {auth_error}")
        return f"❌ {str(auth_error)}"
    except Exception as e:
        logger.error(
            f"Error listing builds for project '{project}': {e}", exc_info=True
        )
        return f"❌ Error listing builds: {str(e)}"
