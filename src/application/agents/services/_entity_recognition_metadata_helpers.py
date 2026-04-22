"""Metadata helper mixin for entity-recognition orchestration outcomes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.domain.agents.contracts.assessment_compat import (
    assessment_payload,
    confidence_from_entity_recognition_contract,
)

if TYPE_CHECKING:
    from src.application.agents.services.extraction_service import (
        ExtractionDocumentOutcome,
    )
    from src.application.agents.services.governance_service import GovernanceDecision
    from src.domain.agents.contracts.entity_recognition import EntityRecognitionContract
    from src.type_definitions.common import JSONObject
    from src.type_definitions.ingestion import IngestResult


class _EntityRecognitionMetadataHelpers:
    """Mixin that builds metadata payloads for ERA and extraction outcomes."""

    @staticmethod
    def _build_outcome_metadata(  # noqa: PLR0913
        *,
        contract: EntityRecognitionContract,
        governance: GovernanceDecision,
        run_id: str | None,
        pipeline_run_id: str | None,
        wrote_to_kernel: bool,
        dictionary_variables_created: int,
        dictionary_synonyms_created: int,
        dictionary_entity_types_created: int,
        ingestion_result: IngestResult | None,
    ) -> JSONObject:
        metadata: JSONObject = {
            "entity_recognition_decision": contract.decision,
            "entity_recognition_confidence": (
                confidence_from_entity_recognition_contract(contract)
            ),
            "entity_recognition_rationale": contract.rationale,
            "entity_recognition_run_id": run_id,
            "entity_recognition_shadow_mode": governance.shadow_mode,
            "entity_recognition_requires_review": governance.requires_review,
            "entity_recognition_governance_reason": governance.reason,
            "entity_recognition_wrote_to_kernel": wrote_to_kernel,
            "entity_recognition_dictionary_variables_created": (
                dictionary_variables_created
            ),
            "entity_recognition_dictionary_synonyms_created": (
                dictionary_synonyms_created
            ),
            "entity_recognition_dictionary_entity_types_created": (
                dictionary_entity_types_created
            ),
            "entity_recognition_processed_at": datetime.now(UTC).isoformat(),
        }
        entity_recognition_assessment = assessment_payload(contract)
        if entity_recognition_assessment is not None:
            metadata["entity_recognition_assessment"] = entity_recognition_assessment
        if pipeline_run_id is not None and pipeline_run_id.strip():
            metadata["pipeline_run_id"] = pipeline_run_id.strip()
        if contract.decision != "generated":
            metadata["entity_recognition_failure_reason"] = (
                f"agent_decision:{contract.decision}"
            )
            metadata["entity_recognition_error"] = contract.rationale
        elif governance.reason != "auto" and not wrote_to_kernel:
            metadata["entity_recognition_failure_reason"] = governance.reason
            metadata["entity_recognition_error"] = contract.rationale
        if ingestion_result is not None:
            metadata["entity_recognition_ingestion_success"] = ingestion_result.success
            metadata["entity_recognition_ingestion_entities_created"] = (
                ingestion_result.entities_created
            )
            metadata["entity_recognition_ingestion_observations_created"] = (
                ingestion_result.observations_created
            )
            metadata["entity_recognition_ingestion_errors"] = ingestion_result.errors
        return metadata

    @staticmethod
    def _build_extraction_metadata(
        extraction_outcome: ExtractionDocumentOutcome,
    ) -> JSONObject:
        rejected_relation_reasons = list(extraction_outcome.rejected_relation_reasons)
        rejected_relation_details = list(extraction_outcome.rejected_relation_details)
        if (
            not rejected_relation_reasons
            and extraction_outcome.relations_extracted == 0
        ):
            if extraction_outcome.errors:
                for error in extraction_outcome.errors:
                    normalized_error = error.strip()
                    if not normalized_error:
                        continue
                    reason = f"extraction_error:{normalized_error}"[:255]
                    if reason not in rejected_relation_reasons:
                        rejected_relation_reasons.append(reason)
                    rejected_relation_details.append(
                        {
                            "reason": reason,
                            "payload": {"error": normalized_error},
                        },
                    )
            else:
                fallback_reason = (
                    f"extraction_no_relations:{extraction_outcome.reason}"
                )[:255]
                rejected_relation_reasons.append(fallback_reason)
                rejected_relation_details.append(
                    {
                        "reason": fallback_reason,
                        "payload": {
                            "status": extraction_outcome.status,
                            "reason": extraction_outcome.reason,
                            "wrote_to_kernel": extraction_outcome.wrote_to_kernel,
                        },
                    },
                )
        return {
            "extraction_stage_status": extraction_outcome.status,
            "extraction_stage_reason": extraction_outcome.reason,
            "extraction_stage_run_id": extraction_outcome.run_id,
            "extraction_stage_review_required": extraction_outcome.review_required,
            "extraction_stage_shadow_mode": extraction_outcome.shadow_mode,
            "extraction_stage_wrote_to_kernel": extraction_outcome.wrote_to_kernel,
            "extraction_stage_observations_extracted": (
                extraction_outcome.observations_extracted
            ),
            "extraction_stage_relations_extracted": (
                extraction_outcome.relations_extracted
            ),
            "extraction_stage_rejected_facts": extraction_outcome.rejected_facts,
            "extraction_stage_rejected_relation_reasons": rejected_relation_reasons,
            "extraction_stage_rejected_relation_details": rejected_relation_details,
            "extraction_stage_ingestion_entities_created": (
                extraction_outcome.ingestion_entities_created
            ),
            "extraction_stage_ingestion_observations_created": (
                extraction_outcome.ingestion_observations_created
            ),
            "extraction_stage_persisted_relations": (
                extraction_outcome.persisted_relations_count
            ),
            "extraction_stage_pending_review_relations": (
                extraction_outcome.pending_review_relations_count
            ),
            "extraction_stage_forbidden_relations": (
                extraction_outcome.forbidden_relations_count
            ),
            "extraction_stage_undefined_relations": (
                extraction_outcome.undefined_relations_count
            ),
            "extraction_stage_concept_members_created": (
                extraction_outcome.concept_members_created_count
            ),
            "extraction_stage_concept_aliases_created": (
                extraction_outcome.concept_aliases_created_count
            ),
            "extraction_stage_concept_decisions_proposed": (
                extraction_outcome.concept_decisions_proposed_count
            ),
            "extraction_stage_policy_run_id": extraction_outcome.policy_step_run_id,
            "extraction_stage_policy_proposals": (
                extraction_outcome.policy_proposals_count
            ),
            "extraction_stage_relation_type_mapping_proposals": (
                extraction_outcome.relation_type_mapping_proposals_count
            ),
            "extraction_stage_relation_synonym_proposals_attempted": (
                extraction_outcome.relation_synonym_proposals_attempted_count
            ),
            "extraction_stage_relation_synonym_proposals_created": (
                extraction_outcome.relation_synonym_proposals_created_count
            ),
            "extraction_stage_relation_synonym_proposals_skipped": (
                extraction_outcome.relation_synonym_proposals_skipped_count
            ),
            "extraction_stage_relation_synonym_proposals_failed": (
                extraction_outcome.relation_synonym_proposals_failed_count
            ),
            "extraction_stage_funnel": extraction_outcome.extraction_funnel,
            "extraction_stage_errors": list(extraction_outcome.errors),
        }


__all__ = ["_EntityRecognitionMetadataHelpers"]
