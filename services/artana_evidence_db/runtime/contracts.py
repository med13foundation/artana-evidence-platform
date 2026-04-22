"""Graph runtime contracts owned by the standalone graph service."""

from __future__ import annotations

import os
from dataclasses import dataclass

from artana_evidence_db.graph_domain_config import (
    BuiltinRelationCategory,
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

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True)
class GraphRuntimeIdentity:
    """Default runtime identity values supplied by the graph runtime pack."""

    service_name: str
    jwt_issuer: str


@dataclass(frozen=True)
class SourceTypeDomainContextDefault:
    """Default domain context for one source type."""

    source_type: str
    domain_context: str


@dataclass(frozen=True)
class GraphDomainContextPolicy:
    """Pack-owned policy for resolving source-type domain defaults."""

    source_type_defaults: tuple[SourceTypeDomainContextDefault, ...]


@dataclass(frozen=True)
class GraphAgentCapability:
    """Opaque AI capability metadata exposed by a graph domain pack."""

    name: str
    supported_source_types: tuple[str, ...]
    default_source_type: str | None = None
    step_key_prefix: str | None = None


@dataclass(frozen=True)
class GraphAgentCapabilities:
    """Opaque AI capability bundle for AI service discovery."""

    entity_recognition: GraphAgentCapability
    extraction: GraphAgentCapability
    graph_connection: GraphAgentCapability
    graph_search: GraphAgentCapability


@dataclass(frozen=True)
class FeatureFlagDefinition:
    """Runtime env contract for one graph-runtime feature."""

    primary_env_name: str
    legacy_env_name: str | None = None
    default_enabled: bool = False

    @property
    def default_value(self) -> str:
        return "1" if self.default_enabled else "0"

    @property
    def env_display_name(self) -> str:
        if self.legacy_env_name is None:
            return f"{self.primary_env_name}=1"
        return f"{self.primary_env_name}=1 (legacy alias: {self.legacy_env_name}=1)"


@dataclass(frozen=True)
class GraphFeatureFlags:
    """Feature-flag definitions exposed by the graph runtime pack."""

    entity_embeddings: FeatureFlagDefinition
    relation_suggestions: FeatureFlagDefinition
    hypothesis_generation: FeatureFlagDefinition
    search_agent: FeatureFlagDefinition


def is_flag_enabled(definition: FeatureFlagDefinition) -> bool:
    """Resolve one graph-runtime feature flag from env."""
    value = os.getenv(definition.primary_env_name)
    if value is not None:
        return value.strip().lower() in _TRUE_VALUES

    if definition.legacy_env_name is not None:
        legacy_value = os.getenv(definition.legacy_env_name)
        if legacy_value is not None:
            return legacy_value.strip().lower() in _TRUE_VALUES

    return definition.default_value in _TRUE_VALUES


@dataclass(frozen=True)
class GraphDomainPack:
    """Single graph runtime pack layered on top of artana-evidence-db internals."""

    name: str
    version: str
    runtime_identity: GraphRuntimeIdentity
    view_extension: GraphViewExtension
    feature_flags: GraphFeatureFlags
    dictionary_loading_extension: GraphDictionaryLoadingExtension
    domain_context_policy: GraphDomainContextPolicy
    agent_capabilities: GraphAgentCapabilities
    relation_suggestion_extension: GraphRelationSuggestionExtension
    relation_autopromotion_defaults: RelationAutopromotionDefaults

    @property
    def dictionary_domain_contexts(
        self,
    ) -> tuple[DictionaryDomainContextDefinition, ...]:
        """Compatibility accessor for pack-owned builtin dictionary contexts."""
        return self.dictionary_loading_extension.builtin_domain_contexts


__all__ = [
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
    "SourceTypeDomainContextDefault",
    "is_flag_enabled",
]
