"""Trigger a workflow via ``workflow_dispatch`` and discover the new run (#311).

The dispatch endpoint answers 204 without a run id, so after a successful POST
the workflow's recent ``workflow_dispatch`` runs are polled for one created
after the request was sent. Newer API versions may answer 200 with a
``workflow_run_id``; that is used directly.
"""

from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

from mcp_server_git.utils.tool_failure import ToolFailure, fail

from .workflow_actions import (
    get_json,
    run_guarded,
    run_summary,
    run_summary_lines,
    status_failure,
)

__all__ = ["github_dispatch_workflow"]

_POLL_INTERVAL_S = 3
_MAX_WAIT_S = 60
_CLOCK_SKEW = timedelta(seconds=5)
_NOT_VISIBLE = (
    "dispatched; run not visible yet — poll "
    "github_list_workflow_runs(event='workflow_dispatch')"
)


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _invalid_workflow_id(workflow_id: str) -> ToolFailure | None:
    if not workflow_id or "/" in workflow_id or ".." in workflow_id:
        return fail(
            f"❌ Invalid workflow_id {workflow_id!r}: pass a workflow file name "
            "such as 'ci.yml' or a numeric workflow id (no '/' or '..')."
        )
    return None


def _short_ref(ref: str) -> str:
    """Strip ``refs/heads/``/``refs/tags/``; a run's head_branch has no prefix."""
    for prefix in ("refs/heads/", "refs/tags/"):
        if ref.startswith(prefix):
            return ref[len(prefix) :]
    return ref


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _newest_since(runs: list[dict], since: datetime) -> dict | None:
    """The newest run created at or after ``since``, if any."""
    fresh = [
        (created, run)
        for run in runs
        if (created := _parse_time(run.get("created_at"))) and created >= since
    ]
    return max(fresh, key=lambda pair: pair[0])[1] if fresh else None


async def _discover_run(
    client: Any, endpoint: str, since: datetime, wait_for_run_s: int
) -> dict | None:
    """Poll for the dispatched run every 3 s, for at most ``wait_for_run_s``."""
    for _ in range(math.ceil(wait_for_run_s / _POLL_INTERVAL_S)):
        await _sleep(_POLL_INTERVAL_S)
        data = await get_json(client, endpoint)
        run = _newest_since((data or {}).get("workflow_runs") or [], since)
        if run is not None:
            return run
    return None


async def _resolve_ref(
    client: Any, repo_owner: str, repo_name: str, ref: str | None
) -> str | ToolFailure:
    if ref:
        return ref
    response = await client.get(f"/repos/{repo_owner}/{repo_name}")
    if response.status != 200:
        return await status_failure(
            "look up the default branch", response, repo_owner, repo_name
        )
    return (await response.json())["default_branch"]


async def _dispatch_failure(
    response: Any, action: str, repo_owner: str, repo_name: str, ref: str
) -> ToolFailure:
    if response.status == 422:
        body = await response.text()
        return fail(
            f"❌ Cannot {action} (422): the workflow has no `workflow_dispatch` "
            f"trigger on ref '{ref}', or the inputs do not match its declared "
            f"inputs. GitHub said: {body}"
        )
    return await status_failure(action, response, repo_owner, repo_name)


async def _response_run_id(response: Any) -> int | None:
    """``workflow_run_id`` from a 200 body, if the API supplied one."""
    if response.status != 200:
        return None
    try:
        body = await response.json()
    except Exception:
        return None
    return body.get("workflow_run_id") if isinstance(body, dict) else None


async def _dispatch_op(
    client: Any,
    repo_owner: str,
    repo_name: str,
    workflow_id: str,
    ref: str | None,
    inputs: dict[str, str] | None,
    wait_for_run_s: int,
) -> str:
    resolved = await _resolve_ref(client, repo_owner, repo_name, ref)
    if isinstance(resolved, ToolFailure):
        return resolved
    base = f"/repos/{repo_owner}/{repo_name}/actions/workflows/{quote(workflow_id, safe='')}"
    payload: dict[str, Any] = {"ref": resolved}
    if inputs is not None:
        payload["inputs"] = inputs
    since = datetime.now(UTC) - _CLOCK_SKEW
    response = await client.post(f"{base}/dispatches", json=payload)
    action = f"dispatch workflow {workflow_id} on {resolved}"
    if response.status not in (200, 204):
        return await _dispatch_failure(
            response, action, repo_owner, repo_name, resolved
        )
    headline = f"✅ Dispatched {action}"
    run_id = await _response_run_id(response)
    if run_id is not None:
        return f"{headline}\n{await run_summary(client, repo_owner, repo_name, run_id)}"
    if wait_for_run_s <= 0:
        return f"{headline}\n{_NOT_VISIBLE}"
    runs_endpoint = (
        f"{base}/runs?event=workflow_dispatch&branch={quote(_short_ref(resolved), safe='')}"
        "&per_page=5"
    )
    run = await _discover_run(client, runs_endpoint, since, wait_for_run_s)
    if run is None:
        return f"{headline}\n{_NOT_VISIBLE}"
    return f"{headline}\n{run_summary_lines(run)}"


async def github_dispatch_workflow(
    repo_owner: str,
    repo_name: str,
    workflow_id: str,
    ref: str | None = None,
    inputs: dict[str, str] | None = None,
    wait_for_run_s: int = 15,
) -> str:
    """Dispatch a workflow (POST /actions/workflows/{id}/dispatches); find its run."""
    invalid = _invalid_workflow_id(workflow_id)
    if invalid is not None:
        return invalid
    wait = max(0, min(_MAX_WAIT_S, wait_for_run_s))
    return await run_guarded(
        lambda client: _dispatch_op(
            client, repo_owner, repo_name, workflow_id, ref, inputs, wait
        )
    )
