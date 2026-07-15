"""Post-gold categorical safety-request construction and verification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.pilot_loader import (
    LoadedEvidenceSelectionExpertPilot,
)

from .attestation import canonical_payload_sha256
from .blinding import keyed_blind_digest
from .evaluation_contracts import (
    EvidenceSelectionExpertPilotGoldArtifact,
    EvidenceSelectionExpertPilotSafetyAuditItem,
    EvidenceSelectionExpertPilotSafetyAuditRequest,
)
from .review_contracts import (
    EvidenceSelectionExpertPilotSignedSafetyCompletion,
)
from .review_loader import (
    VerifiedExpertPilotRegistry,
    verify_literal_spans,
    verify_review_time_and_signature,
)

if TYPE_CHECKING:
    from .result import LoadedExpertPilotModelRun


@dataclass(frozen=True, slots=True)
class PreparedExpertPilotSafetyAudit:
    """Model-blinded request plus private item-to-run mappings."""

    request: EvidenceSelectionExpertPilotSafetyAuditRequest
    run_and_record_by_item_id: dict[str, tuple[str, str]]


@dataclass(frozen=True, slots=True)
class VerifiedExpertPilotSafetyAudit:
    """Certified categorical safety findings over the exact frozen request."""

    signed_completion: EvidenceSelectionExpertPilotSignedSafetyCompletion
    payload_sha256: str


def prepare_expert_pilot_safety_audit(
    *,
    loaded_pilot: LoadedEvidenceSelectionExpertPilot,
    evaluation_protocol_sha256: str,
    gold: EvidenceSelectionExpertPilotGoldArtifact,
    model_runs: tuple[LoadedExpertPilotModelRun, ...],
    blinding_key: bytes,
) -> PreparedExpertPilotSafetyAudit:
    """Expose every selected claim without revealing model identity or gold labels."""

    gold_sha256 = canonical_payload_sha256(gold)
    items: list[EvidenceSelectionExpertPilotSafetyAuditItem] = []
    mappings: dict[str, tuple[str, str]] = {}
    for run in model_runs:
        blinded_run_id = (
            "blinded-run-"
            + keyed_blind_digest(
                key=blinding_key,
                namespace="safety-run",
                parts=(
                    loaded_pilot.protocol.study_id,
                    run.reference.run_id,
                ),
            )[:12]
        )
        for result in run.evaluation.record_results:
            if result.prediction_decision != "select":
                continue
            if result.assessment is None:
                raise ValueError(
                    "selected registered result is missing agent assessment"
                )
            supplement = loaded_pilot.supplements_by_record[result.record_id]
            item_id = (
                "safety-"
                + keyed_blind_digest(
                    key=blinding_key,
                    namespace="safety-item",
                    parts=(
                        loaded_pilot.protocol.study_id,
                        run.reference.run_id,
                        result.record_id,
                    ),
                )[:16]
            )
            items.append(
                EvidenceSelectionExpertPilotSafetyAuditItem(
                    audit_item_id=item_id,
                    blinded_run_id=blinded_run_id,
                    title=supplement.title,
                    bounded_source_text=tuple(
                        section.text for section in supplement.abstract_sections
                    ),
                    agent_explanation=result.assessment.explanation,
                    agent_evidence_spans=result.evidence_spans,
                )
            )
            mappings[item_id] = (run.reference.run_id, result.record_id)
    return PreparedExpertPilotSafetyAudit(
        request=EvidenceSelectionExpertPilotSafetyAuditRequest(
            schema_version="evidence_selection_expert_pilot_safety_request.v1",
            study_id=loaded_pilot.protocol.study_id,
            frozen_gold_sha256=gold_sha256,
            evaluation_protocol_sha256=evaluation_protocol_sha256,
            review_phase="after_adjudicated_gold_freeze",
            completion_status="requires_human_safety_findings",
            items=tuple(items),
        ),
        run_and_record_by_item_id=mappings,
    )


def load_and_verify_safety_completion(
    *,
    path: Path,
    prepared: PreparedExpertPilotSafetyAudit,
    registry: VerifiedExpertPilotRegistry,
    loaded_pilot: LoadedEvidenceSelectionExpertPilot,
    earliest_time: datetime,
) -> VerifiedExpertPilotSafetyAudit:
    """Verify post-gold chronology, exact coverage, literal spans, and signer."""

    signed = EvidenceSelectionExpertPilotSignedSafetyCompletion.model_validate_json(
        path.read_bytes()
    )
    payload = signed.payload
    credential = registry.credentials_by_slot[loaded_pilot.protocol.adjudicator_slot]
    if (
        payload.study_id,
        payload.safety_reviewer_slot,
        payload.safety_request_sha256,
        payload.frozen_gold_sha256,
    ) != (
        loaded_pilot.protocol.study_id,
        loaded_pilot.protocol.adjudicator_slot,
        canonical_payload_sha256(prepared.request),
        prepared.request.frozen_gold_sha256,
    ):
        raise ValueError("safety completion does not bind the frozen request and gold")
    verify_review_time_and_signature(
        completed_at=payload.completed_at,
        signed_payload=payload,
        signature_hex=signed.signature_hex,
        reviewer_key_id=signed.reviewer_key_id,
        credential=credential,
        registry=registry,
        earliest_time=earliest_time,
    )
    expected_ids = tuple(item.audit_item_id for item in prepared.request.items)
    finding_ids = tuple(finding.audit_item_id for finding in payload.findings)
    if finding_ids != expected_ids:
        raise ValueError("safety findings must exactly follow request item order")
    for item, finding in zip(prepared.request.items, payload.findings, strict=True):
        verify_literal_spans(
            supporting_spans=finding.claim_spans,
            source_text=(item.agent_explanation,),
        )
        verify_literal_spans(
            supporting_spans=finding.source_support_spans,
            source_text=(item.title, *item.bounded_source_text),
        )
        if finding.assessment == "supported" and not finding.source_support_spans:
            raise ValueError("supported safety findings require literal source support")
        if (
            finding.assessment in {"unsupported_nonsevere", "unsupported_high_severity"}
            and not finding.claim_spans
        ):
            raise ValueError("overclaim findings require a literal agent claim span")
    return VerifiedExpertPilotSafetyAudit(
        signed_completion=signed,
        payload_sha256=canonical_payload_sha256(payload),
    )


__all__ = [
    "PreparedExpertPilotSafetyAudit",
    "VerifiedExpertPilotSafetyAudit",
    "load_and_verify_safety_completion",
    "prepare_expert_pilot_safety_audit",
]
