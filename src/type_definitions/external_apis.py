"""
External API response type definitions for Artana Resource Library.

Contains TypedDict classes for responses from external biomedical APIs:
ClinVar, PubMed, HPO, UniProt, etc. These provide type safety when
processing external data and help prevent runtime errors.
"""

from typing import NotRequired, TypedDict

from src.type_definitions.common import JSONObject, JSONValue


# ClinVar API Types
class ClinVarESearchResult(TypedDict):
    """Structured ClinVar search payload returned from ESearch."""

    count: str
    retmax: str
    retstart: str
    idlist: list[str]
    querytranslation: NotRequired[str]
    translationset: NotRequired[list[JSONObject]]
    translationstack: NotRequired[list[JSONObject]]


class ClinVarSearchResponse(TypedDict):
    """ClinVar ESearch API response structure."""

    header: JSONObject
    esearchresult: ClinVarESearchResult


class ClinVarVariantRecord(TypedDict, total=False):
    """Individual ClinVar variant record."""

    variation_id: str
    variation_name: str
    gene: JSONObject | None
    condition: JSONObject | None
    clinical_significance: JSONObject | None
    review_status: str | None
    interpretation: JSONObject | None
    submissions: list[JSONObject]
    last_updated: str | None


ClinVarVariantResultMap = dict[str, ClinVarVariantRecord | list[str]]


class ClinVarVariantResponse(TypedDict):
    """ClinVar ESummary API response for variant details."""

    header: JSONObject
    result: ClinVarVariantResultMap


# PubMed API Types
class PubMedSearchResponse(TypedDict):
    """PubMed ESearch API response structure."""

    header: JSONObject
    esearchresult: JSONObject
    count: str
    retmax: str
    retstart: str
    idlist: list[str]
    translationset: list[JSONObject]
    translationstack: JSONObject
    querytranslation: str


class PubMedArticleAuthor(TypedDict, total=False):
    """PubMed article author information."""

    lastname: str
    firstname: str
    initials: str
    affiliation: str | None


class PubMedArticleJournal(TypedDict, total=False):
    """PubMed article journal information."""

    title: str
    volume: str | None
    issue: str | None
    pages: str | None


class PubMedArticleResponse(TypedDict, total=False):
    """PubMed ESummary API response for article details."""

    uid: str
    pubmed_id: str
    doi: str | None
    title: str
    authors: list[PubMedArticleAuthor]
    journal: PubMedArticleJournal
    pubdate: str
    abstract: str | None
    keywords: list[str]
    pmc_id: str | None


# HPO Ontology Types
class HPOTerm(TypedDict, total=False):
    """HPO ontology term structure."""

    id: str
    name: str
    definition: str | None
    synonyms: list[str]
    parents: list[str]
    children: list[str]
    ancestors: list[str]
    descendants: list[str]
    comment: str | None


class HPOOntologyResponse(TypedDict):
    """HPO ontology API response structure."""

    version: str
    date: str
    terms: dict[str, HPOTerm]
    metadata: JSONObject


# UniProt API Types
class UniProtReference(TypedDict, total=False):
    """UniProt reference structure."""

    citation: str
    authors: list[str]
    title: str
    journal: str
    volume: str | None
    pages: str | None
    year: int
    doi: str | None
    pubmed_id: str | None


class UniProtFeature(TypedDict, total=False):
    """UniProt protein feature structure."""

    type: str
    description: str
    begin: int
    end: int
    evidence: list[str]


class UniProtEntryResponse(TypedDict, total=False):
    """UniProt entry API response structure."""

    accession: str
    name: str
    protein_names: list[str]
    gene_name: str | None
    organism: str
    sequence: str
    length: int
    molecular_weight: int | None
    features: list[UniProtFeature]
    references: list[UniProtReference]
    function: str | None
    subcellular_location: list[str] | None
    tissue_specificity: str | None
    disease_association: list[str] | None
    last_modified: str


# Generic External API Response Types
class ExternalAPIError(TypedDict):
    """Generic external API error response."""

    error: str
    message: str
    code: str | None
    details: JSONObject | None


class ExternalAPIRateLimit(TypedDict):
    """External API rate limit information."""

    limit: int
    remaining: int
    reset_time: int
    retry_after: int | None


class ExternalAPIResponse(TypedDict, total=False):
    """Generic external API response wrapper."""

    success: bool
    data: JSONValue | None
    error: ExternalAPIError | None
    rate_limit: ExternalAPIRateLimit | None
    request_id: str | None
    timestamp: str


# Validation Types for External Data
class ExternalDataValidationResult(TypedDict):
    """Result of validating external API data."""

    is_valid: bool
    errors: list[str]
    warnings: list[str]
    data_quality_score: float
    transformation_needed: bool
    sanitized_data: JSONValue | None


class APIEndpointConfig(TypedDict):
    """Configuration for external API endpoints."""

    base_url: str
    timeout: int
    retries: int
    rate_limit: int
    headers: dict[str, str]
    auth_required: bool
    cache_enabled: bool


# Runtime Validation Types
class ValidationIssue(TypedDict):
    """Individual validation issue."""

    field: str
    issue_type: str  # "missing", "invalid", "unexpected"
    message: str
    severity: str  # "error", "warning", "info"


class APIResponseValidationResult(TypedDict):
    """Result of validating a generic external API response."""

    is_valid: bool
    issues: list[ValidationIssue]
    data_quality_score: float
    sanitized_data: JSONValue | None
    validation_time_ms: float


class ClinVarSearchValidationResult(TypedDict):
    """Result of validating a ClinVar search response."""

    is_valid: bool
    issues: list[ValidationIssue]
    data_quality_score: float
    sanitized_data: ClinVarSearchResponse | None
    validation_time_ms: float


class ClinVarVariantValidationResult(TypedDict):
    """Result of validating a ClinVar variant response."""

    is_valid: bool
    issues: list[ValidationIssue]
    data_quality_score: float
    sanitized_data: ClinVarVariantResponse | None
    validation_time_ms: float


# Zenodo API Types
class ZenodoMetadata(TypedDict, total=False):
    """Zenodo deposit metadata structure."""

    title: str
    description: str
    creators: list[dict[str, str]]
    keywords: list[str]
    license: str
    publication_date: str
    access_right: str
    communities: list[dict[str, str]]
    subjects: list[dict[str, str]]
    version: str
    language: str
    notes: str


class ZenodoFileInfo(TypedDict):
    """Zenodo file information."""

    id: str
    filename: str
    filesize: int
    checksum: str
    download: str


class ZenodoDepositResponse(TypedDict, total=False):
    """Zenodo deposit creation/response structure."""

    id: int
    conceptrecid: str
    doi: str
    doi_url: str
    metadata: ZenodoMetadata
    created: str
    modified: str
    owner: int
    record_id: int
    record_url: str
    state: str
    submitted: bool
    files: list[ZenodoFileInfo]
    links: dict[str, str]


class ZenodoPublishResponse(TypedDict):
    """Zenodo publication response structure."""

    id: int
    doi: str
    doi_url: str
    record_url: str
    conceptdoi: str
    conceptrecid: str
