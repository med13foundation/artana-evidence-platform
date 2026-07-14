"""Load and bind a frozen benchmark-v2 expert pilot protocol."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .contracts import EvidenceSelectionBenchmarkArtifactRef
from .loader import (
    LoadedEvidenceSelectionBenchmarkV2,
    load_benchmark_v2,
    read_verified_artifact,
)
from .pilot_contracts import (
    EvidenceSelectionExpertPilotProtocol,
    EvidenceSelectionExpertPilotSourceSupplement,
    EvidenceSelectionExpertPilotSupplementManifest,
)


@dataclass(frozen=True, slots=True)
class LoadedEvidenceSelectionExpertPilot:
    """Fully verified pilot protocol, benchmark, and source supplements."""

    protocol_path: Path
    protocol_sha256: str
    protocol: EvidenceSelectionExpertPilotProtocol
    benchmark: LoadedEvidenceSelectionBenchmarkV2
    supplement_manifest_sha256: str
    supplement_manifest: EvidenceSelectionExpertPilotSupplementManifest
    supplements_by_record: dict[str, EvidenceSelectionExpertPilotSourceSupplement]
    supplement_sha256_by_record: dict[str, str]


def load_expert_pilot(
    *,
    protocol_path: Path,
    repository_root: Path,
) -> LoadedEvidenceSelectionExpertPilot:
    """Verify a diagnostic pilot without converting it into expert evidence."""

    resolved_root = repository_root.resolve()
    protocol_bytes = protocol_path.read_bytes()
    protocol = EvidenceSelectionExpertPilotProtocol.model_validate_json(
        protocol_bytes,
    )
    benchmark_path, _ = read_verified_artifact(
        reference=protocol.benchmark_fixture,
        repository_root=resolved_root,
    )
    benchmark = load_benchmark_v2(
        fixture_path=benchmark_path,
        repository_root=resolved_root,
    )
    manifest_path, manifest_bytes = read_verified_artifact(
        reference=protocol.supplement_manifest,
        repository_root=resolved_root,
    )
    del manifest_path
    manifest = EvidenceSelectionExpertPilotSupplementManifest.model_validate_json(
        manifest_bytes,
    )
    supplements_by_source, supplement_hashes_by_source = _load_supplements(
        manifest=manifest,
        repository_root=resolved_root,
    )
    _verify_protocol_inventory(protocol=protocol, benchmark=benchmark)
    supplements, supplement_hashes = _bind_complete_source_inventory(
        benchmark=benchmark,
        supplements_by_source=supplements_by_source,
        supplement_hashes_by_source=supplement_hashes_by_source,
    )
    return LoadedEvidenceSelectionExpertPilot(
        protocol_path=protocol_path,
        protocol_sha256=hashlib.sha256(protocol_bytes).hexdigest(),
        protocol=protocol,
        benchmark=benchmark,
        supplement_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        supplement_manifest=manifest,
        supplements_by_record=supplements,
        supplement_sha256_by_record=supplement_hashes,
    )


def _load_supplements(
    *,
    manifest: EvidenceSelectionExpertPilotSupplementManifest,
    repository_root: Path,
) -> tuple[
    dict[str, EvidenceSelectionExpertPilotSourceSupplement],
    dict[str, str],
]:
    supplements: dict[str, EvidenceSelectionExpertPilotSourceSupplement] = {}
    hashes: dict[str, str] = {}
    for reference in manifest.supplements:
        _, content = read_verified_artifact(
            reference=EvidenceSelectionBenchmarkArtifactRef(
                path=reference.path,
                sha256=reference.sha256,
            ),
            repository_root=repository_root,
        )
        supplement = EvidenceSelectionExpertPilotSourceSupplement.model_validate_json(
            content,
        )
        expected_identity = (reference.source_key, reference.source_record_id)
        actual_identity = (
            supplement.source_key,
            supplement.source_record_id,
        )
        if actual_identity != expected_identity:
            raise ValueError(
                "expert-pilot supplement source identity mismatch: "
                f"{reference.source_record_id}"
            )
        supplements[reference.source_record_id] = supplement
        hashes[reference.source_record_id] = reference.sha256
    return supplements, hashes


def _verify_protocol_inventory(
    *,
    protocol: EvidenceSelectionExpertPilotProtocol,
    benchmark: LoadedEvidenceSelectionBenchmarkV2,
) -> None:
    case_ids = tuple(case.case_id for case in benchmark.historical_v1.cases)
    record_count = sum(len(case.records) for case in benchmark.historical_v1.cases)
    if protocol.expected_case_ids != case_ids:
        raise ValueError("expert-pilot protocol case inventory does not match benchmark")
    if protocol.expected_record_count != record_count:
        raise ValueError("expert-pilot protocol record count does not match benchmark")


def _bind_complete_source_inventory(
    *,
    benchmark: LoadedEvidenceSelectionBenchmarkV2,
    supplements_by_source: dict[str, EvidenceSelectionExpertPilotSourceSupplement],
    supplement_hashes_by_source: dict[str, str],
) -> tuple[
    dict[str, EvidenceSelectionExpertPilotSourceSupplement],
    dict[str, str],
]:
    records = tuple(
        record
        for case in benchmark.historical_v1.cases
        for record in case.records
    )
    expected_source_ids = {record.source_record_id for record in records}
    if set(supplements_by_source) != expected_source_ids:
        raise ValueError(
            "expert-pilot supplements must exactly cover every benchmark source"
        )
    supplements_by_record = {
        record.record_id: supplements_by_source[record.source_record_id]
        for record in records
    }
    hashes_by_record = {
        record.record_id: supplement_hashes_by_source[record.source_record_id]
        for record in records
    }
    return supplements_by_record, hashes_by_record


__all__ = ["LoadedEvidenceSelectionExpertPilot", "load_expert_pilot"]
