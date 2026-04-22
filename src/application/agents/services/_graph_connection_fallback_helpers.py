"""Fallback relation helpers for graph-connection orchestration."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from src.application.agents.services._fact_assessment_scoring import (
    fact_evidence_weight,
)
from src.domain.agents.contracts.fact_assessment import (
    FactAssessment,
    GroundingLevel,
    MappingStatus,
    SpeculationLevel,
    build_fact_assessment_from_confidence,
)
from src.domain.agents.contracts.graph_connection import (
    ProposedRelation,
    RejectedCandidate,
)
from src.domain.value_objects.relation_types import normalize_relation_type

if TYPE_CHECKING:
    from artana_evidence_db.kernel_repositories import (
        KernelRelationRepository,
    )

_MAX_PROMOTED_REJECTED_CANDIDATES = 3
_MAX_EXTERNAL_FALLBACK_RELATIONS = 8
_MAX_NEIGHBOURHOOD_FALLBACK_RELATIONS = 3
_BLOCKED_GRAPH_FALLBACK_REASONS = frozenset(
    {
        "relation_evidence_span_missing",
        "relation_endpoint_shape_rejected",
    },
)


def _build_graph_fallback_assessment(
    confidence: float,
    *,
    rationale: str,
) -> FactAssessment:
    return build_fact_assessment_from_confidence(
        confidence,
        confidence_rationale=rationale,
        grounding_level=GroundingLevel.GRAPH_INFERENCE,
        mapping_status=MappingStatus.NOT_APPLICABLE,
        speculation_level=SpeculationLevel.NOT_APPLICABLE,
    )


def resolve_relations_for_persistence(
    contract_proposed_relations: tuple[ProposedRelation, ...],
    contract_rejected_candidates: tuple[RejectedCandidate, ...],
    *,
    fallback_relations: tuple[ProposedRelation, ...] = (),
    prefer_fallback: bool = False,
) -> tuple[tuple[ProposedRelation, ...], int, int]:
    """Select relation payloads to persist, with fallback promotion behavior."""
    normalized_fallback_relations = normalize_external_fallback_relations(
        fallback_relations,
    )
    if prefer_fallback and normalized_fallback_relations:
        return normalized_fallback_relations, 0, len(normalized_fallback_relations)
    if contract_proposed_relations:
        return tuple(contract_proposed_relations), 0, 0
    if normalized_fallback_relations:
        return normalized_fallback_relations, 0, len(normalized_fallback_relations)

    promoted: list[ProposedRelation] = []
    sorted_candidates = sorted(
        contract_rejected_candidates,
        key=fact_evidence_weight,
        reverse=True,
    )
    for candidate in sorted_candidates:
        promoted_relation = promote_rejected_candidate(candidate)
        if promoted_relation is None:
            continue
        promoted.append(promoted_relation)
        if len(promoted) >= _MAX_PROMOTED_REJECTED_CANDIDATES:
            break
    return tuple(promoted), len(promoted), 0


def normalize_external_fallback_relations(
    fallback_relations: tuple[ProposedRelation, ...],
) -> tuple[ProposedRelation, ...]:
    """Normalize external fallback relations into persistence-safe payloads."""
    normalized_relations: list[ProposedRelation] = []
    seen_triplets: set[tuple[str, str, str]] = set()
    for relation in fallback_relations:
        source_id = relation.source_id.strip()
        target_id = relation.target_id.strip()
        relation_type = normalize_relation_type(relation.relation_type)
        if not source_id or not target_id or not relation_type:
            continue
        if source_id == target_id:
            continue
        try:
            UUID(source_id)
            UUID(target_id)
        except ValueError:
            continue
        normalized_evidence_summary = relation.evidence_summary.strip()
        normalized_reasoning = relation.reasoning.strip()
        if _contains_blocked_reason(
            normalized_evidence_summary,
        ) or _contains_blocked_reason(
            normalized_reasoning,
        ):
            continue
        triplet = (source_id, relation_type, target_id)
        if triplet in seen_triplets:
            continue
        seen_triplets.add(triplet)
        normalized_relations.append(
            ProposedRelation(
                source_id=source_id,
                relation_type=relation_type,
                target_id=target_id,
                assessment=relation.assessment,
                confidence=min(max(fact_evidence_weight(relation), 0.05), 0.49),
                evidence_summary=(
                    normalized_evidence_summary[:2000]
                    if normalized_evidence_summary
                    else (
                        "Promoted from extraction-stage relation candidate for "
                        "graph fallback review."
                    )
                ),
                evidence_tier="COMPUTATIONAL",
                supporting_provenance_ids=[
                    provenance_id
                    for provenance_id in relation.supporting_provenance_ids
                    if isinstance(provenance_id, str) and provenance_id.strip()
                ][:5],
                supporting_document_count=max(
                    int(relation.supporting_document_count),
                    0,
                ),
                reasoning=(
                    normalized_reasoning[:4000]
                    if normalized_reasoning
                    else (
                        "Fail-open graph fallback using extraction-stage relation "
                        "candidate."
                    )
                ),
            ),
        )
        if len(normalized_relations) >= _MAX_EXTERNAL_FALLBACK_RELATIONS:
            break
    return tuple(normalized_relations)


def promote_rejected_candidate(
    candidate: RejectedCandidate,
) -> ProposedRelation | None:
    """Convert a rejected candidate into a low-confidence fallback relation."""
    if _contains_blocked_reason(candidate.reason):
        return None
    source_id = candidate.source_id.strip()
    target_id = candidate.target_id.strip()
    relation_type = normalize_relation_type(candidate.relation_type)
    if not source_id or not target_id or not relation_type:
        return None
    if source_id == target_id:
        return None
    try:
        UUID(source_id)
        UUID(target_id)
    except ValueError:
        return None

    promoted_confidence = min(max(fact_evidence_weight(candidate), 0.1), 0.49)
    truncated_reason = candidate.reason.strip()[:240]
    evidence_summary = (
        f"Promoted from graph rejected candidate for review: {truncated_reason}"
    )
    return ProposedRelation(
        source_id=source_id,
        relation_type=relation_type,
        target_id=target_id,
        assessment=_build_graph_fallback_assessment(
            promoted_confidence,
            rationale=(
                "Fail-open promotion from rejected candidate to avoid silent graph "
                "drop; human review required."
            ),
        ),
        confidence=promoted_confidence,
        evidence_summary=evidence_summary,
        evidence_tier="COMPUTATIONAL",
        supporting_provenance_ids=[],
        supporting_document_count=0,
        reasoning=(
            "Fail-open promotion from rejected candidate to avoid silent graph "
            "drop; human review required."
        ),
    )


def _contains_blocked_reason(text: str) -> bool:
    normalized_text = text.strip().lower()
    if not normalized_text:
        return False
    return any(
        blocked_reason in normalized_text
        for blocked_reason in _BLOCKED_GRAPH_FALLBACK_REASONS
    )


def build_seed_neighbourhood_fallback_relations(
    relation_repository: KernelRelationRepository,
    *,
    seed_entity_id: str,
) -> tuple[ProposedRelation, ...]:
    """Promote existing seed-neighbourhood relations as fail-open fallback."""
    try:
        neighbourhood = relation_repository.find_neighborhood(
            seed_entity_id,
            depth=1,
            relation_types=None,
        )
    except Exception:  # noqa: BLE001 - never block graph fallback path
        return ()

    fallback_relations: list[ProposedRelation] = []
    seen_triplets: set[tuple[str, str, str]] = set()
    for relation in neighbourhood:
        source_id = str(relation.source_id).strip()
        target_id = str(relation.target_id).strip()
        relation_type = normalize_relation_type(relation.relation_type)
        if not source_id or not target_id or not relation_type:
            continue
        if source_id == target_id:
            continue
        triplet = (source_id, relation_type, target_id)
        if triplet in seen_triplets:
            continue
        seen_triplets.add(triplet)

        aggregate_confidence = float(relation.aggregate_confidence)
        fallback_confidence = min(max(aggregate_confidence, 0.1), 0.35)
        provenance_id = (
            str(relation.provenance_id) if relation.provenance_id is not None else None
        )
        fallback_relations.append(
            ProposedRelation(
                source_id=source_id,
                relation_type=relation_type,
                target_id=target_id,
                assessment=_build_graph_fallback_assessment(
                    fallback_confidence,
                    rationale=(
                        "Fail-open neighbourhood fallback from existing graph edges "
                        "around the seed entity."
                    ),
                ),
                confidence=min(max(fact_evidence_weight(relation), 0.1), 0.35),
                evidence_summary=(
                    "Promoted from existing seed-neighbourhood relation "
                    "to avoid empty graph output; requires review."
                ),
                evidence_tier="COMPUTATIONAL",
                supporting_provenance_ids=(
                    [provenance_id] if provenance_id is not None else []
                ),
                supporting_document_count=1 if provenance_id is not None else 0,
                reasoning=(
                    "Fail-open neighbourhood fallback from existing graph edges "
                    "around the seed entity."
                ),
            ),
        )
        if len(fallback_relations) >= _MAX_NEIGHBOURHOOD_FALLBACK_RELATIONS:
            break
    return tuple(fallback_relations)


__all__ = [
    "build_seed_neighbourhood_fallback_relations",
    "normalize_external_fallback_relations",
    "promote_rejected_candidate",
    "resolve_relations_for_persistence",
]
