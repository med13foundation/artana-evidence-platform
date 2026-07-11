"""Filesystem identity checks for evidence-selection artifact writers."""

from __future__ import annotations

from pathlib import Path


def paths_alias(left: Path, right: Path) -> bool:
    """Return whether two paths resolve to the same target or existing file."""

    if left.resolve(strict=False) == right.resolve(strict=False):
        return True
    if not left.exists() or not right.exists():
        return False
    try:
        return left.samefile(right)
    except OSError:
        return False


def paths_nested(left: Path, right: Path) -> bool:
    """Return whether either resolved path is an ancestor of the other."""

    resolved_left = left.resolve(strict=False)
    resolved_right = right.resolve(strict=False)
    return (
        resolved_left in resolved_right.parents
        or resolved_right in resolved_left.parents
    )


__all__ = ["paths_alias", "paths_nested"]
