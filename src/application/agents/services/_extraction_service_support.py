"""Support types/helpers extracted from extraction_service for size/clarity."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from src.application.agents.services._extraction_outcome_helpers import (
    merge_rejected_relation_details,
    merge_rejected_relation_reasons,
)
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from artana_evidence_db.evidence_sentence_harness_port import (
        EvidenceSentenceHarnessPort,
    )
    from artana_evidence_db.kernel_repositories import (
        KernelClaimEvidenceRepository,
        KernelClaimParticipantRepository,
        KernelEntityRepository,
        KernelRelationClaimRepository,
        KernelRelationProjectionSourceRepository,
        KernelRelationRepository,
    )
    from artana_evidence_db.kernel_services import (
        KernelRelationProjectionMaterializationService,
    )
    from artana_evidence_db.semantic_ports import ConceptPort, DictionaryPort

    from src.application.agents.services._extraction_chunking_helpers import (
        ChunkedExtractionSummary,
    )
    from src.application.agents.services.governance_service import (
        GovernanceDecision,
        GovernanceService,
    )
    from src.application.services.ports.ingestion_pipeline_port import (
        IngestionPipelinePort,
    )
    from src.domain.agents.contracts.extraction import ExtractionContract
    from src.domain.agents.ports.extraction_agent_port import ExtractionAgentPort
    from src.domain.agents.ports.extraction_policy_agent_port import (
        ExtractionPolicyAgentPort,
    )
    from src.domain.agents.ports.mapping_judge_port import MappingJudgePort
    from src.domain.entities.source_document import SourceDocument
    from src.type_definitions.common import JSONObject


@dataclass(frozen=True)
class ExtractionServiceDependencies:
    """Dependencies required by extraction orchestration."""

    extraction_agent: ExtractionAgentPort
    ingestion_pipeline: IngestionPipelinePort
    extraction_policy_agent: ExtractionPolicyAgentPort | None = None
    endpoint_shape_judge: MappingJudgePort | None = None
    concept_merge_judge: MappingJudgePort | None = None
    relation_repository: KernelRelationRepository | None = None
    relation_claim_repository: KernelRelationClaimRepository | None = None
    relation_projection_source_repository: (
        KernelRelationProjectionSourceRepository | None
    ) = None
    relation_projection_materialization_service: (
        KernelRelationProjectionMaterializationService | None
    ) = None
    claim_participant_repository: KernelClaimParticipantRepository | None = None
    claim_evidence_repository: KernelClaimEvidenceRepository | None = None
    entity_repository: KernelEntityRepository | None = None
    dictionary_service: DictionaryPort | None = None
    concept_service: ConceptPort | None = None
    evidence_sentence_harness: EvidenceSentenceHarnessPort | None = None
    governance_service: GovernanceService | None = None
    review_queue_submitter: Callable[[str, str, str | None, str], None] | None = None
    rollback_on_error: Callable[[], None] | None = None


@dataclass(frozen=True)
class ExtractionDocumentOutcome:
    """Outcome of extraction + ingestion for one document."""

    document_id: UUID
    status: Literal["extracted", "failed"]
    reason: str
    review_required: bool
    shadow_mode: bool
    wrote_to_kernel: bool
    run_id: str | None = None
    observations_extracted: int = 0
    relations_extracted: int = 0
    rejected_facts: int = 0
    rejected_relation_reasons: tuple[str, ...] = ()
    rejected_relation_details: tuple[JSONObject, ...] = ()
    ingestion_entities_created: int = 0
    ingestion_observations_created: int = 0
    relation_claims_count: int = 0
    persisted_relations_count: int = 0
    pending_review_relations_count: int = 0
    pending_review_entity_candidates_count: int = 0
    forbidden_relations_count: int = 0
    undefined_relations_count: int = 0
    concept_members_created_count: int = 0
    concept_aliases_created_count: int = 0
    concept_decisions_proposed_count: int = 0
    policy_step_run_id: str | None = None
    policy_proposals_count: int = 0
    relation_type_mapping_proposals_count: int = 0
    relation_synonym_proposals_attempted_count: int = 0
    relation_synonym_proposals_created_count: int = 0
    relation_synonym_proposals_skipped_count: int = 0
    relation_synonym_proposals_failed_count: int = 0
    seed_entity_ids: tuple[str, ...] = ()
    extraction_funnel: JSONObject = field(default_factory=dict)
    errors: tuple[str, ...] = ()


def build_initial_extraction_funnel(
    *,
    contract: ExtractionContract,
    chunk_summary: ChunkedExtractionSummary,
) -> JSONObject:
    return {
        "chunk_mode": chunk_summary.mode,
        "chunk_count": chunk_summary.chunk_count,
        "chunk_successful": chunk_summary.successful_chunks,
        "chunk_failed": chunk_summary.failed_chunks,
        "entity_candidates_generated": len(contract.entities),
        "observation_candidates_generated": len(contract.observations),
        "relation_candidates_generated": len(contract.relations),
        "rejected_facts_generated": len(contract.rejected_facts),
    }


def merge_extraction_funnels(
    *,
    initial_funnel: JSONObject,
    persistence_funnel: JSONObject,
) -> JSONObject:
    merged: JSONObject = {
        str(key): to_json_value(value) for key, value in initial_funnel.items()
    }
    for key, value in persistence_funnel.items():
        merged[str(key)] = to_json_value(value)
    return merged


def review_priority_for_reason(reason: str) -> str:
    if reason in {
        "agent_requested_escalation",
        "evidence_required",
        "entity_candidate_missing_required_anchors",
    }:
        return "high"
    if reason in {"confidence_below_threshold", "entity_candidate_requires_review"}:
        return "medium"
    return "low"


def normalize_seed_entity_ids(seed_entity_ids: list[str]) -> tuple[str, ...]:
    normalized_ids: list[str] = []
    for seed_entity_id in seed_entity_ids:
        normalized = seed_entity_id.strip()
        if not normalized or normalized in normalized_ids:
            continue
        normalized_ids.append(normalized)
    return tuple(normalized_ids)


def build_extraction_outcome(  # noqa: PLR0913
    *,
    document: SourceDocument,
    contract: ExtractionContract,
    governance: GovernanceDecision,
    run_id: str | None,
    wrote_to_kernel: bool,
    reason: str,
    ingestion_entities_created: int = 0,
    ingestion_observations_created: int = 0,
    relation_claims_count: int = 0,
    persisted_relations_count: int = 0,
    pending_review_relations_count: int = 0,
    pending_review_entity_candidates_count: int = 0,
    forbidden_relations_count: int = 0,
    undefined_relations_count: int = 0,
    concept_members_created_count: int = 0,
    concept_aliases_created_count: int = 0,
    concept_decisions_proposed_count: int = 0,
    policy_step_run_id: str | None = None,
    policy_proposals_count: int = 0,
    relation_type_mapping_proposals_count: int = 0,
    relation_synonym_proposals_attempted_count: int = 0,
    relation_synonym_proposals_created_count: int = 0,
    relation_synonym_proposals_skipped_count: int = 0,
    relation_synonym_proposals_failed_count: int = 0,
    relation_rejected_reasons: tuple[str, ...] = (),
    relation_rejected_details: tuple[JSONObject, ...] = (),
    seed_entity_ids: tuple[str, ...] = (),
    extraction_funnel: JSONObject | None = None,
    errors: tuple[str, ...] = (),
    status_override: Literal["extracted", "failed"] | None = None,
) -> ExtractionDocumentOutcome:
    status: Literal["extracted", "failed"] = (
        status_override
        if status_override is not None
        else ("extracted" if wrote_to_kernel or governance.shadow_mode else "failed")
    )
    return ExtractionDocumentOutcome(
        document_id=document.id,
        status=status,
        reason=reason,
        review_required=governance.requires_review,
        shadow_mode=governance.shadow_mode,
        wrote_to_kernel=wrote_to_kernel,
        run_id=run_id,
        observations_extracted=len(contract.observations),
        relations_extracted=len(contract.relations),
        rejected_facts=len(contract.rejected_facts),
        rejected_relation_reasons=(
            merge_rejected_relation_reasons(
                contract,
                relation_rejected_reasons,
            )
        ),
        rejected_relation_details=(
            merge_rejected_relation_details(
                contract,
                relation_rejected_details,
            )
        ),
        ingestion_entities_created=ingestion_entities_created,
        ingestion_observations_created=ingestion_observations_created,
        relation_claims_count=relation_claims_count,
        persisted_relations_count=persisted_relations_count,
        pending_review_relations_count=pending_review_relations_count,
        pending_review_entity_candidates_count=(
            pending_review_entity_candidates_count
        ),
        forbidden_relations_count=forbidden_relations_count,
        undefined_relations_count=undefined_relations_count,
        concept_members_created_count=concept_members_created_count,
        concept_aliases_created_count=concept_aliases_created_count,
        concept_decisions_proposed_count=concept_decisions_proposed_count,
        policy_step_run_id=policy_step_run_id,
        policy_proposals_count=policy_proposals_count,
        relation_type_mapping_proposals_count=relation_type_mapping_proposals_count,
        relation_synonym_proposals_attempted_count=(
            relation_synonym_proposals_attempted_count
        ),
        relation_synonym_proposals_created_count=(
            relation_synonym_proposals_created_count
        ),
        relation_synonym_proposals_skipped_count=(
            relation_synonym_proposals_skipped_count
        ),
        relation_synonym_proposals_failed_count=(
            relation_synonym_proposals_failed_count
        ),
        seed_entity_ids=seed_entity_ids,
        extraction_funnel=extraction_funnel or {},
        errors=errors,
    )


__all__ = [
    "ExtractionDocumentOutcome",
    "ExtractionServiceDependencies",
    "build_extraction_outcome",
    "build_initial_extraction_funnel",
    "merge_extraction_funnels",
    "normalize_seed_entity_ids",
    "review_priority_for_reason",
]
