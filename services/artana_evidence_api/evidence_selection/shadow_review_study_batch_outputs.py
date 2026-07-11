"""Transactional filesystem helpers for shadow-review study batches."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path


def prepare_batch_output_dir(output_dir: Path) -> bool:
    """Ensure the batch root exists and report whether this call created it."""

    output_dir_existed = output_dir.exists()
    if output_dir_existed and not output_dir.is_dir():
        msg = f"Output directory must be a directory: {output_dir}"
        raise ValueError(msg)
    output_dir.mkdir(parents=True, exist_ok=True)
    return not output_dir_existed


def rollback_published_batch_outputs(
    *,
    entry_output_dirs: Sequence[Path],
    batch_output_dir: Path,
    remove_empty_batch_output_dir: bool,
) -> None:
    """Remove only entry artifacts published by the failed batch invocation."""

    for entry_output_dir in reversed(entry_output_dirs):
        _remove_output_directory(entry_output_dir)
    if remove_empty_batch_output_dir:
        _remove_empty_output_directory_tree(batch_output_dir)


def _remove_output_directory(output_dir: Path) -> None:
    if output_dir.is_symlink():
        output_dir.unlink()
        return
    for path in sorted(output_dir.rglob("*"), reverse=True):
        if path.is_file() or path.is_symlink():
            path.unlink()
        elif path.is_dir():
            path.rmdir()
    output_dir.rmdir()


def _remove_empty_output_directory_tree(output_dir: Path) -> None:
    for path in sorted(output_dir.rglob("*"), reverse=True):
        if path.is_dir() and not path.is_symlink():
            path.rmdir()
    output_dir.rmdir()
