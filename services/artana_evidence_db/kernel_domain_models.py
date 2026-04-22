"""Service-local bridge for kernel and governance domain models."""

from __future__ import annotations

from artana_evidence_db.claim_evidence_models import KernelClaimEvidence
from artana_evidence_db.claim_participant_models import (
    ClaimParticipantRole,
    KernelClaimParticipant,
)
from artana_evidence_db.claim_relation_models import KernelClaimRelation
from artana_evidence_db.concept_models import (
    ConceptAlias,
    ConceptDecision,
    ConceptDecisionProposal,
    ConceptDecisionStatus,
    ConceptDecisionType,
    ConceptHarnessCheck,
    ConceptHarnessOutcome,
    ConceptHarnessResult,
    ConceptHarnessVerdict,
    ConceptLink,
    ConceptMember,
    ConceptPolicy,
    ConceptPolicyMode,
    ConceptSet,
)
from artana_evidence_db.dictionary_models import (
    DictionaryChangelog,
    DictionaryDomainContext,
    DictionaryEntityType,
    DictionaryProposal,
    DictionaryProposalStatus,
    DictionaryProposalType,
    DictionaryRelationSynonym,
    DictionaryRelationType,
    DictionarySearchResult,
    EntityResolutionPolicy,
    RelationConstraint,
    TransformRegistry,
    TransformVerificationResult,
    ValueSet,
    ValueSetItem,
    VariableDefinition,
    VariableSynonym,
)
from artana_evidence_db.embedding_models import (
    KernelEntityEmbedding,
    KernelEntitySimilarityCandidate,
)
from artana_evidence_db.graph_core_models import (
    EvidenceSentenceGenerationRequest,
    EvidenceSentenceGenerationResult,
    KernelEntity,
    KernelObservation,
    KernelProvenanceRecord,
    KernelRelation,
    KernelRelationEvidence,
    RelationEvidenceWrite,
)
from artana_evidence_db.reasoning_path_models import (
    KernelReasoningPath,
    KernelReasoningPathStep,
)
from artana_evidence_db.relation_claim_models import (
    KernelRelationClaim,
    KernelRelationConflictSummary,
    RelationClaimStatus,
)
from artana_evidence_db.relation_projection_source_model import (
    KernelRelationProjectionSource,
)
from artana_evidence_db.source_document_reference_model import (
    KernelSourceDocumentReference,
)
from artana_evidence_db.space_registry import KernelSpaceRegistryEntry

__all__ = [
    "ClaimParticipantRole",
    "ConceptAlias",
    "ConceptDecision",
    "ConceptDecisionProposal",
    "ConceptDecisionStatus",
    "ConceptDecisionType",
    "ConceptHarnessCheck",
    "ConceptHarnessOutcome",
    "ConceptHarnessResult",
    "ConceptHarnessVerdict",
    "ConceptLink",
    "ConceptMember",
    "ConceptPolicy",
    "ConceptPolicyMode",
    "ConceptSet",
    "DictionaryChangelog",
    "DictionaryDomainContext",
    "DictionaryEntityType",
    "DictionaryProposal",
    "DictionaryProposalStatus",
    "DictionaryProposalType",
    "DictionaryRelationSynonym",
    "DictionaryRelationType",
    "DictionarySearchResult",
    "EvidenceSentenceGenerationRequest",
    "EvidenceSentenceGenerationResult",
    "EntityResolutionPolicy",
    "KernelClaimEvidence",
    "KernelClaimParticipant",
    "KernelClaimRelation",
    "KernelEntity",
    "KernelEntityEmbedding",
    "KernelEntitySimilarityCandidate",
    "KernelObservation",
    "KernelProvenanceRecord",
    "KernelReasoningPath",
    "KernelReasoningPathStep",
    "KernelRelation",
    "KernelRelationEvidence",
    "KernelRelationClaim",
    "KernelRelationConflictSummary",
    "KernelRelationProjectionSource",
    "KernelSpaceRegistryEntry",
    "KernelSourceDocumentReference",
    "RelationClaimStatus",
    "RelationEvidenceWrite",
    "RelationConstraint",
    "TransformRegistry",
    "TransformVerificationResult",
    "ValueSet",
    "ValueSetItem",
    "VariableDefinition",
    "VariableSynonym",
]
