"""
Domain-specific type definitions for Artana Resource Library.

Contains types for domain entities, value objects, and domain operations.
"""

import abc
from datetime import datetime
from typing import Protocol, TypedDict, TypeVar

from .common import EntityStatus, JSONObject, JSONValue, PriorityLevel, ValidationResult

# Generic types for domain operations
T = TypeVar("T")  # Generic entity type
T_contra = TypeVar(
    "T_contra",
    contravariant=True,
)  # Generic entity type (contravariant for protocols)
ID = TypeVar("ID")  # Generic ID type


class DomainEntity(Protocol):
    """Protocol for domain entities with an identifier."""

    id: str | int | None

    def model_dump(self) -> JSONObject:  # pragma: no cover - structure only
        """Return a JSON-serializable representation of the entity."""
        ...


# Domain entity identifiers
GeneIdentifier = str
VariantIdentifier = str
PhenotypeIdentifier = str
EvidenceIdentifier = str
PublicationIdentifier = str


# Domain operation result types
class DomainOperationResult(TypedDict, total=False):
    """Result of a domain operation."""

    success: bool
    entity: DomainEntity | None
    errors: list[str]
    warnings: list[str]
    validation_result: ValidationResult


# Business rule validation types
class BusinessRuleViolation(TypedDict):
    """Business rule violation details."""

    rule_name: str
    entity_type: str
    entity_id: str
    violation_type: str
    message: str
    severity: str
    suggested_fix: str | None


class BusinessRuleValidationResult(TypedDict):
    """Result of business rule validation."""

    is_valid: bool
    violations: list[BusinessRuleViolation]
    entity_type: str
    entity_id: str
    validated_at: datetime


# Relationship types
class GeneVariantRelationship(TypedDict):
    """Gene-variant relationship data."""

    gene_id: str
    variant_id: str
    relationship_type: str
    confidence_score: float
    evidence_count: int
    last_updated: datetime


class VariantPhenotypeRelationship(TypedDict):
    """Variant-phenotype relationship data."""

    variant_id: str
    phenotype_id: str
    evidence_level: str
    confidence_score: float
    publications: list[str]
    inheritance_pattern: str | None


class EvidencePublicationRelationship(TypedDict):
    """Evidence-publication relationship data."""

    evidence_id: str
    publication_id: str
    citation_type: str
    relevance_score: float


# Domain service operation types
class GeneAnalysisResult(TypedDict):
    """Result of gene analysis operations."""

    gene_id: str
    variant_count: int
    phenotype_count: int
    evidence_count: int
    clinical_significance_summary: dict[str, int]
    population_frequency_range: dict[str, float]
    inheritance_patterns: list[str]


class VariantAnalysisResult(TypedDict):
    """Result of variant analysis operations."""

    variant_id: str
    gene_id: str
    clinical_significance: str
    evidence_levels: dict[str, int]
    phenotype_associations: list[str]
    population_frequency: dict[str, float]
    functional_predictions: dict[str, str]


class EvidenceConsistencyResult(TypedDict):
    """Result of evidence consistency analysis."""

    evidence_id: str
    is_consistent: bool
    conflicts: list[str]
    supporting_evidence: list[str]
    confidence_score: float
    last_reviewed: datetime


# Curation workflow types
class CurationDecision(TypedDict):
    """Curation decision data."""

    entity_id: str
    entity_type: str
    decision: str  # approve, reject, quarantine
    curator_id: str
    decision_date: datetime
    comments: str | None
    confidence_score: float


class CurationQueueItem(TypedDict):
    """Item in curation queue."""

    entity_id: str
    entity_type: str
    priority: PriorityLevel
    status: EntityStatus
    queued_date: datetime
    last_modified: datetime
    validation_errors: list[str]
    evidence_count: int


# Domain event types
class DomainEvent(TypedDict):
    """Base domain event structure."""

    event_type: str
    entity_type: str
    entity_id: str
    timestamp: datetime
    user_id: str | None
    details: JSONObject


class GeneCreatedEvent(DomainEvent):
    """Gene created event."""

    gene_data: JSONObject


class VariantUpdatedEvent(DomainEvent):
    """Variant updated event."""

    changes: JSONObject
    old_values: JSONObject


class EvidenceValidatedEvent(DomainEvent):
    """Evidence validated event."""

    validation_result: ValidationResult


# Validation rule types
class ValidationRule(Protocol[T_contra]):
    """Protocol for validation rules."""

    @abc.abstractmethod
    def validate(self, entity: T_contra) -> ValidationResult:
        """Validate an entity against this rule."""
        ...


class SyntacticValidationRule(ValidationRule[T_contra]):
    """Syntactic validation rule (format/structure)."""

    @abc.abstractmethod
    def validate(self, entity: T_contra) -> ValidationResult:
        """Validate entity syntax."""
        ...


class SemanticValidationRule(ValidationRule[T_contra]):
    """Semantic validation rule (business logic)."""

    @abc.abstractmethod
    def validate(self, entity: T_contra) -> ValidationResult:
        """Validate entity semantics."""
        ...


class CompletenessValidationRule(ValidationRule[T_contra]):
    """Completeness validation rule (required fields)."""

    @abc.abstractmethod
    def validate(self, entity: T_contra) -> ValidationResult:
        """Validate entity completeness."""
        ...


# Domain service result types
class GeneDerivedProperties(TypedDict):
    """Derived properties calculated for genes."""

    genomic_size: int | None
    has_genomic_location: bool
    external_id_count: int


class VariantDerivedProperties(TypedDict):
    """Derived properties calculated for variants."""

    has_population_data: bool
    population_frequency_count: int
    average_population_frequency: float | None
    has_functional_impact: bool
    evidence_count: int
    significance_consistency_score: float


class EvidenceConsistencyAnalysis(TypedDict):
    """Result of evidence consistency analysis."""

    total_evidence: int
    conflicting_evidence: int
    consistent_evidence: int
    consistency_score: float
    dominant_significance: str | None
    significance_distribution: dict[str, int]


class EvidenceDerivedProperties(TypedDict):
    """Derived properties calculated for evidence."""

    confidence_category: str
    evidence_strength: str
    has_publication: bool
    has_functional_data: bool
    data_completeness_score: float
    reliability_score: float


# Normalization types
class NormalizationResult(TypedDict, total=False):
    """Result of data normalization."""

    original_value: JSONValue
    normalized_value: JSONValue
    normalization_method: str
    confidence_score: float
    alternatives: list[JSONValue]


class IdentifierNormalizationResult(NormalizationResult):
    """Result of identifier normalization."""

    identifier_type: str
    source: str
    canonical_form: str


# Provenance types
class ProvenanceChain(TypedDict):
    """Chain of data provenance."""

    source: str
    source_version: str | None
    acquired_at: datetime
    processing_steps: list[str]
    derived_from: list[str] | None
    quality_score: float
    validation_status: str


# Quality metrics types
class QualityMetrics(TypedDict, total=False):
    """Quality metrics for data entities."""

    completeness_score: float
    consistency_score: float
    accuracy_score: float
    timeliness_score: float
    measured_at: datetime
    entity_type: str
    entity_id: str


class DataQualityReport(TypedDict):
    """Comprehensive data quality report."""

    overall_score: float
    metrics_by_type: dict[str, QualityMetrics]
    issues_found: list[str]
    recommendations: list[str]
    generated_at: datetime
    coverage: dict[str, int]  # entity_type -> count
