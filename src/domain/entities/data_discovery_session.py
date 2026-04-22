"""
Domain entities for Data Discovery sessions.

These entities represent user data discovery sessions for discovering, testing,
and validating data sources before adding them to Research Spaces.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.domain.entities.user_data_source import SourceType
from src.type_definitions.common import JSONObject

from .data_discovery_parameters import (
    AdvancedQueryParameters,
    PubMedSortOption,
    QueryParameterCapabilities,
    QueryParameters,
    QueryParameterType,
    TestResultStatus,
)


class SourceCatalogEntry(BaseModel):
    """
    Domain entity representing an entry in the data source catalog.

    This represents a discoverable data source that users can test
    and potentially add to their Research Spaces.
    """

    model_config = ConfigDict(frozen=True)

    # Identity
    id: str = Field(..., description="Unique identifier for the catalog entry")
    name: str = Field(..., min_length=1, max_length=200, description="Display name")

    # Classification
    category: str = Field(..., description="Category this source belongs to")
    subcategory: str | None = Field(None, description="Optional subcategory")

    # Description and metadata
    description: str = Field(..., max_length=1000, description="Detailed description")
    tags: list[str] = Field(default_factory=list, description="Searchable tags")
    source_type: SourceType = Field(
        default=SourceType.API,
        description="Underlying ingestion type (api, file_upload, database, etc.)",
    )

    # Query capabilities
    param_type: QueryParameterType = Field(
        ...,
        description="Type of parameters this source accepts",
    )
    url_template: str | None = Field(
        None,
        description="URL template for external links",
    )

    # Technical details
    data_format: str | None = Field(
        None,
        description="Expected data format (json, xml, csv)",
    )
    api_endpoint: str | None = Field(None, description="API endpoint if applicable")

    # Governance
    is_active: bool = Field(
        default=True,
        description="Whether this source is currently available",
    )
    requires_auth: bool = Field(
        default=False,
        description="Whether authentication is required",
    )

    # Usage statistics
    usage_count: int = Field(default=0, description="Number of times tested")
    success_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Success rate of queries",
    )

    # Integration
    source_template_id: UUID | None = Field(
        None,
        description="Linked SourceTemplate if this maps to an ingestible source",
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When this catalog entry was created",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When this catalog entry was last updated",
    )
    capabilities: QueryParameterCapabilities = Field(
        default_factory=QueryParameterCapabilities,
        description="Advanced query parameter capabilities supported by this source",
    )

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        """Validate and normalize tags."""
        max_tags = 10
        normalized = [tag.strip().lower() for tag in v if tag.strip()]
        if len(normalized) > max_tags:
            msg = f"Maximum {max_tags} tags allowed"
            raise ValueError(msg)
        # Remove duplicates while preserving order
        seen = set()
        deduplicated = []
        for tag in normalized:
            if tag not in seen:
                seen.add(tag)
                deduplicated.append(tag)
        return deduplicated

    def is_testable(self) -> bool:
        """Check if this source can be tested in the workbench."""
        return self.is_active and self.param_type != QueryParameterType.NONE

    def supports_parameter(self, param_type: QueryParameterType) -> bool:
        """Check if this source supports the given parameter type."""
        # API sources support any parameter type
        if self.param_type == QueryParameterType.API:
            return True
        # Exact match
        if self.param_type == param_type:
            return True
        # GeneAndTerm sources support individual gene/term parameters
        return bool(
            self.param_type == QueryParameterType.GENE_AND_TERM
            and param_type
            in [
                QueryParameterType.GENE,
                QueryParameterType.TERM,
                QueryParameterType.GENE_AND_TERM,
            ],
        )


class QueryTestResult(BaseModel):
    """
    Domain entity representing the result of a query test.

    Contains the outcome of testing a source with specific parameters.
    """

    model_config = ConfigDict(frozen=True)

    # Identity
    id: UUID = Field(..., description="Unique identifier for this test result")
    catalog_entry_id: str = Field(..., description="ID of the catalog entry tested")
    session_id: UUID = Field(..., description="Workbench session this test belongs to")

    # Test execution
    parameters: AdvancedQueryParameters = Field(
        ...,
        description="Parameters used for the test",
    )
    status: TestResultStatus = Field(..., description="Outcome status of the test")

    # Results
    response_data: JSONObject | None = Field(
        None,
        description="Raw response data from the source",
    )
    response_url: str | None = Field(None, description="Generated URL if applicable")
    error_message: str | None = Field(None, description="Error message if test failed")

    # Metadata
    execution_time_ms: int | None = Field(
        None,
        description="Time taken to execute test",
    )
    data_quality_score: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Quality score of returned data",
    )

    # Timestamps
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the test started",
    )
    completed_at: datetime | None = Field(None, description="When the test completed")

    def is_successful(self) -> bool:
        """Check if this test was successful."""
        return self.status == TestResultStatus.SUCCESS

    def has_data(self) -> bool:
        """Check if this test returned data."""
        return self.response_data is not None or self.response_url is not None

    def get_duration_ms(self) -> int | None:
        """Get the test duration in milliseconds."""
        if self.completed_at is None:
            return None
        return int((self.completed_at - self.started_at).total_seconds() * 1000)


UpdatePayload = dict[str, object]


class DataDiscoverySession(BaseModel):
    """
    Domain entity representing a user's data discovery session.

    A session tracks a user's discovery and testing activities across
    multiple data sources within a Research Space context.
    """

    model_config = ConfigDict(frozen=True)

    # Identity
    id: UUID = Field(..., description="Unique identifier for the session")
    owner_id: UUID = Field(..., description="User who owns this session")

    # Context
    research_space_id: UUID | None = Field(
        None,
        description="Research Space this session belongs to",
    )
    name: str = Field(
        default="Untitled Session",
        min_length=1,
        max_length=200,
        description="User-friendly session name",
    )

    # Current state
    current_parameters: AdvancedQueryParameters = Field(
        default_factory=lambda: AdvancedQueryParameters(
            gene_symbol=None,
            search_term=None,
        ),
        description="Current query parameters for the session",
    )

    # Session data
    tested_sources: list[str] = Field(
        default_factory=list,
        description="IDs of sources that have been tested",
    )
    selected_sources: list[str] = Field(
        default_factory=list,
        description="IDs of sources selected for potential addition",
    )

    # Statistics
    total_tests_run: int = Field(
        default=0,
        description="Total number of tests executed",
    )
    successful_tests: int = Field(default=0, description="Number of successful tests")

    # Lifecycle
    is_active: bool = Field(default=True, description="Whether this session is active")

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the session was created",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the session was last updated",
    )
    last_activity_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the session was last used",
    )

    def _clone_with_updates(self, updates: UpdatePayload) -> "DataDiscoverySession":
        """Internal helper to maintain immutability with typed updates."""
        return self.model_copy(update=updates)

    def update_parameters(self, parameters: QueryParameters) -> "DataDiscoverySession":
        """Create new session with updated parameters."""
        update_payload: UpdatePayload = {
            "current_parameters": parameters,
            "updated_at": datetime.now(UTC),
            "last_activity_at": datetime.now(UTC),
        }
        return self._clone_with_updates(update_payload)

    def record_test(
        self,
        catalog_entry_id: str,
        *,
        success: bool,
    ) -> "DataDiscoverySession":
        """Create new session with test recorded."""
        new_tested_sources = list({*self.tested_sources, catalog_entry_id})
        new_successful_tests = self.successful_tests + (1 if success else 0)

        update_payload: UpdatePayload = {
            "tested_sources": new_tested_sources,
            "total_tests_run": self.total_tests_run + 1,
            "successful_tests": new_successful_tests,
            "updated_at": datetime.now(UTC),
            "last_activity_at": datetime.now(UTC),
        }
        return self._clone_with_updates(update_payload)

    def toggle_source_selection(self, catalog_entry_id: str) -> "DataDiscoverySession":
        """Create new session with source selection toggled."""
        new_selected = (
            [*self.selected_sources, catalog_entry_id]
            if catalog_entry_id not in self.selected_sources
            else [s for s in self.selected_sources if s != catalog_entry_id]
        )

        update_payload: UpdatePayload = {
            "selected_sources": new_selected,
            "updated_at": datetime.now(UTC),
            "last_activity_at": datetime.now(UTC),
        }
        return self._clone_with_updates(update_payload)

    def is_source_selected(self, catalog_entry_id: str) -> bool:
        """Check if a source is selected."""
        return catalog_entry_id in self.selected_sources

    def with_selected_sources(
        self,
        source_ids: Sequence[str],
    ) -> "DataDiscoverySession":
        """
        Create new session with an explicit set of selected sources.

        Args:
            source_ids: Iterable of catalog entry IDs to persist
        """
        deduped: list[str] = []
        seen: set[str] = set()
        for source_id in source_ids:
            if source_id in seen:
                continue
            seen.add(source_id)
            deduped.append(source_id)
        update_payload: UpdatePayload = {
            "selected_sources": deduped,
            "updated_at": datetime.now(UTC),
            "last_activity_at": datetime.now(UTC),
        }
        return self._clone_with_updates(update_payload)

    def is_source_tested(self, catalog_entry_id: str) -> bool:
        """Check if a source has been tested."""
        return catalog_entry_id in self.tested_sources

    def get_success_rate(self) -> float:
        """Calculate success rate for this session."""
        if self.total_tests_run == 0:
            return 0.0
        return self.successful_tests / self.total_tests_run


__all__ = [
    "AdvancedQueryParameters",
    "DataDiscoverySession",
    "PubMedSortOption",
    "QueryParameterCapabilities",
    "QueryParameters",
    "QueryParameterType",
    "QueryTestResult",
    "SourceCatalogEntry",
    "TestResultStatus",
]
