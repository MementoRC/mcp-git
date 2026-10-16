"""git_bundle_create / git_bundle_verify against real repositories (issue #283)."""

from pathlib import Path

from mcp_server_git.git._bundle_ops import git_bundle_create, git_bundle_verify
from mcp_server_git.utils.tool_failure import ToolFailure


def test_git_bundle_create_returns_success_when_repo_has_commits(real_repo, tmp_path):
    out = tmp_path / "backup.bundle"

    result = git_bundle_create(real_repo, str(out))

    assert result.startswith("✅")
    assert not isinstance(result, ToolFailure)
    assert out.stat().st_size > 0


def test_git_bundle_create_refuses_overwrite_when_output_exists(real_repo, tmp_path):
    out = tmp_path / "backup.bundle"
    out.write_text("precious")

    result = git_bundle_create(real_repo, str(out))

    assert isinstance(result, ToolFailure)
    assert "overwrite" in result
    assert out.read_text() == "precious"


def test_git_bundle_create_replaces_file_when_overwrite_true(real_repo, tmp_path):
    out = tmp_path / "backup.bundle"
    out.write_text("old")

    result = git_bundle_create(real_repo, str(out), overwrite=True)

    assert result.startswith("✅")
    assert out.read_bytes().startswith(b"# v")


def test_git_bundle_create_bundles_only_named_refs_when_refs_given(real_repo, tmp_path):
    real_repo.create_head("side")
    out = tmp_path / "main-only.bundle"

    result = git_bundle_create(real_repo, str(out), refs=["main"])

    assert result.startswith("✅")
    assert "refs/heads/main" in out.read_bytes().decode("latin-1")
    assert "refs/heads/side" not in out.read_bytes().decode("latin-1")


def test_git_bundle_create_fails_when_ref_has_dangerous_characters(real_repo, tmp_path):
    result = git_bundle_create(real_repo, str(tmp_path / "x.bundle"), refs=["a;rm"])

    assert isinstance(result, ToolFailure)
    assert not (tmp_path / "x.bundle").exists()


def test_git_bundle_create_fails_when_ref_is_unknown_option(real_repo, tmp_path):
    result = git_bundle_create(
        real_repo, str(tmp_path / "x.bundle"), refs=["--output=/etc/x"]
    )

    assert isinstance(result, ToolFailure)


def test_git_bundle_create_fails_when_output_directory_missing(real_repo, tmp_path):
    result = git_bundle_create(real_repo, str(tmp_path / "nope" / "x.bundle"))

    assert isinstance(result, ToolFailure)
    assert "does not exist" in result


def test_git_bundle_create_fails_when_ref_unknown_to_git(real_repo, tmp_path):
    result = git_bundle_create(real_repo, str(tmp_path / "x.bundle"), refs=["nope"])

    assert isinstance(result, ToolFailure)
    assert result.startswith("❌ Bundle create failed")


def test_git_bundle_verify_returns_success_when_bundle_valid(real_repo, tmp_path):
    out = tmp_path / "backup.bundle"
    git_bundle_create(real_repo, str(out))

    result = git_bundle_verify(real_repo, str(out))

    assert result.startswith("✅")
    assert not isinstance(result, ToolFailure)


def test_git_bundle_verify_fails_when_file_missing(real_repo, tmp_path):
    result = git_bundle_verify(real_repo, str(tmp_path / "absent.bundle"))

    assert isinstance(result, ToolFailure)
    assert "not found" in result


def test_git_bundle_verify_fails_when_file_is_not_a_bundle(real_repo, tmp_path):
    bogus = Path(tmp_path / "bogus.bundle")
    bogus.write_text("not a bundle")

    result = git_bundle_verify(real_repo, str(bogus))

    assert isinstance(result, ToolFailure)
    assert result.startswith("❌ Bundle verify failed")
