"""Canonical graph runtime configuration owned by the standalone graph service."""

from __future__ import annotations

from artana_evidence_db.runtime.biomedical_pack import BIOMEDICAL_GRAPH_DOMAIN_PACK
from artana_evidence_db.runtime.contracts import (
    BuiltinRelationCategory,
    BuiltinRelationSynonymDefinition,
    BuiltinRelationTypeDefinition,
    DictionaryDomainContextDefinition,
    FeatureFlagDefinition,
    GraphAgentCapabilities,
    GraphAgentCapability,
    GraphDictionaryLoadingConfig,
    GraphDictionaryLoadingExtension,
    GraphDomainContextPolicy,
    GraphDomainPack,
    GraphDomainViewType,
    GraphFeatureFlags,
    GraphRelationSuggestionConfig,
    GraphRelationSuggestionExtension,
    GraphRuntimeIdentity,
    GraphViewConfig,
    GraphViewExtension,
    RelationAutopromotionDefaults,
    SourceTypeDomainContextDefault,
    is_flag_enabled,
)
from artana_evidence_db.runtime.domain_context import (
    default_graph_domain_context_for_source_type,
    resolve_graph_domain_context,
)
from artana_evidence_db.runtime.env import (
    allow_graph_test_auth_headers,
    resolve_graph_jwt_secret,
)
from artana_evidence_db.runtime.pack_registry import (
    bootstrap_default_graph_domain_packs,
    clear_graph_domain_pack_registry,
    create_graph_domain_context_policy,
    create_graph_domain_pack,
    create_relation_autopromotion_defaults,
    list_graph_domain_packs,
    register_graph_domain_pack,
    resolve_graph_domain_pack,
)
from artana_evidence_db.runtime.sports_pack import SPORTS_GRAPH_DOMAIN_PACK

__all__ = [
    "BIOMEDICAL_GRAPH_DOMAIN_PACK",
    "BuiltinRelationCategory",
    "BuiltinRelationSynonymDefinition",
    "BuiltinRelationTypeDefinition",
    "DictionaryDomainContextDefinition",
    "FeatureFlagDefinition",
    "GraphAgentCapabilities",
    "GraphAgentCapability",
    "GraphDictionaryLoadingConfig",
    "GraphDictionaryLoadingExtension",
    "GraphDomainContextPolicy",
    "GraphDomainPack",
    "GraphDomainViewType",
    "GraphFeatureFlags",
    "GraphRelationSuggestionConfig",
    "GraphRelationSuggestionExtension",
    "GraphRuntimeIdentity",
    "GraphViewConfig",
    "GraphViewExtension",
    "RelationAutopromotionDefaults",
    "SPORTS_GRAPH_DOMAIN_PACK",
    "SourceTypeDomainContextDefault",
    "allow_graph_test_auth_headers",
    "bootstrap_default_graph_domain_packs",
    "clear_graph_domain_pack_registry",
    "create_graph_domain_context_policy",
    "create_graph_domain_pack",
    "create_relation_autopromotion_defaults",
    "default_graph_domain_context_for_source_type",
    "is_flag_enabled",
    "list_graph_domain_packs",
    "register_graph_domain_pack",
    "resolve_graph_domain_context",
    "resolve_graph_domain_pack",
    "resolve_graph_jwt_secret",
]
