"""Pydantic models for GitHub Projects (v2) tools (#345)."""

from typing import Literal

from pydantic import BaseModel, Field

_OWNER = "Login of the user or organization that owns the project"
_TYPE = "Whether the owner is a 'user' or an 'org'"
_NUMBER = "Project number (as in github.com/orgs/<owner>/projects/<number>)"
_REPO = "Repository name, or owner/name, of the issue/PR"
_ITEM = "Project item node id (alternative to repo + issue_number)"
_FIELD = "Project field NAME (case-insensitive)"


class _ProjectBase(BaseModel):
    owner: str = Field(description=_OWNER)
    owner_type: Literal["user", "org"] = Field(description=_TYPE)
    project_number: int = Field(description=_NUMBER)


class GitHubProjectListItems(_ProjectBase):
    repo: str | None = Field(default=None, description="Only items from this repo")
    numbers: list[int] | None = Field(
        default=None, description="Only items with these issue/PR numbers"
    )
    field: str | None = Field(default=None, description="Filter: field name")
    value: str | None = Field(
        default=None, description="Filter: required value of `field`"
    )


class GitHubProjectGetFields(_ProjectBase):
    pass


class GitHubProjectSetItemField(_ProjectBase):
    field: str = Field(description=_FIELD)
    value: str = Field(
        description="Option NAME (single-select), iteration title, text, number "
        "or ISO date (YYYY-MM-DD)"
    )
    repo: str | None = Field(default=None, description=_REPO)
    issue_number: int | None = Field(default=None, description="Issue or PR number")
    item_id: str | None = Field(default=None, description=_ITEM)


class GitHubProjectClearItemField(_ProjectBase):
    field: str = Field(description=_FIELD)
    repo: str | None = Field(default=None, description=_REPO)
    issue_number: int | None = Field(default=None, description="Issue or PR number")
    item_id: str | None = Field(default=None, description=_ITEM)


class GitHubProjectArchiveItem(_ProjectBase):
    repo: str | None = Field(default=None, description=_REPO)
    issue_number: int | None = Field(default=None, description="Issue or PR number")
    item_id: str | None = Field(default=None, description=_ITEM)


class GitHubProjectAddItem(_ProjectBase):
    url: str | None = Field(default=None, description="Issue or PR URL")
    repo: str | None = Field(default=None, description=_REPO)
    number: int | None = Field(default=None, description="Issue or PR number")
    fields: dict[str, str] | None = Field(
        default=None, description="Initial values, field NAME -> value"
    )
