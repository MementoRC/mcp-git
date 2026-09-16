"""Resolve a GitHub check run to its Azure build job's log (issue #229).

Hops: GitHub check run -> details_url -> Azure project/buildId/jobId ->
timeline -> Job record -> child Task records. The Job's own log is a
generic "Container" log; the real build output lives on a child Task
record, so selection works over those (see _select_task).
"""

import logging
from urllib.parse import parse_qs, urlparse

from ..github.client import github_client_context
from .api import azure_client_context
from .log_rendering import FAILURE_RESULTS, fetch_and_render_log, fetch_timeline

logger = logging.getLogger(__name__)


def _parse_check_run_details_url(
    details_url: str | None,
) -> tuple[str, int, str] | None:
    """Parse a GitHub check run's Azure-backed details_url.

    Expected shape (only jobId varies between runs):
        https://dev.azure.com/<org>/<project_guid>/_build/results
            ?buildId=<id>&view=logs&jobId=<guid>

    Returns (project_guid, build_id, job_id), or None when the URL is
    missing, malformed, or not an Azure DevOps build-results link.
    """
    if not details_url:
        return None
    parsed = urlparse(details_url)
    if parsed.netloc != "dev.azure.com":
        return None
    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) < 3 or segments[2] != "_build":
        return None
    project = segments[1]
    query = parse_qs(parsed.query)
    build_ids = query.get("buildId")
    job_ids = query.get("jobId")
    if not build_ids or not job_ids:
        return None
    try:
        build_id = int(build_ids[0])
    except ValueError:
        return None
    return project, build_id, job_ids[0]


def _find_job_record(records: list[dict], job_id: str) -> dict | None:
    """Locate the Job timeline record whose id matches the check run's jobId."""
    for record in records:
        if record.get("type") == "Job" and record.get("id") == job_id:
            return record
    return None


def _child_tasks_with_logs(records: list[dict], job_id: str) -> list[dict]:
    """Collect a Job's child Task records that have real log content.

    The Job's own log (log.id on the Job record itself) is a generic
    "Container" log; the actual build output lives on its child Task
    records (parentId == job_id), so those are what selection works over.
    """
    return [
        record
        for record in records
        if record.get("type") == "Task"
        and record.get("parentId") == job_id
        and (record.get("log") or {}).get("id") is not None
    ]


def _select_task(
    children: list[dict], task_name: str | None
) -> tuple[dict | None, str]:
    """Pick the child Task to fetch a log for.

    Priority: an explicit task_name match (case-insensitive), then the
    first task with a failing result, then the task with the largest log
    (by line count when known; ``max`` keeps the first entry on a tie, so
    this also covers "fetch order" when no line counts are available).

    Returns (selected, reason). selected is None only when task_name was
    given but matched no child.
    """
    if task_name is not None:
        for task in children:
            if (task.get("name") or "").lower() == task_name.lower():
                return task, f"matched task_name={task_name!r}"
        return None, ""

    for task in children:
        if task.get("result") in FAILURE_RESULTS:
            return task, f"first task with failing result ({task['result']})"

    largest = max(
        children, key=lambda task: (task.get("log") or {}).get("lineCount") or 0
    )
    return largest, "largest log (no failing task)"


def _build_check_run_header(
    *,
    check_run_id: int,
    build_id: int,
    job_record: dict,
    selected: dict,
    siblings: list[dict],
    reason: str,
) -> list[str]:
    """Render the header shown above the selected task's log content.

    Always names the resolved job/task and lists the sibling tasks (with
    their log ids) so a caller who wanted a different one can re-query
    azure_get_build_logs directly, instead of the alternatives being
    silently discarded.
    """
    job_name = job_record.get("name", "N/A")
    task_name = selected.get("name", "N/A")
    output = [
        f"Azure log for check run #{check_run_id} (build #{build_id}):\n",
        f"Job: {job_name}",
        f"Task: {task_name}" + (f"  ({reason})" if reason else ""),
    ]
    other_siblings = [task for task in siblings if task is not selected]
    if other_siblings:
        output.append("Other tasks in this job (re-query with azure_get_build_logs):")
        for task in other_siblings:
            sibling_log_id = (task.get("log") or {}).get("id", "N/A")
            output.append(f"  - {task.get('name', 'N/A')}: Log #{sibling_log_id}")
    output.append("")
    return output


