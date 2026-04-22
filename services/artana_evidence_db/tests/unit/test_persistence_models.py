from __future__ import annotations

from artana_evidence_db.entity_embedding_model import EntityEmbeddingModel
from artana_evidence_db.entity_embedding_status_model import (
    EntityEmbeddingStatusModel,
)
from artana_evidence_db.entity_lookup_models import (
    EntityAliasModel,
    EntityIdentifierModel,
)
from artana_evidence_db.kernel_claim_models import (
    ClaimEvidenceModel,
    ClaimParticipantModel,
    RelationClaimModel,
    RelationProjectionSourceModel,
)
from artana_evidence_db.kernel_concept_models import (
    ConceptAliasModel,
    ConceptDecisionModel,
    ConceptHarnessResultModel,
    ConceptLinkModel,
    ConceptMemberModel,
    ConceptPolicyModel,
    ConceptSetModel,
)
from artana_evidence_db.kernel_dictionary_models import (
    DictionaryChangelogModel,
    DictionaryDataTypeModel,
    DictionaryDomainContextModel,
    DictionaryEntityTypeModel,
    DictionaryRelationSynonymModel,
    DictionaryRelationTypeModel,
    DictionarySensitivityLevelModel,
    EntityResolutionPolicyModel,
    RelationConstraintModel,
    TransformRegistryModel,
    ValueSetItemModel,
    ValueSetModel,
    VariableDefinitionModel,
    VariableSynonymModel,
)
from artana_evidence_db.kernel_entity_models import EntityModel
from artana_evidence_db.kernel_relation_models import (
    RelationEvidenceModel,
    RelationModel,
)
from artana_evidence_db.observation_persistence_model import ObservationModel
from artana_evidence_db.operation_run_models import (
    GraphOperationRunModel,
    GraphOperationRunStatusEnum,
    GraphOperationRunTypeEnum,
)
from artana_evidence_db.pack_seed_models import (
    GraphPackSeedOperationEnum,
    GraphPackSeedStatusEnum,
    GraphPackSeedStatusModel,
)
from artana_evidence_db.provenance_model import ProvenanceModel
from artana_evidence_db.read_models import (
    EntityClaimSummaryModel,
    EntityMechanismPathModel,
    EntityNeighborModel,
    EntityRelationSummaryModel,
)
from artana_evidence_db.reasoning_path_persistence_models import (
    ReasoningPathModel,
    ReasoningPathStepModel,
)
from artana_evidence_db.source_document_model import (
    DocumentExtractionStatusEnum,
    DocumentFormatEnum,
    EnrichmentStatusEnum,
    SourceDocumentModel,
)
from artana_evidence_db.space_models import (
    GraphSpaceMembershipModel,
    GraphSpaceMembershipRoleEnum,
    GraphSpaceModel,
    GraphSpaceStatusEnum,
)


def test_source_document_model_exports_local_enums() -> None:
    assert SourceDocumentModel.__table__.name == "source_documents"
    assert DocumentFormatEnum.JSON.value == "json"
    assert EnrichmentStatusEnum.PENDING.value == "pending"
    assert DocumentExtractionStatusEnum.EXTRACTED.value == "extracted"


def test_operation_run_model_exports_local_enums() -> None:
    assert GraphOperationRunModel.__table__.name == "graph_operation_runs"
    assert GraphOperationRunTypeEnum.PROJECTION_REPAIR.value == "projection_repair"
    assert GraphOperationRunStatusEnum.SUCCEEDED.value == "succeeded"


def test_pack_seed_model_exports_local_enums() -> None:
    assert GraphPackSeedStatusModel.__table__.name == "graph_pack_seed_status"
    assert GraphPackSeedStatusEnum.SEEDED.value == "seeded"
    assert GraphPackSeedOperationEnum.REPAIR.value == "repair"


def test_entity_and_relation_models_use_local_tables() -> None:
    assert EntityModel.__table__.name == "entities"
    assert EntityIdentifierModel.__table__.name == "entity_identifiers"
    assert EntityAliasModel.__table__.name == "entity_aliases"
    assert EntityEmbeddingModel.__table__.name == "entity_embeddings"
    assert EntityEmbeddingStatusModel.__table__.name == "entity_embedding_status"
    assert RelationModel.__table__.name == "relations"
    assert RelationEvidenceModel.__table__.name == "relation_evidence"


def test_claim_models_use_local_tables() -> None:
    assert ClaimEvidenceModel.__table__.name == "claim_evidence"
    assert ClaimParticipantModel.__table__.name == "claim_participants"
    assert RelationClaimModel.__table__.name == "relation_claims"
    assert RelationProjectionSourceModel.__table__.name == "relation_projection_sources"


def test_concept_models_use_local_tables() -> None:
    assert ConceptSetModel.__table__.name == "concept_sets"
    assert ConceptMemberModel.__table__.name == "concept_members"
    assert ConceptAliasModel.__table__.name == "concept_aliases"
    assert ConceptLinkModel.__table__.name == "concept_links"
    assert ConceptPolicyModel.__table__.name == "concept_policies"
    assert ConceptDecisionModel.__table__.name == "concept_decisions"
    assert ConceptHarnessResultModel.__table__.name == "concept_harness_results"


def test_dictionary_models_use_local_table_aliases() -> None:
    assert DictionaryDataTypeModel.__table__.name == "dictionary_data_types"
    assert DictionaryDomainContextModel.__table__.name == "dictionary_domain_contexts"
    assert (
        DictionarySensitivityLevelModel.__table__.name
        == "dictionary_sensitivity_levels"
    )
    assert DictionaryEntityTypeModel.__table__.name == "dictionary_entity_types"
    assert DictionaryRelationTypeModel.__table__.name == "dictionary_relation_types"
    assert (
        DictionaryRelationSynonymModel.__table__.name == "dictionary_relation_synonyms"
    )
    assert ValueSetModel.__table__.name == "value_sets"
    assert ValueSetItemModel.__table__.name == "value_set_items"
    assert VariableDefinitionModel.__table__.name == "variable_definitions"
    assert VariableSynonymModel.__table__.name == "variable_synonyms"
    assert TransformRegistryModel.__table__.name == "transform_registry"
    assert EntityResolutionPolicyModel.__table__.name == "entity_resolution_policies"
    assert RelationConstraintModel.__table__.name == "relation_constraints"
    assert DictionaryChangelogModel.__table__.name == "dictionary_changelog"


def test_space_models_use_local_tables_and_enums() -> None:
    assert GraphSpaceModel.__table__.name == "graph_spaces"
    assert GraphSpaceMembershipModel.__table__.name == "graph_space_memberships"
    assert GraphSpaceStatusEnum.ACTIVE.value == "active"
    assert GraphSpaceMembershipRoleEnum.ADMIN.value == "admin"


def test_provenance_model_uses_local_table() -> None:
    assert ProvenanceModel.__table__.name == "provenance"


def test_read_models_use_local_tables() -> None:
    assert EntityNeighborModel.__table__.name == "entity_neighbors"
    assert EntityClaimSummaryModel.__table__.name == "entity_claim_summary"
    assert EntityMechanismPathModel.__table__.name == "entity_mechanism_paths"
    assert EntityRelationSummaryModel.__table__.name == "entity_relation_summary"


def test_reasoning_path_models_use_local_tables() -> None:
    assert ReasoningPathModel.__table__.name == "reasoning_paths"
    assert ReasoningPathStepModel.__table__.name == "reasoning_path_steps"


def test_observation_model_uses_local_table() -> None:
    assert ObservationModel.__table__.name == "observations"
