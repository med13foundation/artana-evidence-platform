"""
Shared data discovery parameter models and enums.
"""

from __future__ import annotations

from datetime import date  # noqa: TC003
from enum import Enum
from typing import Literal, assert_never

from pydantic import BaseModel, ConfigDict, Field

from src.type_definitions.storage import StorageUseCase  # noqa: TC001

__all__ = [
    "AdvancedQueryParameters",
    "CatalogAIProfile",
    "CatalogDiscoveryDefaults",
    "QueryParameterCapabilities",
    "PubMedSortOption",
    "QueryParameters",
    "QueryParameterType",
    "TestResultStatus",
]


class QueryParameterType(str, Enum):
    """Types of query parameters supported by data sources."""

    GENE = "gene"
    TERM = "term"
    GENE_AND_TERM = "gene_and_term"
    NONE = "none"
    API = "api"


class TestResultStatus(str, Enum):
    """Status of a query test result."""

    __test__ = False

    PENDING = "pending"
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    VALIDATION_FAILED = "validation_failed"


ScheduleFrequencyProfile = Literal[
    "manual",
    "hourly",
    "daily",
    "weekly",
    "monthly",
    "cron",
]
# Supported cadence values in catalog-discovery defaults.


class CatalogAIProfile(BaseModel):
    """Catalog-level defaults for AI-assisted query generation."""

    model_config = ConfigDict(frozen=True)

    is_ai_managed: bool = False
    source_type: str = Field(
        default="pubmed",
        description="Query-generation source type passed to AI pipelines.",
    )
    agent_prompt: str = Field(
        default="",
        description="Default prompt used when generating queries.",
    )
    use_research_space_context: bool = Field(
        default=True,
        description="Whether research-space context should be used.",
    )
    model_id: str | None = Field(
        default=None,
        description="Optional model override for AI generation.",
    )
    default_query: str | None = Field(
        default=None,
        description="Seed query when no explicit query exists.",
    )


class CatalogDiscoveryDefaults(BaseModel):
    """Catalog-level defaults for source scheduling and AI behavior."""

    model_config = ConfigDict(frozen=True)

    schedule_enabled: bool = Field(
        default=False,
        description="Whether schedule defaults should enable ingestion.",
    )
    schedule_frequency: ScheduleFrequencyProfile = Field(
        default="manual",
        description="Default ingestion frequency.",
    )
    schedule_timezone: str = Field(
        default="UTC",
        description="Default timezone for schedule execution.",
    )
    ai_profile: CatalogAIProfile = Field(
        default_factory=CatalogAIProfile,
        description="Defaults for AI-assisted query generation.",
    )


class QueryParameterCapabilities(BaseModel):
    """Describes which advanced parameters a source supports."""

    model_config = ConfigDict(frozen=True)

    supports_date_range: bool = False
    supports_publication_types: bool = False
    supports_language_filter: bool = False
    supports_sort_options: bool = False
    supports_additional_terms: bool = False
    max_results_limit: int = Field(default=1000, ge=1, le=1000)

    supported_storage_use_cases: list[StorageUseCase] = Field(
        default_factory=list,
        description="Storage use cases supported by this source",
    )

    supports_variation_type: bool = False
    supports_clinical_significance: bool = False
    supports_review_status: bool = False
    supports_organism: bool = False
    discovery_defaults: CatalogDiscoveryDefaults = Field(
        default_factory=CatalogDiscoveryDefaults,
        description="Catalog-level defaults for discovered sources.",
    )


class QueryParameters(BaseModel):
    """Domain entity representing parameters for a query test."""

    model_config = ConfigDict(frozen=True)

    gene_symbol: str | None = Field(
        None,
        description="Gene symbol to query (e.g., MED13)",
    )
    search_term: str | None = Field(None, description="Phenotype or search term")

    def has_gene(self) -> bool:
        return self.gene_symbol is not None and self.gene_symbol.strip() != ""

    def has_term(self) -> bool:
        return self.search_term is not None and self.search_term.strip() != ""

    def can_run_query(self, param_type: QueryParameterType) -> bool:
        if param_type == QueryParameterType.GENE:
            return self.has_gene()
        if param_type == QueryParameterType.TERM:
            return self.has_term()
        if param_type == QueryParameterType.GENE_AND_TERM:
            return self.has_gene() and self.has_term()
        if param_type == QueryParameterType.NONE:
            return True
        if param_type == QueryParameterType.API:
            return True
        assert_never(param_type)


class PubMedSortOption(str, Enum):
    """Supported PubMed sort options."""

    RELEVANCE = "relevance"
    PUBLICATION_DATE = "publication_date"
    AUTHOR = "author"
    JOURNAL = "journal"
    TITLE = "title"


class AdvancedQueryParameters(QueryParameters):
    """Extended query parameters with advanced filters."""

    model_config = ConfigDict(frozen=True)

    date_from: date | None = Field(
        default=None,
        description="Earliest publication date to include.",
    )
    date_to: date | None = Field(
        default=None,
        description="Latest publication date to include.",
    )
    publication_types: list[str] = Field(
        default_factory=list,
        description="Publication types (validated against PublicationType).",
    )
    languages: list[str] = Field(
        default_factory=list,
        description="Language filters (ISO codes).",
    )
    sort_by: PubMedSortOption = Field(
        default=PubMedSortOption.RELEVANCE,
        description="Sort order for PubMed results.",
    )
    max_results: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum number of results to fetch.",
    )
    additional_terms: str | None = Field(
        default=None,
        description="Additional PubMed query syntax appended to the search.",
    )

    variation_types: list[str] = Field(
        default_factory=list,
        description="ClinVar variation types (e.g. single_nucleotide_variant).",
    )
    clinical_significance: list[str] = Field(
        default_factory=list,
        description="ClinVar clinical significance (e.g. pathogenic).",
    )
    is_reviewed: bool | None = Field(
        default=None,
        description="Filter by Swiss-Prot (true) or TrEMBL (false).",
    )
    organism: str | None = Field(
        default=None,
        description="Filter by organism (e.g. Human, Mouse).",
    )
