"""Re-run the failed checks of a pull request in one call (#309).

Failed GitHub Actions jobs are grouped by run (one rerun-failed-jobs per run);
checks from other apps (Azure Pipelines, ...) are rerequested individually.
"""

from __future__ import annotations

import re
from typing import Any

from mcp_server_git.utils.tool_failure import ToolFailure, fail

from ._failures import http_failure
from .workflow_actions import (
    job_run_id,
    rerequest_check_op,
    rerun_run_op,
    run_guarded,
)

__all__ = ["github_rerun_failed_pr_checks"]

_FAILED_CONCLUSIONS = frozenset(
    {"failure", "timed_out", "cancelled", "startup_failure"}
)
_JOB_URL = re.compile(r"/actions/runs/(\d+)/job/(\d+)")
_PER_PAGE = 100


async def _head_sha(
    client: Any, repo_owner: str, repo_name: str, pr_number: int
) -> str | ToolFailure:
    response = await client.get(f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}")
    if response.status != 200:
        return await http_failure(f"fetch PR #{pr_number}", response)
    return (await response.json())["head"]["sha"]


async def _check_runs(
    client: Any, repo_owner: str, repo_name: str, sha: str
) -> list[dict] | ToolFailure:
    """All check runs of a commit, following ``page`` until exhausted."""
    endpoint = f"/repos/{repo_owner}/{repo_name}/commits/{sha}/check-runs"
    runs: list[dict] = []
    page = 1
    while True:
        response = await client.get(
            endpoint, params={"per_page": _PER_PAGE, "page": page}
        )
        if response.status != 200:
            return await http_failure(f"list check runs for {sha[:8]}", response)
        data = await response.json()
        batch = data.get("check_runs", [])
        runs.extend(batch)
        if len(batch) < _PER_PAGE or len(runs) >= data.get("total_count", 0):
            return runs
        page += 1


async def _actions_run_id(
    client: Any, repo_owner: str, repo_name: str, check: dict
) -> int | None:
    match = _JOB_URL.search(check.get("details_url") or "")
    if match:
        return int(match.group(1))
    return await job_run_id(client, repo_owner, repo_name, check["id"])


async def _plan(
    client: Any, repo_owner: str, repo_name: str, failed: list[dict]
) -> tuple[dict[int, list[str]], list[dict]]:
    """Group failures: ``{run_id: [job names]}`` plus checks to rerequest."""
    runs: dict[int, list[str]] = {}
    rerequests: list[dict] = []
    for check in failed:
        run_id = None
        if (check.get("app") or {}).get("slug") == "github-actions":
            run_id = await _actions_run_id(client, repo_owner, repo_name, check)
        if run_id is None:
            rerequests.append(check)
        else:
            runs.setdefault(run_id, []).append(check.get("name", "?"))
    return runs, rerequests


def _plan_lines(runs: dict[int, list[str]], rerequests: list[dict]) -> list[str]:
    lines = [
        f"Would rerun failed jobs of run {run_id} ({', '.join(names)})"
        for run_id, names in runs.items()
    ]
    lines += [
        f"Would rerequest check run {c['id']} ({c.get('name', '?')})"
        for c in rerequests
    ]
    return lines


async def _execute(
    client: Any,
    repo_owner: str,
    repo_name: str,
    runs: dict[int, list[str]],
    rerequests: list[dict],
) -> tuple[list[str], bool]:
    """Result lines (each result leads with its own ✅/❌) and whether any succeeded."""
    results = [
        await rerun_run_op(client, repo_owner, repo_name, run_id, True)
        for run_id in runs
    ]
    results += [
        await rerequest_check_op(client, repo_owner, repo_name, check["id"])
        for check in rerequests
    ]
    failures = sum(isinstance(r, ToolFailure) for r in results)
    ok = len(results) - failures
    lines = [*results, f"{ok} of {len(results)} actions succeeded, {failures} failed"]
    return lines, ok > 0


async def _rerun_failed(
    client: Any, repo_owner: str, repo_name: str, pr_number: int, dry_run: bool
) -> str:
    sha = await _head_sha(client, repo_owner, repo_name, pr_number)
    if isinstance(sha, ToolFailure):
        return sha
    checks = await _check_runs(client, repo_owner, repo_name, sha)
    if isinstance(checks, ToolFailure):
        return checks
    failed = [c for c in checks if c.get("conclusion") in _FAILED_CONCLUSIONS]
    if not failed:
        return f"✅ No failed checks on PR #{pr_number}"
    runs, rerequests = await _plan(client, repo_owner, repo_name, failed)
    header = f"PR #{pr_number} ({sha[:8]}): {len(failed)} failed check run(s)"
    if dry_run:
        return "\n".join(
            [f"{header} (dry run, nothing changed)"] + _plan_lines(runs, rerequests)
        )
    lines, any_ok = await _execute(client, repo_owner, repo_name, runs, rerequests)
    text = "\n".join([header, *lines])
    return text if any_ok else fail(text)


async def github_rerun_failed_pr_checks(
    repo_owner: str, repo_name: str, pr_number: int, dry_run: bool = False
) -> str:
    """Re-run every failed check of a PR's head commit (CHANGES CI state)."""
    return await run_guarded(
        lambda client: _rerun_failed(client, repo_owner, repo_name, pr_number, dry_run)
    )
