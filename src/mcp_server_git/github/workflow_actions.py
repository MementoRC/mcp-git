"""GitHub Actions and check-run mutations: cancel, rerun, rerequest (#301, #309).

Every tool CHANGES CI state. After a successful mutation the run (or check
run) is fetched once more so the reply carries its status, conclusion and
``run_attempt``; the caller can then poll with ``github_get_workflow_run``.
A failed follow-up fetch never turns a successful mutation into a failure.

The ``*_op`` coroutines take an open client so ``pr_check_rerun`` can reuse
them; the public tools wrap them in :func:`run_guarded`.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from mcp_server_git.github.client import github_client_context
from mcp_server_git.utils.tool_failure import ToolFailure, fail

from ._failures import http_failure

logger = logging.getLogger(__name__)

__all__ = [
    "github_cancel_workflow_run",
    "github_force_cancel_workflow_run",
    "github_rerequest_check_run",
    "github_rerun_failed_jobs",
    "github_rerun_job",
    "github_rerun_workflow_run",
]

_CANCEL_HINT = "the run is not in a cancellable state (it may already be completed)"
_RERUN_HINT = "the run cannot be re-run yet (for example it is still in progress)"
_ACTIONS_APP = "github-actions"


async def run_guarded(op: Callable[[Any], Awaitable[str]]) -> str:
    """Run ``op(client)`` with the shared token/network/unexpected-error ladder."""
    try:
        async with github_client_context() as client:
            return await op(client)
    except ValueError as auth_error:
        logger.error(f"Authentication error in workflow action: {auth_error}")
        return fail(f"❌ {str(auth_error)}")
    except ConnectionError as conn_error:
        logger.error(f"Connection error in workflow action: {conn_error}")
        return fail(f"❌ Network connection failed: {str(conn_error)}")
    except Exception as e:
        logger.error(f"Unexpected error in workflow action: {e}", exc_info=True)
        return fail(f"❌ Error: {str(e)}")


async def status_failure(
    action: str,
    response: Any,
    repo_owner: str,
    repo_name: str,
    *,
    scope: str = "actions",
    conflict_hint: str = "",
) -> ToolFailure:
    """Map an unexpected HTTP status of a mutation to a ready failure."""
    status = response.status
    body = await response.text()
    if status == 403:
        return fail(
            f"❌ {action} denied (403): the token lacks `{scope}: write` on "
            f"{repo_owner}/{repo_name}. On a cross-fork PR the token needs it "
            f"on the base repository. GitHub said: {body}"
        )
    if status == 404:
        return fail(
            f"❌ {action}: not found in {repo_owner}/{repo_name}, or the token "
            f"cannot see it (404). GitHub said: {body}"
        )
    if status == 409:
        return fail(f"❌ Cannot {action}: {conflict_hint} (409). GitHub said: {body}")
    return await http_failure(action, response)


async def _post_expecting(
    client: Any,
    endpoint: str,
    expected: int,
    action: str,
    repo_owner: str,
    repo_name: str,
    *,
    payload: dict | None = None,
    conflict_hint: str = "",
) -> ToolFailure | None:
    """POST and return ``None`` on the expected status, else the failure."""
    response = await client.post(endpoint, json=payload or {})
    if response.status == expected:
        return None
    return await status_failure(
        action, response, repo_owner, repo_name, conflict_hint=conflict_hint
    )


async def get_json(client: Any, endpoint: str) -> dict | None:
    """GET a JSON object; ``None`` on any non-200 status or error."""
    try:
        response = await client.get(endpoint)
        return await response.json() if response.status == 200 else None
    except Exception as e:
        logger.warning(f"Follow-up GET {endpoint} failed: {e}")
        return None


def run_summary_lines(run: dict) -> str:
    return (
        f"Run {run.get('id')}: {run.get('name')}\n"
        f"  Status: {run.get('status')}\n"
        f"  Conclusion: {run.get('conclusion')}\n"
        f"  Attempt: {run.get('run_attempt')}\n"
        f"  URL: {run.get('html_url')}"
    )


async def run_summary(client: Any, repo_owner: str, repo_name: str, run_id: int) -> str:
    """Fetch the run and summarise it, or say the status could not be fetched."""
    run = await get_json(
        client, f"/repos/{repo_owner}/{repo_name}/actions/runs/{run_id}"
    )
    if run is None:
        return (
            f"Run {run_id}: status could not be fetched (poll github_get_workflow_run)."
        )
    return run_summary_lines(run)


async def job_run_id(
    client: Any, repo_owner: str, repo_name: str, job_id: int
) -> int | None:
    """The run a job belongs to, or ``None`` when the job cannot be fetched."""
    job = await get_json(
        client, f"/repos/{repo_owner}/{repo_name}/actions/jobs/{job_id}"
    )
    return job.get("run_id") if job else None


def _success(headline: str, summary: str) -> str:
    return f"✅ {headline}\n{summary}\nPoll with github_get_workflow_run."


async def _cancel_op(
    client: Any, repo_owner: str, repo_name: str, run_id: int, suffix: str
) -> str:
    action = f"{suffix} workflow run {run_id}"
    base = f"/repos/{repo_owner}/{repo_name}/actions/runs/{run_id}"
    failure = await _post_expecting(
        client,
        f"{base}/{suffix}",
        202,
        action,
        repo_owner,
        repo_name,
        conflict_hint=_CANCEL_HINT,
    )
    if failure is not None:
        return failure
    summary = await run_summary(client, repo_owner, repo_name, run_id)
    return _success(f"Requested {action}", summary)


async def rerun_run_op(
    client: Any,
    repo_owner: str,
    repo_name: str,
    run_id: int,
    failed_only: bool = False,
    enable_debug_logging: bool = False,
) -> str:
    """Re-run a whole run, or only its failed jobs; reports the refreshed run."""
    suffix = "rerun-failed-jobs" if failed_only else "rerun"
    action = f"rerun {'failed jobs of ' if failed_only else ''}workflow run {run_id}"
    base = f"/repos/{repo_owner}/{repo_name}/actions/runs/{run_id}"
    failure = await _post_expecting(
        client,
        f"{base}/{suffix}",
        201,
        action,
        repo_owner,
        repo_name,
        payload={"enable_debug_logging": True} if enable_debug_logging else None,
        conflict_hint=_RERUN_HINT,
    )
    if failure is not None:
        return failure
    summary = await run_summary(client, repo_owner, repo_name, run_id)
    return _success(f"Requested {action}", summary)


async def rerun_job_op(
    client: Any,
    repo_owner: str,
    repo_name: str,
    job_id: int,
    enable_debug_logging: bool = False,
) -> str:
    """Re-run one job (and its dependents); reports the refreshed parent run."""
    action = f"rerun job {job_id}"
    failure = await _post_expecting(
        client,
        f"/repos/{repo_owner}/{repo_name}/actions/jobs/{job_id}/rerun",
        201,
        action,
        repo_owner,
        repo_name,
        payload={"enable_debug_logging": True} if enable_debug_logging else None,
        conflict_hint=_RERUN_HINT,
    )
    if failure is not None:
        return failure
    run_id = await job_run_id(client, repo_owner, repo_name, job_id)
    if run_id is None:
        summary = f"Job {job_id}: parent run could not be fetched."
    else:
        summary = await run_summary(client, repo_owner, repo_name, run_id)
    return _success(f"Requested {action}", summary)


async def _actions_check_hint(
    client: Any, repo_owner: str, repo_name: str, check_run_id: int, status: int
) -> ToolFailure | None:
    """Failure steering to github_rerun_job when the check run is an Actions job."""
    check = await get_json(
        client, f"/repos/{repo_owner}/{repo_name}/check-runs/{check_run_id}"
    )
    if not check or (check.get("app") or {}).get("slug") != _ACTIONS_APP:
        return None
    return fail(
        f"❌ Cannot rerequest check run {check_run_id} ({status}): it was created "
        f"by GitHub Actions, which rejects rerequest. Use github_rerun_job with "
        f"job_id={check_run_id} (an Actions check-run id is its job id)."
    )


async def rerequest_check_op(
    client: Any, repo_owner: str, repo_name: str, check_run_id: int
) -> str:
    """Rerequest a check run created by a GitHub App; reports its refreshed state."""
    action = f"rerequest check run {check_run_id}"
    endpoint = f"/repos/{repo_owner}/{repo_name}/check-runs/{check_run_id}"
    response = await client.post(f"{endpoint}/rerequest", json={})
    if response.status != 201:
        if response.status in (403, 422):
            hint = await _actions_check_hint(
                client, repo_owner, repo_name, check_run_id, response.status
            )
            if hint is not None:
                return hint
        return await status_failure(
            action, response, repo_owner, repo_name, scope="checks"
        )
    check = await get_json(client, endpoint)
    if check is None:
        summary = f"Check run {check_run_id}: status could not be fetched."
    else:
        summary = (
            f"Check run {check_run_id}: {check.get('name')}\n"
            f"  Status: {check.get('status')}\n"
            f"  App: {(check.get('app') or {}).get('slug')}\n"
            f"  Details: {check.get('details_url')}"
        )
    return f"✅ Requested {action}\n{summary}"


async def github_cancel_workflow_run(
    repo_owner: str, repo_name: str, run_id: int
) -> str:
    """Cancel a workflow run (POST /actions/runs/{run_id}/cancel)."""
    return await run_guarded(
        lambda client: _cancel_op(client, repo_owner, repo_name, run_id, "cancel")
    )


async def github_force_cancel_workflow_run(
    repo_owner: str, repo_name: str, run_id: int
) -> str:
    """Force-cancel a run that ignores a normal cancel (POST .../force-cancel)."""
    return await run_guarded(
        lambda client: _cancel_op(client, repo_owner, repo_name, run_id, "force-cancel")
    )


async def github_rerun_workflow_run(
    repo_owner: str,
    repo_name: str,
    run_id: int,
    failed_only: bool = False,
    enable_debug_logging: bool = False,
) -> str:
    """Re-run a workflow run, or only its failed jobs with ``failed_only``."""
    return await run_guarded(
        lambda client: rerun_run_op(
            client, repo_owner, repo_name, run_id, failed_only, enable_debug_logging
        )
    )


async def github_rerun_failed_jobs(
    repo_owner: str,
    repo_name: str,
    run_id: int,
    enable_debug_logging: bool = False,
) -> str:
    """Re-run only the failed jobs of a run."""
    return await github_rerun_workflow_run(
        repo_owner, repo_name, run_id, True, enable_debug_logging
    )


async def github_rerun_job(
    repo_owner: str,
    repo_name: str,
    job_id: int,
    enable_debug_logging: bool = False,
) -> str:
    """Re-run a single Actions job."""
    return await run_guarded(
        lambda client: rerun_job_op(
            client, repo_owner, repo_name, job_id, enable_debug_logging
        )
    )


async def github_rerequest_check_run(
    repo_owner: str, repo_name: str, check_run_id: int
) -> str:
    """Rerequest a check run created by a GitHub App (e.g. Azure Pipelines)."""
    return await run_guarded(
        lambda client: rerequest_check_op(client, repo_owner, repo_name, check_run_id)
    )
