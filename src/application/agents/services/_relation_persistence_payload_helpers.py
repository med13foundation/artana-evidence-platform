"""Payload and text normalization helpers for relation persistence."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.agents.services._fact_assessment_scoring import (
    fact_assessment_payload,
    fact_evidence_weight,
)

if TYPE_CHECKING:
    from src.application.agents.services._extraction_relation_policy_helpers import (
        _ResolvedRelationCandidate,
    )
    from src.domain.agents.contracts.extraction import ExtractedRelation
    from src.type_definitions.common import JSONObject


def normalize_optional_text(raw_value: str | None) -> str | None:
    """Normalize optional text by trimming whitespace."""
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip()
    return normalized or None


def normalize_run_id(run_id: str | None) -> str | None:
    """Normalize optional run ID by trimming whitespace."""
    if run_id is None:
        return None
    normalized = run_id.strip()
    return normalized or None


def relation_payload(relation: ExtractedRelation) -> JSONObject:
    """Build a JSON payload for an extracted relation candidate."""
    payload: JSONObject = {
        "source_type": relation.source_type,
        "relation_type": relation.relation_type,
        "target_type": relation.target_type,
        "polarity": relation.polarity,
        "claim_text": relation.claim_text,
        "claim_section": relation.claim_section,
        "source_label": relation.source_label,
        "target_label": relation.target_label,
        "evidence_excerpt": relation.evidence_excerpt,
        "evidence_locator": relation.evidence_locator,
    }
    if relation.source_anchors:
        payload["source_anchors"] = relation.source_anchors
    if relation.target_anchors:
        payload["target_anchors"] = relation.target_anchors
    assessment = fact_assessment_payload(relation)
    if assessment is not None:
        payload["assessment"] = assessment
    payload["derived_confidence"] = fact_evidence_weight(relation)
    return payload


def candidate_payload(  # noqa: C901
    candidate: _ResolvedRelationCandidate,
) -> JSONObject:
    """Build a JSON payload for a resolved relation candidate."""
    payload: JSONObject = {
        "source_type": candidate.source_type,
        "relation_type": candidate.relation_type,
        "target_type": candidate.target_type,
        "polarity": candidate.polarity,
        "confidence": candidate.confidence,
        "validation_state": candidate.validation_state,
        "validation_reason": candidate.validation_reason,
        "persistability": candidate.persistability,
    }
    if candidate.assessment is not None:
        payload["assessment"] = candidate.assessment
    payload["derived_confidence"] = candidate.confidence
    if candidate.source_entity_id is not None:
        payload["source_entity_id"] = candidate.source_entity_id
    if candidate.target_entity_id is not None:
        payload["target_entity_id"] = candidate.target_entity_id
    if candidate.source_label is not None:
        payload["source_label"] = candidate.source_label
    if candidate.target_label is not None:
        payload["target_label"] = candidate.target_label
    if candidate.source_anchors:
        payload["source_anchors"] = candidate.source_anchors
    if candidate.target_anchors:
        payload["target_anchors"] = candidate.target_anchors
    if candidate.evidence_excerpt is not None:
        payload["evidence_excerpt"] = candidate.evidence_excerpt
    if candidate.evidence_locator is not None:
        payload["evidence_locator"] = candidate.evidence_locator
    if candidate.claim_text is not None:
        payload["claim_text"] = candidate.claim_text
    if candidate.claim_section is not None:
        payload["claim_section"] = candidate.claim_section
    return payload


__all__ = [
    "candidate_payload",
    "normalize_optional_text",
    "normalize_run_id",
    "relation_payload",
]
