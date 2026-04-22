# Artana Resource Library - SQLAlchemy Database Models
# Metadata-driven graph kernel + infrastructure models
#
# MIGRATION NOTE (2026-02-09): Old domain-specific models (Gene, Variant,
# Phenotype, Evidence, Mechanism, etc.) have been replaced by the kernel
# schema: Entity, Observation, Relation, Provenance + Dictionary tables.
# Surviving infrastructure models are preserved below.

from . import (
    audit,
    base,
    data_discovery,
    data_source_activation,
    extraction_queue,
    harness,
    ingestion_job,
    ingestion_scheduler_job,
    ingestion_source_lock,
    pipeline_run_event,
    publication,
    publication_extraction,
    research_space,
    review,
    session,
    source_document,
    source_record_ledger,
    source_sync_state,
    source_template,
    storage,
    system_status,
    user,
    user_data_source,
)
from .kernel import (
    ClaimParticipantModel,
    ClaimRelationModel,
    ConceptAliasModel,
    ConceptDecisionModel,
    ConceptHarnessResultModel,
    ConceptLinkModel,
    ConceptMemberModel,
    ConceptPolicyModel,
    ConceptSetModel,
    EntityAliasModel,
    EntityClaimSummaryModel,
    EntityEmbeddingModel,
    EntityIdentifierModel,
    EntityMechanismPathModel,
    EntityModel,
    EntityNeighborModel,
    EntityRelationSummaryModel,
    EntityResolutionPolicyModel,
    GraphOperationRunModel,
    GraphOperationRunStatusEnum,
    GraphOperationRunTypeEnum,
    GraphSpaceMembershipModel,
    GraphSpaceMembershipRoleEnum,
    GraphSpaceModel,
    GraphSpaceStatusEnum,
    ObservationModel,
    ProvenanceModel,
    RelationClaimModel,
    RelationConstraintModel,
    RelationEvidenceModel,
    RelationModel,
    TransformRegistryModel,
    VariableDefinitionModel,
    VariableSynonymModel,
)

# ── Surviving infrastructure models ──
AuditLog = audit.AuditLog
Base = base.Base
HarnessApprovalModel = harness.HarnessApprovalModel
HarnessChatMessageModel = harness.HarnessChatMessageModel
HarnessChatSessionModel = harness.HarnessChatSessionModel
HarnessGraphSnapshotModel = harness.HarnessGraphSnapshotModel
HarnessIntentModel = harness.HarnessIntentModel
HarnessProposalModel = harness.HarnessProposalModel
HarnessResearchStateModel = harness.HarnessResearchStateModel
HarnessRunModel = harness.HarnessRunModel
HarnessScheduleModel = harness.HarnessScheduleModel
SessionModel = session.SessionModel
SystemStatusModel = system_status.SystemStatusModel
UserModel = user.UserModel

SourceTemplateModel = source_template.SourceTemplateModel
SourceTypeEnum = source_template.SourceTypeEnum
TemplateCategory = source_template.TemplateCategoryEnum

UserDataSourceModel = user_data_source.UserDataSourceModel
DataSourceActivationModel = data_source_activation.DataSourceActivationModel
IngestionJobModel = ingestion_job.IngestionJobModel
ExtractionQueueItemModel = extraction_queue.ExtractionQueueItemModel
PublicationModel = publication.PublicationModel
PublicationType = publication.PublicationType
PublicationExtractionModel = publication_extraction.PublicationExtractionModel
ExtractionOutcomeEnum = publication_extraction.ExtractionOutcomeEnum
ReviewRecord = review.ReviewRecord
SourceSyncStateModel = source_sync_state.SourceSyncStateModel
SourceRecordLedgerModel = source_record_ledger.SourceRecordLedgerModel
SourceDocumentModel = source_document.SourceDocumentModel
IngestionSchedulerJobModel = ingestion_scheduler_job.IngestionSchedulerJobModel
IngestionSourceLockModel = ingestion_source_lock.IngestionSourceLockModel
PipelineRunEventModel = pipeline_run_event.PipelineRunEventModel
DocumentFormatEnum = source_document.DocumentFormatEnum
EnrichmentStatusEnum = source_document.EnrichmentStatusEnum
DocumentExtractionStatusEnum = source_document.DocumentExtractionStatusEnum

