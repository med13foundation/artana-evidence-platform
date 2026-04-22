from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, NoReturn

from artana_evidence_db.kernel_domain_models import (
    EvidenceSentenceGenerationRequest,
    EvidenceSentenceGenerationResult,
)
from sqlalchemy.exc import SQLAlchemyError

from src.application.agents.services._extraction_relation_auto_resolve_helpers import (
    _ExtractionRelationAutoResolveHelpers,
)
from src.application.agents.services._extraction_relation_candidate_write_flow import (
    _PersistCandidatesResult,
    persist_relation_candidates,
)
from src.application.agents.services._extraction_relation_canonicalization_helpers import (
    _ExtractionRelationCanonicalizationHelpers,
)
from src.application.agents.services._extraction_relation_full_auto_helpers import (
    _ExtractionRelationFullAutoHelpers,
)
from src.application.agents.services._extraction_relation_policy_helpers import (
    RelationClaimPolarity,
    _ExtractionRelationPolicyHelpers,
    _ResolvedRelationCandidate,
)
from src.application.agents.services._relation_endpoint_entity_resolution_helpers import (
    EndpointEntityResolutionResult,
    _RelationEndpointEntityResolutionHelpers,
)
from src.application.agents.services._relation_evidence_span_helpers import (
    append_span_to_summary,
    resolve_relation_evidence_span,
)
from src.application.agents.services._relation_persistence_shared_helpers import (
    fact_assessment_payload,
    fact_evidence_weight,
    normalize_optional_text,
    normalize_run_id,
    relation_payload,
)
from src.application.services.claim_first_metrics import (
    emit_claim_first_extraction_metrics,
    increment_metric,
)
from src.domain.value_objects.relation_types import normalize_relation_type
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from collections.abc import Callable

    from artana_evidence_db.evidence_sentence_harness_port import (
        EvidenceSentenceHarnessPort,
    )
    from artana_evidence_db.kernel_domain_models import (
        ClaimEvidenceSentenceConfidence,
        ClaimEvidenceSentenceSource,
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
    from artana_evidence_db.semantic_ports import ConceptPort

    from src.application.agents.services._extraction_relation_policy_helpers import (
        RelationGovernanceMode,
    )
    from src.domain.agents.contracts.extraction import (
        ExtractedEntityCandidate,
        ExtractedRelation,
        ExtractionContract,
    )
    from src.domain.agents.contracts.extraction_policy import (
        ExtractionPolicyContract,
        RelationConstraintProposal,
        RelationTypeMappingProposal,
    )
    from src.domain.agents.ports.mapping_judge_port import MappingJudgePort
    from src.domain.entities.source_document import SourceDocument
    from src.type_definitions.common import JSONObject, ResearchSpaceSettings

logger = logging.getLogger(__name__)
_MIN_GENERATED_EVIDENCE_SENTENCE_LENGTH = 24


def _normalize_claim_polarity_value(raw_polarity: str) -> RelationClaimPolarity:
    normalized = raw_polarity.strip().upper()
    if normalized == "SUPPORT":
        return "SUPPORT"
    if normalized == "REFUTE":
        return "REFUTE"
    if normalized == "HYPOTHESIS":
        return "HYPOTHESIS"
    return "UNCERTAIN"


def _normalize_claim_evidence_sentence_source(
    source: str | None,
) -> ClaimEvidenceSentenceSource | None:
    if source == "verbatim_span":
        return "verbatim_span"
    if source == "artana_generated":
        return "artana_generated"
    return None


def _normalize_claim_evidence_sentence_confidence(
    confidence: str | None,
) -> ClaimEvidenceSentenceConfidence | None:
    if confidence == "low":
        return "low"
    if confidence == "medium":
        return "medium"
    if confidence == "high":
        return "high"
    return None


def _raise_missing_projection_lineage_support() -> NoReturn:
    msg = "Claim-backed extraction persistence requires projection lineage support"
    raise ValueError(msg)


def _raise_missing_materialized_relation() -> NoReturn:
    msg = "Resolved support claim did not materialize a canonical relation"
    raise ValueError(msg)


@dataclass(frozen=True)
class RelationPersistenceResult:
    persisted_relations_count: int = 0
    pending_review_relations_count: int = 0
    relation_claims_count: int = 0
    claim_evidence_rows_created_count: int = 0
    non_persistable_claims_count: int = 0
    forbidden_relations_count: int = 0
    undefined_relations_count: int = 0
    concept_members_created_count: int = 0
    concept_aliases_created_count: int = 0
    concept_decisions_proposed_count: int = 0
    policy_proposals_count: int = 0
    relation_type_mapping_proposals_count: int = 0
    relation_synonym_proposals_attempted_count: int = 0
    relation_synonym_proposals_created_count: int = 0
    relation_synonym_proposals_skipped_count: int = 0
    relation_synonym_proposals_failed_count: int = 0
    policy_run_id: str | None = None
    rejected_relation_reasons: tuple[str, ...] = ()
    rejected_relation_details: tuple[JSONObject, ...] = ()
    funnel: JSONObject = field(default_factory=dict)
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class _CandidateBuildResult:
    candidates: tuple[_ResolvedRelationCandidate, ...] = ()
    rejected_relation_reasons: tuple[str, ...] = ()
    rejected_relation_details: tuple[JSONObject, ...] = ()
    invalid_components_count: int = 0
    endpoint_resolution_failed_count: int = 0
    endpoint_shape_rejected_count: int = 0
    self_loop_count: int = 0
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class _RelationWriteOutcome:
    persisted_relations_count: int = 0
    pending_review_relations_count: int = 0
    relation_claims_count_delta: int = 0
    claim_evidence_rows_created_count_delta: int = 0
    relation_claims_queued_for_review_count: int = 0
    persistence_failed_count: int = 0
    errors: tuple[str, ...] = ()


class _ExtractionRelationPersistenceHelpers(
    _ExtractionRelationAutoResolveHelpers,
    _ExtractionRelationCanonicalizationHelpers,
    _ExtractionRelationFullAutoHelpers,
    _RelationEndpointEntityResolutionHelpers,
    _ExtractionRelationPolicyHelpers,
):
    _relations: KernelRelationRepository | None
    _relation_claims: KernelRelationClaimRepository | None
    _relation_projection_sources: KernelRelationProjectionSourceRepository | None
    _materializer: KernelRelationProjectionMaterializationService | None
    _claim_participants: KernelClaimParticipantRepository | None
    _claim_evidences: KernelClaimEvidenceRepository | None
    _entities: KernelEntityRepository | None
    _concepts: ConceptPort | None
    _evidence_sentence_harness: EvidenceSentenceHarnessPort | None
    _concept_merge_judge: MappingJudgePort | None
    _rollback_on_error: Callable[[], None] | None

    async def _persist_extracted_relations(
        self,
        *,
        document: SourceDocument,
        contract: ExtractionContract,
        research_space_settings: ResearchSpaceSettings,
        publication_entity_ids: tuple[str, ...],
        model_id: str | None,
    ) -> RelationPersistenceResult:
        started_at = datetime.now(UTC)
        run_id = normalize_run_id(contract.agent_run_id)
        if document.research_space_id is None:
            return RelationPersistenceResult(
                errors=("relation_persistence_missing_research_space_id",),
            )
        research_space_id = str(document.research_space_id)
        relation_governance_mode = self._resolve_relation_governance_mode(
            research_space_settings,
        )
        if not contract.relations:
            return RelationPersistenceResult()
        if self._relations is None or self._entities is None:
            return RelationPersistenceResult(
                errors=("relation_persistence_unavailable",),
            )

        logger.info(
            "Extraction relation persistence helper started",
            extra={
                "document_id": str(document.id),
                "run_id": run_id,
                "research_space_id": research_space_id,
                "relation_candidates_input_count": len(contract.relations),
                "publication_entity_ids_count": len(publication_entity_ids),
                "relation_governance_mode": relation_governance_mode,
            },
        )

        publication_entity_id = (
            publication_entity_ids[0] if publication_entity_ids else None
        )
        candidate_build_started_at = datetime.now(UTC)
        candidate_build = self._build_relation_candidates(
            research_space_id=research_space_id,
            relations=contract.relations,
            entity_candidates=contract.entities,
            publication_entity_id=publication_entity_id,
        )
        logger.info(
            "Extraction relation candidates built",
            extra={
                "document_id": str(document.id),
                "run_id": run_id,
                "duration_ms": int(
                    (datetime.now(UTC) - candidate_build_started_at).total_seconds()
                    * 1000,
                ),
                "candidates_count": len(candidate_build.candidates),
                "invalid_components_count": candidate_build.invalid_components_count,
                "endpoint_resolution_failed_count": (
                    candidate_build.endpoint_resolution_failed_count
                ),
                "endpoint_shape_rejected_count": (
                    candidate_build.endpoint_shape_rejected_count
                ),
                "self_loop_count": candidate_build.self_loop_count,
                "error_count": len(candidate_build.errors),
            },
        )
        unknown_patterns = self._build_unknown_relation_patterns(
            candidate_build.candidates,
        )
        policy_step_started_at = datetime.now(UTC)
        policy_step = await self._run_policy_step(
            research_space_id=research_space_id,
            document=document,
            source_type=contract.source_type,
            unknown_patterns=unknown_patterns,
            model_id=model_id,
        )
        logger.info(
            "Extraction relation policy step finished",
            extra={
                "document_id": str(document.id),
                "run_id": run_id,
                "duration_ms": int(
                    (datetime.now(UTC) - policy_step_started_at).total_seconds() * 1000,
                ),
                "unknown_patterns_count": len(unknown_patterns),
                "policy_contract_present": policy_step.contract is not None,
                "error_count": len(policy_step.errors),
            },
        )
        proposal_store_started_at = datetime.now(UTC)
        proposal_store_result = self._store_policy_constraint_proposals(
            research_space_id=research_space_id,
            document=document,
            policy_contract=policy_step.contract,
            policy_run_id=normalize_run_id(
                (
                    policy_step.contract.agent_run_id
                    if policy_step.contract is not None
                    else None
                ),
            ),
            relation_governance_mode=relation_governance_mode,
        )
        logger.info(
            "Extraction relation policy proposals stored",
            extra={
                "document_id": str(document.id),
                "run_id": run_id,
                "duration_ms": int(
                    (datetime.now(UTC) - proposal_store_started_at).total_seconds()
                    * 1000,
                ),
                "proposal_count": (
                    proposal_store_result.constraint_proposals_created_count
                ),
                "relation_type_mapping_proposals_count": (
                    proposal_store_result.relation_type_mapping_proposals_count
                ),
                "relation_synonym_proposals_attempted_count": (
                    proposal_store_result.relation_synonym_proposals_attempted_count
                ),
                "relation_synonym_proposals_created_count": (
                    proposal_store_result.relation_synonym_proposals_created_count
                ),
                "relation_synonym_proposals_skipped_count": (
                    proposal_store_result.relation_synonym_proposals_skipped_count
                ),
                "relation_synonym_proposals_failed_count": (
                    proposal_store_result.relation_synonym_proposals_failed_count
                ),
                "error_count": len(proposal_store_result.errors),
            },
        )
        persist_candidates_started_at = datetime.now(UTC)
        persist_result = self._persist_relation_candidates(
            document=document,
            run_id=run_id,
            candidates=candidate_build.candidates,
            policy_contract=policy_step.contract,
            relation_governance_mode=relation_governance_mode,
            research_space_settings=research_space_settings,
        )
        logger.info(
            "Extraction relation candidates persisted",
            extra={
                "document_id": str(document.id),
                "run_id": run_id,
                "duration_ms": int(
                    (datetime.now(UTC) - persist_candidates_started_at).total_seconds()
                    * 1000,
                ),
                "persisted_relations_count": persist_result.persisted_relations_count,
                "pending_review_relations_count": (
                    persist_result.pending_review_relations_count
                ),
                "relation_claims_count": persist_result.relation_claims_count,
                "claim_evidence_rows_created_count": (
                    persist_result.claim_evidence_rows_created_count
                ),
                "non_persistable_claims_count": (
                    persist_result.non_persistable_claims_count
                ),
                "evidence_span_missing_count": (
                    persist_result.evidence_span_missing_count
                ),
                "forbidden_relations_count": persist_result.forbidden_relations_count,
                "undefined_relations_count": persist_result.undefined_relations_count,
                "concept_members_created_count": (
                    persist_result.concept_members_created_count
                ),
                "concept_aliases_created_count": (
                    persist_result.concept_aliases_created_count
                ),
                "concept_decisions_proposed_count": (
                    persist_result.concept_decisions_proposed_count
                ),
                "persistence_failed_count": persist_result.persistence_failed_count,
                "full_auto_retry_skipped_count": (
                    persist_result.full_auto_retry_skipped_count
                ),
                "error_count": len(persist_result.errors),
            },
        )
        emit_claim_first_extraction_metrics(
            research_space_id=research_space_id,
            source_document_id=str(document.id),
            claims_created=persist_result.relation_claims_count,
            claims_non_persistable=persist_result.non_persistable_claims_count,
            relations_draft_created=persist_result.persisted_relations_count,
            relation_claims_queued_for_review=(
                persist_result.relation_claims_queued_for_review_count
            ),
            claim_evidence_rows_created=persist_result.claim_evidence_rows_created_count,
            research_space_settings=research_space_settings,
        )
        logger.info(
            "Extraction relation persistence helper finished",
            extra={
                "document_id": str(document.id),
                "run_id": run_id,
                "duration_ms": int(
                    (datetime.now(UTC) - started_at).total_seconds() * 1000,
                ),
                "relation_candidates_input_count": len(contract.relations),
                "relation_claims_count": persist_result.relation_claims_count,
                "claim_evidence_rows_created_count": (
                    persist_result.claim_evidence_rows_created_count
                ),
                "persisted_relations_count": persist_result.persisted_relations_count,
                "non_persistable_claims_count": (
                    persist_result.non_persistable_claims_count
                ),
                "concept_members_created_count": (
                    persist_result.concept_members_created_count
                ),
                "concept_aliases_created_count": (
                    persist_result.concept_aliases_created_count
                ),
                "concept_decisions_proposed_count": (
                    persist_result.concept_decisions_proposed_count
                ),
                "full_auto_retry_skipped_count": (
                    persist_result.full_auto_retry_skipped_count
                ),
                "total_error_count": len(
                    candidate_build.errors
                    + policy_step.errors
                    + proposal_store_result.errors
                    + persist_result.errors,
                ),
            },
        )
        return RelationPersistenceResult(
            persisted_relations_count=persist_result.persisted_relations_count,
            pending_review_relations_count=persist_result.pending_review_relations_count,
            relation_claims_count=persist_result.relation_claims_count,
            claim_evidence_rows_created_count=(
                persist_result.claim_evidence_rows_created_count
            ),
            non_persistable_claims_count=persist_result.non_persistable_claims_count,
            forbidden_relations_count=persist_result.forbidden_relations_count,
            undefined_relations_count=persist_result.undefined_relations_count,
            concept_members_created_count=persist_result.concept_members_created_count,
            concept_aliases_created_count=persist_result.concept_aliases_created_count,
            concept_decisions_proposed_count=(
                persist_result.concept_decisions_proposed_count
            ),
            policy_proposals_count=(
                proposal_store_result.constraint_proposals_created_count
            ),
            relation_type_mapping_proposals_count=(
                proposal_store_result.relation_type_mapping_proposals_count
            ),
            relation_synonym_proposals_attempted_count=(
                proposal_store_result.relation_synonym_proposals_attempted_count
            ),
            relation_synonym_proposals_created_count=(
                proposal_store_result.relation_synonym_proposals_created_count
            ),
            relation_synonym_proposals_skipped_count=(
                proposal_store_result.relation_synonym_proposals_skipped_count
            ),
            relation_synonym_proposals_failed_count=(
                proposal_store_result.relation_synonym_proposals_failed_count
            ),
            policy_run_id=normalize_run_id(
                (
                    policy_step.contract.agent_run_id
                    if policy_step.contract is not None
                    else None
                ),
            ),
            rejected_relation_reasons=self._merge_unique_reasons(
                candidate_build.rejected_relation_reasons,
                persist_result.rejected_relation_reasons,
            ),
            rejected_relation_details=(
                candidate_build.rejected_relation_details
                + persist_result.rejected_relation_details
            ),
            funnel={
                "relation_candidates_generated": len(contract.relations),
                "relation_candidates_after_prevalidation": len(
                    candidate_build.candidates,
                ),
                "relation_candidates_prevalidation_rejected": (
                    candidate_build.invalid_components_count
                    + candidate_build.endpoint_resolution_failed_count
                    + candidate_build.self_loop_count
                ),
                "relation_candidates_invalid_components": (
                    candidate_build.invalid_components_count
                ),
                "relation_candidates_endpoint_resolution_failed": (
                    candidate_build.endpoint_resolution_failed_count
                ),
                "relation_candidates_endpoint_shape_rejected": (
                    candidate_build.endpoint_shape_rejected_count
                ),
                "relation_candidates_self_loop": candidate_build.self_loop_count,
                "relation_candidates_evidence_span_missing": (
                    persist_result.evidence_span_missing_count
                ),
                "relation_candidates_forbidden": (
                    persist_result.forbidden_relations_count
                ),
                "relation_candidates_undefined": (
                    persist_result.undefined_relations_count
                ),
                "concept_members_created": (
                    persist_result.concept_members_created_count
                ),
                "concept_aliases_created": (
                    persist_result.concept_aliases_created_count
                ),
                "concept_decisions_proposed": (
                    persist_result.concept_decisions_proposed_count
                ),
                "relation_claims_created": persist_result.relation_claims_count,
                "claim_evidence_rows_created": (
                    persist_result.claim_evidence_rows_created_count
                ),
                "relation_claims_queued_for_review": (
                    persist_result.relation_claims_queued_for_review_count
                ),
                "relation_claims_non_persistable": (
                    persist_result.non_persistable_claims_count
                ),
                "relation_candidates_persisted": (
                    persist_result.persisted_relations_count
                ),
                "relation_candidates_pending_review": (
                    persist_result.pending_review_relations_count
                ),
                "relation_candidates_persistence_failed": (
                    persist_result.persistence_failed_count
                ),
                "relation_candidates_full_auto_retry_skipped": (
                    persist_result.full_auto_retry_skipped_count
                ),
                "relation_policy_unknown_patterns": len(unknown_patterns),
                "relation_policy_proposals_created": (
                    proposal_store_result.constraint_proposals_created_count
                ),
                "relation_type_mapping_proposals": (
                    proposal_store_result.relation_type_mapping_proposals_count
                ),
                "relation_synonym_proposals_attempted": (
                    proposal_store_result.relation_synonym_proposals_attempted_count
                ),
                "relation_synonym_proposals_created": (
                    proposal_store_result.relation_synonym_proposals_created_count
                ),
                "relation_synonym_proposals_skipped": (
                    proposal_store_result.relation_synonym_proposals_skipped_count
                ),
                "relation_synonym_proposals_failed": (
                    proposal_store_result.relation_synonym_proposals_failed_count
                ),
            },
            errors=(
                candidate_build.errors
                + policy_step.errors
                + proposal_store_result.errors
                + persist_result.errors
            ),
        )

    def _build_relation_candidates(
        self,
        *,
        research_space_id: str,
        relations: list[ExtractedRelation],
        entity_candidates: list[ExtractedEntityCandidate],
        publication_entity_id: str | None,
    ) -> _CandidateBuildResult:
        candidates: list[_ResolvedRelationCandidate] = []
        rejected_reasons: list[str] = []
        rejected_details: list[JSONObject] = []
        errors: list[str] = []
        invalid_components_count = 0
        endpoint_resolution_failed_count = 0
        endpoint_shape_rejected_count = 0
        self_loop_count = 0
        entity_candidate_index = self._build_extracted_entity_candidate_index(
            entity_candidates,
        )

        for relation in relations:
            normalized_source_type = self._normalize_component(relation.source_type)
            normalized_relation_type = normalize_relation_type(relation.relation_type)
            normalized_target_type = self._normalize_component(relation.target_type)
            normalized_source_label = normalize_optional_text(relation.source_label)
            normalized_target_label = normalize_optional_text(relation.target_label)
            normalized_source_anchors = self._resolve_relation_endpoint_anchors(
                relation=relation,
                endpoint_name="source",
                entity_candidate_index=entity_candidate_index,
            )
            normalized_target_anchors = self._resolve_relation_endpoint_anchors(
                relation=relation,
                endpoint_name="target",
                entity_candidate_index=entity_candidate_index,
            )
            normalized_polarity = _normalize_claim_polarity_value(relation.polarity)
            normalized_claim_text = normalize_optional_text(relation.claim_text)
            normalized_claim_section = normalize_optional_text(relation.claim_section)
            normalized_evidence_excerpt = normalize_optional_text(
                relation.evidence_excerpt,
            )
            normalized_evidence_locator = normalize_optional_text(
                relation.evidence_locator,
            )
            payload = relation_payload(relation)

            if (
                not normalized_source_type
                or not normalized_relation_type
                or not normalized_target_type
            ):
                self._record_rejected_relation(
                    reasons=rejected_reasons,
                    details=rejected_details,
                    reason="invalid_relation_components",
                    payload=payload,
                    metadata={
                        "validation_state": "INVALID_COMPONENTS",
                        "validation_reason": (
                            "source_type, relation_type, and target_type are required"
                        ),
                    },
                )
                errors.append("relation_persistence_skipped_invalid_components")
                candidates.append(
                    _ResolvedRelationCandidate(
                        source_entity_id=None,
                        target_entity_id=None,
                        source_type=normalized_source_type or "UNKNOWN",
                        relation_type=normalized_relation_type or "UNKNOWN",
                        target_type=normalized_target_type or "UNKNOWN",
                        source_label=normalized_source_label,
                        target_label=normalized_target_label,
                        source_anchors=normalized_source_anchors or None,
                        target_anchors=normalized_target_anchors or None,
                        confidence=fact_evidence_weight(relation),
                        assessment=fact_assessment_payload(relation),
                        validation_state="INVALID_COMPONENTS",
                        validation_reason=(
                            "source_type, relation_type, and target_type are required"
                        ),
                        evidence_excerpt=normalized_evidence_excerpt,
                        evidence_locator=normalized_evidence_locator,
                        polarity=normalized_polarity,
                        claim_text=normalized_claim_text,
                        claim_section=normalized_claim_section,
                        persistability="NON_PERSISTABLE",
                    ),
                )
                invalid_components_count += 1
                continue

            source_resolution = self._resolve_relation_endpoint_entity_id(
                research_space_id=research_space_id,
                entity_type=normalized_source_type,
                label=relation.source_label,
                anchors=normalized_source_anchors,
                publication_entity_id=publication_entity_id,
                endpoint_name="source",
            )
            target_resolution = self._resolve_relation_endpoint_entity_id(
                research_space_id=research_space_id,
                entity_type=normalized_target_type,
                label=relation.target_label,
                anchors=normalized_target_anchors,
                publication_entity_id=publication_entity_id,
                endpoint_name="target",
            )
            source_entity_id = source_resolution.entity_id
            target_entity_id = target_resolution.entity_id
            if source_entity_id is None or target_entity_id is None:
                (
                    rejection_reason,
                    validation_reason,
                    rejection_metadata,
                ) = self._build_endpoint_resolution_rejection(
                    source_resolution=source_resolution,
                    target_resolution=target_resolution,
                )
                self._record_rejected_relation(
                    reasons=rejected_reasons,
                    details=rejected_details,
                    reason=rejection_reason,
                    payload=payload,
                    metadata=rejection_metadata,
                )
                errors.append(
                    (
                        "relation_persistence_skipped:"
                        f"{normalized_source_type}:{normalized_relation_type}:"
                        f"{normalized_target_type}"
                    ),
                )
                candidates.append(
                    _ResolvedRelationCandidate(
                        source_entity_id=source_entity_id,
                        target_entity_id=target_entity_id,
                        source_type=normalized_source_type,
                        relation_type=normalized_relation_type,
                        target_type=normalized_target_type,
                        source_label=normalized_source_label,
                        target_label=normalized_target_label,
                        source_anchors=normalized_source_anchors or None,
                        target_anchors=normalized_target_anchors or None,
                        confidence=fact_evidence_weight(relation),
                        assessment=fact_assessment_payload(relation),
                        validation_state="ENDPOINT_UNRESOLVED",
                        validation_reason=validation_reason,
                        evidence_excerpt=normalized_evidence_excerpt,
                        evidence_locator=normalized_evidence_locator,
                        polarity=normalized_polarity,
                        claim_text=normalized_claim_text,
                        claim_section=normalized_claim_section,
                        persistability="NON_PERSISTABLE",
                    ),
                )
                endpoint_resolution_failed_count += 1
                if rejection_reason == "relation_endpoint_shape_rejected":
                    endpoint_shape_rejected_count += 1
                continue
            if source_entity_id == target_entity_id:
                self._record_rejected_relation(
                    reasons=rejected_reasons,
                    details=rejected_details,
                    reason="relation_self_loop",
                    payload=payload,
                    metadata={
                        "validation_state": "SELF_LOOP",
                        "validation_reason": "self-loop relations are not allowed",
                    },
                )
                candidates.append(
                    _ResolvedRelationCandidate(
                        source_entity_id=source_entity_id,
                        target_entity_id=target_entity_id,
                        source_type=normalized_source_type,
                        relation_type=normalized_relation_type,
                        target_type=normalized_target_type,
                        source_label=normalized_source_label,
                        target_label=normalized_target_label,
                        source_anchors=normalized_source_anchors or None,
                        target_anchors=normalized_target_anchors or None,
                        confidence=fact_evidence_weight(relation),
                        assessment=fact_assessment_payload(relation),
                        validation_state="SELF_LOOP",
                        validation_reason="self-loop relations are not allowed",
                        evidence_excerpt=normalized_evidence_excerpt,
                        evidence_locator=normalized_evidence_locator,
                        polarity=normalized_polarity,
                        claim_text=normalized_claim_text,
                        claim_section=normalized_claim_section,
                        persistability="NON_PERSISTABLE",
                    ),
                )
                self_loop_count += 1
                continue

            validation_state, validation_reason = (
                self._resolve_relation_validation_state(
                    source_type=normalized_source_type,
                    relation_type=normalized_relation_type,
                    target_type=normalized_target_type,
                )
            )
            candidates.append(
                _ResolvedRelationCandidate(
                    source_entity_id=source_entity_id,
                    target_entity_id=target_entity_id,
                    source_type=normalized_source_type,
                    relation_type=normalized_relation_type,
                    target_type=normalized_target_type,
                    source_label=normalized_source_label,
                    target_label=normalized_target_label,
                    source_anchors=normalized_source_anchors or None,
                    target_anchors=normalized_target_anchors or None,
                    confidence=fact_evidence_weight(relation),
                    assessment=fact_assessment_payload(relation),
                    validation_state=validation_state,
                    validation_reason=validation_reason,
                    evidence_excerpt=normalized_evidence_excerpt,
                    evidence_locator=normalized_evidence_locator,
                    polarity=normalized_polarity,
                    claim_text=normalized_claim_text,
                    claim_section=normalized_claim_section,
                    persistability="PERSISTABLE",
                ),
            )

        return _CandidateBuildResult(
            candidates=tuple(candidates),
            rejected_relation_reasons=tuple(rejected_reasons),
            rejected_relation_details=tuple(rejected_details),
            invalid_components_count=invalid_components_count,
            endpoint_resolution_failed_count=endpoint_resolution_failed_count,
            endpoint_shape_rejected_count=endpoint_shape_rejected_count,
            self_loop_count=self_loop_count,
            errors=tuple(errors),
        )

    @staticmethod
    def _build_extracted_entity_candidate_index(
        entity_candidates: list[ExtractedEntityCandidate],
    ) -> dict[tuple[str, str], ExtractedEntityCandidate | None]:
        index: dict[tuple[str, str], ExtractedEntityCandidate | None] = {}
        for candidate in entity_candidates:
            normalized_type = candidate.entity_type.strip().upper()
            if not normalized_type:
                continue
            labels = {
                candidate.label.strip().lower(),
            }
            for key in (
                "display_label",
                "hgvs_notation",
                "mechanism_name",
                "hpo_term",
                "name",
                "label",
                "gene_symbol",
            ):
                value = candidate.anchors.get(key)
                if isinstance(value, str) and value.strip():
                    labels.add(value.strip().lower())
            for label in labels:
                if not label:
                    continue
                candidate_key = (normalized_type, label)
                existing = index.get(candidate_key)
                if existing is None and candidate_key in index:
                    continue
                if existing is not None:
                    index[candidate_key] = None
                    continue
                index[candidate_key] = candidate
        return index

    @staticmethod
    def _resolve_relation_endpoint_anchors(
        *,
        relation: ExtractedRelation,
        endpoint_name: str,
        entity_candidate_index: dict[tuple[str, str], ExtractedEntityCandidate | None],
    ) -> JSONObject:
        raw_anchors = (
            relation.source_anchors if endpoint_name == "source" else relation.target_anchors
        )
        if isinstance(raw_anchors, dict) and raw_anchors:
            return {
                str(key): to_json_value(value)
                for key, value in raw_anchors.items()
                if value is not None
                and (
                    not isinstance(value, str)
                    or bool(value.strip())
                )
            }
        entity_type = relation.source_type if endpoint_name == "source" else relation.target_type
        label = relation.source_label if endpoint_name == "source" else relation.target_label
        normalized_type = entity_type.strip().upper()
        normalized_label = normalize_optional_text(label)
        if not normalized_type or normalized_label is None:
            return {}
        candidate = entity_candidate_index.get(
            (normalized_type, normalized_label.lower()),
        )
        if candidate is None:
            return {}
        resolved: JSONObject = {
            str(key): to_json_value(value)
            for key, value in candidate.anchors.items()
            if value is not None
            and (
                not isinstance(value, str)
                or bool(value.strip())
            )
        }
        if candidate.label.strip() and "display_label" not in resolved:
            resolved["display_label"] = candidate.label.strip()
        return resolved

    @staticmethod
    def _build_endpoint_resolution_rejection(
        *,
        source_resolution: EndpointEntityResolutionResult,
        target_resolution: EndpointEntityResolutionResult,
    ) -> tuple[str, str, JSONObject]:
        source_reason = source_resolution.failure_reason
        target_reason = target_resolution.failure_reason
        is_missing_required_anchors = (
            source_reason == "relation_endpoint_missing_required_anchors"
            or target_reason == "relation_endpoint_missing_required_anchors"
        )
        is_shape_rejection = (
            source_reason == "relation_endpoint_shape_rejected"
            or target_reason == "relation_endpoint_shape_rejected"
        )
        reason = (
            "relation_endpoint_missing_required_anchors"
            if is_missing_required_anchors
            else (
            "relation_endpoint_shape_rejected"
            if is_shape_rejection
            else "relation_endpoint_resolution_failed"
            )
        )
        validation_reason = (
            "source or target endpoint is missing required anchors"
            if is_missing_required_anchors
            else (
                "source or target endpoint failed entity-shape guard"
                if is_shape_rejection
                else "source or target endpoint could not be resolved"
            )
        )
        metadata: JSONObject = {
            "validation_state": "ENDPOINT_UNRESOLVED",
            "validation_reason": validation_reason,
            "source_endpoint_failure_reason": source_reason,
            "target_endpoint_failure_reason": target_reason,
        }
        if source_resolution.failure_metadata is not None:
            metadata["source_endpoint_failure_metadata"] = (
                source_resolution.failure_metadata
            )
        if target_resolution.failure_metadata is not None:
            metadata["target_endpoint_failure_metadata"] = (
                target_resolution.failure_metadata
            )
        return reason, validation_reason, metadata

    def _should_require_relation_evidence_span(
        self,
        *,
        document: SourceDocument,
        candidate: _ResolvedRelationCandidate,
        research_space_settings: ResearchSpaceSettings,
    ) -> bool:
        source_type_value = document.source_type.value.strip().lower()
        if source_type_value != "pubmed":
            return False
        custom_settings = research_space_settings.get("custom")
        if isinstance(custom_settings, dict):
            explicit = custom_settings.get("pubmed_require_evidence_span")
            if isinstance(explicit, bool):
                return explicit
        dictionary = self._dictionary
        if dictionary is None:
            return True
        try:
            return dictionary.requires_evidence(
                candidate.source_type,
                candidate.relation_type,
                candidate.target_type,
            )
        except ValueError:
            return True

    def _prepare_relation_evidence_summary(  # noqa: PLR0913
        self,
        *,
        document: SourceDocument,
        candidate: _ResolvedRelationCandidate,
        relation_governance_mode: RelationGovernanceMode,
        constraint_proposal: RelationConstraintProposal | None,
        mapping_proposal: RelationTypeMappingProposal | None,
        requires_evidence_span: bool,
    ) -> tuple[str, JSONObject, str | None]:
        base_summary = self._build_relation_evidence_summary(
            document=document,
            candidate=candidate,
            relation_governance_mode=relation_governance_mode,
            constraint_proposal=constraint_proposal,
            mapping_proposal=mapping_proposal,
        )
        raw_record = self._extract_raw_record(document)
        span_result = resolve_relation_evidence_span(
            source_label=candidate.source_label,
            target_label=candidate.target_label,
            candidate_excerpt=candidate.evidence_excerpt,
            candidate_locator=candidate.evidence_locator,
            raw_record=raw_record,
        )
        metadata: JSONObject = {
            "span_required": requires_evidence_span,
            **span_result.metadata,
        }
        if span_result.failure_reason is not None:
            metadata["span_status"] = "missing"
            metadata["span_failure_reason"] = span_result.failure_reason
            if requires_evidence_span:
                return base_summary, metadata, span_result.failure_reason
            return base_summary, metadata, None
        span_text = span_result.span_text
        if span_text is None:
            metadata["span_status"] = "missing"
            metadata["span_failure_reason"] = "span_unavailable"
            if requires_evidence_span:
                return base_summary, metadata, "span_unavailable"
            return base_summary, metadata, None
        metadata["span_status"] = "resolved"
        metadata["span_text"] = span_text
        return (
            append_span_to_summary(base_summary=base_summary, span_text=span_text),
            metadata,
            None,
        )

    def _generate_optional_relation_evidence_sentence(
        self,
        *,
        document: SourceDocument,
        candidate: _ResolvedRelationCandidate,
        evidence_summary: str,
        relation_evidence_metadata: JSONObject,
        run_id: str | None,
    ) -> EvidenceSentenceGenerationResult:
        harness = self._evidence_sentence_harness
        if harness is None:
            return EvidenceSentenceGenerationResult(
                outcome="failed",
                failure_reason="evidence_sentence_harness_unavailable",
            )

        raw_record = self._extract_raw_record(document)
        document_text: str | None = None
        for field_name in ("full_text", "text", "abstract", "title"):
            field_value = raw_record.get(field_name)
            if not isinstance(field_value, str):
                continue
            normalized_value = normalize_optional_text(field_value)
            if normalized_value is None:
                continue
            document_text = normalized_value[:120000]
            break

        request = EvidenceSentenceGenerationRequest(
            research_space_id=(
                str(document.research_space_id)
                if document.research_space_id is not None
                else "unknown"
            ),
            source_type=document.source_type.value,
            relation_type=candidate.relation_type,
            source_label=candidate.source_label,
            target_label=candidate.target_label,
            evidence_summary=evidence_summary[:2000],
            evidence_excerpt=normalize_optional_text(candidate.evidence_excerpt),
            evidence_locator=normalize_optional_text(candidate.evidence_locator),
            document_text=document_text,
            document_id=str(document.id),
            run_id=run_id,
            metadata={
                "relation_evidence": relation_evidence_metadata,
                "confidence": candidate.confidence,
                "validation_state": candidate.validation_state,
            },
        )
        try:
            result = harness.generate(request)
        except Exception as exc:  # noqa: BLE001 - fail-open for optional sentence path
            return EvidenceSentenceGenerationResult(
                outcome="failed",
                failure_reason=f"evidence_sentence_harness_error:{type(exc).__name__}",
                metadata={"error": str(exc)},
            )

        normalized_sentence = normalize_optional_text(result.sentence)
        if result.outcome != "generated":
            failure_reason = normalize_optional_text(result.failure_reason)
            return EvidenceSentenceGenerationResult(
                outcome="failed",
                failure_reason=failure_reason or "evidence_sentence_generation_failed",
                metadata=result.metadata,
            )
        if normalized_sentence is None:
            return EvidenceSentenceGenerationResult(
                outcome="failed",
                failure_reason="generated_sentence_empty",
                metadata=result.metadata,
            )
        if len(normalized_sentence) < _MIN_GENERATED_EVIDENCE_SENTENCE_LENGTH:
            return EvidenceSentenceGenerationResult(
                outcome="failed",
                failure_reason="generated_sentence_too_short",
                metadata=result.metadata,
            )
        return EvidenceSentenceGenerationResult(
            outcome="generated",
            sentence=normalized_sentence[:2000],
            source="artana_generated",
            confidence=result.confidence or "low",
            rationale=normalize_optional_text(result.rationale),
            metadata=result.metadata,
        )

    @staticmethod
    def _claim_evidence_reference_from_metadata(
        *,
        metadata: JSONObject,
        primary_key: str,
        fallback_key: str,
    ) -> str | None:
        primary_value = metadata.get(primary_key)
        if isinstance(primary_value, str):
            normalized_primary = normalize_optional_text(primary_value)
            if normalized_primary is not None:
                return normalized_primary
        fallback_value = metadata.get(fallback_key)
        if isinstance(fallback_value, str):
            return normalize_optional_text(fallback_value)
        return None

    def _create_claim_evidence_record(  # noqa: PLR0913
        self,
        *,
        claim_id: str,
        document: SourceDocument,
        run_id: str | None,
        relation_evidence_metadata: JSONObject,
        evidence_sentence: str | None,
        evidence_sentence_source: str | None,
        evidence_sentence_confidence: str | None,
        evidence_sentence_rationale: str | None,
        candidate_confidence: float,
    ) -> tuple[str, ...]:
        if self._claim_evidences is None:
            return ("claim_evidence_repository_unavailable",)
        metadata_copy: JSONObject = {
            str(key): value for key, value in relation_evidence_metadata.items()
        }
        figure_reference = self._claim_evidence_reference_from_metadata(
            metadata=metadata_copy,
            primary_key="figure_reference",
            fallback_key="figure_ref",
        )
        table_reference = self._claim_evidence_reference_from_metadata(
            metadata=metadata_copy,
            primary_key="table_reference",
            fallback_key="table_ref",
        )
        normalized_sentence_source = _normalize_claim_evidence_sentence_source(
            evidence_sentence_source,
        )
        normalized_sentence_confidence = _normalize_claim_evidence_sentence_confidence(
            evidence_sentence_confidence,
        )
        try:
            self._claim_evidences.create(
                claim_id=claim_id,
                source_document_id=str(document.id),
                agent_run_id=run_id,
                sentence=evidence_sentence,
                sentence_source=normalized_sentence_source,
                sentence_confidence=normalized_sentence_confidence,
                sentence_rationale=evidence_sentence_rationale,
                figure_reference=figure_reference,
                table_reference=table_reference,
                confidence=float(candidate_confidence),
                metadata=metadata_copy,
            )
            increment_metric(
                "claim_evidence_rows_created_total",
                tags={
                    "research_space_id": (
                        str(document.research_space_id)
                        if document.research_space_id is not None
                        else "unknown"
                    ),
                    "source_document_id": str(document.id),
                },
            )
        except (TypeError, ValueError, SQLAlchemyError) as exc:
            error_code = self._map_relation_write_error_code(exc)
            return (f"claim_evidence_create_failed:{error_code}",)
        return ()

    def _persist_candidate_relation(  # noqa: C901, PLR0911, PLR0912, PLR0913, PLR0915
        self,
        *,
        document: SourceDocument,
        run_id: str | None,
        research_space_id: str,
        relation_governance_mode: RelationGovernanceMode,
        effective_candidate: _ResolvedRelationCandidate,
        evidence_summary: str,
        evidence_sentence: str | None,
        evidence_sentence_source: str | None,
        evidence_sentence_confidence: str | None,
        evidence_sentence_rationale: str | None,
        relation_evidence_metadata: JSONObject,
        claim_id: str | None,
        payload: JSONObject,
        candidate_signature: tuple[str, str, str, str, str],
        full_auto_retry_index: dict[tuple[str, str, str, str, str], str],
        dictionary_fingerprint: str,
        index: int,
        total_candidates: int,
        should_log_candidate: bool,
    ) -> _RelationWriteOutcome:
        errors: list[str] = []
        relation_claims_count_delta = 0
        claim_evidence_rows_created_count_delta = 0
        relation_claims_queued_for_review_count = 0
        del evidence_summary
        if self._relation_claims is None or claim_id is None:
            return _RelationWriteOutcome(
                persistence_failed_count=1,
                errors=("relation_claim_required_for_projection",),
            )
        if self._materializer is None:
            return _RelationWriteOutcome(
                persistence_failed_count=1,
                errors=("relation_projection_materializer_unavailable",),
            )
        source_entity_id = effective_candidate.source_entity_id
        target_entity_id = effective_candidate.target_entity_id
        if source_entity_id is None or target_entity_id is None:
            return _RelationWriteOutcome(
                persistence_failed_count=1,
                errors=("relation_persistence_missing_endpoint_entity_id",),
            )
        if relation_governance_mode != "FULL_AUTO":
            self._enqueue_review_item(
                entity_type="relation_claim",
                entity_id=claim_id,
                research_space_id=research_space_id,
                priority=self._review_priority_for_candidate(
                    candidate=effective_candidate,
                ),
            )
            if should_log_candidate:
                logger.info(
                    "Persist relation candidate completed as claim-only review item",
                    extra={
                        "document_id": str(document.id),
                        "run_id": run_id,
                        "candidate_index": index,
                        "candidate_total": total_candidates,
                        "claim_id": claim_id,
                        "relation_type": effective_candidate.relation_type,
                    },
                )
            return _RelationWriteOutcome(
                pending_review_relations_count=1,
                relation_claims_count_delta=relation_claims_count_delta,
                claim_evidence_rows_created_count_delta=(
                    claim_evidence_rows_created_count_delta
                ),
                relation_claims_queued_for_review_count=1,
                errors=tuple(errors),
            )
        try:
            status_errors = self._set_claim_system_status(
                claim_id=claim_id,
                claim_status="RESOLVED",
            )
            errors.extend(status_errors)
            if effective_candidate.polarity == "SUPPORT":
                materialized = self._materializer.materialize_support_claim(
                    claim_id=claim_id,
                    research_space_id=research_space_id,
                    projection_origin="EXTRACTION",
                )
                if materialized.relation is None:
                    _raise_missing_materialized_relation()
            else:
                linked_relation = (
                    self._materializer.find_claim_backed_relation_for_claim(
                        claim_id=claim_id,
                        research_space_id=research_space_id,
                    )
                )
                if linked_relation is None:
                    self._relation_claims.clear_relation_link(claim_id)
                else:
                    errors.extend(
                        self._link_claim_to_relation(
                            claim_id=claim_id,
                            relation_id=str(linked_relation.id),
                        ),
                    )
            if candidate_signature in full_auto_retry_index:
                full_auto_retry_index.pop(candidate_signature)
        except (TypeError, ValueError, SQLAlchemyError) as exc:
            self._rollback_after_persistence_error(
                context="relation_projection_materialization",
            )
            error_code = self._map_relation_write_error_code(exc)
            errors.append(
                (
                    "relation_persistence_failed:"
                    f"{error_code}:{effective_candidate.relation_type}:"
                    f"{source_entity_id}"
                    f"->{target_entity_id}"
                ),
            )
            relation_claims_count_delta -= 1
            try:
                recreated_claim = self._relation_claims.create(
                    research_space_id=research_space_id,
                    source_document_id=str(document.id),
                    agent_run_id=run_id,
                    source_type=effective_candidate.source_type,
                    relation_type=effective_candidate.relation_type,
                    target_type=effective_candidate.target_type,
                    source_label=effective_candidate.source_label,
                    target_label=effective_candidate.target_label,
                    confidence=effective_candidate.confidence,
                    validation_state=effective_candidate.validation_state,
                    validation_reason=effective_candidate.validation_reason,
                    persistability=effective_candidate.persistability,
                    claim_status="NEEDS_MAPPING",
                    polarity=effective_candidate.polarity,
                    claim_text=effective_candidate.claim_text,
                    claim_section=effective_candidate.claim_section,
                    linked_relation_id=None,
                    metadata=payload,
                )
                claim_id = str(recreated_claim.id)
                relation_claims_count_delta += 1
                claim_evidence_errors = self._create_claim_evidence_record(
                    claim_id=claim_id,
                    document=document,
                    run_id=run_id,
                    relation_evidence_metadata=relation_evidence_metadata,
                    evidence_sentence=evidence_sentence,
                    evidence_sentence_source=evidence_sentence_source,
                    evidence_sentence_confidence=evidence_sentence_confidence,
                    evidence_sentence_rationale=evidence_sentence_rationale,
                    candidate_confidence=effective_candidate.confidence,
                )
                if not claim_evidence_errors:
                    claim_evidence_rows_created_count_delta += 1
                errors.extend(claim_evidence_errors)
                full_auto_retry_index[candidate_signature] = dictionary_fingerprint
                self._enqueue_review_item(
                    entity_type="relation_claim",
                    entity_id=claim_id,
                    research_space_id=research_space_id,
                    priority="high",
                )
                relation_claims_queued_for_review_count += 1
                if should_log_candidate:
                    logger.info(
                        "Persist relation candidate claim restored after projection rollback",
                        extra={
                            "document_id": str(document.id),
                            "run_id": run_id,
                            "candidate_index": index,
                            "candidate_total": total_candidates,
                            "claim_id": claim_id,
                            "relation_type": effective_candidate.relation_type,
                            "error_code": error_code,
                        },
                    )
            except (TypeError, ValueError, SQLAlchemyError) as claim_exc:
                self._rollback_after_persistence_error(
                    context="relation_claim_recreate",
                )
                claim_error_code = self._map_relation_write_error_code(
                    claim_exc,
                )
                errors.append(
                    (
                        "relation_claim_recreate_failed:"
                        f"{claim_error_code}:{effective_candidate.relation_type}"
                    ),
                )
                if should_log_candidate:
                    logger.warning(
                        "Persist relation candidate claim recreate failed after rollback",
                        extra={
                            "document_id": str(document.id),
                            "run_id": run_id,
                            "candidate_index": index,
                            "candidate_total": total_candidates,
                            "relation_type": effective_candidate.relation_type,
                            "error_code": claim_error_code,
                            "error": str(claim_exc),
                        },
                    )
            if should_log_candidate:
                logger.warning(
                    "Persist relation candidate projection write failed",
                    extra={
                        "document_id": str(document.id),
                        "run_id": run_id,
                        "candidate_index": index,
                        "candidate_total": total_candidates,
                        "relation_type": effective_candidate.relation_type,
                        "source_entity_id": source_entity_id,
                        "target_entity_id": target_entity_id,
                        "error_code": error_code,
                        "error": str(exc),
                    },
                )
            return _RelationWriteOutcome(
                relation_claims_count_delta=relation_claims_count_delta,
                claim_evidence_rows_created_count_delta=(
                    claim_evidence_rows_created_count_delta
                ),
                relation_claims_queued_for_review_count=(
                    relation_claims_queued_for_review_count
                ),
                persistence_failed_count=1,
                errors=tuple(errors),
            )
        if effective_candidate.polarity == "SUPPORT":
            relation = self._materializer.find_claim_backed_relation_for_claim(
                claim_id=claim_id,
                research_space_id=research_space_id,
            )
            if relation is None:
                msg = "Materialized support claim is missing canonical relation"
                raise ValueError(msg)
            self._enqueue_review_item(
                entity_type="relation",
                entity_id=str(relation.id),
                research_space_id=research_space_id,
                priority=self._review_priority_for_candidate(
                    candidate=effective_candidate,
                ),
            )
            if should_log_candidate:
                logger.info(
                    "Persist relation candidate completed as claim-backed projection",
                    extra={
                        "document_id": str(document.id),
                        "run_id": run_id,
                        "candidate_index": index,
                        "candidate_total": total_candidates,
                        "relation_id": str(relation.id),
                        "claim_id": claim_id,
                        "validation_state": effective_candidate.validation_state,
                        "relation_type": effective_candidate.relation_type,
                    },
                )
            return _RelationWriteOutcome(
                persisted_relations_count=1,
                pending_review_relations_count=1,
                relation_claims_count_delta=relation_claims_count_delta,
                claim_evidence_rows_created_count_delta=(
                    claim_evidence_rows_created_count_delta
                ),
                relation_claims_queued_for_review_count=(
                    relation_claims_queued_for_review_count
                ),
                errors=tuple(errors),
            )

        self._enqueue_review_item(
            entity_type="relation_claim",
            entity_id=claim_id,
            research_space_id=research_space_id,
            priority=self._review_priority_for_candidate(
                candidate=effective_candidate,
            ),
        )
        if should_log_candidate:
            logger.info(
                "Persist relation candidate completed as resolved non-support claim",
                extra={
                    "document_id": str(document.id),
                    "run_id": run_id,
                    "candidate_index": index,
                    "candidate_total": total_candidates,
                    "claim_id": claim_id,
                    "validation_state": effective_candidate.validation_state,
                    "relation_type": effective_candidate.relation_type,
                    "polarity": effective_candidate.polarity,
                },
            )
        return _RelationWriteOutcome(
            pending_review_relations_count=1,
            relation_claims_count_delta=relation_claims_count_delta,
            claim_evidence_rows_created_count_delta=(
                claim_evidence_rows_created_count_delta
            ),
            relation_claims_queued_for_review_count=(
                relation_claims_queued_for_review_count + 1
            ),
            errors=tuple(errors),
        )

    def _persist_relation_candidates(  # noqa: PLR0913
        self,
        *,
        document: SourceDocument,
        run_id: str | None,
        candidates: tuple[_ResolvedRelationCandidate, ...],
        policy_contract: ExtractionPolicyContract | None,
        relation_governance_mode: RelationGovernanceMode,
        research_space_settings: ResearchSpaceSettings,
    ) -> _PersistCandidatesResult:
        return persist_relation_candidates(
            helper=self,
            document=document,
            run_id=run_id,
            candidates=candidates,
            policy_contract=policy_contract,
            relation_governance_mode=relation_governance_mode,
            research_space_settings=research_space_settings,
        )

    @staticmethod
    def _extract_raw_record(document: SourceDocument) -> JSONObject:
        msg = "subclass must implement _extract_raw_record"
        raise NotImplementedError(msg)


__all__ = ["RelationPersistenceResult", "_ExtractionRelationPersistenceHelpers"]
