"""Atomic custody persistence for one validated staged provider output."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic import BaseModel


class CustodyPersistenceError(RuntimeError):
    """A validated provider return could not be preserved and verified."""


@dataclass(frozen=True, slots=True)
class StageCustodyPaths:
    bundle: Path
    receipt: Path
    raw_output: Path


@dataclass(frozen=True, slots=True)
class StageCustodyRecord:
    stage: str
    response_id: str
    provider_input_sha256: str
    output_sha256: str
    schema_sha256: str
    bundle_sha256: str
    receipt_sha256: str
    raw_output_sha256: str


@dataclass(frozen=True, slots=True)
class StageCustodyInput:
    paths: StageCustodyPaths
    stage: str
    provider_input: str
    schema_sha256: str


def persist_stage_custody(
    *,
    custody_input: StageCustodyInput,
    output: BaseModel,
    canonical_payload: dict[str, object],
    receipt: dict[str, object],
) -> StageCustodyRecord:
    """Persist one self-contained bundle before derivative artifact views."""

    response_id = _response_id(receipt)
    output_sha256 = _canonical_sha256(canonical_payload)
    provider_input_sha256 = hashlib.sha256(
        custody_input.provider_input.encode()
    ).hexdigest()
    budgets = receipt.get("budgets")
    if not isinstance(budgets, dict):
        raise CustodyPersistenceError("verified receipt lacks budget accounting")
    bundle = {
        "stage": custody_input.stage,
        "response_id": response_id,
        "provider_input_sha256": provider_input_sha256,
        "output_sha256": output_sha256,
        "schema_sha256": custody_input.schema_sha256,
        "requested_and_observed_budgets": budgets,
        "receipt": receipt,
        "typed_output": canonical_payload,
    }
    bundle_sha256 = write_json_atomic(custody_input.paths.bundle, bundle)
    verified_bundle = _read_json_object(custody_input.paths.bundle)
    if _canonical_sha256(verified_bundle) != _canonical_sha256(bundle):
        raise CustodyPersistenceError("atomic custody bundle differs after readback")
    output_payload = output.model_dump(mode="json")
    if output_payload != canonical_payload:
        raise CustodyPersistenceError(
            "typed model serialization differs from canonical provider payload"
        )
    receipt_sha256 = write_json_atomic(custody_input.paths.receipt, receipt)
    raw_output_sha256 = write_json_atomic(
        custody_input.paths.raw_output, output_payload
    )
    if _canonical_sha256(_read_json_object(custody_input.paths.receipt)) != (
        _canonical_sha256(receipt)
    ):
        raise CustodyPersistenceError("receipt differs after readback")
    if _canonical_sha256(_read_json_object(custody_input.paths.raw_output)) != (
        _canonical_sha256(output_payload)
    ):
        raise CustodyPersistenceError("typed output differs after readback")
    return StageCustodyRecord(
        stage=custody_input.stage,
        response_id=response_id,
        provider_input_sha256=provider_input_sha256,
        output_sha256=output_sha256,
        schema_sha256=custody_input.schema_sha256,
        bundle_sha256=bundle_sha256,
        receipt_sha256=receipt_sha256,
        raw_output_sha256=raw_output_sha256,
    )


def _response_id(receipt: dict[str, object]) -> str:
    identity = receipt.get("identity")
    response_id = identity.get("response_id") if isinstance(identity, dict) else None
    if not isinstance(response_id, str) or not response_id:
        raise CustodyPersistenceError("verified receipt lacks provider response ID")
    return response_id


def write_json_atomic(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    encoded = payload.encode()
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(encoded)
            temporary.flush()
            os.fsync(temporary.fileno())
        Path(temporary_name).replace(path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        temporary_name = None
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
    actual = path.read_bytes()
    if actual != encoded:
        raise CustodyPersistenceError("atomic artifact bytes differ after readback")
    return hashlib.sha256(actual).hexdigest()


def write_json_exclusive(path: Path, value: object) -> str:
    """Durably create one reservation without a check-then-write race."""

    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise CustodyPersistenceError("exclusive custody artifact already exists") from exc
    try:
        with os.fdopen(descriptor, "wb") as target:
            target.write(encoded)
            target.flush()
            os.fsync(target.fileno())
        _fsync_directory(path.parent)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    actual = path.read_bytes()
    if actual != encoded:
        raise CustodyPersistenceError("exclusive artifact bytes differ after readback")
    return hashlib.sha256(actual).hexdigest()


def _fsync_directory(path: Path) -> None:
    directory_fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _read_json_object(path: Path) -> dict[str, object]:
    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise CustodyPersistenceError("custody artifact is not a JSON object")
    return loaded


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


__all__ = [
    "CustodyPersistenceError",
    "StageCustodyPaths",
    "StageCustodyInput",
    "StageCustodyRecord",
    "persist_stage_custody",
    "write_json_atomic",
    "write_json_exclusive",
]
