"""Fail-closed loading for packet publications and signed first-pass reviews."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from artana_evidence_api.evidence_selection.diagnostics.agent_evaluation import (
    EvidenceSelectionSemanticAgentEvaluation,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.loader import (
    read_verified_artifact,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.pilot_contracts import (
    EvidenceSelectionExpertPilotMachineSidecar,
    EvidenceSelectionExpertPilotPublicationManifest,
    EvidenceSelectionExpertPilotReviewerPacket,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.pilot_loader import (
    LoadedEvidenceSelectionExpertPilot,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.pilot_packets import (
    EvidenceSelectionExpertPilotPacketBundle,
    verify_expert_pilot_packet_bundle,
)
from pydantic import BaseModel

from .attestation import (
    canonical_payload_sha256,
    verify_ed25519_signature,
)
from .evaluation_contracts import (
    EvidenceSelectionExpertPilotEvaluationProtocol,
)
from .review_contracts import (
    EvidenceSelectionExpertPilotReviewerCredential,
    EvidenceSelectionExpertPilotSignedReviewCompletion,
    EvidenceSelectionExpertPilotSignedReviewerRegistry,
)

_REVIEWER_SLOT_COUNT = 3


@dataclass(frozen=True, slots=True)
class LoadedExpertPilotPublication:
    """Verified packet publication and complete packet-sidecar inventory."""

    directory: Path
    manifest: EvidenceSelectionExpertPilotPublicationManifest
    manifest_sha256: str
    bundles_by_packet_id: dict[str, EvidenceSelectionExpertPilotPacketBundle]


@dataclass(frozen=True, slots=True)
class VerifiedExpertPilotRegistry:
    """Issuer-verified reviewer credentials for the exact study."""

    signed_registry: EvidenceSelectionExpertPilotSignedReviewerRegistry
    payload_sha256: str
    issuer_public_key_sha256: str
    credentials_by_slot: dict[str, EvidenceSelectionExpertPilotReviewerCredential]


@dataclass(frozen=True, slots=True)
class VerifiedExpertPilotReviewCompletion:
    """One signed first-pass completion paired with its immutable packet."""

    signed_completion: EvidenceSelectionExpertPilotSignedReviewCompletion
    payload_sha256: str
    bundle: EvidenceSelectionExpertPilotPacketBundle


def load_expert_pilot_evaluation_protocol(
    *,
    path: Path,
    repository_root: Path,
    loaded_pilot: LoadedEvidenceSelectionExpertPilot,
) -> tuple[EvidenceSelectionExpertPilotEvaluationProtocol, str]:
    """Verify the pre-review protocol and all registered live-agent artifacts."""

    content = path.read_bytes()
    protocol = EvidenceSelectionExpertPilotEvaluationProtocol.model_validate_json(
        content
    )
    protocol_sha256 = hashlib.sha256(content).hexdigest()
    if protocol.study_id != loaded_pilot.protocol.study_id:
        raise ValueError("evaluation protocol study does not match expert pilot")
    if (
        protocol.pilot_protocol.path,
        protocol.pilot_protocol.sha256,
    ) != (
        loaded_pilot.protocol_path.resolve().relative_to(repository_root).as_posix(),
        loaded_pilot.protocol_sha256,
    ):
        raise ValueError("evaluation protocol does not bind the loaded pilot protocol")
    if protocol.acceptance_thresholds != loaded_pilot.protocol.acceptance_thresholds:
        raise ValueError("evaluation thresholds drifted from the pilot protocol")
    case_ids = [case.case_id for case in loaded_pilot.benchmark.historical_v1.cases]
    record_identities = [
        f"{case.case_id}\0{record.record_id}"
        for case in loaded_pilot.benchmark.historical_v1.cases
        for record in case.records
    ]
    if (
        protocol.expected_case_count != len(case_ids)
        or protocol.expected_record_count != len(record_identities)
        or protocol.case_inventory_sha256 != _inventory_sha256(case_ids)
        or protocol.record_inventory_sha256 != _inventory_sha256(record_identities)
    ):
        raise ValueError(
            "evaluation protocol case or record scope does not match pilot"
        )
    expected_record_pairs = [
        (case.case_id, record.record_id)
        for case in loaded_pilot.benchmark.historical_v1.cases
        for record in case.records
    ]
    expected_case_roles = {
        case.case_id: case.evaluation_role
        for case in loaded_pilot.benchmark.historical_v1.cases
    }
    historical_reference = loaded_pilot.benchmark.fixture.historical_v1
    for run in protocol.model_runs:
        _, run_bytes = read_verified_artifact(
            reference=run.artifact,
            repository_root=repository_root,
        )
        evaluation = EvidenceSelectionSemanticAgentEvaluation.model_validate_json(
            run_bytes
        )
        if (
            evaluation.model_id != run.model_id
            or evaluation.evaluated_commit != protocol.evaluated_commit
        ):
            raise ValueError(f"registered model identity mismatch: {run.run_id}")
        if (
            evaluation.fixture_path,
            evaluation.fixture_sha256,
        ) != (
            historical_reference.path,
            historical_reference.sha256,
        ):
            raise ValueError(f"registered model run fixture mismatch: {run.run_id}")
        record_pairs = [
            (result.case_id, result.record_id) for result in evaluation.record_results
        ]
        if record_pairs != expected_record_pairs or len(set(record_pairs)) != len(
            record_pairs
        ):
            raise ValueError(f"registered model run inventory mismatch: {run.run_id}")
        score_case_roles = {
            result.case_id: result.evaluation_role
            for result in evaluation.score.case_results
        }
        if (
            len(score_case_roles) != len(evaluation.score.case_results)
            or score_case_roles != expected_case_roles
        ):
            raise ValueError(f"registered model run case-role mismatch: {run.run_id}")
    return protocol, protocol_sha256


def load_expert_pilot_publication(
    *,
    directory: Path,
    loaded_pilot: LoadedEvidenceSelectionExpertPilot,
) -> LoadedExpertPilotPublication:
    """Verify manifest hashes, exact files, HMAC sidecars, and packet inventory."""

    resolved = directory.resolve()
    manifest_path = resolved / "publication_manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = EvidenceSelectionExpertPilotPublicationManifest.model_validate_json(
        manifest_bytes
    )
    expected_header = (
        loaded_pilot.protocol.study_id,
        loaded_pilot.protocol_sha256,
        loaded_pilot.benchmark.fixture_sha256,
        loaded_pilot.supplement_manifest_sha256,
    )
    actual_header = (
        manifest.study_id,
        manifest.protocol_sha256,
        manifest.benchmark_fixture_sha256,
        manifest.supplement_manifest_sha256,
    )
    if actual_header != expected_header:
        raise ValueError("expert-pilot publication identity does not match protocol")
    expected_files = {"publication_manifest.json"} | {
        artifact.path for artifact in manifest.artifacts
    }
    actual_files = {
        path.relative_to(resolved).as_posix()
        for path in resolved.rglob("*")
        if path.is_file()
    }
    if actual_files != expected_files:
        raise ValueError("expert-pilot publication file inventory is not exact")
    packets: dict[str, EvidenceSelectionExpertPilotReviewerPacket] = {}
    sidecars: dict[str, EvidenceSelectionExpertPilotMachineSidecar] = {}
    for artifact in manifest.artifacts:
        path = (resolved / artifact.path).resolve()
        if not path.is_relative_to(resolved):
            raise ValueError("expert-pilot publication artifact escapes directory")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != artifact.sha256:
            raise ValueError(
                f"expert-pilot publication digest mismatch: {artifact.path}"
            )
        if artifact.artifact_kind == "reviewer_packet":
            packet = EvidenceSelectionExpertPilotReviewerPacket.model_validate_json(
                content
            )
            packets[packet.packet_id] = packet
        else:
            sidecar = EvidenceSelectionExpertPilotMachineSidecar.model_validate_json(
                content
            )
            sidecars[sidecar.packet_id] = sidecar
    if set(packets) != set(sidecars) or len(packets) != manifest.reviewer_packet_count:
        raise ValueError(
            "expert-pilot publication packet-sidecar pairing is incomplete"
        )
    bundles = {
        packet_id: EvidenceSelectionExpertPilotPacketBundle(
            reviewer_packet=packets[packet_id],
            machine_sidecar=sidecars[packet_id],
        )
        for packet_id in packets
    }
    for bundle in bundles.values():
        verify_expert_pilot_packet_bundle(bundle)
    expected_slots = set(loaded_pilot.protocol.independent_reviewer_slots)
    actual_slots = {bundle.reviewer_packet.reviewer_slot for bundle in bundles.values()}
    if actual_slots != expected_slots:
        raise ValueError("expert-pilot publication reviewer slots are incomplete")
    expected_case_count = len(loaded_pilot.protocol.expected_case_ids)
    if any(
        sum(bundle.reviewer_packet.reviewer_slot == slot for bundle in bundles.values())
        != expected_case_count
        for slot in expected_slots
    ):
        raise ValueError("expert-pilot publication case coverage is incomplete")
    return LoadedExpertPilotPublication(
        directory=resolved,
        manifest=manifest,
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        bundles_by_packet_id=bundles,
    )


def load_and_verify_reviewer_registry(
    *,
    path: Path,
    issuer_public_key_hex: str,
    issuer_key_id: str,
    loaded_pilot: LoadedEvidenceSelectionExpertPilot,
    evaluation_protocol_sha256: str,
    publication_manifest_sha256: str,
) -> VerifiedExpertPilotRegistry:
    """Verify the external trust anchor and exact independent reviewer roster."""

    signed = EvidenceSelectionExpertPilotSignedReviewerRegistry.model_validate_json(
        path.read_bytes()
    )
    if signed.issuer_key_id != issuer_key_id:
        raise ValueError("reviewer registry issuer key ID does not match trust anchor")
    verify_ed25519_signature(
        payload=signed.payload,
        public_key_hex=issuer_public_key_hex,
        signature_hex=signed.signature_hex,
    )
    payload = signed.payload
    if (
        payload.study_id,
        payload.pilot_protocol_sha256,
        payload.evaluation_protocol_sha256,
        payload.publication_manifest_sha256,
    ) != (
        loaded_pilot.protocol.study_id,
        loaded_pilot.protocol_sha256,
        evaluation_protocol_sha256,
        publication_manifest_sha256,
    ):
        raise ValueError("reviewer registry does not bind the loaded study protocols")
    credentials = {item.reviewer_slot: item for item in payload.credentials}
    expected_slots = {
        *loaded_pilot.protocol.independent_reviewer_slots,
        loaded_pilot.protocol.adjudicator_slot,
    }
    if set(credentials) != expected_slots or len(credentials) != _REVIEWER_SLOT_COUNT:
        raise ValueError("reviewer registry must contain exactly the three study slots")
    if any(
        credentials[slot].review_role != "independent_first_pass"
        for slot in loaded_pilot.protocol.independent_reviewer_slots
    ) or (
        credentials[loaded_pilot.protocol.adjudicator_slot].review_role
        != "adjudicator_and_safety_reviewer"
    ):
        raise ValueError("reviewer registry roles do not match the pilot protocol")
    return VerifiedExpertPilotRegistry(
        signed_registry=signed,
        payload_sha256=canonical_payload_sha256(payload),
        issuer_public_key_sha256=hashlib.sha256(
            bytes.fromhex(issuer_public_key_hex)
        ).hexdigest(),
        credentials_by_slot=credentials,
    )


def load_and_verify_first_pass_completions(
    *,
    directory: Path,
    publication: LoadedExpertPilotPublication,
    registry: VerifiedExpertPilotRegistry,
    evaluation_protocol: EvidenceSelectionExpertPilotEvaluationProtocol,
    evaluation_protocol_sha256: str,
) -> tuple[VerifiedExpertPilotReviewCompletion, ...]:
    """Verify exact review coverage, certified signers, and literal evidence."""

    paths = sorted(path for path in directory.resolve().rglob("*") if path.is_file())
    if any(path.suffix != ".json" for path in paths):
        raise ValueError("first-pass completion directory may contain only JSON files")
    if len(paths) != len(publication.bundles_by_packet_id):
        raise ValueError("first-pass completion count does not match packet count")
    verified: list[VerifiedExpertPilotReviewCompletion] = []
    seen_packets: set[str] = set()
    for path in paths:
        signed = EvidenceSelectionExpertPilotSignedReviewCompletion.model_validate_json(
            path.read_bytes()
        )
        payload = signed.payload
        bundle = publication.bundles_by_packet_id.get(payload.packet_id)
        if bundle is None or payload.packet_id in seen_packets:
            raise ValueError(
                "first-pass completion packet identity is unknown or duplicate"
            )
        seen_packets.add(payload.packet_id)
        packet = bundle.reviewer_packet
        credential = registry.credentials_by_slot.get(payload.reviewer_slot)
        if credential is None or credential.review_role != "independent_first_pass":
            raise ValueError("first-pass completion reviewer slot is not certified")
        if (
            payload.study_id,
            payload.reviewer_slot,
            payload.review_case_id,
            payload.reviewer_packet_sha256,
            payload.evaluation_protocol_sha256,
            payload.reviewer_id,
            signed.reviewer_key_id,
        ) != (
            packet.study_id,
            packet.reviewer_slot,
            packet.review_case_id,
            bundle.machine_sidecar.reviewer_packet_sha256,
            evaluation_protocol_sha256,
            credential.reviewer_id,
            credential.key_id,
        ):
            raise ValueError(
                "first-pass completion identity does not match packet and credential"
            )
        registry_payload = registry.signed_registry.payload
        if (
            not (
                registry_payload.valid_from
                <= payload.completed_at
                <= registry_payload.valid_until
            )
            or payload.completed_at < evaluation_protocol.registered_at
        ):
            raise ValueError(
                "first-pass completion time is outside the registered window"
            )
        verify_ed25519_signature(
            payload=payload,
            public_key_hex=credential.public_key_hex,
            signature_hex=signed.signature_hex,
        )
        candidate_ids = tuple(candidate.candidate_id for candidate in packet.candidates)
        finding_ids = tuple(finding.candidate_id for finding in payload.findings)
        if finding_ids != candidate_ids:
            raise ValueError(
                "first-pass findings must exactly follow packet candidate order"
            )
        for candidate, finding in zip(packet.candidates, payload.findings, strict=True):
            _verify_literal_spans(
                supporting_spans=finding.supporting_spans,
                source_text=(
                    candidate.title,
                    *(section.text for section in candidate.bounded_source_text),
                ),
            )
        verified.append(
            VerifiedExpertPilotReviewCompletion(
                signed_completion=signed,
                payload_sha256=canonical_payload_sha256(payload),
                bundle=bundle,
            )
        )
    return tuple(
        sorted(verified, key=lambda item: item.signed_completion.payload.packet_id)
    )


def verify_review_time_and_signature(
    *,
    completed_at: datetime,
    signed_payload: BaseModel,
    signature_hex: str,
    reviewer_key_id: str,
    credential: EvidenceSelectionExpertPilotReviewerCredential,
    registry: VerifiedExpertPilotRegistry,
    earliest_time: datetime,
) -> None:
    """Apply the shared certified signer and chronology boundary."""

    if (reviewer_key_id, getattr(signed_payload, "reviewer_id", None)) != (
        credential.key_id,
        credential.reviewer_id,
    ):
        raise ValueError("signed reviewer identity does not match certified credential")
    registry_payload = registry.signed_registry.payload
    if (
        not (
            registry_payload.valid_from <= completed_at <= registry_payload.valid_until
        )
        or completed_at < earliest_time
    ):
        raise ValueError("signed human completion violates credential chronology")
    verify_ed25519_signature(
        payload=signed_payload,
        public_key_hex=credential.public_key_hex,
        signature_hex=signature_hex,
    )


def _inventory_sha256(values: list[str]) -> str:
    return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()


def verify_literal_spans(
    *,
    supporting_spans: tuple[str, ...],
    source_text: tuple[str, ...],
) -> None:
    """Public span verifier used by adjudication and safety phases."""

    _verify_literal_spans(
        supporting_spans=supporting_spans,
        source_text=source_text,
    )


def _verify_literal_spans(
    *,
    supporting_spans: tuple[str, ...],
    source_text: tuple[str, ...],
) -> None:
    for span in supporting_spans:
        if not any(span in source for source in source_text):
            raise ValueError("expert-pilot supporting span is not literal packet text")


__all__ = [
    "LoadedExpertPilotPublication",
    "VerifiedExpertPilotRegistry",
    "VerifiedExpertPilotReviewCompletion",
    "load_and_verify_first_pass_completions",
    "load_and_verify_reviewer_registry",
    "load_expert_pilot_evaluation_protocol",
    "load_expert_pilot_publication",
    "verify_literal_spans",
    "verify_review_time_and_signature",
]
