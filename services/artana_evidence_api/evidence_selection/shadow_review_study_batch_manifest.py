"""Build strict manifests for completed shadow-review study batches."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from artana_evidence_api.evidence_selection.output_paths import paths_alias
from artana_evidence_api.evidence_selection.shadow_review_completion import (
    EvidenceSelectionShadowReviewSourceInputRequest,
    build_evidence_selection_shadow_review_source_inputs,
    machine_packet_sidecar_path,
)
from artana_evidence_api.evidence_selection.shadow_review_study_batch import (
    EvidenceSelectionShadowReviewStudyBatchManifest,
)
from artana_evidence_api.evidence_selection_validation import (
    EvidenceSelectionExpertStudyEvidenceKind,
)
from artana_evidence_api.types.common import JSONObject, json_object
from pydantic import ValidationError

_MANIFEST_SCHEMA_VERSION = "evidence_selection_shadow_review_study_batch.v1"
_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class EvidenceSelectionShadowReviewStudyBatchManifestBuildRequest:
    """Completed packet paths and shared source identity for a batch manifest."""

    batch_id: str
    packet_paths: tuple[Path, ...]
    source_system: str
    export_id_prefix: str
    exported_at: str
    exporter_id: str
    redaction_statement: str
    study_evidence_kind: EvidenceSelectionExpertStudyEvidenceKind
    adjudication_note: str | None = None
    manifest_path: Path | None = None
    description: str | None = None
    machine_packet_paths: tuple[Path, ...] | None = None


def build_evidence_selection_shadow_review_study_batch_manifest(
    request: EvidenceSelectionShadowReviewStudyBatchManifestBuildRequest,
) -> EvidenceSelectionShadowReviewStudyBatchManifest:
    """Build a strict batch manifest from completed shadow-review packets."""

    if not request.packet_paths:
        msg = "At least one completed shadow-review packet is required."
        raise ValueError(msg)
    machine_packet_paths = request.machine_packet_paths or tuple(
        machine_packet_sidecar_path(packet_path) for packet_path in request.packet_paths
    )
    if len(machine_packet_paths) != len(request.packet_paths):
        msg = "Every completed shadow-review packet requires one machine packet path."
        raise ValueError(msg)
    _reject_duplicate_packet_paths(
        (*machine_packet_paths, *request.packet_paths),
    )
    entries: list[JSONObject] = []
    for index, (machine_packet_path, packet_path) in enumerate(
        zip(machine_packet_paths, request.packet_paths, strict=True),
        start=1,
    ):
        packet = _load_completed_packet(
            machine_packet_path=machine_packet_path,
            packet_path=packet_path,
            adjudication_note=request.adjudication_note,
            description=request.description,
        )
        study_id = _packet_study_id(packet, packet_path=packet_path)
        entry_id = f"{index:02d}-{_slug(study_id)}"
        entries.append(
            {
                "entry_id": entry_id,
                "machine_packet_path": str(
                    _packet_path_for_manifest(
                        packet_path=machine_packet_path,
                        manifest_path=request.manifest_path,
                    ),
                ),
                "packet_path": str(
                    _packet_path_for_manifest(
                        packet_path=packet_path,
                        manifest_path=request.manifest_path,
                    ),
                ),
                "output_subdir": entry_id,
                "adjudication_note": request.adjudication_note,
                "source_system": request.source_system,
                "export_id": f"{request.export_id_prefix}-{entry_id}",
                "exported_at": request.exported_at,
                "exporter_id": request.exporter_id,
                "redaction_statement": request.redaction_statement,
                "study_evidence_kind": request.study_evidence_kind,
                "description": request.description,
            },
        )
    return EvidenceSelectionShadowReviewStudyBatchManifest.model_validate(
        {
            "schema_version": _MANIFEST_SCHEMA_VERSION,
            "batch_id": request.batch_id,
            "entries": entries,
        },
    )


def _reject_duplicate_packet_paths(packet_paths: tuple[Path, ...]) -> None:
    if any(
        paths_alias(left, right)
        for index, left in enumerate(packet_paths)
        for right in packet_paths[index + 1 :]
    ):
        msg = "Completed shadow-review packet paths must be unique."
        raise ValueError(msg)


def _load_completed_packet(
    *,
    machine_packet_path: Path,
    packet_path: Path,
    adjudication_note: str | None,
    description: str | None,
) -> JSONObject:
    machine_packet = _load_json_object(machine_packet_path)
    packet = _load_json_object(packet_path)
    try:
        build_evidence_selection_shadow_review_source_inputs(
            EvidenceSelectionShadowReviewSourceInputRequest(
                machine_packet=machine_packet,
                packet=packet,
                adjudication_note=adjudication_note,
                description=description,
            ),
        )
    except (ValueError, ValidationError) as exc:
        msg = f"{packet_path} is not a completed shadow-review packet: {exc}"
        raise ValueError(msg) from exc
    return packet


def _load_json_object(path: Path) -> JSONObject:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        msg = f"{path} is not valid JSON: {exc.msg}."
        raise ValueError(msg) from exc
    result = json_object(payload)
    if result is None:
        msg = f"{path} does not contain a JSON object."
        raise ValueError(msg)
    return result


def _packet_study_id(packet: JSONObject, *, packet_path: Path) -> str:
    study_id = packet.get("study_id")
    if not isinstance(study_id, str) or not study_id.strip():
        msg = f"{packet_path} is missing a non-empty study_id."
        raise ValueError(msg)
    return study_id


def _slug(value: str) -> str:
    slug = _SLUG_PATTERN.sub("-", value.strip().lower()).strip("-")
    if slug == "":
        msg = "Packet study_id must contain at least one alphanumeric character."
        raise ValueError(msg)
    return slug


def _packet_path_for_manifest(*, packet_path: Path, manifest_path: Path | None) -> Path:
    if manifest_path is None:
        return packet_path
    return Path(
        os.path.relpath(
            packet_path.resolve(strict=False),
            start=manifest_path.parent.resolve(strict=False),
        ),
    )


__all__ = [
    "EvidenceSelectionShadowReviewStudyBatchManifestBuildRequest",
    "build_evidence_selection_shadow_review_study_batch_manifest",
]
