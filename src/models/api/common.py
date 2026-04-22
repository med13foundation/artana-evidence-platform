"""
Common API schemas for Artana Resource Library.

Shared Pydantic models for pagination, errors, and health checks.
"""

from pydantic import BaseModel, ConfigDict, Field

from src.type_definitions.common import JSONObject


class PaginationParams(BaseModel):
    """Query parameters for paginated endpoints."""

    page: int = Field(default=1, ge=1, description="Page number (1-based)")
    per_page: int = Field(default=20, ge=1, le=100, description="Items per page")
    sort_by: str | None = Field(None, description="Field to sort by")
    sort_order: str = Field(
        default="asc",
        pattern="^(asc|desc)$",
        description="Sort order",
    )


class PaginatedResponse[T](BaseModel):
    """Response wrapper for paginated results."""

    model_config = ConfigDict(strict=True)

    items: list[T] = Field(..., description="List of items")
    total: int = Field(..., description="Total number of items")
    page: int = Field(..., description="Current page number")
    per_page: int = Field(..., description="Items per page")
    total_pages: int = Field(..., description="Total number of pages")
    has_next: bool = Field(..., description="Whether there is a next page")
    has_prev: bool = Field(..., description="Whether there is a previous page")


class ErrorDetail(BaseModel):
    """Detailed error information."""

    field: str | None = Field(None, description="Field that caused the error")
    message: str = Field(..., description="Error message")
    code: str | None = Field(None, description="Error code")


class ErrorResponse(BaseModel):
    """Standard error response format."""

    model_config = ConfigDict(strict=True)

    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Human-readable error message")
    details: list[ErrorDetail] | None = Field(
        None,
        description="Detailed error information",
    )
    request_id: str | None = Field(
        None,
        description="Request identifier for debugging",
    )


class HealthComponent(BaseModel):
    """Health status of a system component."""

    status: str = Field(
        ...,
        pattern="^(healthy|degraded|unhealthy)$",
        description="Component health status",
    )
    message: str | None = Field(None, description="Status message")
    details: JSONObject | None = Field(None, description="Additional details")


class HealthResponse(BaseModel):
    """Health check response for the API."""

    model_config = ConfigDict(strict=True)

    status: str = Field(
        ...,
        pattern="^(healthy|degraded|unhealthy)$",
        description="Overall system health",
    )
    timestamp: str = Field(..., description="Health check timestamp")
    version: str = Field(..., description="API version")
    uptime: str | None = Field(None, description="System uptime")
    components: dict[str, HealthComponent] | None = Field(
        None,
        description="Component health statuses",
    )


class DashboardSummary(BaseModel):
    """Aggregate dashboard summary statistics."""

    pending_count: int = Field(..., ge=0, description="Pending item count")
    approved_count: int = Field(..., ge=0, description="Approved item count")
    rejected_count: int = Field(..., ge=0, description="Rejected item count")
    total_items: int = Field(..., ge=0, description="Total tracked items")
    entity_counts: dict[str, int] = Field(
        default_factory=dict,
        description="Entity-specific counts",
    )


class ActivityFeedItem(BaseModel):
    """Entry representing a dashboard activity feed item."""

    message: str = Field(..., description="Activity message")
    category: str = Field(..., description="Activity category/level")
    icon: str | None = Field(None, description="Optional icon identifier")
    created_at: str = Field(..., description="ISO8601 timestamp")


class GeneSummary(BaseModel):
    """Compact gene representation for nested responses."""

    model_config = ConfigDict(strict=True)

    id: int | None = Field(None, description="Internal gene identifier")
    gene_id: str | None = Field(None, description="Public gene ID")
    symbol: str | None = Field(None, description="Gene symbol")
    name: str | None = Field(None, description="Gene name")


class VariantLinkSummary(BaseModel):
    """Compact variant representation for nested responses."""

    model_config = ConfigDict(strict=True)

    id: int | None = Field(None, description="Variant primary key")
    variant_id: str | None = Field(None, description="Public variant ID")
    clinvar_id: str | None = Field(None, description="ClinVar accession")
    gene_symbol: str | None = Field(None, description="Associated gene symbol")


class PhenotypeSummary(BaseModel):
    """Compact phenotype representation for nested responses."""

    model_config = ConfigDict(strict=True)

    id: int | None = Field(None, description="Phenotype primary key")
    hpo_id: str | None = Field(None, description="HPO identifier")
    name: str | None = Field(None, description="Phenotype name")


class PublicationSummary(BaseModel):
    """Compact publication representation for nested responses."""

    model_config = ConfigDict(strict=True)

    id: int | None = Field(None, description="Publication primary key")
    title: str | None = Field(None, description="Publication title")
    pubmed_id: str | None = Field(None, description="PubMed identifier")
    doi: str | None = Field(None, description="DOI")


class ExportEntityInfo(BaseModel):
    """Information about an exportable entity type."""

    type: str = Field(..., description="Entity type identifier")
    description: str = Field(..., description="Human-readable description")


class ExportOptionsResponse(BaseModel):
    """Response containing export options and entity information."""

    entity_type: str = Field(..., description="Entity type being described")
    export_formats: list[str] = Field(..., description="Available export formats")
    compression_formats: list[str] = Field(
        ...,
        description="Available compression formats",
    )
    info: JSONObject = Field(..., description="Entity-specific export information")


class UsageInfo(BaseModel):
    """Usage information for export endpoints."""

    endpoint: str = Field(..., description="Example endpoint usage")
    description: str = Field(..., description="Usage description")


class ExportableEntitiesResponse(BaseModel):
    """Response listing all exportable entity types."""

    exportable_entities: list[ExportEntityInfo] = Field(
        ...,
        description="List of exportable entity types with descriptions",
    )
    supported_formats: list[str] = Field(
        ...,
        description="List of supported export formats",
    )
    supported_compression: list[str] = Field(
        ...,
        description="List of supported compression formats",
    )
    usage: UsageInfo = Field(
        ...,
        description="Usage information and examples",
    )