ResearchSpaceModel = research_space.ResearchSpaceModel
ResearchSpaceMembershipModel = research_space.ResearchSpaceMembershipModel
MembershipRoleEnum = research_space.MembershipRoleEnum
SpaceStatusEnum = research_space.SpaceStatusEnum

SourceCatalogEntryModel = data_discovery.SourceCatalogEntryModel

StorageConfigurationModel = storage.StorageConfigurationModel
StorageHealthSnapshotModel = storage.StorageHealthSnapshotModel
StorageHealthStatusEnum = storage.StorageHealthStatusEnum
StorageOperationModel = storage.StorageOperationModel
StorageOperationStatusEnum = storage.StorageOperationStatusEnum
StorageOperationTypeEnum = storage.StorageOperationTypeEnum
StorageProviderEnum = storage.StorageProviderEnum

__all__ = [
    # Base
    "Base",
    # Kernel: Dictionary (Layer 1)
    "VariableDefinitionModel",
    "VariableSynonymModel",
    "TransformRegistryModel",
    "EntityResolutionPolicyModel",
    "RelationConstraintModel",
    # Kernel: Concept Manager
    "ConceptSetModel",
    "ConceptMemberModel",
    "ConceptAliasModel",
    "ConceptLinkModel",
    "ConceptPolicyModel",
    "ConceptDecisionModel",
    "ConceptHarnessResultModel",
    "ClaimParticipantModel",
    "ClaimRelationModel",
    # Kernel: Data (Layer 2)
    "EntityClaimSummaryModel",
    "EntityAliasModel",
    "EntityMechanismPathModel",
    "EntityModel",
    "EntityIdentifierModel",
    "EntityNeighborModel",
    "EntityEmbeddingModel",
    "GraphOperationRunModel",
    "GraphOperationRunStatusEnum",
    "GraphOperationRunTypeEnum",
    "GraphSpaceMembershipModel",
    "GraphSpaceMembershipRoleEnum",
    "GraphSpaceModel",
    "GraphSpaceStatusEnum",
    "ObservationModel",
    "RelationClaimModel",
    "RelationEvidenceModel",
    "RelationModel",
    "ProvenanceModel",
    "EntityRelationSummaryModel",
    # Surviving infrastructure
    "AuditLog",
    "SessionModel",
    "HarnessRunModel",
    "HarnessIntentModel",
    "HarnessApprovalModel",
    "HarnessChatSessionModel",
    "HarnessChatMessageModel",
    "HarnessGraphSnapshotModel",
    "HarnessProposalModel",
    "HarnessResearchStateModel",
    "HarnessScheduleModel",
    "SourceTemplateModel",
    "SourceTypeEnum",
    "StorageConfigurationModel",
    "StorageHealthSnapshotModel",
    "StorageHealthStatusEnum",
    "StorageOperationModel",
    "StorageOperationStatusEnum",
    "StorageOperationTypeEnum",
    "StorageProviderEnum",
    "SystemStatusModel",
    "TemplateCategory",
    "UserModel",
    # Restored Infrastructure
    "UserDataSourceModel",
    "DataSourceActivationModel",
    "IngestionJobModel",
    "ExtractionQueueItemModel",
    "PublicationModel",
    "PublicationType",
    "PublicationExtractionModel",
    "ExtractionOutcomeEnum",
    "ReviewRecord",
    "SourceSyncStateModel",
    "SourceRecordLedgerModel",
    "SourceDocumentModel",
    "IngestionSchedulerJobModel",
    "IngestionSourceLockModel",
    "PipelineRunEventModel",
    "DocumentFormatEnum",
    "EnrichmentStatusEnum",
    "DocumentExtractionStatusEnum",
    # Restored ResearchSpace
    "ResearchSpaceModel",
    "ResearchSpaceMembershipModel",
    "MembershipRoleEnum",
    "SpaceStatusEnum",
    # Restored DataDiscovery
    "SourceCatalogEntryModel",
]
