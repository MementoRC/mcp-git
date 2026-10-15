"""Job listing and name-based job lookup for a GitHub Actions workflow run."""

from __future__ import annotations

from typing import Any

from mcp_server_git.github._failures import http_failure
from mcp_server_git.utils.tool_failure import ToolFailure, fail

_JOBS_PER_PAGE = 100
_MAX_JOB_PAGES = 20


async def list_run_jobs(
    client: Any, repo_owner: str, repo_name: str, run_id: int | None
) -> tuple[list[dict], Any]:
    """All jobs of a run across pages; returns (jobs, bad_response_or_None)."""
    jobs: list[dict] = []
    for page in range(1, _MAX_JOB_PAGES + 1):
        response = await client.get(
            f"/repos/{repo_owner}/{repo_name}/actions/runs/{run_id}/jobs",
            params={"per_page": _JOBS_PER_PAGE, "page": page},
        )
        if response.status != 200:
            return jobs, response
        page_jobs = (await response.json()).get("jobs", [])
        jobs.extend(page_jobs)
        if len(page_jobs) < _JOBS_PER_PAGE:
            break
    return jobs, None


async def select_job_id(
    client: Any,
    repo_owner: str,
    repo_name: str,
    job_id: int | None,
    run_id: int | None,
    job_name: str | None,
) -> int | ToolFailure:
    """The job id to fetch: ``job_id`` itself, or resolved from run_id + job_name."""
    bad_selector = _selector_error(job_id, run_id, job_name)
    if bad_selector is not None:
        return bad_selector
    if job_id is not None:
        return job_id
    return await _resolve_job_id(client, repo_owner, repo_name, run_id, job_name)


def _selector_error(
    job_id: int | None, run_id: int | None, job_name: str | None
) -> ToolFailure | None:
    """Failure unless exactly one of job_id or (run_id and job_name) is given."""
    if job_id is not None and (run_id is not None or job_name is not None):
        return fail(
            "❌ Pass either job_id or run_id with job_name, not both. "
            "Omit run_id and job_name when job_id is given."
        )
    if job_id is None and (run_id is None or job_name is None):
        return fail("❌ Specify the job with job_id, or with both run_id and job_name.")
    return None


async def _resolve_job_id(
    client: Any,
    repo_owner: str,
    repo_name: str,
    run_id: int | None,
    job_name: str | None,
) -> int | ToolFailure:
    """The id of the single job in the run named exactly ``job_name``."""
    jobs, bad_response = await list_run_jobs(client, repo_owner, repo_name, run_id)
    if bad_response is not None:
        return await http_failure(f"list jobs for run #{run_id}", bad_response)
    matches = [job for job in jobs if job.get("name") == job_name]
    if not matches:
        available = ", ".join(repr(job.get("name")) for job in jobs) or "none"
        return fail(
            f"❌ No job named '{job_name}' in run #{run_id}. "
            f"Available jobs: {available}"
        )
    if len(matches) > 1:
        ids = ", ".join(str(job.get("id")) for job in matches)
        return fail(
            f"❌ {len(matches)} jobs named '{job_name}' in run #{run_id} "
            f"(ids: {ids}). Pass job_id to pick one."
        )
    return matches[0]["id"]
