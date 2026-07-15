"""Deterministic disagreement requests and signed expert gold construction."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.pilot_contracts import (
    EvidenceSelectionExpertPilotAbstractSection,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.pilot_loader import (
    LoadedEvidenceSelectionExpertPilot,
)

from .attestation import canonical_payload_sha256
from .evaluation_contracts import (
    EvidenceSelectionExpertPilotGoldArtifact,
    EvidenceSelectionExpertPilotGoldRecord,
)
from .review_contracts import (
    EvidenceSelectionExpertPilotAdjudicationItem,
    EvidenceSelectionExpertPilotAdjudicationRequest,
    EvidenceSelectionExpertPilotFirstPassFinding,
    EvidenceSelectionExpertPilotReviewFinding,
    EvidenceSelectionExpertPilotSignedAdjudicationCompletion,
)
from .review_loader import (
    LoadedExpertPilotPublication,
    VerifiedExpertPilotRegistry,
    VerifiedExpertPilotReviewCompletion,
    verify_literal_spans,
    verify_review_time_and_signature,
)

_FIRST_PASS_REVIEWER_COUNT = 2


@dataclass(frozen=True, slots=True)
class _RecordFirstPassReview:
    reviewer_slot: str
    case_id: str
    review_case_id: str
    completion_sha256: str
    completed_at: datetime
    finding: EvidenceSelectionExpertPilotReviewFinding
    title: str
    bounded_source_text: tuple[EvidenceSelectionExpertPilotAbstractSection, ...]
    goal: str
    instructions: str
    inclusion_criteria: tuple[str, ...]
    exclusion_criteria: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PreparedExpertPilotAdjudication:
    """Generated request plus private record mappings retained by the importer."""

    request: EvidenceSelectionExpertPilotAdjudicationRequest
    reviews_by_record: dict[str, tuple[_RecordFirstPassReview, ...]]
    record_id_by_item_id: dict[str, str]


@dataclass(frozen=True, slots=True)
class VerifiedExpertPilotAdjudication:
    """Certified third-reviewer result over the exact generated request."""

    signed_completion: EvidenceSelectionExpertPilotSignedAdjudicationCompletion
    payload_sha256: str


def prepare_expert_pilot_adjudication(
    *,
    loaded_pilot: LoadedEvidenceSelectionExpertPilot,
    evaluation_protocol_sha256: str,
    registry: VerifiedExpertPilotRegistry,
    completions: tuple[VerifiedExpertPilotReviewCompletion, ...],
) -> PreparedExpertPilotAdjudication:
    """Create a model-blinded request for every disagreement or uncertain review."""

    reviews_by_record = _index_first_pass_reviews(
        loaded_pilot=loaded_pilot,
        completions=completions,
    )
    completion_sha256s = tuple(sorted(item.payload_sha256 for item in completions))
    items: list[EvidenceSelectionExpertPilotAdjudicationItem] = []
    record_id_by_item: dict[str, str] = {}
    for case in loaded_pilot.benchmark.historical_v1.cases:
        for record in case.records:
            reviews = reviews_by_record[record.record_id]
            if not _requires_adjudication(reviews):
                continue
            item_id = (
                "adjudication-"
                + _blind_digest(
                    loaded_pilot.protocol.study_id,
                    record.record_id,
                    "adjudication",
                )[:16]
            )
            review_case_id = (
                "adjudication-case-"
                + _blind_digest(
                    loaded_pilot.protocol.study_id,
                    case.case_id,
                    "adjudication-case",
                )[:16]
            )
            first = reviews[0]
            source_texts = {review.bounded_source_text for review in reviews}
            if len(source_texts) != 1:
                raise ValueError("reviewer packets disagree on bounded source text")
            bounded_source_text = next(iter(source_texts))
            items.append(
                EvidenceSelectionExpertPilotAdjudicationItem(
                    adjudication_item_id=item_id,
                    review_case_id=review_case_id,
                    goal=first.goal,
                    instructions=first.instructions,
                    inclusion_criteria=first.inclusion_criteria,
                    exclusion_criteria=first.exclusion_criteria,
                    title=first.title,
                    bounded_source_text=bounded_source_text,
                    first_pass_findings=tuple(
                        _normalized_finding(review.finding) for review in reviews
                    ),
                )
            )
            record_id_by_item[item_id] = record.record_id
    request = EvidenceSelectionExpertPilotAdjudicationRequest(
        schema_version="evidence_selection_expert_pilot_adjudication_request.v1",
        study_id=loaded_pilot.protocol.study_id,
        pilot_protocol_sha256=loaded_pilot.protocol_sha256,
        evaluation_protocol_sha256=evaluation_protocol_sha256,
        reviewer_registry_payload_sha256=registry.payload_sha256,
        first_pass_completion_sha256s=completion_sha256s,
        completion_status="requires_human_adjudication",
        items=tuple(items),
    )
    return PreparedExpertPilotAdjudication(
        request=request,
        reviews_by_record=reviews_by_record,
        record_id_by_item_id=record_id_by_item,
    )


def load_and_verify_adjudication_completion(
    *,
    path: Path | None,
    prepared: PreparedExpertPilotAdjudication,
    registry: VerifiedExpertPilotRegistry,
    loaded_pilot: LoadedEvidenceSelectionExpertPilot,
) -> VerifiedExpertPilotAdjudication | None:
    """Verify exact disagreement coverage, chronology, spans, and signer role."""

    if not prepared.request.items:
        if path is not None:
            raise ValueError("adjudication completion is forbidden when no items exist")
        return None
    if path is None:
        raise ValueError("adjudication completion is required for unresolved items")
    signed = (
        EvidenceSelectionExpertPilotSignedAdjudicationCompletion.model_validate_json(
            path.read_bytes()
        )
    )
    payload = signed.payload
    credential = registry.credentials_by_slot[loaded_pilot.protocol.adjudicator_slot]
    if (
        payload.study_id,
        payload.adjudicator_slot,
        payload.adjudication_request_sha256,
    ) != (
        loaded_pilot.protocol.study_id,
        loaded_pilot.protocol.adjudicator_slot,
        canonical_payload_sha256(prepared.request),
    ):
        raise ValueError("adjudication completion does not bind the generated request")
    latest_first_pass = max(
        review.completed_at
        for reviews in prepared.reviews_by_record.values()
        for review in reviews
    )
    verify_review_time_and_signature(
        completed_at=payload.completed_at,
        signed_payload=payload,
        signature_hex=signed.signature_hex,
        reviewer_key_id=signed.reviewer_key_id,
        credential=credential,
        registry=registry,
        earliest_time=latest_first_pass,
    )
    expected_ids = tuple(item.adjudication_item_id for item in prepared.request.items)
    finding_ids = tuple(finding.adjudication_item_id for finding in payload.findings)
    if finding_ids != expected_ids:
        raise ValueError("adjudication findings must exactly follow request item order")
    for item, finding in zip(prepared.request.items, payload.findings, strict=True):
        verify_literal_spans(
            supporting_spans=finding.supporting_spans,
            source_text=(
                item.title,
                *(section.text for section in item.bounded_source_text),
            ),
        )
        if (
            finding.selection_label in {"select", "reject"}
            and finding.packet_sufficiency == "sufficient"
            and not finding.supporting_spans
        ):
            raise ValueError("decisive adjudication requires literal supporting spans")
    return VerifiedExpertPilotAdjudication(
        signed_completion=signed,
        payload_sha256=canonical_payload_sha256(payload),
    )


def build_expert_pilot_gold(
    *,
    loaded_pilot: LoadedEvidenceSelectionExpertPilot,
    evaluation_protocol_sha256: str,
    publication: LoadedExpertPilotPublication,
    registry: VerifiedExpertPilotRegistry,
    completions: tuple[VerifiedExpertPilotReviewCompletion, ...],
    prepared: PreparedExpertPilotAdjudication,
    adjudication: VerifiedExpertPilotAdjudication | None,
) -> EvidenceSelectionExpertPilotGoldArtifact:
    """Resolve signed categorical findings into immutable gold and agreement."""

    adjudicated_by_record = {}
    if adjudication is not None:
        adjudicated_by_record = {
            prepared.record_id_by_item_id[finding.adjudication_item_id]: finding
            for finding in adjudication.signed_completion.payload.findings
        }
    records: list[EvidenceSelectionExpertPilotGoldRecord] = []
    agreement_count = 0
    selection_agreement_count = 0
    sufficiency_agreement_count = 0
    for case in loaded_pilot.benchmark.historical_v1.cases:
        for record in case.records:
            reviews = prepared.reviews_by_record[record.record_id]
            normalized = tuple(
                _normalized_finding(review.finding) for review in reviews
            )
            exact_pair_agreement = _finding_pair(reviews[0]) == _finding_pair(
                reviews[1]
            )
            agreement_count += exact_pair_agreement
            selection_agreement_count += (
                reviews[0].finding.selection_label == reviews[1].finding.selection_label
            )
            sufficiency_agreement_count += (
                reviews[0].finding.packet_sufficiency
                == reviews[1].finding.packet_sufficiency
            )
            resolution: Literal["first_pass_agreement", "third_reviewer_adjudication"]
            if _requires_adjudication(reviews):
                finding = adjudicated_by_record.get(record.record_id)
                if finding is None:
                    raise ValueError(
                        "adjudicated gold is missing a required resolution"
                    )
                selection_label = finding.selection_label
                packet_sufficiency = finding.packet_sufficiency
                resolution = "third_reviewer_adjudication"
            else:
                selection_label = reviews[0].finding.selection_label
                packet_sufficiency = reviews[0].finding.packet_sufficiency
                resolution = "first_pass_agreement"
            records.append(
                EvidenceSelectionExpertPilotGoldRecord(
                    case_id=case.case_id,
                    record_id=record.record_id,
                    evaluation_role=case.evaluation_role,
                    selection_label=selection_label,
                    packet_sufficiency=packet_sufficiency,
                    resolution=resolution,
                    score_eligible=(
                        packet_sufficiency == "sufficient"
                        and selection_label in {"select", "reject"}
                    ),
                    first_pass_findings=normalized,
                )
            )
    return EvidenceSelectionExpertPilotGoldArtifact(
        schema_version="evidence_selection_expert_pilot_gold.v1",
        study_id=loaded_pilot.protocol.study_id,
        pilot_protocol_sha256=loaded_pilot.protocol_sha256,
        evaluation_protocol_sha256=evaluation_protocol_sha256,
        publication_manifest_sha256=publication.manifest_sha256,
        reviewer_registry_payload_sha256=registry.payload_sha256,
        first_pass_completion_sha256s=tuple(
            sorted(item.payload_sha256 for item in completions)
        ),
        adjudication_completion_sha256=(
            adjudication.payload_sha256 if adjudication is not None else None
        ),
        total_record_count=len(records),
        score_eligible_record_count=sum(record.score_eligible for record in records),
        first_pass_agreement_count=agreement_count,
        first_pass_selection_agreement_count=selection_agreement_count,
        first_pass_sufficiency_agreement_count=sufficiency_agreement_count,
        first_pass_percent_agreement=agreement_count / len(records),
        first_pass_selection_percent_agreement=(
            selection_agreement_count / len(records)
        ),
        first_pass_sufficiency_percent_agreement=(
            sufficiency_agreement_count / len(records)
        ),
        records=tuple(records),
    )


def _index_first_pass_reviews(
    *,
    loaded_pilot: LoadedEvidenceSelectionExpertPilot,
    completions: tuple[VerifiedExpertPilotReviewCompletion, ...],
) -> dict[str, tuple[_RecordFirstPassReview, ...]]:
    by_record: dict[str, list[_RecordFirstPassReview]] = {}
    slot_order = {
        slot: index
        for index, slot in enumerate(loaded_pilot.protocol.independent_reviewer_slots)
    }
    for completion in completions:
        payload = completion.signed_completion.payload
        packet = completion.bundle.reviewer_packet
        for candidate, binding, finding in zip(
            packet.candidates,
            completion.bundle.machine_sidecar.candidate_bindings,
            payload.findings,
            strict=True,
        ):
            by_record.setdefault(binding.record_id, []).append(
                _RecordFirstPassReview(
                    reviewer_slot=payload.reviewer_slot,
                    case_id=completion.bundle.machine_sidecar.case_id,
                    review_case_id=payload.review_case_id,
                    completion_sha256=completion.payload_sha256,
                    completed_at=payload.completed_at,
                    finding=finding,
                    title=candidate.title,
                    bounded_source_text=candidate.bounded_source_text,
                    goal=packet.goal,
                    instructions=packet.instructions,
                    inclusion_criteria=packet.inclusion_criteria,
                    exclusion_criteria=packet.exclusion_criteria,
                )
            )
    expected_ids = {
        record.record_id
        for case in loaded_pilot.benchmark.historical_v1.cases
        for record in case.records
    }
    if set(by_record) != expected_ids:
        raise ValueError(
            "first-pass reviews do not cover the exact benchmark inventory"
        )
    result = {
        record_id: tuple(
            sorted(reviews, key=lambda item: slot_order[item.reviewer_slot])
        )
        for record_id, reviews in by_record.items()
    }
    if any(
        len(reviews) != _FIRST_PASS_REVIEWER_COUNT
        or {review.reviewer_slot for review in reviews}
        != set(loaded_pilot.protocol.independent_reviewer_slots)
        for reviews in result.values()
    ):
        raise ValueError("every record requires two distinct first-pass reviewer slots")
    return result


def _requires_adjudication(reviews: tuple[_RecordFirstPassReview, ...]) -> bool:
    return (
        _finding_pair(reviews[0]) != _finding_pair(reviews[1])
        or any(review.finding.selection_label == "abstain" for review in reviews)
        or any(
            review.finding.packet_sufficiency == "insufficient" for review in reviews
        )
    )


def _finding_pair(review: _RecordFirstPassReview) -> tuple[str, str]:
    return (
        review.finding.selection_label,
        review.finding.packet_sufficiency,
    )


def _normalized_finding(
    finding: EvidenceSelectionExpertPilotReviewFinding,
) -> EvidenceSelectionExpertPilotFirstPassFinding:
    return EvidenceSelectionExpertPilotFirstPassFinding(
        selection_label=finding.selection_label,
        packet_sufficiency=finding.packet_sufficiency,
        supporting_spans=finding.supporting_spans,
        reviewer_explanation=finding.reviewer_explanation,
    )


def _blind_digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


__all__ = [
    "PreparedExpertPilotAdjudication",
    "VerifiedExpertPilotAdjudication",
    "build_expert_pilot_gold",
    "load_and_verify_adjudication_completion",
    "prepare_expert_pilot_adjudication",
]
