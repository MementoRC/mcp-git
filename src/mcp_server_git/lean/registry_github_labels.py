"""Label management tool definitions (issue #327).

Kept apart from ``registry_github.py`` (size budget).
"""

from ..github.issue_labels import github_add_issue_labels, github_remove_issue_label
from ..github.labels import (
    github_create_label,
    github_list_labels,
    github_update_label,
)
from ..github.models_labels import (
    GitHubAddIssueLabels,
    GitHubCreateLabel,
    GitHubListLabels,
    GitHubRemoveIssueLabel,
    GitHubUpdateLabel,
)
from .interface import ToolDefinition

_SPECS = (
    (
        "github_list_labels",
        github_list_labels,
        "List a repository's labels (name, color, description) via GET /labels.",
        GitHubListLabels,
    ),
    (
        "github_create_label",
        github_create_label,
        "MUTATING: creates a label via POST /labels (color accepts a leading '#'). "
        "An already-existing label is reported as a non-failure.",
        GitHubCreateLabel,
    ),
    (
        "github_update_label",
        github_update_label,
        "MUTATING: renames/recolors/redescribes a label via PATCH /labels/{name}; "
        "only provided fields are sent. Reports 'not found' on 404.",
        GitHubUpdateLabel,
    ),
    (
        "github_add_issue_labels",
        github_add_issue_labels,
        "MUTATING: ADDS labels to an issue/PR via POST /issues/{n}/labels, keeping "
        "existing ones (unlike github_update_issue(labels=...), which replaces them). "
        "Returns the resulting label names.",
        GitHubAddIssueLabels,
    ),
    (
        "github_remove_issue_label",
        github_remove_issue_label,
        "MUTATING: removes one label from an issue/PR via DELETE "
        "/issues/{n}/labels/{label}. A label that is not applied is a non-failure.",
        GitHubRemoveIssueLabel,
    ),
)


def label_tool_definitions() -> list[ToolDefinition]:
    """ToolDefinitions for the label management GitHub tools."""
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
