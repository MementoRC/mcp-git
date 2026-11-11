"""GitHub Projects (v2) tool definitions (#345)."""

from ..github.models_projects import (
    GitHubProjectAddItem,
    GitHubProjectArchiveItem,
    GitHubProjectClearItemField,
    GitHubProjectGetFields,
    GitHubProjectListItems,
    GitHubProjectSetItemField,
)
from ..github.projects import (
    github_project_add_item,
    github_project_archive_item,
    github_project_clear_item_field,
    github_project_get_fields,
    github_project_list_items,
    github_project_set_item_field,
)
from .interface import ToolDefinition

_NEEDS = "Needs a token with the 'project' scope. owner_type is 'user' or 'org'. "

_SPECS = (
    (
        "github_project_list_items",
        github_project_list_items,
        "Lists GitHub Project (v2) items via GraphQL: content (type, repo, number, "
        "title, state) and ALL field values flattened by field name, e.g. "
        '{"Status": "In progress"}. Filters: repo, numbers, field+value. '
        "Paginates past 100 items. " + _NEEDS + "('read:project' suffices.)",
        GitHubProjectListItems,
    ),
    (
        "github_project_get_fields",
        github_project_get_fields,
        "Lists a GitHub Project's fields with ids and types, plus single-select "
        "option ids/names and iterations. " + _NEEDS,
        GitHubProjectGetFields,
    ),
    (
        "github_project_set_item_field",
        github_project_set_item_field,
        "MUTATING: sets a project item's field by field NAME. Select the item by "
        "repo+issue_number or item_id. value is an option NAME (single-select), "
        "iteration title, text, number or ISO date. Returns before/after; an "
        "unknown option lists the valid ones. " + _NEEDS,
        GitHubProjectSetItemField,
    ),
    (
        "github_project_clear_item_field",
        github_project_clear_item_field,
        "MUTATING: clears a project item's field value by field NAME. " + _NEEDS,
        GitHubProjectClearItemField,
    ),
    (
        "github_project_archive_item",
        github_project_archive_item,
        "MUTATING: archives a project item (repo+issue_number or item_id). " + _NEEDS,
        GitHubProjectArchiveItem,
    ),
    (
        "github_project_add_item",
        github_project_add_item,
        "MUTATING: adds an issue or PR to a project by url or repo+number, "
        "optionally setting initial field values by name via `fields`. The content "
        "lookup and add run under the project owner's token, which must be able "
        "to read the content repo even if it belongs to another owner. " + _NEEDS,
        GitHubProjectAddItem,
    ),
)


def project_tool_definitions() -> list[ToolDefinition]:
    """ToolDefinitions for the GitHub Projects (v2) tools."""
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
