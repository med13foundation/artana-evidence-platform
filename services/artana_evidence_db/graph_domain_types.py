"""Typed graph-domain configuration contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

GraphDomainViewType = str
BuiltinRelationCategory = Literal[
    "core_causal",
    "extended_scientific",
    "document_governance",
]


@dataclass(frozen=True, slots=True)
class DictionaryDomainContextDefinition:
    """One builtin dictionary domain context definition."""

    id: str
    display_name: str
    description: str


@dataclass(frozen=True, slots=True)
class BuiltinEntityTypeDefinition:
    """One builtin canonical entity type definition."""

    entity_type: str
    display_name: str
    description: str
    domain_context: str


@dataclass(frozen=True, slots=True)
class BuiltinRelationTypeDefinition:
    """One builtin canonical relation type definition."""

    relation_type: str
    display_name: str
    description: str
    domain_context: str
    category: BuiltinRelationCategory
    is_directional: bool = True
    inverse_label: str | None = None


@dataclass(frozen=True, slots=True)
class BuiltinRelationSynonymDefinition:
    """One builtin relation synonym definition."""

    relation_type: str
    synonym: str
    source: str | None = None


@dataclass(frozen=True, slots=True)
class BuiltinRelationConstraintDefinition:
    """One builtin allowed relation constraint definition.

    The ``profile`` field controls governance behavior:
      - ``"FORBIDDEN"`` — nonsensical or explicitly prohibited combination.
        Claims are rejected at validation time.
      - ``"EXPECTED"`` — high-value combination actively sought by
        extraction agents. Claims are auto-promotable if evidence is strong.
      - ``"ALLOWED"`` — valid combination accepted through the governed path.
        Claims require standard review (default).
      - ``"REVIEW_ONLY"`` — valid but unusual combination. Claims always
        require human review before promotion.
    """

    source_type: str
    relation_type: str
    target_type: str
    requires_evidence: bool = True
    profile: str = "ALLOWED"


@dataclass(frozen=True, slots=True)
class BuiltinQualifierDefinition:
    """One builtin qualifier key for the claim participant qualifier registry.

    Qualifier keys are registered in the variable_definitions table so that
    extraction agents are constrained to known keys, preventing ad-hoc
    qualifier drift across agents or prompt versions.
    """

    variable_id: str
    canonical_name: str
    display_name: str
    data_type: str  # STRING, INTEGER, FLOAT, DATE, CODED
    description: str
    constraints: dict[str, object] | None = None
    is_scoping: bool = False


class GraphDictionaryLoadingExtension(Protocol):
    """Dictionary-loading semantics owned by the graph service."""

    @property
    def builtin_domain_contexts(self) -> tuple[DictionaryDomainContextDefinition, ...]:
        """Return builtin dictionary domain contexts seeded by the service."""

    @property
    def builtin_entity_types(self) -> tuple[BuiltinEntityTypeDefinition, ...]:
        """Return builtin canonical entity types seeded by the service."""

    @property
    def builtin_relation_types(self) -> tuple[BuiltinRelationTypeDefinition, ...]:
        """Return builtin canonical relation types seeded by the service."""

    @property
    def builtin_relation_synonyms(
        self,
    ) -> tuple[BuiltinRelationSynonymDefinition, ...]:
        """Return builtin relation synonyms seeded by the service."""

    @property
    def builtin_relation_constraints(
        self,
    ) -> tuple[BuiltinRelationConstraintDefinition, ...]:
        """Return builtin allowed relation constraints seeded by the service."""

    @property
    def builtin_qualifier_definitions(
        self,
    ) -> tuple[BuiltinQualifierDefinition, ...]:
        """Return builtin qualifier keys seeded by the service."""


@dataclass(frozen=True, slots=True)
class GraphDictionaryLoadingConfig:
    """Configurable dictionary-loading semantics for the graph service."""

    builtin_domain_contexts: tuple[DictionaryDomainContextDefinition, ...]
    builtin_entity_types: tuple[BuiltinEntityTypeDefinition, ...] = ()
    builtin_relation_types: tuple[BuiltinRelationTypeDefinition, ...] = ()
    builtin_relation_synonyms: tuple[BuiltinRelationSynonymDefinition, ...] = ()
    builtin_relation_constraints: tuple[BuiltinRelationConstraintDefinition, ...] = ()
    builtin_qualifier_definitions: tuple[BuiltinQualifierDefinition, ...] = ()


class GraphViewExtension(Protocol):
    """Graph-view semantics owned by the graph service."""

    @property
    def entity_view_types(self) -> dict[GraphDomainViewType, str]:
        """Return the entity view type mapping."""

    @property
    def document_view_types(self) -> frozenset[GraphDomainViewType]:
        """Return the document view types."""

    @property
    def claim_view_types(self) -> frozenset[GraphDomainViewType]:
        """Return the claim view types."""

    @property
    def mechanism_relation_types(self) -> frozenset[str]:
        """Return relation types used for mechanism-oriented graph views."""

    @property
    def supported_view_types(self) -> frozenset[GraphDomainViewType]:
        """Return all supported view types."""

    def normalize_view_type(self, value: str) -> GraphDomainViewType:
        """Normalize one raw route value into a supported graph view type."""

    def is_entity_view(self, view_type: GraphDomainViewType) -> bool:
        """Return whether the given view type targets an entity resource."""

    def is_claim_view(self, view_type: GraphDomainViewType) -> bool:
        """Return whether the given view type targets a claim resource."""

    def is_document_view(self, view_type: GraphDomainViewType) -> bool:
        """Return whether the given view type targets a document resource."""


class GraphRelationSuggestionExtension(Protocol):
    """Relation-suggestion semantics owned by the graph service."""

    @property
    def vector_candidate_limit(self) -> int:
        """Return the maximum vector candidate count to retrieve."""

    @property
    def min_vector_similarity(self) -> float:
        """Return the minimum vector similarity threshold."""


@dataclass(frozen=True, slots=True)
class GraphViewConfig:
    """Configurable graph-view semantics for the graph service."""

    entity_view_types: dict[GraphDomainViewType, str]
    document_view_types: frozenset[GraphDomainViewType]
    claim_view_types: frozenset[GraphDomainViewType]
    mechanism_relation_types: frozenset[str]

    @property
    def supported_view_types(self) -> frozenset[GraphDomainViewType]:
        """Return all supported view types for the configured service domain."""
        return (
            frozenset(self.entity_view_types)
            | self.document_view_types
            | self.claim_view_types
        )

    def normalize_view_type(self, value: str) -> GraphDomainViewType:
        """Normalize one raw route value into a supported graph view type."""
        normalized = value.strip().lower()
        if normalized in self.supported_view_types:
            return normalized
        msg = f"Unsupported graph view type '{value}'"
        raise ValueError(msg)

    def is_entity_view(self, view_type: GraphDomainViewType) -> bool:
        """Return whether the given view type targets an entity resource."""
        return view_type in self.entity_view_types

    def is_claim_view(self, view_type: GraphDomainViewType) -> bool:
        """Return whether the given view type targets a claim resource."""
        return view_type in self.claim_view_types

    def is_document_view(self, view_type: GraphDomainViewType) -> bool:
        """Return whether the given view type targets a document resource."""
        return view_type in self.document_view_types


@dataclass(frozen=True, slots=True)
class GraphRelationSuggestionConfig:
    """Default relation-suggestion extension configuration."""

    vector_candidate_limit: int = 100
    min_vector_similarity: float = 0.0



