"""AI-side graph-domain configuration contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from src.type_definitions.common import JSONValue


@dataclass(frozen=True)
class EntityRecognitionPromptConfig:
    """Prompt selection config for entity-recognition adapters."""

    system_prompts_by_source_type: dict[str, str]

    def supported_source_types(self) -> frozenset[str]:
        return frozenset(self.system_prompts_by_source_type)

    def system_prompt_for(self, source_type: str) -> str | None:
        return self.system_prompts_by_source_type.get(source_type)


@dataclass(frozen=True)
class EntityRecognitionCompactRecordRule:
    """Compact-record shaping rules for one entity-recognition source type."""

    fields: tuple[str, ...]
    preferred_text_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class EntityRecognitionPayloadConfig:
    """Payload shaping config for entity-recognition adapters."""

    compact_record_rules: dict[str, EntityRecognitionCompactRecordRule]

    def compact_record_rule_for(
        self,
        source_type: str,
    ) -> EntityRecognitionCompactRecordRule | None:
        return self.compact_record_rules.get(source_type)


@dataclass(frozen=True)
class ExtractionCompactRecordRule:
    """Compact-record shaping rules for one extraction source type."""

    fields: tuple[str, ...]
    chunk_fields: tuple[str, ...] | None = None
    chunk_indicator_field: str | None = None
    fallback_text_field: str | None = None

    def fields_for_chunk_scope(self, *, is_chunk_scope: bool) -> tuple[str, ...]:
        if is_chunk_scope and self.chunk_fields is not None:
            return self.chunk_fields
        return self.fields


@dataclass(frozen=True)
class ExtractionPayloadConfig:
    """Payload shaping config for extraction adapters."""

    compact_record_rules: dict[str, ExtractionCompactRecordRule]

    def compact_record_rule_for(
        self,
        source_type: str,
    ) -> ExtractionCompactRecordRule | None:
        return self.compact_record_rules.get(source_type)


@dataclass(frozen=True)
class ExtractionPromptConfig:
    """Prompt selection config for extraction adapters."""

    system_prompts_by_source_type: dict[str, str]

    def supported_source_types(self) -> frozenset[str]:
        return frozenset(self.system_prompts_by_source_type)

    def system_prompt_for(self, source_type: str) -> str | None:
        return self.system_prompts_by_source_type.get(source_type)


class GraphConnectorExtension(Protocol):
    """Connector dispatch semantics for graph-connection adapters."""

    @property
    def default_source_type(self) -> str:
        """Return the default connector source type."""

    @property
    def system_prompts_by_source_type(self) -> dict[str, str]:
        """Return connector prompts keyed by source type."""

    def supported_source_types(self) -> frozenset[str]:
        """Return supported connector source types."""

    def resolve_source_type(self, source_type: str | None) -> str:
        """Resolve one optional source type into a connector source type."""

    def system_prompt_for(self, source_type: str) -> str | None:
        """Return the system prompt for one connector source type."""

    def step_key_for(self, source_type: str) -> str:
        """Return the replay step key for one connector source type."""


@dataclass(frozen=True)
class GraphConnectionPromptConfig:
    """Prompt selection config for graph-connection adapters."""

    default_source_type: str
    system_prompts_by_source_type: dict[str, str]
    step_key_prefix: str = "graph.connection"

    def supported_source_types(self) -> frozenset[str]:
        return frozenset(self.system_prompts_by_source_type)

    def resolve_source_type(self, source_type: str | None) -> str:
        if isinstance(source_type, str):
            normalized = source_type.strip().lower()
            if normalized:
                return normalized
        return self.default_source_type

    def system_prompt_for(self, source_type: str) -> str | None:
        return self.system_prompts_by_source_type.get(source_type.strip().lower())

    def step_key_for(self, source_type: str) -> str:
        normalized = source_type.strip().lower()
        return f"{self.step_key_prefix}.{normalized}.v1"


class GraphSearchExtension(Protocol):
    """Graph search semantics consumed by runtime adapters."""

    @property
    def system_prompt(self) -> str:
        """Return the prompt used by graph-search adapters."""

    @property
    def step_key(self) -> str:
        """Return the step key emitted by graph-search execution."""


@dataclass(frozen=True)
class GraphSearchConfig:
    """Default graph search extension configuration."""

    system_prompt: str
    step_key: str = "graph.search.v1"


@dataclass(frozen=True)
class BootstrapRelationTypeDefinition:
    relation_type: str
    display_name: str
    description: str
    is_directional: bool
    inverse_label: str | None


@dataclass(frozen=True)
class BootstrapRelationConstraintDefinition:
    source_type: str
    relation_type: str
    target_type: str
    requires_evidence: bool


@dataclass(frozen=True)
class BootstrapVariableDefinition:
    variable_id: str
    canonical_name: str
    display_name: str
    data_type: str
    description: str
    constraints: dict[str, JSONValue] | None
    synonyms: tuple[str, ...]


@dataclass(frozen=True)
class DomainBootstrapEntityTypes:
    domain_context: str
    entity_types: tuple[str, ...]


@dataclass(frozen=True)
class EntityRecognitionBootstrapConfig:
    default_relation_type: str
    default_relation_display_name: str
    default_relation_description: str
    default_relation_inverse_label: str | None
    interaction_relation_type: str
    interaction_relation_display_name: str
    interaction_relation_description: str
    interaction_relation_inverse_label: str | None
    min_entity_types_for_default_relation: int
    interaction_entity_types: tuple[str, ...]
    domain_entity_types: tuple[DomainBootstrapEntityTypes, ...]
    source_types_with_publication_baseline: tuple[str, ...]
    publication_baseline_source_label: str
    publication_baseline_entity_description: str
    publication_baseline_entity_types: tuple[str, ...]
    publication_baseline_relation_types: tuple[BootstrapRelationTypeDefinition, ...]
    publication_baseline_constraints: tuple[BootstrapRelationConstraintDefinition, ...]
    publication_metadata_variables: tuple[BootstrapVariableDefinition, ...]


@dataclass(frozen=True)
class EntityRecognitionHeuristicFieldMap:
    """Fallback field mappings for source-specific entity heuristics."""

    source_type_fields: dict[str, dict[str, tuple[str, ...]]]
    default_source_type: str
    primary_entity_types: dict[str, str]

    def field_keys_for(self, source_type: str, field: str) -> tuple[str, ...]:
        source_mapping = self.source_type_fields.get(
            source_type,
            self.source_type_fields[self.default_source_type],
        )
        return source_mapping.get(field, ())

    def primary_entity_type_for(self, source_type: str) -> str:
        return self.primary_entity_types.get(
            source_type,
            self.primary_entity_types[self.default_source_type],
        )


@dataclass(frozen=True)
class ExtractionHeuristicRelation:
    """Heuristic relation emitted by deterministic extraction fallback."""

    source_type: str
    relation_type: str
    target_type: str
    polarity: Literal["SUPPORT", "REFUTE", "UNCERTAIN", "HYPOTHESIS"] = "UNCERTAIN"


@dataclass(frozen=True)
class ExtractionHeuristicConfig:
    """Extraction fallback defaults."""

    relation_when_variant_and_phenotype_present: ExtractionHeuristicRelation
    claim_text_fields: tuple[str, ...]


@dataclass(frozen=True)
class GraphDomainAiConfig:
    """AI-side config selected to match a graph domain pack."""

    pack_name: str
    entity_recognition_bootstrap: EntityRecognitionBootstrapConfig
    entity_recognition_fallback: EntityRecognitionHeuristicFieldMap
    entity_recognition_payload: EntityRecognitionPayloadConfig
    entity_recognition_prompt: EntityRecognitionPromptConfig
    extraction_fallback: ExtractionHeuristicConfig
    extraction_payload: ExtractionPayloadConfig
    extraction_prompt: ExtractionPromptConfig
    graph_connection_prompt: GraphConnectorExtension
    search_extension: GraphSearchExtension


__all__ = [
    "BootstrapRelationConstraintDefinition",
    "BootstrapRelationTypeDefinition",
    "BootstrapVariableDefinition",
    "DomainBootstrapEntityTypes",
    "EntityRecognitionBootstrapConfig",
    "EntityRecognitionCompactRecordRule",
    "EntityRecognitionHeuristicFieldMap",
    "EntityRecognitionPayloadConfig",
    "EntityRecognitionPromptConfig",
    "ExtractionCompactRecordRule",
    "ExtractionHeuristicConfig",
    "ExtractionHeuristicRelation",
    "ExtractionPayloadConfig",
    "ExtractionPromptConfig",
    "GraphConnectionPromptConfig",
    "GraphConnectorExtension",
    "GraphDomainAiConfig",
    "GraphSearchConfig",
    "GraphSearchExtension",
]
