"""Transactional publication and verification for comparison evidence bundles."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .protocol import sha256_path

MANIFEST_NAME = "semantic_model_comparison_manifest.json"
MANIFEST_DIGEST_NAME = "semantic_model_comparison_manifest.sha256"
_CONTROL_FILES = frozenset({MANIFEST_NAME, MANIFEST_DIGEST_NAME})


class SemanticBundleEntry(BaseModel):
    """One content-addressed file in a completed comparison bundle."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    relative_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=0)


class SemanticBundleManifest(BaseModel):
    """Complete inventory written before a staged bundle is promoted."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_semantic_bundle.v2"]
    status: Literal["complete"]
    generated_at: datetime
    protocol_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    entries: tuple[SemanticBundleEntry, ...]


class SemanticBundleFailureReceipt(BaseModel):
    """Non-evidence receipt proving that a comparison did not publish."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_semantic_bundle_failure.v1"]
    status: Literal["failed"]
    failed_at: datetime
    error_type: str = Field(min_length=1)
    published_bundle: Literal[False]


def prepare_staging_directory(output_dir: Path) -> Path:
    """Create a private sibling directory for an all-or-nothing publication."""

    if output_dir.exists():
        raise ValueError("comparison output directory must not already exist")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    failure_path(output_dir).unlink(missing_ok=True)
    staging = output_dir.with_name(f".{output_dir.name}.{uuid4().hex}.staging")
    staging.mkdir(parents=False, exist_ok=False)
    return staging


def write_bundle_manifest(
    *,
    staging_dir: Path,
    protocol_sha256: str,
    generated_at: datetime,
) -> SemanticBundleManifest:
    """Inventory every staged artifact and write the final in-bundle manifest."""

    entries = tuple(
        SemanticBundleEntry(
            relative_path=path.relative_to(staging_dir).as_posix(),
            sha256=sha256_path(path),
            size_bytes=path.stat().st_size,
        )
        for path in sorted(staging_dir.rglob("*"))
        if path.is_file() and path.name not in _CONTROL_FILES
    )
    if not entries:
        raise ValueError("comparison bundle cannot be empty")
    manifest = SemanticBundleManifest(
        schema_version="evidence_selection_semantic_bundle.v2",
        status="complete",
        generated_at=generated_at,
        protocol_sha256=protocol_sha256,
        entries=entries,
    )
    _write_json(staging_dir / MANIFEST_NAME, manifest.model_dump(mode="json"))
    return manifest


def verify_bundle(directory: Path) -> SemanticBundleManifest:
    """Fail if a completed bundle has missing, extra, or modified artifacts."""

    manifest_path = directory / MANIFEST_NAME
    manifest = SemanticBundleManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8"),
    )
    actual_paths = {
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file() and path.name not in _CONTROL_FILES
    }
    declared_paths = {entry.relative_path for entry in manifest.entries}
    if len(declared_paths) != len(manifest.entries) or actual_paths != declared_paths:
        raise ValueError("comparison bundle file inventory does not match its manifest")
    for entry in manifest.entries:
        path = _resolved_bundle_path(directory=directory, relative=entry.relative_path)
        if path.stat().st_size != entry.size_bytes or sha256_path(path) != entry.sha256:
            raise ValueError(
                f"comparison bundle artifact digest mismatch: {entry.relative_path}",
            )
    return manifest


def promote_bundle(*, staging_dir: Path, output_dir: Path) -> str:
    """Publish one complete evidence generation with a single atomic rename."""

    verify_bundle(staging_dir)
    manifest_digest = sha256_path(staging_dir / MANIFEST_NAME)
    digest_path(staging_dir).write_text(f"{manifest_digest}\n", encoding="ascii")
    verify_published_bundle(staging_dir)
    staging_dir.replace(output_dir)
    return manifest_digest


def verify_published_bundle(directory: Path) -> SemanticBundleManifest:
    """Verify both the bundle inventory and its in-generation integrity anchor."""

    manifest = verify_bundle(directory)
    expected_digest = digest_path(directory).read_text(encoding="ascii").strip()
    if expected_digest != sha256_path(directory / MANIFEST_NAME):
        raise ValueError("comparison bundle manifest digest does not match its anchor")
    return manifest


def discard_staging(staging_dir: Path) -> None:
    """Remove an unpublished staging directory after any execution failure."""

    shutil.rmtree(staging_dir, ignore_errors=True)


def write_failure_receipt(*, output_dir: Path, error: BaseException) -> Path:
    """Write a non-resumable failure marker without publishing partial evidence."""

    receipt = SemanticBundleFailureReceipt(
        schema_version="evidence_selection_semantic_bundle_failure.v1",
        status="failed",
        failed_at=datetime.now(UTC),
        error_type=type(error).__name__,
        published_bundle=False,
    )
    path = failure_path(output_dir)
    _write_json(path, receipt.model_dump(mode="json"))
    return path


def failure_path(output_dir: Path) -> Path:
    return output_dir.with_name(f"{output_dir.name}.failed.json")


def digest_path(output_dir: Path) -> Path:
    return output_dir / MANIFEST_DIGEST_NAME


def _resolved_bundle_path(*, directory: Path, relative: str) -> Path:
    path = (directory / relative).resolve()
    if not path.is_relative_to(directory.resolve()):
        raise ValueError("comparison bundle manifest path escapes its directory")
    return path


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


__all__ = [
    "MANIFEST_NAME",
    "MANIFEST_DIGEST_NAME",
    "SemanticBundleManifest",
    "digest_path",
    "discard_staging",
    "failure_path",
    "prepare_staging_directory",
    "promote_bundle",
    "verify_bundle",
    "verify_published_bundle",
    "write_bundle_manifest",
    "write_failure_receipt",
]
