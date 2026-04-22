"""
API-specific type definitions for Artana Resource Library.

Contains types for API endpoints, request/response schemas,
and external API integrations.
"""

from typing import TypedDict

from .common import JSONObject, PaginatedResponse


# Request types
class GeneCreateRequest(TypedDict, total=False):
    """Gene creation request."""

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


class GeneUpdateRequest(GeneCreateRequest):
    """Gene update request (same fields as create)."""


class VariantCreateRequest(TypedDict, total=False):
    """Variant creation request."""

    gene_id: str
    hgvs_notation: str
    variant_type: str
    clinical_significance: str
    population_frequency: dict[str, float]
    chromosome: str | None
    position: int | None
    reference_allele: str | None
    alternate_allele: str | None


class VariantUpdateRequest(VariantCreateRequest):
    """Variant update request."""


class PhenotypeCreateRequest(TypedDict, total=False):
    """Phenotype creation request."""

    hpo_id: str
    name: str
    definition: str | None
    synonyms: list[str]


class PhenotypeUpdateRequest(PhenotypeCreateRequest):
    """Phenotype update request."""


class EvidenceCreateRequest(TypedDict, total=False):
    """Evidence creation request."""

    variant_id: str
    phenotype_id: str | None
    publication_id: str | None
    evidence_level: str
    confidence_score: float
    source: str
    evidence_type: str
    description: str | None


class EvidenceUpdateRequest(EvidenceCreateRequest):
    """Evidence update request."""


class PublicationCreateRequest(TypedDict, total=False):
    """Publication creation request."""

    title: str
    authors: list[str]
    journal: str | None
    publication_year: int
    doi: str | None
    pmid: str | None
    abstract: str | None


class PublicationUpdateRequest(PublicationCreateRequest):
    """Publication update request."""


# Query parameter types
class GeneQueryParams(TypedDict, total=False):
    """Gene query parameters."""

    page: int
    per_page: int
    search: str
    sort_by: str
    sort_order: str
    symbol: str
    chromosome: str
    gene_type: str


class VariantQueryParams(TypedDict, total=False):
    """Variant query parameters."""

    page: int
    per_page: int
    search: str
    sort_by: str
    sort_order: str
    gene_id: str
    clinical_significance: str
    variant_type: str


class PhenotypeQueryParams(TypedDict, total=False):
    """Phenotype query parameters."""

    page: int
    per_page: int
    search: str
    sort_by: str
    sort_order: str
    hpo_id: str


class EvidenceQueryParams(TypedDict, total=False):
    """Evidence query parameters."""

    page: int
    per_page: int
    search: str
    sort_by: str
    sort_order: str
    variant_id: str
    phenotype_id: str
    evidence_level: str
    confidence_min: float
    confidence_max: float


class PublicationQueryParams(TypedDict, total=False):
    """Publication query parameters."""

    page: int
    per_page: int
    search: str
    sort_by: str
    sort_order: str
    author: str
    year_min: int
    year_max: int
    journal: str
    doi: str
    pmid: str


# Response types - using type aliases to avoid TypedDict field overwriting
GeneListResponse = PaginatedResponse
VariantListResponse = PaginatedResponse
PhenotypeListResponse = PaginatedResponse
EvidenceListResponse = PaginatedResponse
PublicationListResponse = PaginatedResponse


# Error response types
class APIError(TypedDict):
    """API error response."""

    error: str
    message: str
    details: JSONObject | None
    code: str


class ValidationErrorResponse(TypedDict):
    """Validation error response."""

    errors: list[dict[str, str]]
    message: str


# Bulk operation types
class BulkUpdateRequest(TypedDict):
    """Bulk update request."""

    ids: list[str]
    updates: JSONObject  # Will be replaced with specific types per entity


class BulkOperationResponse(TypedDict):
    """Bulk operation response."""

    successful: list[str]
    failed: list[dict[str, str]]
    total_processed: int
    errors: list[str]


# Search types
class SearchRequest(TypedDict, total=False):
    """Search request."""

    q: str
    entity_type: str
    filters: JSONObject
    sort_by: str
    sort_order: str
    page: int
    per_page: int


class SearchResult(TypedDict):
    """Individual search result."""

    id: str
    entity_type: str
    title: str
    description: str | None
    score: float
    highlights: list[str]


# Search types
class SearchResponseExtra(TypedDict):
    """Additional fields for search response."""

    query: str
    search_time_ms: int


# Combine with base response (avoiding field redefinition)
SearchResponse = PaginatedResponse  # Base pagination
# Note: In actual usage, combine with SearchResponseExtra fields


# Export all types for easy importing
