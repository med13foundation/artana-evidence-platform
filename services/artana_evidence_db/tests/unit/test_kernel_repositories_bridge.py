from __future__ import annotations

from artana_evidence_db import kernel_repositories


def test_kernel_repositories_bridge_exports_lazy_loaded_classes() -> None:
    assert (
        kernel_repositories.SqlAlchemyKernelClaimEvidenceRepository.__module__
        == "artana_evidence_db.claim_evidence_repository"
    )
    assert (
        kernel_repositories.SqlAlchemyKernelClaimParticipantRepository.__module__
        == "artana_evidence_db.claim_participant_repository"
    )
    assert (
        kernel_repositories.SqlAlchemyKernelClaimRelationRepository.__module__
        == "artana_evidence_db.claim_relation_repository"
    )
    assert (
        kernel_repositories.SqlAlchemyKernelRelationClaimRepository.__module__
        == "artana_evidence_db.relation_claim_repository"
    )
    assert (
        kernel_repositories.SqlAlchemyKernelEntityRepository.__module__
        == "artana_evidence_db.entity_repository"
    )
    assert (
        kernel_repositories.SqlAlchemyKernelObservationRepository.__module__
        == "artana_evidence_db.observation_repository"
    )
    assert (
        kernel_repositories.SqlAlchemyKernelRelationRepository.__module__
        == "artana_evidence_db.relation_repository"
    )
    assert (
        kernel_repositories.SqlAlchemyKernelSpaceRegistryRepository.__name__
        == "SqlAlchemyKernelSpaceRegistryRepository"
    )
    assert (
        kernel_repositories.SqlAlchemyKernelSpaceRegistryRepository.__module__
        == "artana_evidence_db.space_registry_repository"
    )
    assert (
        kernel_repositories.SqlAlchemyKernelSpaceMembershipRepository.__module__
        == "artana_evidence_db.space_membership_repository"
    )
    assert (
        kernel_repositories.SqlAlchemyKernelSpaceAccessRepository.__module__
        == "artana_evidence_db.space_access_repository"
    )
    assert (
        kernel_repositories.SqlAlchemyProvenanceRepository.__module__
        == "artana_evidence_db.provenance_repository"
    )
    assert (
        kernel_repositories.SqlAlchemyKernelSourceDocumentReferenceRepository.__module__
        == "artana_evidence_db.source_document_reference_repository"
    )
    assert (
        kernel_repositories.SqlAlchemyKernelRelationProjectionSourceRepository.__module__
        == "artana_evidence_db.relation_projection_source_repository"
    )
    assert (
        kernel_repositories.SqlAlchemyKernelReasoningPathRepository.__module__
        == "artana_evidence_db.reasoning_path_repository"
    )
