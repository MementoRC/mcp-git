"""GPG signing-key resolution shared by commit and tag operations.

Extracted from ``_commit_ops.py``'s ``git_commit`` (issue #228) so
``_tag_ops.py`` can resolve a signing key with identical precedence without
duplicating the logic.
"""

import os

from ..utils.git_import import Repo


def resolve_gpg_key(
    repo: Repo, gpg_key_id: str | None
) -> tuple[str | None, str | None]:
    """Resolve the GPG signing key to use.

    Precedence: explicit ``gpg_key_id`` -> ``GPG_SIGNING_KEY`` env var ->
    repo's ``user.signingkey`` git config.

    Returns:
        (key_id, error) — exactly one of the two is non-None.
    """
    if gpg_key_id:
        return gpg_key_id, None

    env_key = os.getenv("GPG_SIGNING_KEY")
    if env_key:
        return env_key, None

    try:
        config_key = repo.config_reader().get_value("user", "signingkey")
        return str(config_key), None
    except Exception:
        return (
            None,
            "❌ Could not determine GPG signing key. Please configure GPG_SIGNING_KEY env var",
        )
