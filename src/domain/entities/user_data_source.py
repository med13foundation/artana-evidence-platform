"""
Domain entities for user-managed data sources in Artana Resource Library.

These entities represent user-configured data sources that extend the core system
with additional biomedical data while maintaining provenance and quality standards.
"""

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.type_definitions.common import AuthCredentials, SourceMetadata


def _empty_source_metadata() -> SourceMetadata:
    return {}


class SourceType(str, Enum):
    """Types of data sources supported for user management."""

    FILE_UPLOAD = "file_upload"
    API = "api"
    DATABASE = "database"
    WEB_SCRAPING = "web_scraping"  # Future use
    PUBMED = "pubmed"  # Biomedical literature ingestion
    CLINVAR = "clinvar"  # ClinVar genomic variant ingestion
    MARRVEL = "marrvel"  # MARRVEL gene-centric variant aggregation
    HPO = "hpo"  # Human Phenotype Ontology loader
    UBERON = "uberon"  # Uberon anatomy ontology loader
    CELL_ONTOLOGY = "cell_ontology"  # Cell Ontology loader
    GENE_ONTOLOGY = "gene_ontology"  # Gene Ontology loader
    MONDO = "mondo"  # Monarch Disease Ontology loader
    UNIPROT = "uniprot"  # UniProt protein data source
    DRUGBANK = "drugbank"  # DrugBank drug-target interaction source
    HGNC = "hgnc"  # HGNC human gene nomenclature alias source
    ALPHAFOLD = "alphafold"  # AlphaFold protein structure prediction source
    CLINICAL_TRIALS = "clinical_trials"  # ClinicalTrials.gov registered trials
    MGI = "mgi"  # Mouse Genome Informatics gene/phenotype source
    ZFIN = "zfin"  # Zebrafish Information Network gene/phenotype source


class ScheduleFrequency(str, Enum):
    """Available scheduling cadences for ingestion."""

    MANUAL = "manual"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CRON = "cron"


class SourceStatus(str, Enum):
    """Status of a user data source."""

    DRAFT = "draft"  # Being configured
    ACTIVE = "active"  # Actively ingesting
    INACTIVE = "inactive"  # Temporarily disabled
    ERROR = "error"  # Failed configuration/validation
    PENDING_REVIEW = "pending_review"  # Awaiting curator approval
    ARCHIVED = "archived"  # No longer used


class SourceConfiguration(BaseModel):
    """
    Configuration for a specific data source type.

    This is a flexible schema that adapts based on source_type.
    Each source type has its own validation rules and required fields.
    """

    model_config = ConfigDict(extra="allow")  # Allow additional fields per source type

    # Common fields
    url: str | None = Field(None, description="Source URL for API/database sources")
    file_path: str | None = Field(None, description="File path for uploaded files")
    format: str | None = Field(
        None,
        description="Data format (json, csv, xml, etc.)",
    )
    query: str | None = Field(
        default=None,
        description="Search query for the source (e.g. PubMed query)",
    )

    # Authentication
    auth_type: str | None = Field(None, description="Authentication method")
    auth_credentials: AuthCredentials | None = Field(
        None,
        description="Authentication credentials",
    )

    # Rate limiting
    requests_per_minute: int | None = Field(
        None,
        ge=1,
        le=1000,
        description="API rate limit",
    )

    # Data mapping
    field_mapping: dict[str, str] | None = Field(
        None,
        description="Field name mappings",
    )

    # Source-specific metadata
    metadata: SourceMetadata = Field(
        default_factory=_empty_source_metadata,
        description="Additional source-specific metadata",
    )

    @field_validator("requests_per_minute")
    @classmethod
    def validate_rate_limit(cls, v: int | None) -> int | None:
        """Validate rate limit is reasonable."""
        min_rpm = 1
        if v is not None and v < min_rpm:
            msg = "Requests per minute must be at least 1"
            raise ValueError(msg)
        return v


class IngestionSchedule(BaseModel):
    """Schedule configuration for automated data ingestion."""

    enabled: bool = Field(
        default=False,
        description="Whether scheduled ingestion is enabled",
    )
    frequency: ScheduleFrequency = Field(
        default=ScheduleFrequency.MANUAL,
        description="Desired ingestion cadence",
    )
    start_time: datetime | None = Field(None, description="Scheduled start time")
    timezone: str = Field(default="UTC", description="Timezone for scheduling")
    cron_expression: str | None = Field(
        default=None,
        description="Cron expression used when frequency is cron",
    )
    backend_job_id: str | None = Field(
        default=None,
        description="Identifier assigned by the scheduler backend",
    )
    next_run_at: datetime | None = Field(
        default=None,
        description="Next scheduled execution time",
    )
    last_run_at: datetime | None = Field(
        default=None,
        description="Most recent execution timestamp",
    )

    @field_validator("cron_expression")
    @classmethod
    def _normalize_cron(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("timezone")
    @classmethod
    def _normalize_timezone(cls, value: str) -> str:
        return value or "UTC"

    @model_validator(mode="after")
    def _validate_cron_expression(self) -> "IngestionSchedule":
        if self.frequency == ScheduleFrequency.CRON and not (
            self.cron_expression and self.cron_expression.strip()
        ):
            msg = "cron_expression is required when frequency is cron"
            raise ValueError(msg)
        return self

    @property
    def requires_scheduler(self) -> bool:
        """Return True when this schedule should register with the scheduler backend."""
        return self.enabled and self.frequency != ScheduleFrequency.MANUAL


class QualityMetrics(BaseModel):
    """Quality metrics for a data source."""

    completeness_score: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Data completeness (0-1)",
    )
    consistency_score: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Data consistency (0-1)",
    )
    timeliness_score: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Data timeliness (0-1)",
    )
    overall_score: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Overall quality score (0-1)",
    )

    last_assessed: datetime | None = Field(
        None,
        description="When quality was last assessed",
    )
    issues_count: int = Field(default=0, description="Number of quality issues found")


