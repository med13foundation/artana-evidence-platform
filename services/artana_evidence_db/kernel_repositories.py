"""Service-local bridge for kernel repository implementations."""

from __future__ import annotations

from artana_evidence_db.claim_evidence_repository import (
    SqlAlchemyKernelClaimEvidenceRepository,
)
from artana_evidence_db.claim_participant_repository import (
    SqlAlchemyKernelClaimParticipantRepository,
)
from artana_evidence_db.claim_relation_repository import (
    SqlAlchemyKernelClaimRelationRepository,
)
from artana_evidence_db.concept_repository import SqlAlchemyConceptRepository
from artana_evidence_db.dictionary_repository import SqlAlchemyDictionaryRepository
from artana_evidence_db.entity_embedding_repository import (
    SqlAlchemyEntityEmbeddingRepository,
)
from artana_evidence_db.entity_repository import SqlAlchemyKernelEntityRepository
from artana_evidence_db.graph_query_repository import SqlAlchemyGraphQueryRepository
from artana_evidence_db.observation_repository import (
    SqlAlchemyKernelObservationRepository,
)
from artana_evidence_db.provenance_repository import SqlAlchemyProvenanceRepository
from artana_evidence_db.reasoning_path_repository import (
    SqlAlchemyKernelReasoningPathRepository,
)
from artana_evidence_db.relation_claim_repository import (
    SqlAlchemyKernelRelationClaimRepository,
)
from artana_evidence_db.relation_projection_source_repository import (
    SqlAlchemyKernelRelationProjectionSourceRepository,
)
from artana_evidence_db.relation_repository import SqlAlchemyKernelRelationRepository
from artana_evidence_db.source_document_reference_repository import (
    SqlAlchemyKernelSourceDocumentReferenceRepository,
)
from artana_evidence_db.space_access_repository import (
    SqlAlchemyKernelSpaceAccessRepository,
)
from artana_evidence_db.space_membership_repository import (
    SqlAlchemyKernelSpaceMembershipRepository,
)
from artana_evidence_db.space_registry_repository import (
    SqlAlchemyKernelSpaceRegistryRepository,
)
from artana_evidence_db.space_settings_repository import (
    SqlAlchemyKernelSpaceSettingsRepository,
)

KernelClaimEvidenceRepository = SqlAlchemyKernelClaimEvidenceRepository
KernelClaimParticipantRepository = SqlAlchemyKernelClaimParticipantRepository
KernelClaimRelationRepository = SqlAlchemyKernelClaimRelationRepository
KernelEntityRepository = SqlAlchemyKernelEntityRepository
GraphQueryPort = SqlAlchemyGraphQueryRepository
KernelObservationRepository = SqlAlchemyKernelObservationRepository
KernelReasoningPathRepository = SqlAlchemyKernelReasoningPathRepository
KernelRelationClaimRepository = SqlAlchemyKernelRelationClaimRepository
KernelRelationProjectionSourceRepository = (
    SqlAlchemyKernelRelationProjectionSourceRepository
)
KernelRelationRepository = SqlAlchemyKernelRelationRepository
SourceDocumentReferencePort = SqlAlchemyKernelSourceDocumentReferenceRepository
SpaceAccessPort = SqlAlchemyKernelSpaceAccessRepository
SpaceRegistryPort = SqlAlchemyKernelSpaceRegistryRepository
SpaceSettingsPort = SqlAlchemyKernelSpaceSettingsRepository
ProvenanceRepository = SqlAlchemyProvenanceRepository
DictionaryRepository = SqlAlchemyDictionaryRepository
ConceptRepository = SqlAlchemyConceptRepository
EntityEmbeddingRepository = SqlAlchemyEntityEmbeddingRepository


__all__ = [
    "ConceptRepository",
    "DictionaryRepository",
    "EntityEmbeddingRepository",
    "GraphQueryPort",
    "KernelClaimEvidenceRepository",
    "KernelClaimParticipantRepository",
    "KernelClaimRelationRepository",
    "KernelEntityRepository",
    "KernelObservationRepository",
    "KernelReasoningPathRepository",
    "KernelRelationClaimRepository",
    "KernelRelationProjectionSourceRepository",
    "KernelRelationRepository",
    "ProvenanceRepository",
    "SourceDocumentReferencePort",
    "SpaceAccessPort",
    "SpaceRegistryPort",
    "SpaceSettingsPort",
    "SqlAlchemyKernelClaimEvidenceRepository",
    "SqlAlchemyKernelClaimParticipantRepository",
    "SqlAlchemyKernelClaimRelationRepository",
    "SqlAlchemyKernelEntityRepository",
    "SqlAlchemyEntityEmbeddingRepository",
    "SqlAlchemyGraphQueryRepository",
    "SqlAlchemyKernelObservationRepository",
    "SqlAlchemyKernelReasoningPathRepository",
    "SqlAlchemyKernelRelationClaimRepository",
    "SqlAlchemyKernelRelationProjectionSourceRepository",
    "SqlAlchemyKernelRelationRepository",
    "SqlAlchemyKernelSourceDocumentReferenceRepository",
    "SqlAlchemyKernelSpaceAccessRepository",
    "SqlAlchemyKernelSpaceMembershipRepository",
    "SqlAlchemyKernelSpaceRegistryRepository",
    "SqlAlchemyKernelSpaceSettingsRepository",
    "SqlAlchemyProvenanceRepository",
    "SqlAlchemyDictionaryRepository",
    "SqlAlchemyConceptRepository",
]
