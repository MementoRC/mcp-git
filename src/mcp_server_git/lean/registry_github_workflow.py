"""Workflow-run and check-run mutation tool definitions (issues #301, #309).

Kept apart from ``registry_github.py`` (size budget). There is no safety-tier
system, so each description states that the tool changes CI state.
"""

from ..github.models_workflow_actions import (
    GitHubCancelWorkflowRun,
    GitHubDispatchWorkflow,
    GitHubForceCancelWorkflowRun,
    GitHubRerequestCheckRun,
    GitHubRerunFailedJobs,
    GitHubRerunFailedPRChecks,
    GitHubRerunJob,
    GitHubRerunWorkflowRun,
)
from ..github.pr_check_rerun import github_rerun_failed_pr_checks
from ..github.workflow_actions import (
    github_cancel_workflow_run,
    github_force_cancel_workflow_run,
    github_rerequest_check_run,
    github_rerun_failed_jobs,
    github_rerun_job,
    github_rerun_workflow_run,
)
from ..github.workflow_dispatch import github_dispatch_workflow
from .interface import ToolDefinition

_SPECS = (
    (
        "github_cancel_workflow_run",
        github_cancel_workflow_run,
        "MUTATING: cancels a workflow run via POST /actions/runs/{run_id}/cancel. "
        "Returns the run's refreshed status, conclusion, run_attempt and URL.",
        GitHubCancelWorkflowRun,
    ),
    (
        "github_force_cancel_workflow_run",
        github_force_cancel_workflow_run,
        "MUTATING: force-cancels a run via POST /actions/runs/{run_id}/force-cancel; "
        "use only for runs that ignore a normal cancel. Returns the refreshed run state.",
        GitHubForceCancelWorkflowRun,
    ),
    (
        "github_rerun_workflow_run",
        github_rerun_workflow_run,
        "MUTATING: re-runs a workflow run (or only failed jobs with failed_only) via "
        "POST /actions/runs/{run_id}/rerun[-failed-jobs]. Returns the refreshed run "
        "state including run_attempt and URL.",
        GitHubRerunWorkflowRun,
    ),
    (
        "github_rerun_failed_jobs",
        github_rerun_failed_jobs,
        "MUTATING: re-runs only the failed jobs of a run via "
        "POST /actions/runs/{run_id}/rerun-failed-jobs. Returns the refreshed run state.",
        GitHubRerunFailedJobs,
    ),
    (
        "github_rerun_job",
        github_rerun_job,
        "MUTATING: re-runs one Actions job via POST /actions/jobs/{job_id}/rerun. "
        "Returns the parent run's refreshed state.",
        GitHubRerunJob,
    ),
    (
        "github_rerequest_check_run",
        github_rerequest_check_run,
        "MUTATING: rerequests a GitHub-App check run (e.g. Azure Pipelines) via "
        "POST /check-runs/{check_run_id}/rerequest. Returns its refreshed name, "
        "status, app and details URL.",
        GitHubRerequestCheckRun,
    ),
    (
        "github_dispatch_workflow",
        github_dispatch_workflow,
        "MUTATING: triggers a workflow via POST /actions/workflows/{workflow_id}/"
        "dispatches (file name or numeric id; ref defaults to the default branch). "
        "Returns the discovered run's id, status, attempt and URL, or a hint to poll "
        "when the run is not visible yet.",
        GitHubDispatchWorkflow,
    ),
    (
        "github_rerun_failed_pr_checks",
        github_rerun_failed_pr_checks,
        "MUTATING: re-runs every failed check on a PR's head commit (Actions runs via "
        "rerun-failed-jobs, App checks via rerequest); dry_run only lists the plan. "
        "Returns one result per action and a count.",
        GitHubRerunFailedPRChecks,
    ),
)


def workflow_action_tool_definitions() -> list[ToolDefinition]:
    """ToolDefinitions for the CI-mutating GitHub tools."""
    return [
        ToolDefinition(
            name=name,
            implementation=implementation,
            description=description,
            schema=model.model_json_schema(),
            domain="github",
            complexity="focused",
        )
        for name, implementation, description, model in _SPECS
    ]
