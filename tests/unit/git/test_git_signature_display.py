"""Signature display (#321 item 3): git_log/git_show show_signature, git_verify_commit.

Real temporary repos (no mocked Repo). The unsigned path runs for real; the
signed path generates a throwaway key in a temp GNUPGHOME and skips when gpg
is unavailable. The status decoder is also checked on canned ``%G?`` codes.
"""

import shutil
import subprocess

import pytest

from mcp_server_git.git._signature_ops import (
    SIGNATURE_STATUS_WORDS,
    format_verification,
    git_verify_commit,
)
from mcp_server_git.git.operations import git_log, git_show

pytest.importorskip("git")
from git import Repo  # noqa: E402


@pytest.fixture
def repo(tmp_path) -> Repo:
    path = tmp_path / "repo"
    path.mkdir()
    r = Repo.init(path)
    (path / "a.txt").write_text("v1\n")
    r.index.add(["a.txt"])
    r.index.commit("initial")
    return r


@pytest.fixture
def signed_repo(tmp_path, monkeypatch) -> tuple[Repo, str]:
    if shutil.which("gpg") is None:
        pytest.skip("gpg not installed")
    home = tmp_path / "gnupg"
    home.mkdir(mode=0o700)
    monkeypatch.setenv("GNUPGHOME", str(home))
    keygen = subprocess.run(
        ["gpg", "--batch", "--passphrase", "", "--quick-generate-key",
         "Signer <signer@example.com>", "default", "default", "never"],
        capture_output=True,
        text=True,
    )  # fmt: skip
    if keygen.returncode != 0:
        pytest.skip(f"gpg key generation unavailable: {keygen.stderr[:100]}")
    listing = subprocess.run(
        ["gpg", "--list-secret-keys", "--with-colons"], capture_output=True, text=True
    ).stdout
    key_id = next(x.split(":")[4] for x in listing.splitlines() if x.startswith("sec"))
    path = tmp_path / "srepo"
    path.mkdir()
    r = Repo.init(path)
    (path / "a.txt").write_text("v1\n")
    r.index.add(["a.txt"])
    try:
        r.git.commit(f"--gpg-sign={key_id}", "-m", "signed")
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"gpg signing unavailable: {e}")
    return r, key_id


def test_git_log_returns_status_n_and_subject_when_show_signature_and_oneline_on_unsigned(
    repo: Repo,
):
    out = git_log(repo, oneline=True, show_signature=True, max_count=1)

    fields = out.split()
    assert fields[1] == "N"
    assert out.endswith("initial")


def test_git_log_returns_status_n_when_show_signature_without_oneline_on_unsigned(
    repo: Repo,
):
    out = git_log(repo, show_signature=True, max_count=1)

    assert out.split()[1] == "N"


def test_git_show_returns_commit_when_show_signature_true_on_unsigned(repo: Repo):
    out = git_show(repo, "HEAD", show_signature=True)

    assert "initial" in out
    assert "a.txt" in out


def test_git_verify_commit_returns_not_signed_when_commit_unsigned(repo: Repo):
    out = git_verify_commit(repo)

    assert "Not signed" in out
    assert "❌" not in out


def test_git_verify_commit_returns_failure_when_commit_unknown(repo: Repo):
    out = git_verify_commit(repo, "no-such-ref")

    assert "Verify failed" in out


def test_git_verify_commit_returns_failure_when_commit_looks_like_option(repo: Repo):
    assert "Invalid commit" in git_verify_commit(repo, "--all")


@pytest.mark.parametrize("code", sorted(SIGNATURE_STATUS_WORDS))
def test_format_verification_decodes_status_when_code_given(code: str):
    out = format_verification(code, "ABCD1234", "Alice")

    if code == "N":
        assert "Not signed" in out
    else:
        assert f"{code} ({SIGNATURE_STATUS_WORDS[code]})" in out
        assert "Key: ABCD1234" in out
        assert "Signer: Alice" in out


def test_format_verification_reports_unknown_when_code_unrecognised():
    assert "unknown status" in format_verification("Z", "", "")


def test_git_verify_commit_returns_key_and_signer_when_commit_signed(signed_repo):
    repo, key_id = signed_repo

    out = git_verify_commit(repo)

    assert "Signature status:" in out
    assert key_id[-16:] in out
    assert "Signer <signer@example.com>" in out


def test_git_log_returns_key_and_signer_when_oneline_show_signature_on_signed(
    signed_repo,
):
    repo, key_id = signed_repo

    out = git_log(repo, oneline=True, show_signature=True, max_count=1)

    assert key_id[-16:] in out
    assert "Signer <signer@example.com>" in out
    assert out.endswith("signed")


def test_git_show_returns_gpg_output_when_show_signature_on_signed(signed_repo):
    repo, _ = signed_repo

    out = git_show(repo, "HEAD", show_signature=True)

    assert "gpg:" in out
