"""Load benchmark v2 and verify every immutable diagnostic source."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from artana_evidence_api.evidence_selection.diagnostics.fixture import (
    EvidenceSelectionSemanticDiagnosticCase,
    EvidenceSelectionSemanticDiagnosticFixture,
    load_semantic_diagnostic_fixture,
)
from pydantic import BaseModel, ConfigDict, field_validator

from .contracts import (
    EvidenceSelectionBenchmarkAIDiagnostic,
    EvidenceSelectionBenchmarkArtifactRef,
    EvidenceSelectionBenchmarkEvidenceSpan,
    EvidenceSelectionBenchmarkPacketManifest,
    EvidenceSelectionBenchmarkV2Fixture,
)


class _PacketRecord(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    record_id: str
    source_key: Literal["pubmed"]
    source_record_id: str
    title: str
    evidence_excerpt: str


class _PacketCase(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    case_id: str
    evaluation_role: Literal["primary", "canary"]
    source_run_id: str
    upstream_source_artifact_sha256: str
    goal: str
    instructions: str
    inclusion_criteria: tuple[str, ...]
    exclusion_criteria: tuple[str, ...]
    records: tuple[_PacketRecord, ...]

    @field_validator(
        "inclusion_criteria",
        "exclusion_criteria",
        "records",
        mode="before",
    )
    @classmethod
    def _accept_json_arrays(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value


class _BoundedSourcePacket(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_semantic_source_snapshot.v1"]
    source_kind: Literal["sanitized_live_shadow_result_snapshot"]
    case: _PacketCase


@dataclass(frozen=True, slots=True)
class LoadedEvidenceSelectionBenchmarkV2:
    """Verified benchmark bytes and deterministically migrated diagnostics."""

    fixture_path: Path
    fixture_sha256: str
    fixture: EvidenceSelectionBenchmarkV2Fixture
    historical_v1: EvidenceSelectionSemanticDiagnosticFixture
    packet_manifest: EvidenceSelectionBenchmarkPacketManifest
    packets_by_case: dict[str, _BoundedSourcePacket]
    diagnostics_by_record: dict[str, EvidenceSelectionBenchmarkAIDiagnostic]
    repository_root: Path


def load_benchmark_v2(
    *,
    fixture_path: Path,
    repository_root: Path,
) -> LoadedEvidenceSelectionBenchmarkV2:
    """Load v2, preserve v1 bytes, and verify all bounded packet content."""

    resolved_root = repository_root.resolve()
    fixture_bytes = fixture_path.read_bytes()
    fixture = EvidenceSelectionBenchmarkV2Fixture.model_validate_json(fixture_bytes)
    historical_path, _ = read_verified_artifact(
        reference=fixture.historical_v1,
        repository_root=resolved_root,
    )
    historical_v1 = load_semantic_diagnostic_fixture(historical_path)
    _, manifest_bytes = read_verified_artifact(
        reference=fixture.source_packet_manifest,
        repository_root=resolved_root,
    )
    packet_manifest = EvidenceSelectionBenchmarkPacketManifest.model_validate_json(
        manifest_bytes,
    )
    packets_by_case = _load_packets(
        manifest=packet_manifest,
        historical_v1=historical_v1,
        repository_root=resolved_root,
    )
    diagnostics_by_record = _diagnostics(
        fixture=fixture,
        historical_v1=historical_v1,
        packets_by_case=packets_by_case,
    )
    known_case_ids = {case.case_id for case in historical_v1.cases}
    unknown_bindings = {
        binding.case_id for binding in fixture.expert_review_bindings
    } - known_case_ids
    if unknown_bindings:
        raise ValueError(f"expert review bindings contain unknown cases: {sorted(unknown_bindings)}")
    return LoadedEvidenceSelectionBenchmarkV2(
        fixture_path=fixture_path,
        fixture_sha256=hashlib.sha256(fixture_bytes).hexdigest(),
        fixture=fixture,
        historical_v1=historical_v1,
        packet_manifest=packet_manifest,
        packets_by_case=packets_by_case,
        diagnostics_by_record=diagnostics_by_record,
        repository_root=resolved_root,
    )


def read_verified_artifact(
    *,
    reference: EvidenceSelectionBenchmarkArtifactRef,
    repository_root: Path,
) -> tuple[Path, bytes]:
    """Resolve one repository artifact without path escape or digest drift."""

    resolved_root = repository_root.resolve()
    path = (resolved_root / reference.path).resolve()
    if not path.is_relative_to(resolved_root):
        raise ValueError(f"benchmark artifact escapes repository root: {reference.path}")
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"benchmark artifact is not resolvable: {reference.path}") from exc
    if hashlib.sha256(content).hexdigest() != reference.sha256:
        raise ValueError(f"benchmark artifact digest mismatch: {reference.path}")
    return path, content


def _load_packets(
    *,
    manifest: EvidenceSelectionBenchmarkPacketManifest,
    historical_v1: EvidenceSelectionSemanticDiagnosticFixture,
    repository_root: Path,
) -> dict[str, _BoundedSourcePacket]:
    expected_cases = {case.case_id: case for case in historical_v1.cases}
    if {packet.case_id for packet in manifest.packets} != set(expected_cases):
        raise ValueError("packet manifest case inventory must exactly match historical v1")
    loaded: dict[str, _BoundedSourcePacket] = {}
    for reference in manifest.packets:
        historical_case = expected_cases[reference.case_id]
        if (reference.path, reference.sha256) != (
            historical_case.source_artifact_path,
            historical_case.source_artifact_sha256,
        ):
            raise ValueError(
                f"packet identity does not preserve historical v1 case: {reference.case_id}",
            )
        _, packet_bytes = read_verified_artifact(
            reference=reference,
            repository_root=repository_root,
        )
        packet = _BoundedSourcePacket.model_validate_json(packet_bytes)
        if packet.case.model_dump() != _expected_packet_case(historical_case):
            raise ValueError(f"bounded packet content drifted from v1: {reference.case_id}")
        loaded[reference.case_id] = packet
    return loaded


def _expected_packet_case(
    historical_case: EvidenceSelectionSemanticDiagnosticCase,
) -> dict[str, object]:
    return {
        "case_id": historical_case.case_id,
        "evaluation_role": historical_case.evaluation_role,
        "source_run_id": historical_case.source_run_id,
        "upstream_source_artifact_sha256": historical_case.upstream_source_artifact_sha256,
        "goal": historical_case.goal,
        "instructions": historical_case.instructions,
        "inclusion_criteria": historical_case.inclusion_criteria,
        "exclusion_criteria": historical_case.exclusion_criteria,
        "records": tuple(
            {
                "record_id": record.record_id,
                "source_key": record.source_key,
                "source_record_id": record.source_record_id,
                "title": record.title,
                "evidence_excerpt": record.evidence_excerpt,
            }
            for record in historical_case.records
        ),
    }


def _diagnostics(
    *,
    fixture: EvidenceSelectionBenchmarkV2Fixture,
    historical_v1: EvidenceSelectionSemanticDiagnosticFixture,
    packets_by_case: dict[str, _BoundedSourcePacket],
) -> dict[str, EvidenceSelectionBenchmarkAIDiagnostic]:
    migrated = {
        record.record_id: EvidenceSelectionBenchmarkAIDiagnostic(
            record_id=record.record_id,
            provenance="ai_adjudicated_diagnostic",
            decision=record.expected_label,
            rationale=record.expected_reason,
            evidence_spans=(
                EvidenceSelectionBenchmarkEvidenceSpan(
                    source_locator=f"{record.record_id}:evidence_excerpt",
                    quoted_text=record.evidence_excerpt,
                ),
            ),
        )
        for case in historical_v1.cases
        for record in case.records
    }
    for override in fixture.diagnostic_overrides:
        if override.record_id not in migrated:
            raise ValueError(f"diagnostic override has unknown record: {override.record_id}")
        case_id = next(
            case.case_id
            for case in historical_v1.cases
            if any(record.record_id == override.record_id for record in case.records)
        )
        _verify_diagnostic_spans(
            diagnostic=override,
            packet=packets_by_case[case_id],
        )
        migrated[override.record_id] = override
    return migrated


def _verify_diagnostic_spans(
    *,
    diagnostic: EvidenceSelectionBenchmarkAIDiagnostic,
    packet: _BoundedSourcePacket,
) -> None:
    packet_record = next(
        (record for record in packet.case.records if record.record_id == diagnostic.record_id),
        None,
    )
    if packet_record is None:
        raise ValueError(f"diagnostic record is absent from bounded packet: {diagnostic.record_id}")
    allowed = {
        f"{diagnostic.record_id}:title": packet_record.title,
        f"{diagnostic.record_id}:evidence_excerpt": packet_record.evidence_excerpt,
    }
    for span in diagnostic.evidence_spans:
        source_text = allowed.get(span.source_locator)
        if source_text is None or span.quoted_text not in source_text:
            raise ValueError(
                f"diagnostic evidence span is not bound to packet text: {diagnostic.record_id}",
            )


__all__ = [
    "LoadedEvidenceSelectionBenchmarkV2",
    "load_benchmark_v2",
    "read_verified_artifact",
]
