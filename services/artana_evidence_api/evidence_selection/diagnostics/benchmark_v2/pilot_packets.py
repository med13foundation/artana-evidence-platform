"""Build blinded reviewer packets and signed machine-only identity sidecars."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from artana_evidence_api.evidence_selection.diagnostics.fixture import (
    EvidenceSelectionSemanticDiagnosticCase,
    EvidenceSelectionSemanticDiagnosticRecord,
)
from artana_evidence_api.evidence_selection.shadow_review_integrity import (
    sign_machine_packet_digest,
    verify_machine_packet_signature,
)

from .pilot_contracts import (
    EvidenceSelectionExpertPilotAbstractSection,
    EvidenceSelectionExpertPilotCandidate,
    EvidenceSelectionExpertPilotCandidateBinding,
    EvidenceSelectionExpertPilotMachineSidecar,
    EvidenceSelectionExpertPilotReviewerPacket,
)
from .pilot_loader import LoadedEvidenceSelectionExpertPilot


@dataclass(frozen=True, slots=True)
class EvidenceSelectionExpertPilotPacketBundle:
    """One reviewer-facing packet paired with its private sidecar."""

    reviewer_packet: EvidenceSelectionExpertPilotReviewerPacket
    machine_sidecar: EvidenceSelectionExpertPilotMachineSidecar


def build_expert_pilot_packet_bundles(
    loaded: LoadedEvidenceSelectionExpertPilot,
) -> tuple[EvidenceSelectionExpertPilotPacketBundle, ...]:
    """Build independently ordered packets for every case and reviewer slot."""

    bundles: list[EvidenceSelectionExpertPilotPacketBundle] = []
    packet_refs_by_case = {
        item.case_id: item for item in loaded.benchmark.packet_manifest.packets
    }
    historical_case_ids = tuple(
        case.case_id for case in loaded.benchmark.historical_v1.cases
    )
    for case in loaded.benchmark.historical_v1.cases:
        _validate_reviewer_narrative(
            case=case,
            historical_case_ids=historical_case_ids,
        )
        for reviewer_slot in loaded.protocol.independent_reviewer_slots:
            ordered_records = sorted(
                case.records,
                key=lambda record: _blind_digest(
                    loaded.protocol.study_id,
                    case.case_id,
                    reviewer_slot,
                    record.record_id,
                ),
            )
            packet_id = "packet-" + _blind_digest(
                loaded.protocol.study_id,
                case.case_id,
                reviewer_slot,
                "packet",
            )[:16]
            review_case_id = "case-" + _blind_digest(
                loaded.protocol.study_id,
                case.case_id,
                reviewer_slot,
                "review-case",
            )[:16]
            candidates = tuple(
                _candidate(
                    loaded=loaded,
                    case_id=case.case_id,
                    reviewer_slot=reviewer_slot,
                    record=record,
                )
                for record in ordered_records
            )
            reviewer_packet = EvidenceSelectionExpertPilotReviewerPacket(
                schema_version="evidence_selection_expert_pilot_reviewer_packet.v1",
                study_id=loaded.protocol.study_id,
                packet_id=packet_id,
                reviewer_slot=reviewer_slot,
                review_role="independent_first_pass",
                review_case_id=review_case_id,
                goal=case.goal,
                instructions=case.instructions,
                inclusion_criteria=case.inclusion_criteria,
                exclusion_criteria=case.exclusion_criteria,
                completion_status="requires_human_labels",
                candidates=candidates,
            )
            packet_sha256 = reviewer_packet_sha256(reviewer_packet)
            bindings = tuple(
                EvidenceSelectionExpertPilotCandidateBinding(
                    candidate_id=candidate.candidate_id,
                    record_id=record.record_id,
                    historical_packet_sha256=packet_refs_by_case[case.case_id].sha256,
                    supplement_sha256=loaded.supplement_sha256_by_record.get(
                        record.record_id
                    ),
                )
                for candidate, record in zip(candidates, ordered_records, strict=True)
            )
            signature_payload = _sidecar_digest(
                study_id=loaded.protocol.study_id,
                packet_id=packet_id,
                reviewer_slot=reviewer_slot,
                review_case_id=review_case_id,
                case_id=case.case_id,
                packet_sha256=packet_sha256,
                protocol_sha256=loaded.protocol_sha256,
                benchmark_fixture_sha256=loaded.benchmark.fixture_sha256,
                supplement_manifest_sha256=loaded.supplement_manifest_sha256,
                candidate_bindings=bindings,
            )
            sidecar = EvidenceSelectionExpertPilotMachineSidecar(
                schema_version="evidence_selection_expert_pilot_sidecar.v1",
                study_id=loaded.protocol.study_id,
                packet_id=packet_id,
                reviewer_slot=reviewer_slot,
                review_case_id=review_case_id,
                case_id=case.case_id,
                protocol_sha256=loaded.protocol_sha256,
                benchmark_fixture_sha256=loaded.benchmark.fixture_sha256,
                supplement_manifest_sha256=loaded.supplement_manifest_sha256,
                reviewer_packet_sha256=packet_sha256,
                candidate_bindings=bindings,
                producer_signature=sign_machine_packet_digest(signature_payload),
            )
            bundles.append(
                EvidenceSelectionExpertPilotPacketBundle(
                    reviewer_packet=reviewer_packet,
                    machine_sidecar=sidecar,
                )
            )
    return tuple(bundles)


def verify_expert_pilot_packet_bundle(
    bundle: EvidenceSelectionExpertPilotPacketBundle,
) -> None:
    """Fail closed when packet bytes or sidecar bindings were altered."""

    packet = bundle.reviewer_packet
    sidecar = bundle.machine_sidecar
    packet_sha256 = reviewer_packet_sha256(packet)
    if packet_sha256 != sidecar.reviewer_packet_sha256:
        raise ValueError("expert-pilot reviewer packet digest mismatch")
    if (
        packet.packet_id,
        packet.study_id,
        packet.reviewer_slot,
        packet.review_case_id,
    ) != (
        sidecar.packet_id,
        sidecar.study_id,
        sidecar.reviewer_slot,
        sidecar.review_case_id,
    ):
        raise ValueError("expert-pilot packet identity does not match sidecar")
    candidate_ids = tuple(candidate.candidate_id for candidate in packet.candidates)
    binding_ids = tuple(binding.candidate_id for binding in sidecar.candidate_bindings)
    if candidate_ids != binding_ids:
        raise ValueError("expert-pilot candidate order does not match sidecar")
    verify_machine_packet_signature(
        digest=_sidecar_digest(
            study_id=sidecar.study_id,
            packet_id=sidecar.packet_id,
            reviewer_slot=sidecar.reviewer_slot,
            review_case_id=sidecar.review_case_id,
            case_id=sidecar.case_id,
            packet_sha256=packet_sha256,
            protocol_sha256=sidecar.protocol_sha256,
            benchmark_fixture_sha256=sidecar.benchmark_fixture_sha256,
            supplement_manifest_sha256=sidecar.supplement_manifest_sha256,
            candidate_bindings=sidecar.candidate_bindings,
        ),
        signature=sidecar.producer_signature,
    )


def reviewer_packet_sha256(
    packet: EvidenceSelectionExpertPilotReviewerPacket,
) -> str:
    """Return a canonical digest for one reviewer-facing packet."""

    content = json.dumps(
        packet.model_dump(mode="json"),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _candidate(
    *,
    loaded: LoadedEvidenceSelectionExpertPilot,
    case_id: str,
    reviewer_slot: str,
    record: EvidenceSelectionSemanticDiagnosticRecord,
) -> EvidenceSelectionExpertPilotCandidate:
    supplement = loaded.supplements_by_record[record.record_id]
    source_text: tuple[EvidenceSelectionExpertPilotAbstractSection, ...]
    bounded_text = "\n\n".join(
        section.text for section in supplement.abstract_sections
    )
    source_text = (
        EvidenceSelectionExpertPilotAbstractSection(
            section="SOURCE_TEXT",
            text=bounded_text,
        ),
    )
    return EvidenceSelectionExpertPilotCandidate(
        candidate_id="candidate-"
        + _blind_digest(
            loaded.protocol.study_id,
            case_id,
            reviewer_slot,
            record.record_id,
        )[:16],
        source_key=supplement.source_key,
        source_record_id=supplement.source_record_id,
        source_url=supplement.source_url,
        title=supplement.title,
        bounded_source_text=source_text,
    )


def _blind_digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _validate_reviewer_narrative(
    *,
    case: EvidenceSelectionSemanticDiagnosticCase,
    historical_case_ids: tuple[str, ...],
) -> None:
    narrative = "\n".join(
        (
            case.goal,
            case.instructions,
            *case.inclusion_criteria,
            *case.exclusion_criteria,
        )
    ).casefold()
    forbidden_markers = (
        "ai diagnostic",
        "calibrated probability",
        "canary",
        "expected label",
        "expected_label",
        "harness",
        "historical label",
        "model decision",
        "model identity",
        "ranking",
    )
    leaked_markers = tuple(
        marker
        for marker in (*forbidden_markers, *historical_case_ids)
        if marker.casefold() in narrative
    )
    if leaked_markers:
        raise ValueError(
            "expert-pilot reviewer narrative leaks blinded context: "
            + ", ".join(leaked_markers)
        )


def _sidecar_digest(
    *,
    study_id: str,
    packet_id: str,
    reviewer_slot: str,
    review_case_id: str,
    case_id: str,
    packet_sha256: str,
    protocol_sha256: str,
    benchmark_fixture_sha256: str,
    supplement_manifest_sha256: str,
    candidate_bindings: tuple[EvidenceSelectionExpertPilotCandidateBinding, ...],
) -> str:
    payload = {
        "schema_version": "evidence_selection_expert_pilot_sidecar.v1",
        "study_id": study_id,
        "packet_id": packet_id,
        "reviewer_slot": reviewer_slot,
        "review_case_id": review_case_id,
        "case_id": case_id,
        "protocol_sha256": protocol_sha256,
        "benchmark_fixture_sha256": benchmark_fixture_sha256,
        "supplement_manifest_sha256": supplement_manifest_sha256,
        "reviewer_packet_sha256": packet_sha256,
        "candidate_bindings": [
            binding.model_dump(mode="json") for binding in candidate_bindings
        ],
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


__all__ = [
    "EvidenceSelectionExpertPilotPacketBundle",
    "build_expert_pilot_packet_bundles",
    "reviewer_packet_sha256",
    "verify_expert_pilot_packet_bundle",
]
