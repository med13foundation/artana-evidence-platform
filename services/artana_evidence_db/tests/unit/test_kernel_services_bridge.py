from __future__ import annotations

from artana_evidence_db import kernel_services


def test_kernel_services_bridge_exports_lazy_loaded_symbols() -> None:
    assert (
        kernel_services.ConceptManagementService.__module__
        == "artana_evidence_db.concept_management_service"
    )
    assert (
        kernel_services.DictionaryManagementService.__module__
        == "artana_evidence_db.dictionary_management_service"
    )
    assert (
        kernel_services.KernelEntityService.__module__
        == "artana_evidence_db.entity_service"
    )
    assert (
        kernel_services.KernelClaimEvidenceService.__module__
        == "artana_evidence_db.claim_evidence_service"
    )
    assert (
        kernel_services.KernelClaimParticipantService.__module__
        == "artana_evidence_db.claim_participant_service"
    )
    assert (
        kernel_services.KernelClaimParticipantBackfillService.__module__
        == "artana_evidence_db.claim_participant_backfill_service"
    )
    assert (
        kernel_services.KernelRelationClaimService.__module__
        == "artana_evidence_db.relation_claim_service"
    )
    assert (
        kernel_services.KernelClaimRelationService.__module__
        == "artana_evidence_db.claim_relation_service"
    )
    assert (
        kernel_services.KernelObservationService.__module__
        == "artana_evidence_db.observation_service"
    )
    assert (
        kernel_services.KernelRelationService.__module__
        == "artana_evidence_db.relation_service"
    )
    assert (
        kernel_services.KernelRelationSuggestionService.__module__
        == "artana_evidence_db.kernel_relation_suggestion_service"
    )
    assert (
        kernel_services.KernelClaimProjectionReadinessService.__module__
        == "artana_evidence_db.claim_projection_readiness_service"
    )
    assert (
        kernel_services.KernelRelationProjectionSourceService.__module__
        == "artana_evidence_db.relation_projection_source_service"
    )
    assert (
        kernel_services.ProvenanceService.__module__
        == "artana_evidence_db.provenance_service"
    )
    assert (
        kernel_services.KernelReasoningPathService.__module__
        == "artana_evidence_db.reasoning_path_service"
    )
    assert (
        kernel_services.KernelReasoningPathInvalidationService.__module__
        == "artana_evidence_db.reasoning_path_service"
    )
    assert (
        kernel_services.KernelRelationProjectionMaterializationService.__module__
        == "artana_evidence_db.relation_projection_materialization_service"
    )
    assert (
        kernel_services.KernelGraphViewService.__module__
        == "artana_evidence_db.graph_view_service"
    )
    assert (
        kernel_services.KernelGraphViewNotFoundError.__module__
        == "artana_evidence_db.graph_view_support"
    )
    assert (
        kernel_services.KernelGraphViewValidationError.__module__
        == "artana_evidence_db.graph_view_support"
    )
    assert (
        kernel_services.KernelGraphViewNotFoundError.__name__
        == "KernelGraphViewNotFoundError"
    )