UpdatePayload = dict[str, object]


class UserDataSource(BaseModel):
    """
    Domain entity representing a user-managed data source.

    This is the core entity for the Data Sources module, representing
    a biomedical data source configured and managed by a user.
    """

    model_config = ConfigDict(frozen=True)  # Immutable - changes create new instances

    # Identity
    id: UUID = Field(..., description="Unique identifier for the data source")
    owner_id: UUID = Field(..., description="User who created this source")
    research_space_id: UUID | None = Field(
        None,
        description="Research space this data source belongs to",
    )

    # Basic information
    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Human-readable source name",
    )
    description: str = Field(
        "",
        max_length=1000,
        description="Detailed description of the source",
    )

    # Configuration
    source_type: SourceType = Field(..., description="Type of data source")
    template_id: UUID | None = Field(
        None,
        description="Template used to create this source",
    )
    configuration: SourceConfiguration = Field(
        ...,
        description="Source-specific configuration",
    )

    # Status and lifecycle
    status: SourceStatus = Field(
        default=SourceStatus.DRAFT,
        description="Current status",
    )
    ingestion_schedule: IngestionSchedule = Field(
        default_factory=lambda: IngestionSchedule(
            enabled=False,
            frequency=ScheduleFrequency.MANUAL,
            start_time=None,
            timezone="UTC",
        ),
        description="Ingestion scheduling",
    )

    # Quality and metrics
    quality_metrics: QualityMetrics = Field(
        default_factory=lambda: QualityMetrics(
            completeness_score=None,
            consistency_score=None,
            timeliness_score=None,
            overall_score=None,
            last_assessed=None,
            issues_count=0,
        ),
        description="Quality assessment results",
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When source was created",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When source was last updated",
    )
    last_ingested_at: datetime | None = Field(
        None,
        description="When data was last successfully ingested",
    )

    # Metadata
    tags: list[str] = Field(
        default_factory=list,
        description="User-defined tags for organization",
    )
    version: str = Field(default="1.0", description="Source configuration version")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate source name."""
        if not v.strip():
            msg = "Source name cannot be empty or whitespace"
            raise ValueError(msg)
        return v.strip()

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        """Validate tags are reasonable."""
        max_tags = 10
        if len(v) > max_tags:
            msg = "Maximum 10 tags allowed"
            raise ValueError(msg)
        max_tag_len = 50
        for tag in v:
            if len(tag) > max_tag_len:
                msg = "Tag length cannot exceed 50 characters"
                raise ValueError(msg)
        return [tag.strip().lower() for tag in v if tag.strip()]

    def is_active(self) -> bool:
        """Check if source is actively ingesting data."""
        return self.status == SourceStatus.ACTIVE

    def can_ingest(self) -> bool:
        """Check if source is eligible for data ingestion."""
        return self.status in [SourceStatus.ACTIVE, SourceStatus.DRAFT]

    def _clone_with_updates(self, updates: UpdatePayload) -> "UserDataSource":
        """Internal helper to preserve immutability with typed updates."""
        return self.model_copy(update=updates)

    def update_status(self, new_status: SourceStatus) -> "UserDataSource":
        """Create new instance with updated status."""
        update_payload: UpdatePayload = {
            "status": new_status,
            "updated_at": datetime.now(UTC),
        }
        return self._clone_with_updates(update_payload)

    def update_quality_metrics(self, metrics: QualityMetrics) -> "UserDataSource":
        """Create new instance with updated quality metrics."""
        update_payload: UpdatePayload = {
            "quality_metrics": metrics,
            "updated_at": datetime.now(UTC),
        }
        return self._clone_with_updates(update_payload)

    def record_ingestion(
        self,
        timestamp: datetime | None = None,
    ) -> "UserDataSource":
        """Create new instance with updated ingestion timestamp."""
        ingestion_time = timestamp or datetime.now(UTC)
        update_payload: UpdatePayload = {
            "last_ingested_at": ingestion_time,
            "updated_at": datetime.now(UTC),
        }
        return self._clone_with_updates(update_payload)

    def update_configuration(self, config: SourceConfiguration) -> "UserDataSource":
        """Create new instance with updated configuration."""
        update_payload: UpdatePayload = {
            "configuration": config,
            "updated_at": datetime.now(UTC),
            "version": self._increment_version(),
        }
        return self._clone_with_updates(update_payload)

    def update_ingestion_schedule(
        self,
        schedule: IngestionSchedule,
    ) -> "UserDataSource":
        """Create new instance with updated ingestion schedule."""
        update_payload: UpdatePayload = {
            "ingestion_schedule": schedule,
            "updated_at": datetime.now(UTC),
        }
        return self._clone_with_updates(update_payload)

    def _increment_version(self) -> str:
        """Increment version number for configuration changes."""
        try:
            major, minor = self.version.split(".")
            return f"{major}.{int(minor) + 1}"
        except (ValueError, IndexError):
            return "1.0"
