"""Proposal staging for validated variant source measurements."""

from __future__ import annotations

from typing import TYPE_CHECKING

from artana_evidence_api.claim_fingerprint import compute_claim_fingerprint
from artana_evidence_api.proposal_store import HarnessProposalDraft
from artana_evidence_api.types.common import JSONObject
from artana_evidence_api.types.evidence_grade import (
    evidence_grade_for_document,
    metadata_with_evidence_grade,
)
from artana_evidence_api.types.graph_fact_assessment import (
    assessment_confidence_weight,
)
from artana_evidence_api.variant_extraction_contracts import (
    ExtractedEntityCandidate,
    ExtractedObservation,
)
from artana_evidence_api.variant_relation_drafts import (
    _entity_candidate_aliases,
    _entity_candidate_payload,
    _normalized_string,
    _variant_candidate_is_persistable,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_store import HarnessDocumentRecord


def build_source_measurement_observation_drafts(
    *,
    document: HarnessDocumentRecord,
    observations: tuple[ExtractedObservation, ...] | list[ExtractedObservation],
    variant_entities: tuple[ExtractedEntityCandidate, ...],
) -> tuple[list[HarnessProposalDraft], list[JSONObject]]:
    """Stage validated measurements whose subjects match extracted variants."""
    drafts: list[HarnessProposalDraft] = []
    skipped_items: list[JSONObject] = []
    for index, observation in enumerate(observations):
        if observation.source_measurement is None:
            continue
        subject_candidate = _matching_observation_subject(
            observation=observation,
            variant_entities=variant_entities,
        )
        if subject_candidate is None:
            skipped_items.append(
                {
                    "kind": "observation_skipped",
                    "field_name": observation.field_name,
                    "variable_id": observation.variable_id,
                    "subject_label": observation.subject_label,
                    "reason": (
                        "Source-measurement observation subject did not match an "
                        "extracted variant candidate."
                    ),
                },
            )
            continue
        drafts.append(
            _build_source_measurement_observation_draft(
                document=document,
                observation=observation,
                subject_candidate=subject_candidate,
                index=index,
            ),
        )
    return drafts, skipped_items


def _matching_observation_subject(
    *,
    observation: ExtractedObservation,
    variant_entities: tuple[ExtractedEntityCandidate, ...],
) -> ExtractedEntityCandidate | None:
    if observation.subject_label is None or not observation.subject_anchors:
        return None
    normalized_label = observation.subject_label.strip().casefold()
    for candidate in variant_entities:
        if not _variant_candidate_is_persistable(candidate):
            continue
        if all(
            candidate.anchors.get(key) == value
            for key, value in observation.subject_anchors.items()
        ):
            return candidate
        candidate_labels = {
            candidate.label.strip().casefold(),
            *(
                alias.strip().casefold()
                for alias in _entity_candidate_aliases(candidate)
                if alias.strip()
            ),
        }
        if normalized_label in candidate_labels and not observation.subject_anchors:
            return candidate
    return None


def _build_source_measurement_observation_draft(
    *,
    document: HarnessDocumentRecord,
    observation: ExtractedObservation,
    subject_candidate: ExtractedEntityCandidate,
    index: int,
) -> HarnessProposalDraft:
    measurement = observation.source_measurement
    if measurement is None:
        msg = "Source-measurement observation draft requires validated provenance."
        raise ValueError(msg)
    candidate_key = _variant_candidate_key(subject_candidate)
    confidence = assessment_confidence_weight(observation.assessment)
    evidence_grade = evidence_grade_for_document(document)
    fingerprint = compute_claim_fingerprint(
        candidate_key,
        observation.variable_id,
        (
            f"{observation.value!s}|unit:"
            f"{(observation.unit or '').strip().casefold()}"
        ),
    )
    return HarnessProposalDraft(
        proposal_type="observation_candidate",
        source_kind="document_extraction",
        source_key=(
            f"{document.id}:source-measurement:{index}:{observation.variable_id}"
        ),
        document_id=document.id,
        title=(
            f"Extracted observation: {observation.field_name} for "
            f"{subject_candidate.label}"
        ),
        summary=measurement.literal_span,
        confidence=confidence,
        ranking_score=confidence,
        reasoning_path={
            "kind": "source_measurement_observation",
            "field_name": observation.field_name,
            "variable_id": observation.variable_id,
            "candidate_key": candidate_key,
            "assessment": observation.assessment.model_dump(mode="json"),
        },
        evidence_bundle=[
            {
                "source_type": document.source_type,
                "locator": measurement.source_locator,
                "excerpt": measurement.literal_span,
                "relevance": confidence,
            },
        ],
        payload={
            "subject_entity_candidate": _entity_candidate_payload(subject_candidate),
            "variable_id": observation.variable_id,
            "field_name": observation.field_name,
            "value": observation.value,
            "unit": observation.unit,
            "evidence_excerpt": measurement.literal_span,
            "evidence_locator": measurement.source_locator,
            "source_measurement": measurement.model_dump(mode="json"),
        },
        metadata=metadata_with_evidence_grade(
            {
                "document_id": document.id,
                "document_title": document.title,
                "document_source_type": document.source_type,
                "candidate_kind": "observation",
                "candidate_key": candidate_key,
                "assessment": observation.assessment.model_dump(mode="json"),
                "subject_label": subject_candidate.label,
                "source_measurement_validated": True,
            },
            evidence_grade,
        ),
        claim_fingerprint=fingerprint,
        evidence_grade=evidence_grade,
    )


def _variant_candidate_key(candidate: ExtractedEntityCandidate) -> str:
    gene_symbol = _normalized_string(candidate.anchors.get("gene_symbol"))
    hgvs_notation = _normalized_string(candidate.anchors.get("hgvs_notation"))
    if gene_symbol is not None and hgvs_notation is not None:
        return f"VARIANT:{gene_symbol}:{hgvs_notation}"
    return f"VARIANT:{candidate.label.strip().lower()}"


__all__ = ["build_source_measurement_observation_drafts"]