async def azure_get_logs_for_check_run(
    repo_owner: str,
    repo_name: str,
    check_run_id: int,
    task_name: str | None = None,
    tail_lines: int | None = None,
    full_log: bool = False,
    head_lines: int | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
    grep: str | None = None,
    context_lines: int = 0,
    ignore_case: bool = False,
    output_path: str | None = None,
) -> str:
    """Resolve a GitHub check run to its Azure build job and return that job's log.

    Hops: check run -> details_url -> project/buildId/jobId -> timeline ->
    Job record -> child Task records (the Job's own log is a generic
    container log, not the build output; the real output is on a child
    Task). See _select_task for the selection rule.

    Args:
        repo_owner: Repository owner/organization
        repo_name: Repository name
        check_run_id: The GitHub check run ID (Azure-backed, e.g. conda-forge)
        task_name: If given, select the child task with this name
            (case-insensitive) instead of using the failure/largest-log rule
        tail_lines: Return only last N lines (default: 500 for LLM efficiency)
        full_log: If True, return complete log without line limit (still has
            100KB char limit unless output_path is given)
        head_lines: Return only first N lines, reaching the start of the log
        start_line: 1-indexed inclusive start of an explicit window
        end_line: 1-indexed inclusive end of an explicit window
        grep: Regex; return only matching lines. Searches the whole log by
            default, not just the last 500 lines
        context_lines: Lines of context to keep either side of a grep match
        ignore_case: Case-insensitive grep
        output_path: Absolute path to write the complete log to disk instead
            of returning it inline; the response then carries only metadata

    Returns:
        Formatted string with the resolved job/task, sibling tasks, and log
        content (or write metadata when output_path is given).
    """
    try:
        async with github_client_context() as gh_client:
            check_run_response = await gh_client.get(
                f"/repos/{repo_owner}/{repo_name}/check-runs/{check_run_id}"
            )
            if check_run_response.status != 200:
                error_text = await check_run_response.text()
                return (
                    f"❌ Failed to get check run #{check_run_id}: "
                    f"{check_run_response.status} - {error_text}"
                )
            check_run_data = await check_run_response.json()

        parsed = _parse_check_run_details_url(check_run_data.get("details_url"))
        if parsed is None:
            return (
                f"❌ Check run #{check_run_id} does not have a recognizable "
                "Azure DevOps details_url "
                f"(got: {check_run_data.get('details_url')!r}). This tool "
                "only resolves Azure-backed check runs."
            )
        project, build_id, job_id = parsed

        async with azure_client_context() as az_client:
            records, timeline_error = await fetch_timeline(az_client, project, build_id)
            if timeline_error is not None:
                return timeline_error

            job_record = _find_job_record(records, job_id)
            if job_record is None:
                return (
                    f"❌ Job {job_id} (from check run #{check_run_id}) not found "
                    f"in build #{build_id}'s timeline."
                )

            children = _child_tasks_with_logs(records, job_id)
            if not children:
                return (
                    f"❌ Job '{job_record.get('name', job_id)}' in build "
                    f"#{build_id} has no child Task records with logs."
                )

            selected, reason = _select_task(children, task_name)
            if selected is None:
                return (
                    f"❌ No task named {task_name!r} found among children of "
                    f"job '{job_record.get('name', job_id)}'."
                )

            header = _build_check_run_header(
                check_run_id=check_run_id,
                build_id=build_id,
                job_record=job_record,
                selected=selected,
                siblings=children,
                reason=reason,
            )

            return await fetch_and_render_log(
                az_client,
                project,
                build_id,
                selected["log"]["id"],
                header,
                tail_lines=tail_lines,
                full_log=full_log,
                head_lines=head_lines,
                start_line=start_line,
                end_line=end_line,
                grep=grep,
                context_lines=context_lines,
                ignore_case=ignore_case,
                output_path=output_path,
            )

    except ValueError as auth_error:
        logger.error(f"Authentication error getting check run logs: {auth_error}")
        return f"❌ {str(auth_error)}"
    except Exception as e:
        logger.error(
            f"Error getting logs for check run #{check_run_id}: {e}", exc_info=True
        )
        return f"❌ Error getting logs for check run: {str(e)}"
