"""Pydantic models for Azure DevOps API tools"""

from pydantic import BaseModel


class AzureGetBuildStatus(BaseModel):
    """Get status of an Azure DevOps build/pipeline run"""

    project: str
    build_id: int


class AzureGetBuildLogs(BaseModel):
    """Get logs from an Azure DevOps build.

    When log_id is None, lists all logs for the build with joined
    "<Job name> / <Task name>" labels (falling back to the record's own
    name, then "Container", when a join is unavailable).

    When log_id is given, the same selection/output knobs as
    github_get_job_logs are available: tail_lines defaults to the last 500
    lines; head_lines, start_line/end_line, grep, context_lines,
    ignore_case, full_log, and output_path behave identically.
    """

    project: str
    build_id: int
    log_id: int | None = None  # If None, list all logs
    tail_lines: int | None = None  # Return only last N lines (default: 500)
    head_lines: int | None = None  # Return only first N lines (reaches the log start)
    start_line: int | None = None  # 1-indexed inclusive start of an explicit window
    end_line: int | None = None  # 1-indexed inclusive end of an explicit window
    full_log: bool = False  # If True, skip line limit (still has 100KB char limit)
    grep: str | None = None  # Regex; return only matching lines, searched log-wide
    context_lines: int = 0  # Lines of context to keep either side of a grep match
    ignore_case: bool = False  # Case-insensitive grep
    output_path: str | None = None  # Absolute path; write the full log there instead


class AzureGetFailingJobs(BaseModel):
    """Get detailed information about failing jobs in a build"""

    project: str
    build_id: int
    include_logs: bool = True
    log_tail_lines: int = 500  # Number of lines to include from each log (default: 500)


class AzureGetLogsForCheckRun(BaseModel):
    """Resolve a GitHub check run to its Azure build job and return that job's log.

    Steps: check run -> details_url -> parse project GUID + buildId + jobId
    -> timeline -> locate the Job record by id == jobId -> select one of its
    child Task records (the ones with real log content; the Job's own log is
    a generic container log, not the build output).

    Selection rule (in order):
      1. task_name, if given, matched case-insensitively against child tasks.
      2. Otherwise the first child task with a failing result.
      3. Otherwise the child task with the largest log.

    The response header always reports the resolved job/task names, the
    build ID, and the other sibling tasks with their log IDs so a caller who
    wanted a different one can re-query azure_get_build_logs directly.
    """

    repo_owner: str
    repo_name: str
    check_run_id: int
    task_name: str | None = None  # Case-insensitive exact match on task name
    tail_lines: int | None = None  # Return only last N lines (default: 500)
    head_lines: int | None = None  # Return only first N lines (reaches the log start)
    start_line: int | None = None  # 1-indexed inclusive start of an explicit window
    end_line: int | None = None  # 1-indexed inclusive end of an explicit window
    full_log: bool = False  # If True, skip line limit (still has 100KB char limit)
    grep: str | None = None  # Regex; return only matching lines, searched log-wide
    context_lines: int = 0  # Lines of context to keep either side of a grep match
    ignore_case: bool = False  # Case-insensitive grep
    output_path: str | None = None  # Absolute path; write the full log there instead
