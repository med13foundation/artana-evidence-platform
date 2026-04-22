"""Data Transfer Objects for Data Discovery Service."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

from src.domain.entities.data_discovery_parameters import (
    AdvancedQueryParameters,
    PubMedSortOption,
    QueryParameterCapabilities,
    QueryParameterType,
)
from src.domain.entities.user_data_source import SourceType


class QueryParametersModel(BaseModel):
    """API model for query parameters."""

    gene_symbol: str | None = Field(None, description="Gene symbol to query")
    search_term: str | None = Field(None, description="Phenotype or search term")


class AdvancedQueryParametersModel(QueryParametersModel):
    """API model for advanced PubMed parameters."""

    date_from: str | None = Field(None, description="Earliest publication date (ISO)")
    date_to: str | None = Field(None, description="Latest publication date (ISO)")
    publication_types: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    sort_by: str | None = Field(
        default=PubMedSortOption.RELEVANCE.value,
        description="Sort option",
    )
    max_results: int = Field(default=100, ge=1, le=1000)
    additional_terms: str | None = Field(default=None)

    # ClinVar
    variation_types: list[str] = Field(default_factory=list)
    clinical_significance: list[str] = Field(default_factory=list)

    # UniProt
    is_reviewed: bool | None = Field(default=None)
    organism: str | None = Field(default=None)

    def to_domain_model(self) -> AdvancedQueryParameters:
        """Convert serialized parameters into domain AdvancedQueryParameters."""
        return AdvancedQueryParameters(
            gene_symbol=self.gene_symbol,
            search_term=self.search_term,
            date_from=self._parse_date(self.date_from),
            date_to=self._parse_date(self.date_to),
            publication_types=self.publication_types,
            languages=self.languages,
            sort_by=(
                PubMedSortOption(self.sort_by)
                if self.sort_by
                else PubMedSortOption.RELEVANCE
            ),
            max_results=self.max_results,
            additional_terms=self.additional_terms,
            variation_types=self.variation_types,
            clinical_significance=self.clinical_significance,
            is_reviewed=self.is_reviewed,
            organism=self.organism,
        )

    @staticmethod
    def _parse_date(value: str | None) -> date | None:
        if value is None:
            return None
        return date.fromisoformat(value)

    @classmethod
    def from_domain(
        cls,
        parameters: AdvancedQueryParameters,
    ) -> "AdvancedQueryParametersModel":
        return cls(
            gene_symbol=parameters.gene_symbol,
            search_term=parameters.search_term,
            date_from=(
                parameters.date_from.isoformat() if parameters.date_from else None
            ),
            date_to=parameters.date_to.isoformat() if parameters.date_to else None,
            publication_types=parameters.publication_types,
            languages=parameters.languages,
            sort_by=parameters.sort_by.value if parameters.sort_by else None,
            max_results=parameters.max_results,
            additional_terms=parameters.additional_terms,
            variation_types=parameters.variation_types,
            clinical_significance=parameters.clinical_significance,
            is_reviewed=parameters.is_reviewed,
            organism=parameters.organism,
        )


class CreateSessionRequest(BaseModel):
    """Request payload for creating a workbench session."""

    name: str = Field("Untitled Session", description="Session name")
    research_space_id: UUID | None = Field(None, description="Research space ID")
    initial_parameters: AdvancedQueryParametersModel = Field(
        default_factory=lambda: AdvancedQueryParametersModel(
            gene_symbol=None,
            search_term=None,
            date_from=None,
            date_to=None,
            publication_types=[],
            languages=[],
            sort_by=PubMedSortOption.RELEVANCE.value,
            max_results=100,
            additional_terms=None,
            variation_types=[],
            clinical_significance=[],
            is_reviewed=None,
            organism=None,
        ),
        description="Initial query parameters",
    )


class UpdateParametersRequest(BaseModel):
    """Request payload for updating session parameters."""

    parameters: AdvancedQueryParametersModel = Field(
        ...,
        description="New query parameters",
    )


class UpdateSelectionRequest(BaseModel):
    """Request payload for bulk selection updates."""

    source_ids: list[str] = Field(
        default_factory=list,
        description="Catalog entry IDs that should remain selected",
    )


class DataDiscoverySessionResponse(BaseModel):
    """Response model for data discovery sessions."""

    id: UUID
    owner_id: UUID
    research_space_id: UUID | None
    name: str
    current_parameters: AdvancedQueryParametersModel
    selected_sources: list[str]
    tested_sources: list[str]
    total_tests_run: int
    successful_tests: int
    is_active: bool
    created_at: str
    updated_at: str
    last_activity_at: str


class SourceCatalogEntry(BaseModel):
    """Response model for source catalog entries."""

    id: str
    name: str
    category: str
    subcategory: str | None
    description: str
    source_type: SourceType
    param_type: QueryParameterType
    is_active: bool
    requires_auth: bool
    usage_count: int
    success_rate: float
    tags: list[str]
    capabilities: QueryParameterCapabilities


class SourceCapabilitiesDTO(BaseModel):
    """Derived capabilities based on selected sources."""

    supports_gene_search: bool = Field(
        default=False,
        description="Can search by gene symbol",
    )
    supports_term_search: bool = Field(
        default=False,
        description="Can search by phenotype/term",
    )
    supported_parameters: list[str] = Field(
        default_factory=list,
        description="List of supported parameter keys",
    )
    max_results_limit: int = Field(
        default=100,
        description="Maximum allowed results across sources",
    )


class ValidationIssueDTO(BaseModel):
    """Structured validation issue."""

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    severity: str = Field("error", description="error, warning, or info")
    field: str | None = Field(None, description="Related field name if any")


class ValidationResultDTO(BaseModel):
    """Result of validating the current selection."""

    is_valid: bool = Field(..., description="Whether the selection is valid")
    issues: list[ValidationIssueDTO] = Field(
        default_factory=list,
        description="List of validation issues",
    )


class ViewContextDTO(BaseModel):
    """Pre-calculated UI hints."""

    selected_count: int = Field(..., description="Number of selected sources")
    total_available: int = Field(..., description="Total available sources")
    can_run_search: bool = Field(..., description="Whether search can be executed")
    categories: dict[str, int] = Field(
        default_factory=dict,
        description="Count of sources per category",
    )


class OrchestratedSessionState(BaseModel):
    """
    Complete session state with derived data for UI rendering.
    Acts as the 'ViewModel' for the frontend.
    """

    session: DataDiscoverySessionResponse
    capabilities: SourceCapabilitiesDTO
    validation: ValidationResultDTO = Field(
        default_factory=lambda: ValidationResultDTO(is_valid=True, issues=[]),
        description="Validation status and issues",
    )
    view_context: ViewContextDTO = Field(
        ...,
        description="Pre-calculated UI hints (counts, labels)",
    )
