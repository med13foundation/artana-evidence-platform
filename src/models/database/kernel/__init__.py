# Kernel Database Models - Metadata-Driven Graph Kernel
#
# NOTE: Workspace scoping is handled by the existing ResearchSpace models
# (``src/models/database/research_space.py``). The kernel itself provides
# dictionary + fact tables (entities/observations/relations/provenance).

from .claim_evidence import ClaimEvidenceModel
from .claim_participants import ClaimParticipantModel
from .claim_relations import ClaimRelationModel
from .concepts import (
    ConceptAliasModel,
    ConceptDecisionModel,
    ConceptHarnessResultModel,
    ConceptLinkModel,
    ConceptMemberModel,
    ConceptPolicyModel,
    ConceptSetModel,
)
from .dictionary import (
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
from .entities import (
    EntityAliasModel,
    EntityEmbeddingModel,
    EntityIdentifierModel,
    EntityModel,
)
from .observations import ObservationModel
from .operation_runs import (
    GraphOperationRunModel,
    GraphOperationRunStatusEnum,
    GraphOperationRunTypeEnum,
)
from .provenance import ProvenanceModel
from .read_models import (
    EntityClaimSummaryModel,
    EntityMechanismPathModel,
    EntityNeighborModel,
    EntityRelationSummaryModel,
)
from .reasoning_paths import ReasoningPathModel, ReasoningPathStepModel
from .relation_claims import RelationClaimModel
from .relation_projection_sources import RelationProjectionSourceModel
from .relations import RelationEvidenceModel, RelationModel
from .space_memberships import (
    GraphSpaceMembershipModel,
    GraphSpaceMembershipRoleEnum,
)
from .spaces import GraphSpaceModel, GraphSpaceStatusEnum

__all__ = [
    # Dictionary (Layer 1)
    "DictionaryChangelogModel",
    "DictionaryDataTypeModel",
    "DictionaryDomainContextModel",
    "DictionaryEntityTypeModel",
    "DictionaryRelationSynonymModel",
    "DictionaryRelationTypeModel",
    "DictionarySensitivityLevelModel",
    "VariableDefinitionModel",
    "VariableSynonymModel",
    "TransformRegistryModel",
    "ValueSetModel",
    "ValueSetItemModel",
    "EntityResolutionPolicyModel",
    "RelationConstraintModel",
    # Concept Manager
    "ConceptAliasModel",
    "ConceptDecisionModel",
    "ConceptHarnessResultModel",
    "ConceptLinkModel",
    "ConceptMemberModel",
    "ConceptPolicyModel",
    "ConceptSetModel",
    "ClaimEvidenceModel",
    "ClaimParticipantModel",
    "ClaimRelationModel",
    # Core Data (Layer 2)
    "EntityModel",
    "EntityAliasModel",
    "EntityIdentifierModel",
    "EntityEmbeddingModel",
    "GraphOperationRunModel",
    "GraphOperationRunStatusEnum",
    "GraphOperationRunTypeEnum",
    "ObservationModel",
    "RelationEvidenceModel",
    "RelationClaimModel",
    "RelationProjectionSourceModel",
    "RelationModel",
    "ProvenanceModel",
    "EntityClaimSummaryModel",
    "EntityMechanismPathModel",
    "EntityNeighborModel",
    "EntityRelationSummaryModel",
    "ReasoningPathModel",
    "ReasoningPathStepModel",
    "GraphSpaceMembershipModel",
    "GraphSpaceMembershipRoleEnum",
    "GraphSpaceModel",
    "GraphSpaceStatusEnum",
]
