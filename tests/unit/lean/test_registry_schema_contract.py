"""Enumerating contract guard: every registered tool's schema must advertise
every parameter its implementation actually accepts (issue #244).

Hand-written ``schema={...}`` dicts can silently drift from the handler's
real signature and under-report what the tool accepts. This test builds its
tool list from the live ``GitLeanInterface.tool_registry`` (the same source
``tests/lean/test_integration.py`` iterates) rather than a hardcoded name
list, so a tool registered tomorrow is covered automatically with no edit
to this file.
"""

import inspect
from unittest.mock import Mock

import pytest

from mcp_server_git.lean.interface import GitLeanInterface

_INTERFACE = GitLeanInterface(
    git_service=Mock(), github_service=Mock(), azure_service=Mock()
)

_VARIADIC_KINDS = (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)


def _closure_op_func(func):
    """If *func* is a ``wrap_repo_op(...)`` closure -- signature
    ``(repo_path, **kwargs)`` with the real work delegated to a captured
    ``op_func`` -- return that captured ``op_func`` and its ``param_map``
    (or ``None`` for both if *func* is not such a closure)."""
    code = getattr(func, "__code__", None)
    if code is None or "op_func" not in code.co_freevars:
        return None, None
    cells = dict(zip(code.co_freevars, func.__closure__, strict=True))
    op_func = cells["op_func"].cell_contents
    param_map = cells["param_map"].cell_contents if "param_map" in cells else None
    return op_func, param_map


def _unwrap_repo_op_closure(func) -> set[str] | None:
    """If *func* is a ``wrap_repo_op(...)`` closure, return the publicly-
    accepted parameter names of the captured ``op_func`` it delegates to.

    ``wrap_repo_op``'s wrapper always exposes ``repo_path`` (translated from
    the underlying ``repo`` positional) plus whatever ``op_func`` accepts,
    with ``param_map`` renaming internal names back to their public schema
    names (e.g. ``format_str`` -> ``format`` for ``git_log``, the exact
    mismatch ``tests/unit/lean/test_registry_git_param_map.py`` guards).

    Returns None if *func* is not such a closure (no ``op_func`` freevar),
    signalling the caller should fall back to a plain signature read.
    """
    op_func, param_map = _closure_op_func(func)
    if op_func is None:
        return None

    reverse_map = {internal: public for public, internal in (param_map or {}).items()}

    names = {"repo_path"}
    for param in inspect.signature(op_func).parameters.values():
        if param.name in ("self", "repo") or param.kind in _VARIADIC_KINDS:
            continue
        names.add(reverse_map.get(param.name, param.name))
    return names


def _accepted_param_names(tool_def) -> set[str]:
    """Public parameter names the tool's implementation actually accepts."""
    # register_tool wraps implementation with @functools.wraps(...), so
    # __wrapped__ recovers the pre-token-limiter callable actually
    # registered by the domain registry (either a wrap_repo_op closure or
    # the raw git/github/azure handler).
    base = getattr(tool_def.implementation, "__wrapped__", tool_def.implementation)

    unwrapped = _unwrap_repo_op_closure(base)
    if unwrapped is not None:
        return unwrapped

    names = set()
    for param in inspect.signature(base).parameters.values():
        if param.name == "self" or param.kind in _VARIADIC_KINDS:
            continue
        names.add(param.name)
    return names


def _accepts_var_keyword(tool_def) -> bool:
    """True if the (unwrapped) implementation has a ``**kwargs`` catch-all.

    For a ``wrap_repo_op`` closure the wrapper itself is always
    ``(repo_path, **kwargs)``, so that outer signature is never informative
    here -- it is the captured ``op_func``'s own signature that decides
    whether an extra advertised parameter would actually be absorbed.
    """
    base = getattr(tool_def.implementation, "__wrapped__", tool_def.implementation)
    op_func, _ = _closure_op_func(base)
    if op_func is not None:
        base = op_func
    return any(
        param.kind is inspect.Parameter.VAR_KEYWORD
        for param in inspect.signature(base).parameters.values()
    )


_TOOL_NAMES = sorted(_INTERFACE.tool_registry)

# Parameters deliberately NOT advertised: deprecated back-compat aliases the
# handler still accepts from old callers (see the "Deprecated back-compat
# alias" comments at their definitions) but that new callers are meant to
# reach via the modern parameter instead (branch_type / commit_ish). This is
# an intentional discovery omission, not the under-reporting bug issue #244
# targets, so it is exempted by name rather than papered over by widening
# the assertion.
_LEGACY_ALIAS_EXEMPTIONS: dict[str, set[str]] = {
    "git_branch_list": {"remote", "all"},
    "git_tag_create": {"commit"},
}


@pytest.mark.parametrize("tool_name", _TOOL_NAMES, ids=_TOOL_NAMES)
def test_schema_properties_cover_implementation_parameters(tool_name):
    """The schema advertised for *tool_name* must not hide a parameter its
    implementation accepts -- the exact under-reporting bug issue #244
    fixes for the hand-written schemas and guards against for the rest."""
    tool_def = _INTERFACE.tool_registry[tool_name]
    accepted = _accepted_param_names(tool_def)
    schema_properties = set(tool_def.schema.get("properties", {}))
    exempt = _LEGACY_ALIAS_EXEMPTIONS.get(tool_name, set())

    missing = accepted - schema_properties - exempt
    assert not missing, (
        f"{tool_name}: implementation accepts {sorted(missing)} but the "
        f"schema properties do not advertise them (advertised: "
        f"{sorted(schema_properties)})"
    )


# Parameters a schema advertises but the handler genuinely cannot accept,
# kept for a documented reason rather than fixed. Empty by default: an
# over-advertised parameter is a real bug (see issue #238 below) and should
# be fixed at the source, not exempted here. Any entry must be per-tool
# per-parameter and carry a comment saying why the mismatch is intentional.
_OVER_ADVERTISED_EXEMPTIONS: dict[str, set[str]] = {}


@pytest.mark.parametrize("tool_name", _TOOL_NAMES, ids=_TOOL_NAMES)
def test_implementation_accepts_every_schema_property(tool_name):
    """The schema advertised for *tool_name* must not promise a parameter
    its implementation cannot accept.

    This is the opposite direction from
    ``test_schema_properties_cover_implementation_parameters`` and matters
    independently: a caller who follows ``get_tool_spec`` and passes an
    advertised-but-unaccepted parameter hits ``implementation(**parameters)``
    in dispatch, which raises ``TypeError`` -- exactly issue #238, where
    ``github_update_pr()`` was advertised to accept ``draft`` but its
    signature did not have that parameter and calling it that way blew up
    with "got an unexpected keyword argument 'draft'".

    Skipped when the implementation has a ``**kwargs`` catch-all: any
    advertised name is silently absorbed there, so the check is vacuous.
    """
    tool_def = _INTERFACE.tool_registry[tool_name]
    if _accepts_var_keyword(tool_def):
        pytest.skip(
            f"{tool_name}: implementation accepts **kwargs, any name is absorbed"
        )

    accepted = _accepted_param_names(tool_def)
    schema_properties = set(tool_def.schema.get("properties", {}))
    exempt = _OVER_ADVERTISED_EXEMPTIONS.get(tool_name, set())

    extra = schema_properties - accepted - exempt
    assert not extra, (
        f"{tool_name}: schema advertises {sorted(extra)} but the "
        f"implementation does not accept them (accepted: {sorted(accepted)})"
    )
