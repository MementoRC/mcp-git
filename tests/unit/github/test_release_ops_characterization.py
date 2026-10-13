"""Characterization tests for the release ops (issue #266).

Pins the observable output of github_create_release, github_get_release,
github_list_releases, github_update_release, github_upload_release_asset and
github_list_release_assets so the C901 refactor can be proven
behaviour-preserving. Only the ``github_client_context`` boundary is faked.
"""

import os
from unittest.mock import patch

import pytest

from mcp_server_git.github.release_assets import (
    github_list_release_assets,
    github_upload_release_asset,
)
from mcp_server_git.github.releases import (
    github_create_release,
    github_get_release,
    github_list_releases,
    github_update_release,
)

REL_CTX = "mcp_server_git.github.releases.github_client_context"
ASSET_CTX = "mcp_server_git.github.release_assets.github_client_context"


class FakeResponse:
    def __init__(self, status=200, payload=None, text="", headers=None):
        self.status = status
        self._payload = payload
        self._text = text
        self.headers = headers or {}

    async def json(self):
        return self._payload

    async def text(self):
        return self._text


class FakeClient:
    """Serves queued responses in call order and records every call."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def _next(self, method, endpoint, kwargs):
        self.calls.append((method, endpoint, kwargs))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def get(self, endpoint, **kwargs):
        return await self._next("get", endpoint, kwargs)

    async def post(self, endpoint, **kwargs):
        return await self._next("post", endpoint, kwargs)

    async def patch(self, endpoint, **kwargs):
        return await self._next("patch", endpoint, kwargs)


class FakeContext:
    def __init__(self, client=None, exc=None):
        self.client = client
        self.exc = exc

    async def __aenter__(self):
        if self.exc is not None:
            raise self.exc
        return self.client

    async def __aexit__(self, *args):
        return None


def ok(payload, **kw):
    return FakeResponse(200, payload, **kw)


async def _run(func, ctx, args, responses=(), exc=None, **kwargs):
    client = FakeClient(responses)
    with patch(ctx, return_value=FakeContext(client, exc)):
        result = await func(*args, **kwargs)
    return result, client


async def _create(responses=(), exc=None, **kwargs):
    return await _run(
        github_create_release, REL_CTX, ("o", "r", "v1"), responses, exc, **kwargs
    )


async def _get(responses=(), exc=None, **kwargs):
    return await _run(github_get_release, REL_CTX, ("o", "r"), responses, exc, **kwargs)


async def _list(responses=(), exc=None, **kwargs):
    return await _run(
        github_list_releases, REL_CTX, ("o", "r"), responses, exc, **kwargs
    )


async def _update(responses=(), exc=None, **kwargs):
    return await _run(
        github_update_release, REL_CTX, ("o", "r", 5), responses, exc, **kwargs
    )


async def _upload(path, responses=(), exc=None, **kwargs):
    return await _run(
        github_upload_release_asset,
        ASSET_CTX,
        ("o", "r", 5, str(path)),
        responses,
        exc,
        **kwargs,
    )


async def _assets(responses=(), exc=None, **kwargs):
    return await _run(
        github_list_release_assets, ASSET_CTX, ("o", "r", 5), responses, exc, **kwargs
    )


# ---------------------------------------------------------------- handlers

HANDLER_CASES = [
    ("create", "creating release"),
    ("get", "getting release"),
    ("list", "listing releases"),
    ("update", "updating release"),
    ("assets", "listing assets"),
]


async def _call_with_exc(kind, exc, tmp_path):
    if kind == "create":
        return await _create(exc=exc)
    if kind == "get":
        return await _get(exc=exc, release_id=1)
    if kind == "list":
        return await _list(exc=exc)
    if kind == "update":
        return await _update(exc=exc, name="x")
    return await _assets(exc=exc)


@pytest.mark.asyncio
@pytest.mark.parametrize(("kind", "label"), HANDLER_CASES)
async def test_release_ops_return_auth_message_when_value_error_raised(
    kind, label, tmp_path
):
    result, _ = await _call_with_exc(kind, ValueError("bad token"), tmp_path)
    assert result == "❌ bad token"


@pytest.mark.asyncio
@pytest.mark.parametrize(("kind", "label"), HANDLER_CASES)
async def test_release_ops_return_network_message_when_connection_error_raised(
    kind, label, tmp_path
):
    result, _ = await _call_with_exc(kind, ConnectionError("down"), tmp_path)
    assert result == "❌ Network connection failed: down"


@pytest.mark.asyncio
@pytest.mark.parametrize(("kind", "label"), HANDLER_CASES)
async def test_release_ops_return_error_message_when_unexpected_error_raised(
    kind, label, tmp_path
):
    result, _ = await _call_with_exc(kind, RuntimeError("boom"), tmp_path)
    assert result == f"❌ Error {label}: boom"


@pytest.mark.asyncio
async def test_upload_release_asset_handlers_return_messages_when_client_fails(
    tmp_path,
):
    f = tmp_path / "a.txt"
    f.write_bytes(b"x")
    r1, _ = await _upload(f, exc=ValueError("bad token"))
    r2, _ = await _upload(f, exc=ConnectionError("down"))
    r3, _ = await _upload(f, exc=RuntimeError("boom"))
    assert r1 == "❌ bad token"
    assert r2 == "❌ Network connection failed: down"
    assert r3 == "❌ Error uploading asset: boom"


# ------------------------------------------------------------------ create


@pytest.mark.asyncio
async def test_create_release_returns_success_when_defaults_used():
    result, client = await _create([FakeResponse(201, {"html_url": "U", "id": 9})])
    assert result == ("✅ Release v1 created successfully\n🔗 URL: U\n📋 Release ID: 9")
    assert client.calls == [
        (
            "post",
            "/repos/o/r/releases",
            {"json": {"tag_name": "v1", "draft": False, "prerelease": False}},
        )
    ]


@pytest.mark.asyncio
async def test_create_release_includes_all_optional_fields_when_truthy():
    result, client = await _create(
        [ok({"html_url": "U", "id": 9})],
        name="N",
        body="B",
        draft=True,
        prerelease=True,
        target_commitish="main",
        generate_release_notes=True,
    )
    assert result.splitlines()[0] == (
        "✅ Release v1 created successfully (draft, pre-release)"
    )
    assert client.calls[0][2]["json"] == {
        "tag_name": "v1",
        "draft": True,
        "prerelease": True,
        "name": "N",
        "body": "B",
        "target_commitish": "main",
        "generate_release_notes": True,
    }


@pytest.mark.asyncio
async def test_create_release_omits_optional_fields_when_empty_or_none():
    _, client = await _create(
        [ok({})],
        name="",
        body="",
        target_commitish="",
        generate_release_notes=False,
    )
    assert client.calls[0][2]["json"] == {
        "tag_name": "v1",
        "draft": False,
        "prerelease": False,
    }


@pytest.mark.asyncio
async def test_create_release_labels_draft_only_when_only_draft_set():
    result, _ = await _create([ok({})], draft=True)
    assert result == (
        "✅ Release v1 created successfully (draft)\n🔗 URL: \n📋 Release ID: "
    )


@pytest.mark.asyncio
async def test_create_release_labels_prerelease_only_when_only_prerelease_set():
    result, _ = await _create([ok({})], prerelease=True)
    assert result.splitlines()[0] == (
        "✅ Release v1 created successfully (pre-release)"
    )


@pytest.mark.asyncio
async def test_create_release_returns_not_found_when_404():
    result, _ = await _create([FakeResponse(404)])
    assert result == "❌ Repository o/r not found"


@pytest.mark.asyncio
async def test_create_release_returns_message_when_422():
    result, _ = await _create([FakeResponse(422, {"message": "dup"})])
    assert result == "❌ Failed to create release: dup"


@pytest.mark.asyncio
async def test_create_release_returns_default_message_when_422_without_message():
    result, _ = await _create([FakeResponse(422, {})])
    assert result == "❌ Failed to create release: Validation failed"


@pytest.mark.asyncio
async def test_create_release_returns_status_and_text_when_other_status():
    result, _ = await _create([FakeResponse(500, text="oops")])
    assert result == "❌ Failed to create release: 500 - oops"


# --------------------------------------------------------------------- get


@pytest.mark.asyncio
async def test_get_release_returns_error_when_neither_identifier_given():
    result, client = await _get()
    assert result == "❌ Either release_id or tag must be provided"
    assert client.calls == []


@pytest.mark.asyncio
async def test_get_release_returns_error_when_release_id_zero_and_no_tag():
    result, _ = await _get(release_id=0)
    assert result == "❌ Either release_id or tag must be provided"


@pytest.mark.asyncio
async def test_get_release_returns_error_when_both_identifiers_given():
    result, _ = await _get(release_id=1, tag="v1")
    assert result == "❌ Only one of release_id or tag can be provided"


@pytest.mark.asyncio
async def test_get_release_uses_id_endpoint_when_release_id_given():
    _, client = await _get([ok({})], release_id=3)
    assert client.calls == [("get", "/repos/o/r/releases/3", {})]


@pytest.mark.asyncio
async def test_get_release_uses_tag_endpoint_when_tag_given():
    _, client = await _get([ok({})], tag="v1")
    assert client.calls == [("get", "/repos/o/r/releases/tags/v1", {})]


@pytest.mark.asyncio
async def test_get_release_returns_not_found_with_id_when_404_by_id():
    result, _ = await _get([FakeResponse(404)], release_id=3)
    assert result == "❌ Release ID 3 not found in o/r"


@pytest.mark.asyncio
async def test_get_release_returns_not_found_with_tag_when_404_by_tag():
    result, _ = await _get([FakeResponse(404)], tag="v1")
    assert result == "❌ Release tag 'v1' not found in o/r"


@pytest.mark.asyncio
async def test_get_release_returns_status_and_text_when_other_status():
    result, _ = await _get([FakeResponse(500, text="oops")], tag="v1")
    assert result == "❌ Failed to get release: 500 - oops"


@pytest.mark.asyncio
async def test_get_release_formats_full_release_when_all_fields_present():
    release = {
        "tag_name": "v1",
        "name": "First",
        "draft": True,
        "prerelease": True,
        "html_url": "U",
        "created_at": "C",
        "published_at": "P",
        "author": {"login": "bob"},
        "body": "notes",
        "assets": [
            {"name": "a.zip", "size": 10},
            {"name": "b.zip", "size": 20},
        ],
    }
    result, _ = await _get([ok(release)], release_id=1)
    assert result.split("\n") == [
        "Release Information for o/r:",
        "",
        "📦 Tag: v1",
        "📋 Name: First",
        "🏷️  Status: draft, pre-release",
        "🔗 URL: U",
        "📅 Created: C",
        "📅 Published: P",
        "👤 Author: bob",
        "",
        "📝 Description:",
        "notes",
        "",
        "📎 Assets (2):",
        "   • a.zip (10 bytes)",
        "   • b.zip (20 bytes)",
    ]


@pytest.mark.asyncio
async def test_get_release_formats_minimal_release_when_fields_missing():
    result, _ = await _get([ok({})], release_id=1)
    assert result.split("\n") == [
        "Release Information for o/r:",
        "",
        "📦 Tag: None",
        "📋 Name: (none)",
        "🔗 URL: None",
        "📅 Created: None",
        "📅 Published: Not published",
        "",
        "📎 Assets: None",
    ]


@pytest.mark.asyncio
async def test_get_release_labels_prerelease_only_when_only_prerelease_set():
    result, _ = await _get([ok({"prerelease": True})], release_id=1)
    assert "🏷️  Status: pre-release" in result.split("\n")


@pytest.mark.asyncio
async def test_get_release_labels_draft_only_when_only_draft_set():
    result, _ = await _get([ok({"draft": True})], release_id=1)
    assert "🏷️  Status: draft" in result.split("\n")


@pytest.mark.asyncio
async def test_get_release_skips_author_and_assets_when_null():
    result, _ = await _get([ok({"author": None, "assets": None})], release_id=1)
    assert "👤" not in result
    assert result.endswith("📎 Assets: None")


@pytest.mark.asyncio
async def test_get_release_prints_none_login_when_author_lacks_login():
    result, _ = await _get([ok({"author": {"id": 1}})], release_id=1)
    assert "👤 Author: None" in result.split("\n")


@pytest.mark.asyncio
async def test_get_release_does_not_truncate_body_when_long():
    body = "x" * 5000
    result, _ = await _get([ok({"body": body})], release_id=1)
    assert f"\n📝 Description:\n{body}" in result


# -------------------------------------------------------------------- list


@pytest.mark.asyncio
async def test_list_releases_passes_pagination_params_unclamped():
    _, client = await _list([ok([])], per_page=500, page=3)
    assert client.calls == [
        ("get", "/repos/o/r/releases", {"params": {"per_page": 500, "page": 3}})
    ]


@pytest.mark.asyncio
async def test_list_releases_returns_not_found_when_404():
    result, _ = await _list([FakeResponse(404)])
    assert result == "❌ Repository o/r not found"


@pytest.mark.asyncio
async def test_list_releases_returns_status_and_text_when_other_status():
    result, _ = await _list([FakeResponse(500, text="oops")])
    assert result == "❌ Failed to list releases: 500 - oops"


@pytest.mark.asyncio
async def test_list_releases_returns_empty_message_when_no_releases():
    result, _ = await _list([ok([])])
    assert result == "No releases found for o/r"


@pytest.mark.asyncio
async def test_list_releases_formats_entries_when_releases_returned():
    releases = [
        {
            "tag_name": "v2",
            "name": "Two",
            "draft": True,
            "prerelease": True,
            "created_at": "2024-01-02T03:04:05Z",
            "html_url": "U2",
        },
        {"tag_name": "v1", "name": None, "created_at": "", "html_url": "U1"},
        {"tag_name": "v0", "prerelease": True, "html_url": "U0"},
    ]
    result, _ = await _list([ok(releases)])
    assert result.split("\n") == [
        "Releases for o/r:",
        "",
        "📦 v2: Two [draft, pre-release]",
        "   📅 Created: 2024-01-02",
        "   🔗 U2",
        "",
        "📦 v1: v1",
        "   📅 Created: ",
        "   🔗 U1",
        "",
        "📦 v0: v0 [pre-release]",
        "   📅 Created: ",
        "   🔗 U0",
        "",
    ]


@pytest.mark.asyncio
async def test_list_releases_labels_draft_only_when_only_draft_set():
    result, _ = await _list([ok([{"tag_name": "v", "draft": True}])])
    assert "📦 v: v [draft]" in result.split("\n")


@pytest.mark.asyncio
async def test_list_releases_adds_page_footer_when_link_has_next():
    resp = ok([{"tag_name": "v"}], headers={"Link": '<u>; rel="next"'})
    result, _ = await _list([resp])
    assert result.endswith("📄 Page 1 (use page parameter to see more)")


@pytest.mark.asyncio
async def test_list_releases_adds_page_footer_when_page_after_first():
    result, _ = await _list([ok([{"tag_name": "v"}])], page=2)
    assert result.endswith("📄 Page 2 (use page parameter to see more)")


@pytest.mark.asyncio
async def test_list_releases_omits_page_footer_when_single_page():
    result, _ = await _list([ok([{"tag_name": "v"}])])
    assert "📄" not in result


@pytest.mark.asyncio
async def test_list_releases_reports_error_when_created_at_is_null():
    # Preserved quirk: null created_at crashes the formatter (tracked in #273).
    result, _ = await _list([ok([{"tag_name": "v", "created_at": None}])])
    assert result == "❌ Error listing releases: 'NoneType' object is not subscriptable"


# ------------------------------------------------------------------ update


@pytest.mark.asyncio
async def test_update_release_returns_error_when_no_fields_given():
    result, client = await _update()
    assert result == "❌ No fields provided to update"
    assert client.calls == []


@pytest.mark.asyncio
async def test_update_release_sends_only_provided_fields_when_partial():
    result, client = await _update([ok({"html_url": "U", "tag_name": "v9"})], name="N")
    assert result == "✅ Release v9 (ID: 5) updated successfully\n🔗 URL: U"
    assert client.calls == [("patch", "/repos/o/r/releases/5", {"json": {"name": "N"}})]


@pytest.mark.asyncio
async def test_update_release_sends_falsy_values_when_not_none():
    _, client = await _update(
        [ok({})],
        tag_name="",
        name="",
        body="",
        draft=False,
        prerelease=False,
        target_commitish="",
    )
    assert client.calls[0][2]["json"] == {
        "tag_name": "",
        "name": "",
        "body": "",
        "draft": False,
        "prerelease": False,
        "target_commitish": "",
    }


@pytest.mark.asyncio
async def test_update_release_sends_true_flags_when_set():
    _, client = await _update([ok({})], draft=True, prerelease=True)
    assert client.calls[0][2]["json"] == {"draft": True, "prerelease": True}


@pytest.mark.asyncio
async def test_update_release_uses_empty_defaults_when_response_lacks_fields():
    result, _ = await _update([ok({})], name="N")
    assert result == "✅ Release  (ID: 5) updated successfully\n🔗 URL: "


@pytest.mark.asyncio
async def test_update_release_returns_not_found_when_404():
    result, _ = await _update([FakeResponse(404)], name="N")
    assert result == "❌ Release 5 not found in o/r"


@pytest.mark.asyncio
async def test_update_release_returns_status_and_text_when_other_status():
    result, _ = await _update([FakeResponse(500, text="oops")], name="N")
    assert result == "❌ Failed to update release: 500 - oops"


@pytest.mark.asyncio
async def test_update_release_rejects_201_when_status_not_200():
    result, _ = await _update([FakeResponse(201, text="t")], name="N")
    assert result == "❌ Failed to update release: 201 - t"


# ------------------------------------------------------------------ upload


@pytest.fixture
def asset_file(tmp_path):
    f = tmp_path / "pkg.zip"
    f.write_bytes(b"hello")
    return f


def _release_resp(upload_url="https://up/x/assets{?name,label}"):
    return ok({"upload_url": upload_url})


@pytest.mark.asyncio
async def test_upload_release_asset_returns_not_found_when_file_missing(tmp_path):
    missing = tmp_path / "nope.bin"
    result, client = await _upload(missing)
    assert result == f"❌ File not found: {missing}"
    assert client.calls == []


@pytest.mark.asyncio
async def test_upload_release_asset_returns_error_when_path_is_directory(tmp_path):
    result, _ = await _upload(tmp_path)
    assert result == f"❌ Path is not a file: {tmp_path}"


@pytest.mark.asyncio
@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
async def test_upload_release_asset_returns_read_error_when_file_unreadable(
    asset_file,
):
    asset_file.chmod(0)
    try:
        result, _ = await _upload(asset_file)
    finally:
        asset_file.chmod(0o644)
    assert result.startswith(f"❌ Failed to read file {asset_file}: ")
    assert "Permission denied" in result


@pytest.mark.asyncio
async def test_upload_release_asset_uploads_file_when_release_has_upload_url(
    asset_file,
):
    result, client = await _upload(
        asset_file,
        [
            _release_resp(),
            FakeResponse(201, {"browser_download_url": "D", "id": 8, "size": 5}),
        ],
    )
    assert result == (
        "✅ Asset 'pkg.zip' uploaded successfully (5 bytes)\n🔗 URL: D\n📋 Asset ID: 8"
    )
    assert client.calls == [
        ("get", "/repos/o/r/releases/5", {}),
        (
            "post",
            "https://up/x/assets",
            {
                "params": {"name": "pkg.zip"},
                "data": b"hello",
                "headers": {"Content-Type": "application/zip"},
            },
        ),
    ]


@pytest.mark.asyncio
async def test_upload_release_asset_uses_name_and_label_when_given(asset_file):
    result, client = await _upload(
        asset_file,
        [_release_resp(), ok({})],
        name="custom.json",
        label="Lbl",
    )
    assert result == (
        "✅ Asset 'custom.json' uploaded successfully (0 bytes)\n🔗 URL: \n📋 Asset ID: "
    )
    kwargs = client.calls[1][2]
    assert kwargs["params"] == {"name": "custom.json", "label": "Lbl"}
    assert kwargs["headers"] == {"Content-Type": "application/json"}


@pytest.mark.asyncio
async def test_upload_release_asset_ignores_empty_name_and_label(asset_file):
    _, client = await _upload(asset_file, [_release_resp(), ok({})], name="", label="")
    assert client.calls[1][2]["params"] == {"name": "pkg.zip"}


@pytest.mark.asyncio
async def test_upload_release_asset_defaults_content_type_when_unknown_extension(
    tmp_path,
):
    f = tmp_path / "data.zzzunknown"
    f.write_bytes(b"")
    _, client = await _upload(f, [_release_resp(), ok({})])
    assert client.calls[1][2]["headers"] == {"Content-Type": "application/octet-stream"}
    assert client.calls[1][2]["data"] == b""


@pytest.mark.asyncio
async def test_upload_release_asset_defaults_content_type_when_mimetypes_fails(
    asset_file,
):
    with patch("mimetypes.guess_type", side_effect=RuntimeError("corrupt")):
        _, client = await _upload(asset_file, [_release_resp(), ok({})])
    assert client.calls[1][2]["headers"] == {"Content-Type": "application/octet-stream"}


@pytest.mark.asyncio
async def test_upload_release_asset_keeps_url_when_no_template(asset_file):
    _, client = await _upload(asset_file, [_release_resp("https://up/plain"), ok({})])
    assert client.calls[1][1] == "https://up/plain"


@pytest.mark.asyncio
async def test_upload_release_asset_returns_not_found_when_release_404(asset_file):
    result, _ = await _upload(asset_file, [FakeResponse(404)])
    assert result == "❌ Release 5 not found in o/r"


@pytest.mark.asyncio
async def test_upload_release_asset_returns_get_failure_when_release_status_bad(
    asset_file,
):
    result, _ = await _upload(asset_file, [FakeResponse(500, text="oops")])
    assert result == "❌ Failed to get release: 500 - oops"


@pytest.mark.asyncio
async def test_upload_release_asset_returns_error_when_upload_url_missing(
    asset_file,
):
    result, _ = await _upload(asset_file, [ok({})])
    assert result == "❌ Release 5 has no upload URL"


@pytest.mark.asyncio
async def test_upload_release_asset_returns_message_when_upload_422(asset_file):
    result, _ = await _upload(
        asset_file, [_release_resp(), FakeResponse(422, {"message": "exists"})]
    )
    assert result == "❌ Failed to upload asset: exists"


@pytest.mark.asyncio
async def test_upload_release_asset_returns_default_message_when_422_bare(
    asset_file,
):
    result, _ = await _upload(asset_file, [_release_resp(), FakeResponse(422, {})])
    assert result == "❌ Failed to upload asset: Validation failed"


@pytest.mark.asyncio
async def test_upload_release_asset_returns_status_when_upload_fails(asset_file):
    result, _ = await _upload(
        asset_file, [_release_resp(), FakeResponse(500, text="oops")]
    )
    assert result == "❌ Failed to upload asset: 500 - oops"


@pytest.mark.asyncio
async def test_upload_release_asset_accepts_200_when_upload_ok(asset_file):
    result, _ = await _upload(asset_file, [_release_resp(), ok({"id": 1, "size": 9})])
    assert "uploaded successfully (9 bytes)" in result


# ------------------------------------------------------------------ assets


@pytest.mark.asyncio
async def test_list_release_assets_passes_pagination_params_unclamped():
    _, client = await _assets([ok([])], per_page=500, page=4)
    assert client.calls == [
        (
            "get",
            "/repos/o/r/releases/5/assets",
            {"params": {"per_page": 500, "page": 4}},
        )
    ]


@pytest.mark.asyncio
async def test_list_release_assets_returns_not_found_when_404():
    result, _ = await _assets([FakeResponse(404)])
    assert result == "❌ Release 5 not found in o/r"


@pytest.mark.asyncio
async def test_list_release_assets_returns_status_and_text_when_other_status():
    result, _ = await _assets([FakeResponse(500, text="oops")])
    assert result == "❌ Failed to list assets: 500 - oops"


@pytest.mark.asyncio
async def test_list_release_assets_returns_empty_message_when_no_assets():
    result, _ = await _assets([ok([])])
    assert result == "No assets found for release 5"


@pytest.mark.asyncio
async def test_list_release_assets_formats_entries_when_assets_returned():
    assets = [
        {
            "name": "a",
            "id": 1,
            "size": 1023,
            "download_count": 4,
            "content_type": "text/plain",
            "browser_download_url": "UA",
        },
        {"name": "b", "id": 2, "size": 1024, "browser_download_url": "UB"},
        {"name": "c", "id": 3, "size": 1024 * 1024 - 1},
        {"name": "d", "id": 4, "size": 1024 * 1024 * 3 // 2},
        {"name": "e", "id": 5},
    ]
    result, _ = await _assets([ok(assets)])
    lines = result.split("\n")
    assert lines[:2] == ["Assets for Release 5 in o/r:", ""]
    assert lines[2:9] == [
        "📎 a",
        "   ID: 1",
        "   Size: 1023 B",
        "   Type: text/plain",
        "   Downloads: 4",
        "   URL: UA",
        "",
    ]
    assert lines[9:16] == [
        "📎 b",
        "   ID: 2",
        "   Size: 1.0 KB",
        "   Type: unknown",
        "   Downloads: 0",
        "   URL: UB",
        "",
    ]
    assert "   Size: 1024.0 KB" in lines
    assert "   Size: 1.5 MB" in lines
    assert "   Size: 0 B" in lines
    assert "   URL: None" in lines


@pytest.mark.asyncio
async def test_list_release_assets_adds_page_footer_when_link_has_next():
    resp = ok([{"name": "a"}], headers={"Link": '<u>; rel="next"'})
    result, _ = await _assets([resp])
    assert result.endswith("📄 Page 1 (use page parameter to see more)")


@pytest.mark.asyncio
async def test_list_release_assets_adds_page_footer_when_page_after_first():
    result, _ = await _assets([ok([{"name": "a"}])], page=2)
    assert result.endswith("📄 Page 2 (use page parameter to see more)")


@pytest.mark.asyncio
async def test_list_release_assets_omits_page_footer_when_single_page():
    result, _ = await _assets([ok([{"name": "a"}])])
    assert "📄" not in result


@pytest.mark.asyncio
async def test_list_release_assets_reports_error_when_size_is_null():
    # Preserved quirk: null size crashes the size formatter (tracked in #273).
    result, _ = await _assets([ok([{"name": "a", "size": None}])])
    assert result == (
        "❌ Error listing assets: '<' not supported between instances of "
        "'NoneType' and 'int'"
    )
