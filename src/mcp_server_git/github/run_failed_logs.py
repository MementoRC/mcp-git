"""Log tails of a run's failed jobs, for ``github_get_workflow_run(include_logs)``."""

from __future__ import annotations

from mcp_server_git.github.ci_logs import github_get_job_logs
from mcp_server_git.utils.tool_failure import ToolFailure

_TAIL_LINES = 100
_TOTAL_CHAR_CAP = 60_000


async def _job_log_tail(repo_owner: str, repo_name: str, job: dict) -> str:
    """Tail of one job's log, or a one-line note when it cannot be fetched."""
    result = await github_get_job_logs(
        repo_owner, repo_name, job["id"], tail_lines=_TAIL_LINES
    )
    if isinstance(result, ToolFailure):
        reason = str(result).strip().splitlines()[-1]
        return (
            f"Job '{job.get('name')}' (id {job['id']}): could not fetch log - {reason}"
        )
    return str(result)


async def failed_job_logs_lines(
    repo_owner: str, repo_name: str, jobs: list[dict]
) -> list[str]:
    """Report lines with a log tail per failed job; total size is capped."""
    failed = [job for job in jobs if job.get("conclusion") == "failure"]
    if not failed:
        return ["", "Failed job logs: no failed jobs."]
    lines = ["", f"Failed job logs (last {_TAIL_LINES} lines per job):"]
    remaining = _TOTAL_CHAR_CAP
    for job in failed:
        if remaining <= 0:
            lines.append(
                f"Job '{job.get('name')}' (id {job['id']}): log omitted, output cap reached"
            )
            continue
        text = (await _job_log_tail(repo_owner, repo_name, job))[-remaining:]
        remaining -= len(text)
        lines.extend(["", text])
    return lines
