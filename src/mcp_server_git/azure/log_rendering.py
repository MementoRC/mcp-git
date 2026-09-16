"""Shared log fetch/render helpers for Azure DevOps tools.

Used by azure_get_build_logs, azure_get_failing_jobs (api.py), and
azure_get_logs_for_check_run (check_run_logs.py) so the timeline fetch and
the grep/output_path/window rendering logic — matching github_get_job_logs
exactly — are each written once instead of duplicated per tool.
"""

import logging

from ..github.job_log_selection import (
    LogSelectionError,
    build_log_response_lines,
    write_full_log_response,
)

logger = logging.getLogger(__name__)

# Mirrors github/ci_logs.py's limits so Azure log tools behave identically
# to github_get_job_logs.
AZURE_LOGS_MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB hard limit (memory protection)
AZURE_LOGS_MAX_CHARS_FOR_LLM = 100 * 1024  # 100 KB soft limit (~25k tokens)
AZURE_LOGS_SEPARATOR_LENGTH = 60

# Timeline record results that count as a CI failure for job/task selection.
FAILURE_RESULTS = {"failed", "canceled", "abandoned"}


async def fetch_timeline(
    client, project: str, build_id: int
) -> tuple[list[dict], str | None]:
    """Fetch a build's timeline records.

    Shared by azure_get_build_logs (for the "<Job> / <Task>" log index),
    azure_get_failing_jobs, and azure_get_logs_for_check_run so the timeline
    fetch is written once.

    Returns (records, None) on success, or ([], error_message) on failure.
    """
    response = await client.get(
        f"{project}/_apis/build/builds/{build_id}/timeline?api-version=7.1"
    )
    if response.status != 200:
        error_text = await response.text()
        return [], f"❌ Failed to get build timeline: {response.status} - {error_text}"
    timeline_data = await response.json()
    return timeline_data.get("records", []), None


def index_timeline_by_log_id(records: list[dict]) -> dict[int, str]:
    """Map each log id in a timeline to a human-readable "<Job> / <Task>" label.

    Task records are named generically (e.g. "Run OSX build" for every
    variant), so a Task's label joins its own name with its parent Job's
    name (found via parentId). Records without a resolvable Job parent fall
    back to their own name; log ids with no matching record at all are left
    out and the caller falls back to "Container".
    """
    by_id = {record["id"]: record for record in records if record.get("id")}
    index: dict[int, str] = {}
    for record in records:
        log = record.get("log") or {}
        log_id = log.get("id")
        if log_id is None:
            continue
        own_name = record.get("name") or "Container"
        parent = by_id.get(record.get("parentId"))
        if record.get("type") == "Task" and parent and parent.get("name"):
            index[log_id] = f"{parent['name']} / {own_name}"
        else:
            index[log_id] = own_name
    return index


def render_log_index(build_id: int, logs: list[dict], records: list[dict]) -> str:
    """Render the "list all logs" response, joining names in via the timeline."""
    label_by_log_id = index_timeline_by_log_id(records)
    output = [f"Logs for Build #{build_id}:\n"]
    for log in logs:
        label = label_by_log_id.get(log["id"], "Container")
        line_count = log.get("lineCount", 0)
        output.append(f"Log #{log['id']}: {label} ({line_count} lines)")
        if log.get("url"):
            output.append(f"  URL: {log['url']}")
    return "\n".join(output)


async def read_log_lines(response) -> list[str]:
    """Parse an Azure build-log response body into a list of lines.

    Azure DevOps returns log content as JSON with a "value" array of
    strings when Accept negotiation allows it, otherwise plain text.
    """
    content_type = response.headers.get("Content-Type", "")
    if "application/json" in content_type:
        log_data = await response.json()
        if isinstance(log_data, dict) and "value" in log_data:
            return log_data["value"]
        if isinstance(log_data, list):
            return log_data
        return [str(log_data)]
    log_text = await response.text()
    return log_text.split("\n")


async def fetch_and_render_log(
    client,
    project: str,
    build_id: int,
    log_id: int,
    header: list[str],
    *,
    tail_lines: int | None,
    full_log: bool,
    head_lines: int | None,
    start_line: int | None,
    end_line: int | None,
    grep: str | None,
    context_lines: int,
    ignore_case: bool,
    output_path: str | None,
) -> str:
    """Fetch one Azure build log and render it with github_get_job_logs' selection knobs.

    Shared by azure_get_build_logs (fetching by log_id) and
    azure_get_logs_for_check_run (fetching the resolved task's log), so the
    grep/output_path/window handling stays identical between all three tools.
    """
    # Request text/plain: the single-log endpoint returns a bare
    # List<String>, which Azure refuses to serialize as JSON
    # (500 "doesn't implement ISecuredObject"). Plain text works.
    response = await client.get(
        f"{project}/_apis/build/builds/{build_id}/logs/{log_id}?api-version=7.1",
        accept="text/plain",
    )
    if response.status != 200:
        error_text = await response.text()
        return f"❌ Failed to get log #{log_id}: {response.status} - {error_text}"

    logs_text = "\n".join(await read_log_lines(response))

    if output_path is not None:
        return write_full_log_response(header, output_path, logs_text)

    try:
        header.extend(
            build_log_response_lines(
                logs_text,
                tail_lines=tail_lines,
                full_log=full_log,
                head_lines=head_lines,
                start_line=start_line,
                end_line=end_line,
                grep=grep,
                context_lines=context_lines,
                ignore_case=ignore_case,
                size_limit=AZURE_LOGS_MAX_SIZE_BYTES,
                char_limit=AZURE_LOGS_MAX_CHARS_FOR_LLM,
                separator_length=AZURE_LOGS_SEPARATOR_LENGTH,
            )
        )
    except LogSelectionError as exc:
        return f"❌ {exc}"

    return "\n".join(header)
