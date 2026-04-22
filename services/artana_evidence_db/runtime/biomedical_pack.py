"""Biomedical graph runtime pack owned by the standalone graph service."""

from __future__ import annotations

from artana_evidence_db.graph_domain_config import (
    GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG,
    GRAPH_SERVICE_RELATION_AUTOPROMOTION_DEFAULTS,
    GRAPH_SERVICE_RELATION_SUGGESTION_CONFIG,
    GRAPH_SERVICE_VIEW_CONFIG,
)
from artana_evidence_db.runtime.contracts import (
    FeatureFlagDefinition,
    GraphAgentCapabilities,
    GraphAgentCapability,
    GraphDomainContextPolicy,
    GraphDomainPack,
    GraphFeatureFlags,
    GraphRuntimeIdentity,
    SourceTypeDomainContextDefault,
)

BIOMEDICAL_GRAPH_DOMAIN_CONTEXT_POLICY = GraphDomainContextPolicy(
    source_type_defaults=(
        SourceTypeDomainContextDefault(
            source_type="pubmed",
            domain_context="clinical",
        ),
        SourceTypeDomainContextDefault(
            source_type="clinvar",
            domain_context="genomics",
        ),
        SourceTypeDomainContextDefault(
            source_type="marrvel",
            domain_context="genomics",
        ),
    ),
)

BIOMEDICAL_AGENT_CAPABILITIES = GraphAgentCapabilities(
    entity_recognition=GraphAgentCapability(
        name="entity_recognition",
        supported_source_types=("clinvar", "file_upload", "marrvel", "pubmed"),
        default_source_type="clinvar",
        step_key_prefix="entity.recognition",
    ),
    extraction=GraphAgentCapability(
        name="extraction",
        supported_source_types=("clinvar", "marrvel", "pubmed"),
        default_source_type="clinvar",
        step_key_prefix="extraction",
    ),
    graph_connection=GraphAgentCapability(
        name="graph_connection",
        supported_source_types=("clinvar", "pubmed"),
        default_source_type="clinvar",
        step_key_prefix="graph.connection",
    ),
    graph_search=GraphAgentCapability(
        name="graph_search",
        supported_source_types=("graph",),
        default_source_type="graph",
        step_key_prefix="graph.search",
    ),
)

BIOMEDICAL_GRAPH_FEATURE_FLAGS = GraphFeatureFlags(
    entity_embeddings=FeatureFlagDefinition(
        primary_env_name="GRAPH_ENABLE_ENTITY_EMBEDDINGS",
    ),
    relation_suggestions=FeatureFlagDefinition(
        primary_env_name="GRAPH_ENABLE_RELATION_SUGGESTIONS",
    ),
    hypothesis_generation=FeatureFlagDefinition(
        primary_env_name="GRAPH_ENABLE_HYPOTHESIS_GENERATION",
    ),
    search_agent=FeatureFlagDefinition(
        primary_env_name="GRAPH_ENABLE_SEARCH_AGENT",
        default_enabled=True,
    ),
)

BIOMEDICAL_GRAPH_DOMAIN_PACK = GraphDomainPack(
    name="biomedical",
    version="1.0.0",
    runtime_identity=GraphRuntimeIdentity(
        service_name="Biomedical Graph Service",
        jwt_issuer="graph-biomedical",
    ),
    view_extension=GRAPH_SERVICE_VIEW_CONFIG,
    feature_flags=BIOMEDICAL_GRAPH_FEATURE_FLAGS,
    dictionary_loading_extension=GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG,
    domain_context_policy=BIOMEDICAL_GRAPH_DOMAIN_CONTEXT_POLICY,
    agent_capabilities=BIOMEDICAL_AGENT_CAPABILITIES,
    relation_suggestion_extension=GRAPH_SERVICE_RELATION_SUGGESTION_CONFIG,
    relation_autopromotion_defaults=GRAPH_SERVICE_RELATION_AUTOPROMOTION_DEFAULTS,
)


def create_graph_domain_pack() -> GraphDomainPack:
    """Return the active graph runtime pack for runtime composition."""
    return BIOMEDICAL_GRAPH_DOMAIN_PACK


def create_graph_domain_context_policy() -> GraphDomainContextPolicy:
    """Return the active-pack domain-context policy for runtime callers."""
    return BIOMEDICAL_GRAPH_DOMAIN_PACK.domain_context_policy


def create_relation_autopromotion_defaults():
    """Return the active-pack relation auto-promotion defaults."""
    return BIOMEDICAL_GRAPH_DOMAIN_PACK.relation_autopromotion_defaults


__all__ = [
    "BIOMEDICAL_AGENT_CAPABILITIES",
    "BIOMEDICAL_GRAPH_DOMAIN_CONTEXT_POLICY",
    "BIOMEDICAL_GRAPH_DOMAIN_PACK",
    "BIOMEDICAL_GRAPH_FEATURE_FLAGS",
    "create_graph_domain_context_policy",
    "create_graph_domain_pack",
    "create_relation_autopromotion_defaults",
]
