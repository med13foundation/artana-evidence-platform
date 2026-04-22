"""Write-side helpers for hypothesis generation orchestration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.agents.services._hypothesis_generation_support import (
    PathCandidate,
    ScoredCandidate,
    TransferCandidate,
    resolve_validation_state,
)

if TYPE_CHECKING:
    from artana_evidence_db.kernel_domain_models import KernelRelationClaim
    from artana_evidence_db.kernel_services import (
        KernelClaimParticipantService,
        KernelRelationClaimService,
    )

    from src.type_definitions.common import JSONObject


def create_claim_from_candidate(  # noqa: PLR0913
    *,
    relation_claim_service: KernelRelationClaimService,
    claim_participant_service: KernelClaimParticipantService,
    candidate: ScoredCandidate,
    research_space_id: str,
    run_id: str,
    fingerprint: str,
    seed_entity_id: str,
) -> KernelRelationClaim:
    validation_state, validation_reason, persistability = resolve_validation_state(
        relation_allowed=candidate.raw.relation_allowed,
        self_loop=candidate.raw.self_loop,
    )
    source_label = candidate.raw.source_label or candidate.raw.source_entity_id
    target_label = candidate.raw.target_label or candidate.raw.target_entity_id
    claim = relation_claim_service.create_hypothesis_claim(
        research_space_id=research_space_id,
        source_document_id=None,
        agent_run_id=run_id,
        source_type=candidate.raw.source_type,
        relation_type=candidate.raw.relation_type,
        target_type=candidate.raw.target_type,
        source_label=candidate.raw.source_label,
        target_label=candidate.raw.target_label,
        confidence=candidate.score,
        validation_state=validation_state,
        validation_reason=validation_reason,
        persistability=persistability,
        claim_text=(
            f"{source_label} "
            f"{candidate.raw.relation_type.lower().replace('_', ' ')} "
            f"{target_label}"
        ),
        metadata={
            "origin": "graph_agent",
            "run_id": run_id,
            "seed_entity_id": seed_entity_id,
            "candidate_score": round(candidate.score, 6),
            "relation_confidence": round(candidate.raw.relation_confidence, 6),
            "evidence_density": round(candidate.raw.evidence_density, 6),
            "novelty": round(candidate.raw.novelty, 6),
            "relation_diversity": round(candidate.relation_diversity, 6),
            "supporting_provenance_ids": list(candidate.raw.supporting_provenance_ids),
            "supporting_document_count": candidate.raw.supporting_document_count,
            "fingerprint": fingerprint,
            "source_entity_id": candidate.raw.source_entity_id,
            "target_entity_id": candidate.raw.target_entity_id,
            "evidence_summary": candidate.raw.evidence_summary,
            "reasoning": candidate.raw.reasoning,
            "graph_agent_run_id": candidate.raw.graph_agent_run_id,
        },
        claim_status="OPEN",
    )
    create_claim_participants(
        claim_participant_service=claim_participant_service,
        claim_id=str(claim.id),
        research_space_id=research_space_id,
        subject_label=candidate.raw.source_label,
        subject_entity_id=candidate.raw.source_entity_id,
        object_label=candidate.raw.target_label,
        object_entity_id=candidate.raw.target_entity_id,
    )
    return claim


def create_claim_from_path_candidate(  # noqa: PLR0913
    *,
    relation_claim_service: KernelRelationClaimService,
    claim_participant_service: KernelClaimParticipantService,
    candidate: PathCandidate,
    research_space_id: str,
    run_id: str,
    fingerprint: str,
) -> KernelRelationClaim:
    source_label = candidate.source_label or candidate.start_entity_id
    target_label = candidate.target_label or candidate.end_entity_id
    claim = relation_claim_service.create_hypothesis_claim(
        research_space_id=research_space_id,
        source_document_id=None,
        agent_run_id=run_id,
        source_type=candidate.source_type,
        relation_type=candidate.relation_type,
        target_type=candidate.target_type,
        source_label=candidate.source_label,
        target_label=candidate.target_label,
        confidence=candidate.confidence,
        validation_state="ALLOWED",
        validation_reason="derived_from_reasoning_path",
        persistability="NON_PERSISTABLE",
        claim_text=(
            f"{source_label} "
            f"{candidate.relation_type.lower().replace('_', ' ')} "
            f"{target_label}"
        ),
        metadata={
            "origin": "reasoning_path",
            "run_id": run_id,
            "reasoning_path_id": candidate.reasoning_path_id,
            "fingerprint": fingerprint,
            "start_entity_id": candidate.start_entity_id,
            "end_entity_id": candidate.end_entity_id,
            "supporting_claim_ids": list(candidate.supporting_claim_ids),
            "path_confidence": round(candidate.confidence, 6),
            "path_length": candidate.path_length,
        },
        claim_status="OPEN",
    )
    create_claim_participants(
        claim_participant_service=claim_participant_service,
        claim_id=str(claim.id),
        research_space_id=research_space_id,
        subject_label=candidate.source_label,
        subject_entity_id=candidate.start_entity_id,
        object_label=candidate.target_label,
        object_entity_id=candidate.end_entity_id,
    )
    return claim


def create_claim_from_transfer_candidate(  # noqa: PLR0913
    *,
    relation_claim_service: KernelRelationClaimService,
    claim_participant_service: KernelClaimParticipantService,
    candidate: TransferCandidate,
    research_space_id: str,
    run_id: str,
    fingerprint: str,
) -> KernelRelationClaim:
    claim = relation_claim_service.create_hypothesis_claim(
        research_space_id=research_space_id,
        source_document_id=None,
        agent_run_id=run_id,
        source_type=candidate.source_type,
        relation_type=candidate.relation_type,
        target_type=candidate.target_type,
        source_label=candidate.source_label,
        target_label=candidate.target_label,
        confidence=candidate.candidate_score,
        validation_state="ALLOWED",
        validation_reason="derived_from_mechanism_transfer",
        persistability="NON_PERSISTABLE",
        claim_text=(
            f"{candidate.source_label or candidate.start_entity_id} may connect to "
            f"{candidate.target_label or candidate.end_entity_id} through nearby "
            "mechanistically related biology"
        ),
        metadata=_transfer_metadata(
            candidate=candidate,
            run_id=run_id,
            fingerprint=fingerprint,
        ),
        claim_status="OPEN",
    )
    create_claim_participants(
        claim_participant_service=claim_participant_service,
        claim_id=str(claim.id),
        research_space_id=research_space_id,
        subject_label=candidate.source_label,
        subject_entity_id=candidate.start_entity_id,
        object_label=candidate.target_label,
        object_entity_id=candidate.end_entity_id,
    )
    return claim


def create_claim_participants(  # noqa: PLR0913
    *,
    claim_participant_service: KernelClaimParticipantService,
    claim_id: str,
    research_space_id: str,
    subject_label: str | None,
    subject_entity_id: str,
    object_label: str | None,
    object_entity_id: str,
) -> None:
    claim_participant_service.create_participant(
        claim_id=claim_id,
        research_space_id=research_space_id,
        role="SUBJECT",
        label=subject_label,
        entity_id=subject_entity_id,
        position=0,
        qualifiers=None,
    )
    claim_participant_service.create_participant(
        claim_id=claim_id,
        research_space_id=research_space_id,
        role="OBJECT",
        label=object_label,
        entity_id=object_entity_id,
        position=1,
        qualifiers=None,
    )


def _transfer_metadata(
    *,
    candidate: TransferCandidate,
    run_id: str,
    fingerprint: str,
) -> JSONObject:
    return {
        "origin": "mechanism_transfer",
        "run_id": run_id,
        "reasoning_path_id": candidate.reasoning_path_id,
        "fingerprint": fingerprint,
        "start_entity_id": candidate.start_entity_id,
        "end_entity_id": candidate.end_entity_id,
        "source_entity_id": candidate.start_entity_id,
        "target_entity_id": candidate.end_entity_id,
        "supporting_claim_ids": list(candidate.direct_supporting_claim_ids),
        "direct_supporting_claim_ids": list(candidate.direct_supporting_claim_ids),
        "transferred_supporting_claim_ids": list(
            candidate.transferred_supporting_claim_ids,
        ),
        "transferred_from_entities": list(candidate.transferred_from_entity_ids),
        "transferred_from_entity_labels": list(
            candidate.transferred_from_entity_labels,
        ),
        "transfer_basis": list(candidate.transfer_basis),
        "contradiction_claim_ids": list(candidate.contradiction_claim_ids),
        "path_confidence": round(candidate.confidence, 6),
        "path_length": candidate.path_length,
        "candidate_score": round(candidate.candidate_score, 6),
        "direct_support_score": candidate.direct_support_score,
        "transfer_support_score": candidate.transfer_support_score,
        "phenotype_overlap_score": candidate.phenotype_overlap_score,
        "pathway_overlap_score": candidate.pathway_overlap_score,
        "contradiction_penalty": candidate.contradiction_penalty,
        "explanation": candidate.explanation,
    }


__all__ = [
    "create_claim_from_candidate",
    "create_claim_from_path_candidate",
    "create_claim_from_transfer_candidate",
]
