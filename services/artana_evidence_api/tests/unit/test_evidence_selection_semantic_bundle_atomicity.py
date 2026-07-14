"""Atomic publication regressions for semantic evidence bundles."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from artana_evidence_api.evidence_selection.repeatability.bundle import (
    digest_path,
    prepare_staging_directory,
    promote_bundle,
    verify_published_bundle,
    write_bundle_manifest,
)


def test_bundle_generation_is_published_with_one_directory_rename(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "comparison"
    staging = _staged_bundle(output)
    original_replace = Path.replace
    replacements: list[tuple[Path, Path]] = []

    def recording_replace(source: Path, target: Path) -> Path:
        assert digest_path(source).is_file()
        replacements.append((source, target))
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", recording_replace)

    promote_bundle(staging_dir=staging, output_dir=output)

    assert replacements == [(staging, output)]
    assert digest_path(output).is_file()
    verify_published_bundle(output)


def test_failed_directory_rename_never_exposes_partial_generation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "comparison"
    staging = _staged_bundle(output)

    def interrupted_replace(_source: Path, _target: Path) -> Path:
        raise OSError("synthetic rename interruption")

    monkeypatch.setattr(Path, "replace", interrupted_replace)

    with pytest.raises(OSError, match="rename interruption"):
        promote_bundle(staging_dir=staging, output_dir=output)

    assert not output.exists()
    assert digest_path(staging).is_file()
    verify_published_bundle(staging)


def _staged_bundle(output: Path) -> Path:
    staging = prepare_staging_directory(output)
    (staging / "artifact.txt").write_text("complete\n", encoding="ascii")
    write_bundle_manifest(
        staging_dir=staging,
        protocol_sha256="a" * 64,
        generated_at=datetime(2026, 7, 13, tzinfo=UTC),
    )
    return staging
