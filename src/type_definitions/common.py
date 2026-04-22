"""
Common type definitions for Artana Resource Library.

Contains TypedDict classes for update operations, API responses,
and other common patterns throughout the application.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Literal, TypedDict

if TYPE_CHECKING:  # pragma: no cover - typing only
    from datetime import date, datetime

JSONPrimitive = str | int | float | bool | None
type JSONValue = JSONPrimitive | Mapping[str, "JSONValue"] | Sequence["JSONValue"]
JSONObject = dict[str, JSONValue]
RawRecord = dict[str, JSONValue]
"""Raw data record from external sources (typed JSON)."""


# Update operation types (replace previous loosely typed maps)
class GeneUpdate(TypedDict, total=False):
    """Type-safe gene update parameters."""

    symbol: str
    name: str | None
    description: str | None
    gene_type: str
    chromosome: str | None
    start_position: int | None
    end_position: int | None
    ensembl_id: str | None
    ncbi_gene_id: int | None
    uniprot_id: str | None


class VariantUpdate(TypedDict, total=False):
    """Type-safe variant update parameters."""

    gene_id: str
    variant_id: str
    clinvar_id: str
    chromosome: str | None
    position: int | None
    reference_allele: str | None
    alternate_allele: str | None

    hgvs_notation: str
    hgvs_genomic: str | None
    hgvs_protein: str | None
    hgvs_cdna: str | None

    variant_type: str
    clinical_significance: str
    condition: str | None
    review_status: str | None

    population_frequency: dict[str, float]
    allele_frequency: float | None
    gnomad_af: float | None


class PhenotypeUpdate(TypedDict, total=False):
    """Type-safe phenotype update parameters."""

    hpo_id: str
    name: str
    definition: str | None
    synonyms: list[str]
    category: str
    parent_hpo_id: str | None
    is_root_term: bool | None
    frequency_in_med13: str | None
    severity_score: int | None


class MechanismUpdate(TypedDict, total=False):
    """Type-safe mechanism update parameters."""

    name: str
    description: str | None
    evidence_tier: str
    confidence_score: float
    source: str
    lifecycle_state: str
    protein_domains: list[JSONObject]
    phenotype_ids: list[int]


class StatementUpdate(TypedDict, total=False):
    """Type-safe statement update parameters."""

    title: str
    summary: str
    evidence_tier: str
    confidence_score: float
    status: str
    source: str
    protein_domains: list[JSONObject]
    phenotype_ids: list[int]
    promoted_mechanism_id: int | None


class EvidenceUpdate(TypedDict, total=False):
    """Type-safe evidence update parameters."""

    variant_id: str
    phenotype_id: str | None
    publication_id: str | None
    description: str | None
    summary: str | None
    evidence_level: str
    evidence_type: str
    confidence_score: float
    quality_score: int | None
    sample_size: int | None
    study_type: str | None
    statistical_significance: str | None
    reviewed: bool | None
    review_date: date | None
    reviewer_notes: str | None


class PublicationUpdate(TypedDict, total=False):
    """Type-safe publication update parameters."""

    title: str
    authors: list[str]
    journal: str | None
    publication_year: int
    doi: str | None
    pmid: str | None
    abstract: str | None


class ExtractionQueueUpdate(TypedDict, total=False):
    """Type-safe extraction queue update parameters."""

    publication_id: int | None
    pubmed_id: str | None
    source_type: str
    source_record_id: str
    raw_storage_key: str | None
    payload_ref: str | None
    status: str
    attempts: int
    last_error: str | None
    extraction_version: int
    metadata: JSONObject
    queued_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime | None


ExtractionTextSource = Literal[
    "title_abstract",
    "title",
    "abstract",
    "full_text",
]

ExtractionFactType = Literal[
    "variant",
    "phenotype",
    "gene",
    "drug",
    "mechanism",
    "pathway",
    "other",
]


class ExtractionFact(TypedDict, total=False):
    """Structured fact extracted from a publication."""

    fact_type: ExtractionFactType
    value: str
    normalized_id: str | None
    source: str | None
    attributes: JSONObject


class PublicationExtractionUpdate(TypedDict, total=False):
    """Type-safe publication extraction update parameters."""

    status: str
    facts: list[ExtractionFact]
    metadata: JSONObject
    extracted_at: datetime | None
    processor_name: str | None
    processor_version: str | None
    text_source: str | None
    document_reference: str | None


# API response types
class APIResponse(TypedDict, total=False):
    """Standard API response structure."""

    data: list[JSONObject]
    total: int
    page: int
    per_page: int
    errors: list[str]
    message: str


class ApiErrorResponse(TypedDict):
    """Standard API error response structure."""

    success: Literal[False]
    error_type: str
    message: str
    details: JSONObject | None


class PaginatedResponse(TypedDict, total=False):
    """Paginated API response structure."""

    items: list[JSONObject]
    total: int
    page: int
    per_page: int
    total_pages: int
    has_next: bool
    has_prev: bool


# Validation types
class ValidationError(TypedDict):
    """Validation error structure."""

    field: str
    message: str
    code: str


class ValidationResult(TypedDict):
    """Validation result structure."""

    is_valid: bool
    errors: list[ValidationError]
    warnings: list[ValidationError]


# Audit context types
class AuditContext(TypedDict, total=False):
    """Request metadata captured for audit logging."""

    request_id: str
    ip_address: str | None
    user_agent: str | None
    method: str
    path: str


# Status and filter types
EntityStatus = Literal["pending", "approved", "rejected", "quarantined"]
PriorityLevel = Literal["high", "medium", "low"]
ClinicalSignificance = Literal[
    "pathogenic",
    "likely_pathogenic",
    "uncertain_significance",
    "likely_benign",
    "benign",
    "conflicting",
    "not_provided",
]


class EntityFilter(TypedDict, total=False):
    """Common entity filtering parameters."""

    status: EntityStatus
    priority: PriorityLevel
    search: str
    sort_by: str
    sort_order: Literal["asc", "desc"]
    page: int
    per_page: int


# Authentication credential types
class ApiKeyCredentials(TypedDict):
    """API key authentication credentials."""

    api_key: str
    header_name: str  # e.g., "X-API-Key", "Authorization"


class BasicAuthCredentials(TypedDict):
    """Basic authentication credentials."""

    username: str
    password: str


class OAuthCredentials(TypedDict):
    """OAuth authentication credentials."""

    client_id: str
    client_secret: str
    token_url: str
    scope: str | None


class BearerTokenCredentials(TypedDict):
    """Bearer token authentication credentials."""

    token: str


# Union type for all auth credential types
AuthCredentials = (
    ApiKeyCredentials
    | BasicAuthCredentials
    | OAuthCredentials
    | BearerTokenCredentials
    | dict[str, str | int | float | bool | None]
)
"""Type-safe authentication credentials. Falls back to dict for custom auth types."""


# Source-specific metadata types
SourceMetadata = JSONObject


# Research space settings types
class RelationAutoPromotionSettings(TypedDict, total=False):
    """Relation auto-promotion policy controls."""

    enabled: bool
    min_distinct_sources: int
    min_aggregate_confidence: float
    require_distinct_documents: bool
    require_distinct_runs: bool
    block_if_conflicting_evidence: bool
    min_evidence_tier: str
    conflicting_confidence_threshold: float


class ResearchSpaceSourcePreferences(TypedDict, total=False):
    """Per-space discovery source preferences."""

    pubmed: bool
    marrvel: bool
    clinvar: bool
    mondo: bool
    pdf: bool
    text: bool
    drugbank: bool
    alphafold: bool
    uniprot: bool
    hgnc: bool
    clinical_trials: bool
    mgi: bool
    zfin: bool


class ResearchSpaceSettings(TypedDict, total=False):
    """Type-safe research space settings."""

    # Curation settings
    auto_approve: bool
    require_review: bool
    review_threshold: float
    relation_default_review_threshold: float
    relation_review_thresholds: dict[str, float]
    relation_governance_mode: Literal["HUMAN_IN_LOOP", "FULL_AUTO"]
    relation_auto_promotion: RelationAutoPromotionSettings
    claim_non_persistable_baseline_ratio: float
    claim_non_persistable_alert_ratio: float
    dictionary_agent_creation_policy: Literal["ACTIVE", "PENDING_REVIEW"]
    concept_agent_creation_policy: Literal["ACTIVE", "PENDING_REVIEW"]
    concept_policy_mode: Literal["PRECISION", "BALANCED", "DISCOVERY"]
    research_orchestration_mode: Literal[
        "deterministic",
        "full_ai_shadow",
        "full_ai_guarded",
    ]

    # Data source settings
    max_data_sources: int
    allowed_source_types: list[str]
    sources: ResearchSpaceSourcePreferences

    # Access control
    public_read: bool
    allow_invites: bool

    # Notification settings
    email_notifications: bool
    notification_frequency: str

    # Custom settings
    custom: dict[str, str | int | float | bool | None]


# Query specification types
FilterValue = str | int | float | bool | None
QueryFilters = dict[str, FilterValue]


def clone_query_filters(
    filters: Mapping[str, FilterValue] | QueryFilters | None,
) -> QueryFilters | None:
    """Create a shallow copy of query filters with normalized keys."""
    if filters is None:
        return None
    normalized: QueryFilters = {}
    for key, value in dict(filters).items():
        normalized[str(key)] = value
    return normalized


# Statistics and health check types
class StatisticsResponse(TypedDict, total=False):
    """Type-safe statistics response."""

    total_sources: int
    status_counts: dict[str, int]
    type_counts: dict[str, int]
    average_quality_score: float | None
    sources_with_quality_metrics: int


class HealthCheckResponse(TypedDict, total=False):
    """Type-safe health check response."""

    database: bool
    jwt_provider: bool
    password_hasher: bool
    services: bool
