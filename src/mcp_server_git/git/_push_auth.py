"""One authentication mechanism for every GitHub HTTPS push path (issue #303).

When a remote's push URL is ``https://github.com/...`` and a server token
resolves, git runs with ``-c credential.helper=`` (clearing inherited helpers,
including a stale global one) followed by a helper that reads the token from
``MCP_GIT_PUSH_TOKEN``. The token is only placed in that one subprocess's
environment: never in argv, ``.git/config``, logs or output.
"""

from dataclasses import dataclass, field
from urllib.parse import urlsplit

from ..utils.git_import import Repo
from ._github_token import resolve_github_token

__all__ = [
    "CREDENTIAL_OVERRIDES",
    "TOKEN_ENV_VAR",
    "TOKEN_HELPER",
    "PushAuth",
    "configured_push_url",
    "is_github_https",
    "resolve_push_auth",
    "run_push",
]

TOKEN_ENV_VAR = "MCP_GIT_PUSH_TOKEN"
HELPER_RESET = "credential.helper="
TOKEN_HELPER = (
    "credential.helper=!f() { echo username=x-access-token; "
    'echo "password=$' + TOKEN_ENV_VAR + '"; }; f'
)
CREDENTIAL_OVERRIDES = (HELPER_RESET, TOKEN_HELPER)

_SOURCE_LABELS = {
    ".env": "repo .env GITHUB_TOKEN",
    "env": "GITHUB_TOKEN environment variable",
    "gh": "GitHub CLI gh auth token",
}


@dataclass(frozen=True)
class PushAuth:
    """A resolved server token and where it came from (.env, env or gh)."""

    token: str = field(repr=False)
    source: str

    def env(self) -> dict[str, str]:
        """Extra environment for the single authenticated git call."""
        return {TOKEN_ENV_VAR: self.token, "GIT_TERMINAL_PROMPT": "0"}

    def success_note(self) -> str:
        return f"\n🔐 Used server GitHub token ({_SOURCE_LABELS[self.source]})"


def configured_push_url(repo: Repo, remote: str) -> str:
    """Return the remote's push URL: ``pushurl`` over ``url``.

    Read from config (not ``git remote get-url --push``) so the decision
    follows the configured URL rather than an ``insteadOf`` rewrite. When
    ``remote`` is not a configured remote but is itself a URL, it is returned.
    """
    try:
        remote_obj = repo.remote(remote)
    except ValueError:
        return remote if "://" in remote else ""
    url = getattr(remote_obj, "pushurl", None)
    if not isinstance(url, str):
        url = getattr(remote_obj, "url", None)
    return url if isinstance(url, str) else ""


def is_github_https(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme == "https" and parts.hostname == "github.com"


def resolve_push_auth(repo: Repo, url: str) -> PushAuth | None:
    """Token auth for a GitHub HTTPS push URL, else None (system git as-is)."""
    if not is_github_https(url):
        return None
    resolved = resolve_github_token(repo)
    return PushAuth(*resolved) if resolved else None


def run_push(repo: Repo, args: list[str], auth: PushAuth | None) -> None:
    """Run ``git push`` through GitPython, with the per-call helper when authed."""
    if auth is None:
        repo.git.push(*args)
        return
    repo.git(c=list(CREDENTIAL_OVERRIDES)).push(*args, env=auth.env())
