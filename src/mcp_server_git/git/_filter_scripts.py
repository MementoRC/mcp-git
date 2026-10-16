"""Shell filter strings and argv for ``git filter-branch`` (issue #283).

filter-branch runs its filters through ``sh``, so every user-supplied value
embedded here goes through ``shlex.quote``. Python itself never uses a shell:
the argv is passed to git directly. Pathspecs are literal because the run
sets ``GIT_LITERAL_PATHSPECS=1``.
"""

import shlex

__all__ = ["commit_filter", "filter_branch_args", "index_filter"]

# Mirrors filter-branch's git_commit_non_empty_tree, which cannot take -S:
# a single-parent commit whose tree equals its parent's maps to that parent,
# a root commit with the empty tree is dropped, anything else is committed.
_PRUNING_COMMIT = (
    'if test $# = 3 && test "$1" = "$(git rev-parse "$3^{{tree}}")"; '
    'then map "$3"; '
    'elif test $# = 1 && test "$1" = "$EMPTY_TREE"; then :; '
    'else git commit-tree {sign} "$@"; fi'
)


def _quoted(paths: list[str]) -> str:
    return " ".join(shlex.quote(path) for path in paths)


def index_filter(paths: list[str], invert: bool) -> str:
    """Index filter removing *paths*, or (invert) everything outside them.

    Invert rebuilds the index from scratch with only the commit's entries
    under *paths*, so nothing outside them can survive.
    """
    if invert:
        return (
            'git read-tree --empty && git ls-tree -r -z "$GIT_COMMIT" -- '
            f"{_quoted(paths)} | git update-index -z --index-info"
        )
    return f"git rm -r --cached --ignore-unmatch --quiet -- {_quoted(paths)}"


def commit_filter(key: str, prune_empty: bool) -> str:
    """Commit filter signing every rewritten commit with *key*."""
    sign = shlex.quote(f"-S{key}")
    if prune_empty:
        return _PRUNING_COMMIT.format(sign=sign)
    return f'git commit-tree {sign} "$@"'


def filter_branch_args(
    paths: list[str],
    invert: bool,
    prune_empty: bool,
    sign_key: str | None,
    revs: list[str],
    tempdir: str,
) -> list[str]:
    """Full ``git filter-branch`` argv (after the subcommand name)."""
    args = ["-d", tempdir, "--index-filter", index_filter(paths, invert)]
    if sign_key:
        # --prune-empty cannot be combined with --commit-filter; the signing
        # filter prunes by itself when asked to.
        args += ["--commit-filter", commit_filter(sign_key, prune_empty)]
    elif prune_empty:
        args.append("--prune-empty")
    if "--tags" in revs:
        args += ["--tag-name-filter", "cat"]
    return [*args, "--", *revs]
