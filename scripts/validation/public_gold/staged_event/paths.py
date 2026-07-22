"""Repository path discovery for staged-event command-line entrypoints."""

from __future__ import annotations

from pathlib import Path


def repository_root() -> Path:
    """Find the repository root from this installed source file, not the shell cwd."""

    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file() and (
            candidate / "scripts" / "validation"
        ).is_dir():
            return candidate
    raise RuntimeError("Artana repository root could not be located")


__all__ = ["repository_root"]
