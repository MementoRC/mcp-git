"""Shared ref/pattern validation for git operations.

Extracted from ``operations_extended.py`` (issue #228) once ``_tag_ops.py``
needed the same dangerous-character guard, mirroring the precedent set by
``error_text.py`` (#219) and ``text_limits.py`` (#213).
"""

import re

DANGEROUS_CHARS = re.compile(r"[;&|`$()]")


def validate_ref(ref: str, param_name: str) -> str | None:
    """Validate a git ref for dangerous characters. Returns error string or None."""
    if DANGEROUS_CHARS.search(ref):
        return f"❌ Invalid characters detected in {param_name}: '{ref}'"
    return None
