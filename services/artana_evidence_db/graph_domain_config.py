"""Service-local biomedical graph-domain configuration."""

from __future__ import annotations

from artana_evidence_db.graph_domain_constraints import (
    GRAPH_SERVICE_BUILTIN_RELATION_CONSTRAINTS,
)
from artana_evidence_db.graph_domain_qualifiers import (
    GRAPH_SERVICE_BUILTIN_QUALIFIER_DEFINITIONS,
)
from artana_evidence_db.graph_domain_relation_types import (
    GRAPH_SERVICE_BUILTIN_ENTITY_TYPES,
    GRAPH_SERVICE_BUILTIN_RELATION_TYPES,
    GRAPH_SERVICE_DICTIONARY_DOMAIN_CONTEXTS,
)
from artana_evidence_db.graph_domain_synonyms import (
    GRAPH_SERVICE_BUILTIN_RELATION_SYNONYMS,
)
from artana_evidence_db.graph_domain_types import (
    BuiltinEntityTypeDefinition,
    BuiltinQualifierDefinition,
    BuiltinRelationCategory,
    BuiltinRelationConstraintDefinition,
    BuiltinRelationSynonymDefinition,
    BuiltinRelationTypeDefinition,
    DictionaryDomainContextDefinition,
    GraphDictionaryLoadingConfig,
    GraphDictionaryLoadingExtension,
    GraphDomainViewType,
    GraphRelationSuggestionConfig,
    GraphRelationSuggestionExtension,
    GraphViewConfig,
    GraphViewExtension,
)
from artana_evidence_db.relation_autopromotion_policy import (
    RelationAutopromotionDefaults,
)

GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG = GraphDictionaryLoadingConfig(
    builtin_domain_contexts=GRAPH_SERVICE_DICTIONARY_DOMAIN_CONTEXTS,
    builtin_entity_types=GRAPH_SERVICE_BUILTIN_ENTITY_TYPES,
    builtin_relation_types=GRAPH_SERVICE_BUILTIN_RELATION_TYPES,
    builtin_relation_synonyms=GRAPH_SERVICE_BUILTIN_RELATION_SYNONYMS,
    builtin_relation_constraints=GRAPH_SERVICE_BUILTIN_RELATION_CONSTRAINTS,
    builtin_qualifier_definitions=GRAPH_SERVICE_BUILTIN_QUALIFIER_DEFINITIONS,
)

GRAPH_SERVICE_VIEW_CONFIG = GraphViewConfig(
    entity_view_types={
        "gene": "GENE",
        "variant": "VARIANT",
        "phenotype": "PHENOTYPE",
    },
    document_view_types=frozenset({"paper"}),
    claim_view_types=frozenset({"claim"}),
    mechanism_relation_types=frozenset(
        {
            "CAUSES",
            "UPSTREAM_OF",
            "DOWNSTREAM_OF",
            "REFINES",
            "SUPPORTS",
            "GENERALIZES",
            "INSTANCE_OF",
        },
    ),
)

GRAPH_SERVICE_RELATION_SUGGESTION_CONFIG = GraphRelationSuggestionConfig()
GRAPH_SERVICE_RELATION_AUTOPROMOTION_DEFAULTS = RelationAutopromotionDefaults()


__all__ = [
    "BuiltinEntityTypeDefinition",
    "BuiltinQualifierDefinition",
    "BuiltinRelationConstraintDefinition",
    "BuiltinRelationCategory",
    "BuiltinRelationSynonymDefinition",
    "BuiltinRelationTypeDefinition",
    "DictionaryDomainContextDefinition",
    "GRAPH_SERVICE_BUILTIN_ENTITY_TYPES",
    "GRAPH_SERVICE_BUILTIN_QUALIFIER_DEFINITIONS",
    "GRAPH_SERVICE_BUILTIN_RELATION_CONSTRAINTS",
    "GRAPH_SERVICE_BUILTIN_RELATION_SYNONYMS",
    "GRAPH_SERVICE_BUILTIN_RELATION_TYPES",
    "GRAPH_SERVICE_DICTIONARY_DOMAIN_CONTEXTS",
    "GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG",
    "GRAPH_SERVICE_RELATION_AUTOPROMOTION_DEFAULTS",
    "GRAPH_SERVICE_RELATION_SUGGESTION_CONFIG",
    "GRAPH_SERVICE_VIEW_CONFIG",
    "GraphDictionaryLoadingConfig",
    "GraphDictionaryLoadingExtension",
    "GraphRelationSuggestionConfig",
    "GraphRelationSuggestionExtension",
    "GraphDomainViewType",
    "GraphViewConfig",
    "GraphViewExtension",
]
