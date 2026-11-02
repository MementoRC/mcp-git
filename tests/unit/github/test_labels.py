"""github_list_labels / github_create_label / github_update_label (issue #327)."""

import pytest

from mcp_server_git.github.api import (
    github_create_label,
    github_list_labels,
    github_update_label,
)
from mcp_server_git.utils.tool_failure import ToolFailure

from ._label_fakes import FakeResponse, LabelClient, build_interface, call

LABELS = "/repos/o/r/labels"
ENCODED = f"{LABELS}/area%3A%20ci%2Fcd"
LABEL_JSON = {"name": "bug", "color": "d73a4a", "description": "Broken"}


@pytest.mark.asyncio
async def test_list_labels_returns_name_color_description_when_labels_exist():
    route = ("GET", f"{LABELS}?per_page=100&page=1")
    client = LabelClient({route: FakeResponse(200, [LABEL_JSON])})

    result = await call(github_list_labels, client, "o", "r")

    assert "bug" in result and "d73a4a" in result and "Broken" in result


@pytest.mark.asyncio
async def test_create_label_posts_normalised_color_when_color_has_hash():
    client = LabelClient({("POST", LABELS): FakeResponse(201, LABEL_JSON)})

    await call(github_create_label, client, "o", "r", "bug", "#FBCA04", "d")

    assert client.posts() == [
        (LABELS, {"json": {"name": "bug", "color": "fbca04", "description": "d"}})
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["xyz", "fbca0", "#fbca0400", "gggggg"])
async def test_create_label_returns_failure_without_http_when_color_invalid(bad):
    client = LabelClient({})

    result = await call(github_create_label, client, "o", "r", "bug", bad)

    assert isinstance(result, ToolFailure)
    assert client.calls == []


@pytest.mark.asyncio
async def test_create_label_returns_non_failure_when_422_already_exists():
    body = '{"errors":[{"resource":"Label","code":"already_exists"}]}'
    client = LabelClient({("POST", LABELS): FakeResponse(422, text=body)})

    result = await call(github_create_label, client, "o", "r", "bug", "ffffff")

    assert not isinstance(result, ToolFailure)
    assert "already exists" in result


@pytest.mark.asyncio
async def test_create_label_returns_failure_when_422_other_code():
    body = '{"errors":[{"code":"invalid"}]}'
    client = LabelClient({("POST", LABELS): FakeResponse(422, text=body)})

    result = await call(github_create_label, client, "o", "r", "bug", "ffffff")

    assert isinstance(result, ToolFailure)


@pytest.mark.asyncio
async def test_update_label_patches_encoded_path_with_only_given_fields():
    client = LabelClient({("PATCH", ENCODED): FakeResponse(200, LABEL_JSON)})

    await call(github_update_label, client, "o", "r", "area: ci/cd", color="#00ff00")

    assert client.calls == [("PATCH", ENCODED, {"json": {"color": "00ff00"}})]


@pytest.mark.asyncio
async def test_update_label_returns_failure_without_http_when_no_fields_given():
    client = LabelClient({})

    result = await call(github_update_label, client, "o", "r", "bug")

    assert isinstance(result, ToolFailure)
    assert client.calls == []


@pytest.mark.asyncio
async def test_update_label_returns_failure_without_http_when_color_invalid():
    client = LabelClient({})

    result = await call(github_update_label, client, "o", "r", "bug", color="red")

    assert isinstance(result, ToolFailure)
    assert client.calls == []


@pytest.mark.asyncio
async def test_update_label_returns_label_not_found_when_404():
    client = LabelClient({("PATCH", f"{LABELS}/bug"): FakeResponse(404, text="x")})

    result = await call(github_update_label, client, "o", "r", "bug", new_name="b")

    assert isinstance(result, ToolFailure)
    assert "Label" in result and "not found" in result


def test_tool_registry_contains_label_tools_when_interface_built():
    registry = build_interface().tool_registry

    names = {
        "github_list_labels",
        "github_create_label",
        "github_update_label",
        "github_add_issue_labels",
        "github_remove_issue_label",
    }

    assert names <= registry.keys()
    assert all(registry[n].domain == "github" for n in names)
