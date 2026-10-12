"""Characterization tests pinning validate_git_security_config and
enforce_secure_git_config (issue #255 phase 2b).

Real temporary repositories are used; global/system git config is isolated.
The gpg / git-log subprocess calls are replaced via a stand-in subprocess
namespace on the module where a branch cannot be reached otherwise.
"""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from mcp_server_git.git import security
from mcp_server_git.git.security import (
    enforce_secure_git_config,
    validate_git_security_config,
)

pytest.importorskip("git")
from git import Repo  # noqa: E402

W_KEY = "No GPG signing key configured (user.signingkey)"
R_KEY = "Set up GPG signing: git config user.signingkey <key-id>"
W_SIGN = "GPG signing not enabled by default (commit.gpgsign)"
R_SIGN = "Enable GPG signing: git config commit.gpgsign true"
W_NAME = "No user name configured (user.name)"
R_NAME = "Set user name: git config user.name 'Your Name'"
W_EMAIL = "No user email configured (user.email)"
R_EMAIL = "Set user email: git config user.email 'your.email@example.com'"
W_UNSIGNED = "Latest commit is not properly signed"
R_UNSIGNED = "Ensure all commits are GPG signed"

FULL = [
    ("user", "signingkey", "KEY1"),
    ("commit", "gpgsign", "true"),
    ("user", "name", "T"),
    ("user", "email", "t@example.com"),
]


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path_factory):
    # GitPython resolves the global config via ~ rather than GIT_CONFIG_GLOBAL.
    fake_home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(fake_home / ".config"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for var in (
        "GIT_AUTHOR_NAME",
        "GIT_COMMITTER_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_EMAIL",
        "GPG_SIGNING_KEY",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def repo(tmp_path):
    return Repo.init(tmp_path)


def _configure(repo, entries):
    with repo.config_writer() as cw:
        for section, key, value in entries:
            cw.set_value(section, key, value)


def _read(repo, section, key):
    return Repo(repo.working_dir).config_reader().get_value(section, key)


def _fake_run(monkeypatch, returncode=0, stdout="", raises=None):
    def run(*args, **kwargs):
        if raises is not None:
            raise raises
        return SimpleNamespace(returncode=returncode, stdout=stdout)

    monkeypatch.setattr(security, "subprocess", SimpleNamespace(run=run))


class _Boom:
    def __str__(self):
        raise RuntimeError("boom")

    def __bool__(self):
        raise RuntimeError("boom")


class _ValuesRepo:
    """Repo stand-in whose config reader serves fixed values."""

    working_dir = "."

    def __init__(self, values):
        self._values = values

    def config_reader(self):
        return self

    def get_value(self, section, key):
        return self._values[(section, key)]


class _WriterRepo:
    def __init__(self, real, writer):
        self._real = real
        self._writer = writer

    def config_reader(self):
        return self._real.config_reader()

    def config_writer(self):
        return self._writer


# --------------------------- validate_git_security_config ---------------------------


def test_validate_returns_insecure_with_all_warnings_when_repo_empty(repo):
    assert validate_git_security_config(repo) == {
        "status": "insecure",
        "warnings": [
            W_KEY,
            W_SIGN,
            W_NAME,
            W_EMAIL,
            "Could not verify commit signatures",
        ],
        "recommendations": [R_KEY, R_SIGN, R_NAME, R_EMAIL],
    }


def test_validate_returns_unsigned_warning_when_real_commit_unsigned(repo):
    _configure(repo, FULL)
    repo.git.commit("--allow-empty", "-m", "init", "--no-gpg-sign")
    assert validate_git_security_config(repo) == {
        "status": "warning",
        "warnings": [W_UNSIGNED],
        "recommendations": [R_UNSIGNED],
    }


@pytest.mark.parametrize("sig", ["G", "U"])
def test_validate_returns_secure_when_signature_good_or_untrusted(
    repo, monkeypatch, sig
):
    _configure(repo, FULL)
    _fake_run(monkeypatch, stdout=f" {sig}\n")
    assert validate_git_security_config(repo) == {
        "status": "secure",
        "warnings": [],
        "recommendations": [],
    }


def test_validate_returns_unsigned_warning_when_signature_status_other(
    repo, monkeypatch
):
    _configure(repo, FULL)
    _fake_run(monkeypatch, stdout="N")
    result = validate_git_security_config(repo)
    assert result["warnings"] == [W_UNSIGNED]
    assert result["recommendations"] == [R_UNSIGNED]


def test_validate_returns_verify_warning_when_git_log_fails(repo, monkeypatch):
    _configure(repo, FULL)
    _fake_run(monkeypatch, returncode=128)
    assert validate_git_security_config(repo) == {
        "status": "warning",
        "warnings": ["Could not verify commit signatures"],
        "recommendations": [],
    }


def test_validate_returns_check_warning_when_subprocess_raises(repo, monkeypatch):
    _configure(repo, FULL)
    _fake_run(monkeypatch, raises=OSError("nope"))
    assert validate_git_security_config(repo) == {
        "status": "warning",
        "warnings": ["Could not check commit signatures"],
        "recommendations": [],
    }


def test_validate_returns_warning_status_when_one_warning(repo, monkeypatch):
    _configure(repo, FULL[:2] + FULL[3:])
    _fake_run(monkeypatch, stdout="G")
    assert validate_git_security_config(repo) == {
        "status": "warning",
        "warnings": [W_NAME],
        "recommendations": [R_NAME],
    }


def test_validate_returns_warning_status_when_two_warnings(repo, monkeypatch):
    _configure(repo, FULL[:2])
    _fake_run(monkeypatch, stdout="G")
    assert validate_git_security_config(repo) == {
        "status": "warning",
        "warnings": [W_NAME, W_EMAIL],
        "recommendations": [R_NAME, R_EMAIL],
    }


def test_validate_returns_insecure_status_when_three_warnings(repo, monkeypatch):
    _configure(repo, FULL[3:])
    _fake_run(monkeypatch, stdout="G")
    assert validate_git_security_config(repo) == {
        "status": "insecure",
        "warnings": [W_KEY, W_SIGN, W_NAME],
        "recommendations": [R_KEY, R_SIGN, R_NAME],
    }


def test_validate_returns_insecure_status_when_gpgsign_not_true(repo, monkeypatch):
    _configure(repo, [("commit", "gpgsign", "false")])
    _fake_run(monkeypatch, stdout="G")
    result = validate_git_security_config(repo)
    assert result["status"] == "insecure"
    assert result["warnings"] == [W_KEY, W_SIGN, W_NAME, W_EMAIL]
    assert result["recommendations"] == [R_KEY, R_SIGN, R_NAME, R_EMAIL]


def test_validate_accepts_gpgsign_true_case_insensitively_when_upper_case(
    repo, monkeypatch
):
    _configure(repo, [("user", "signingkey", "K"), ("commit", "gpgsign", "TRUE")])
    _fake_run(monkeypatch, stdout="G")
    assert validate_git_security_config(repo)["warnings"] == [W_NAME, W_EMAIL]


def test_validate_returns_gpg_read_warning_when_gpgsign_unstringable(monkeypatch):
    _fake_run(monkeypatch, stdout="G")
    values = {
        ("user", "signingkey"): "K",
        ("commit", "gpgsign"): _Boom(),
        ("user", "name"): "N",
        ("user", "email"): "E",
    }
    assert validate_git_security_config(_ValuesRepo(values)) == {
        "status": "warning",
        "warnings": ["Could not read GPG configuration: boom"],
        "recommendations": [],
    }


def test_validate_returns_user_read_warning_when_user_name_unevaluable(monkeypatch):
    _fake_run(monkeypatch, stdout="G")
    values = {
        ("user", "signingkey"): "K",
        ("commit", "gpgsign"): "true",
        ("user", "name"): _Boom(),
        ("user", "email"): "E",
    }
    assert validate_git_security_config(_ValuesRepo(values)) == {
        "status": "warning",
        "warnings": ["Could not read user configuration: boom"],
        "recommendations": [],
    }


# ----------------------------- enforce_secure_git_config -----------------------------

STRICT_NAME = (
    "❌ No user name configured. Set GIT_AUTHOR_NAME env var or git config user.name"
)
STRICT_EMAIL = (
    "❌ No user email configured. Set GIT_AUTHOR_EMAIL env var or git config user.email"
)
SEC_LINE = "sec   rsa4096/ABCD1234 2023-01-01 [SC]\n"


def test_enforce_returns_optimal_when_already_configured(repo):
    _configure(repo, FULL)
    assert enforce_secure_git_config(repo) == (
        "✅ Git security configuration already optimal"
    )


def test_enforce_returns_name_error_when_strict_and_no_name(repo):
    _configure(repo, FULL[:2] + FULL[3:])
    assert enforce_secure_git_config(repo, strict_mode=True) == STRICT_NAME


def test_enforce_returns_email_error_when_strict_and_no_email(repo):
    _configure(repo, FULL[:3])
    assert enforce_secure_git_config(repo, strict_mode=True) == STRICT_EMAIL


def test_enforce_continues_when_non_strict_and_name_email_missing(repo):
    _configure(repo, FULL[:2])
    assert enforce_secure_git_config(repo, strict_mode=False) == (
        "✅ Git security configuration already optimal"
    )


@pytest.mark.parametrize("var", ["GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"])
def test_enforce_sets_name_from_env_when_name_missing(repo, monkeypatch, var):
    _configure(repo, FULL[:2] + FULL[3:])
    monkeypatch.setenv(var, "Env Name")
    assert enforce_secure_git_config(repo) == (
        "✅ Git security configuration enforced:\n"
        "  • Set user.name to 'Env Name' from environment\n"
        "🔒 Repository is now configured for secure commits"
    )
    assert _read(repo, "user", "name") == "Env Name"


@pytest.mark.parametrize("var", ["GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"])
def test_enforce_sets_email_from_env_when_email_missing(repo, monkeypatch, var):
    _configure(repo, FULL[:3])
    monkeypatch.setenv(var, "e@x.org")
    assert enforce_secure_git_config(repo) == (
        "✅ Git security configuration enforced:\n"
        "  • Set user.email to 'e@x.org' from environment\n"
        "🔒 Repository is now configured for secure commits"
    )
    assert _read(repo, "user", "email") == "e@x.org"


def test_enforce_prefers_author_env_when_both_name_vars_set(repo, monkeypatch):
    _configure(repo, FULL[:2] + FULL[3:])
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Author")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Committer")
    enforce_secure_git_config(repo)
    assert _read(repo, "user", "name") == "Author"


def test_enforce_enables_gpgsign_when_not_true(repo):
    _configure(repo, [FULL[0], ("commit", "gpgsign", "false"), FULL[2], FULL[3]])
    assert enforce_secure_git_config(repo) == (
        "✅ Git security configuration enforced:\n"
        "  • Enabled GPG signing for commits (commit.gpgsign=true)\n"
        "🔒 Repository is now configured for secure commits"
    )
    assert repo.git.config("--local", "commit.gpgsign") == "true"


def test_enforce_sets_signing_key_from_env_when_key_missing(repo, monkeypatch):
    _configure(repo, FULL[1:])
    monkeypatch.setenv("GPG_SIGNING_KEY", "ENVKEY")
    assert enforce_secure_git_config(repo) == (
        "✅ Git security configuration enforced:\n"
        "  • Set GPG signing key to 'ENVKEY' from environment\n"
        "🔒 Repository is now configured for secure commits"
    )
    assert _read(repo, "user", "signingkey") == "ENVKEY"


def test_enforce_autodetects_signing_key_when_gpg_lists_secret_key(repo, monkeypatch):
    _configure(repo, FULL[1:])
    _fake_run(monkeypatch, stdout="/home/x/.gnupg/pubring.kbx\n" + SEC_LINE)
    assert enforce_secure_git_config(repo) == (
        "✅ Git security configuration enforced:\n"
        "  • Auto-detected and set GPG signing key: ABCD1234\n"
        "🔒 Repository is now configured for secure commits"
    )
    assert _read(repo, "user", "signingkey") == "ABCD1234"


def test_enforce_returns_no_keys_found_when_strict_and_no_sec_line(repo, monkeypatch):
    _configure(repo, FULL[1:])
    _fake_run(monkeypatch, stdout="sec nokeyid\nxsec rsa/ABC\n")
    assert enforce_secure_git_config(repo) == (
        "❌ No GPG keys found. Generate a GPG key or set GPG_SIGNING_KEY env var"
    )


def test_enforce_continues_when_non_strict_and_no_sec_line(repo, monkeypatch):
    _configure(repo, FULL[1:])
    _fake_run(monkeypatch, stdout="sec nokeyid\n")
    assert enforce_secure_git_config(repo, strict_mode=False) == (
        "✅ Git security configuration already optimal"
    )


def test_enforce_returns_no_keys_available_when_strict_and_gpg_fails(repo, monkeypatch):
    _configure(repo, FULL[1:])
    _fake_run(monkeypatch, returncode=2, stdout=SEC_LINE)
    assert enforce_secure_git_config(repo) == (
        "❌ No GPG keys available. Install GPG and generate a key"
    )


def test_enforce_returns_no_keys_available_when_strict_and_no_sec_in_output(
    repo, monkeypatch
):
    _configure(repo, FULL[1:])
    _fake_run(monkeypatch, stdout="")
    assert enforce_secure_git_config(repo) == (
        "❌ No GPG keys available. Install GPG and generate a key"
    )


def test_enforce_continues_when_non_strict_and_gpg_fails(repo, monkeypatch):
    _configure(repo, FULL[1:])
    _fake_run(monkeypatch, returncode=2)
    assert enforce_secure_git_config(repo, strict_mode=False) == (
        "✅ Git security configuration already optimal"
    )


def test_enforce_returns_detect_error_when_strict_and_gpg_missing(repo, monkeypatch):
    _configure(repo, FULL[1:])
    _fake_run(monkeypatch, raises=FileNotFoundError("gpg gone"))
    assert enforce_secure_git_config(repo) == (
        "❌ Could not detect GPG keys: gpg gone. Set GPG_SIGNING_KEY env var"
    )


def test_enforce_continues_when_non_strict_and_gpg_missing(repo, monkeypatch):
    _configure(repo, FULL[1:])
    _fake_run(monkeypatch, raises=FileNotFoundError("gpg gone"))
    assert enforce_secure_git_config(repo, strict_mode=False) == (
        "✅ Git security configuration already optimal"
    )


def test_enforce_writes_keys_in_order_when_everything_missing(repo, monkeypatch):
    monkeypatch.setenv("GIT_AUTHOR_NAME", "N")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "e@x")
    monkeypatch.setenv("GPG_SIGNING_KEY", "K")
    writer = MagicMock()
    result = enforce_secure_git_config(_WriterRepo(repo, writer))
    assert [c.args for c in writer.set_value.call_args_list] == [
        ("user", "name", "N"),
        ("user", "email", "e@x"),
        ("commit", "gpgsign", "true"),
        ("user", "signingkey", "K"),
    ]
    assert [c[0] for c in writer.method_calls][-2:] == ["write", "release"]
    assert result == (
        "✅ Git security configuration enforced:\n"
        "  • Set user.name to 'N' from environment\n"
        "  • Set user.email to 'e@x' from environment\n"
        "  • Enabled GPG signing for commits (commit.gpgsign=true)\n"
        "  • Set GPG signing key to 'K' from environment\n"
        "🔒 Repository is now configured for secure commits"
    )


def test_enforce_does_not_write_when_strict_early_return(repo):
    _configure(repo, FULL[:2] + FULL[3:])
    writer = MagicMock()
    assert enforce_secure_git_config(_WriterRepo(repo, writer)) == STRICT_NAME
    writer.write.assert_not_called()


def test_enforce_returns_write_error_when_write_fails(repo):
    _configure(repo, FULL)
    writer = MagicMock()
    writer.write.side_effect = OSError("disk")
    assert enforce_secure_git_config(_WriterRepo(repo, writer)) == (
        "❌ Could not write git configuration: disk"
    )


def test_enforce_returns_failed_error_when_config_writer_raises():
    repo = MagicMock()
    repo.config_writer.side_effect = RuntimeError("locked")
    assert enforce_secure_git_config(repo) == "❌ Security enforcement failed: locked"
