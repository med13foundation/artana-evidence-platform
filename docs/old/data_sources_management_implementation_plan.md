# Data Sources Management Implementation Plan

## Overview

This document provides architectural guidelines for implementing and managing different data sources in the Artana Resource Library. It defines what is **common to all data sources** and what can be **specific to each source type**, following Clean Architecture principles.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Common Infrastructure](#common-infrastructure)
3. [Source-Specific Components](#source-specific-components)
4. [Implementation Patterns](#implementation-patterns)
5. [Adding New Data Sources](#adding-new-data-sources)
6. [Examples](#examples)

---

## Architecture Overview

### Clean Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    Presentation Layer                       │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │         FastAPI Routes • Next.js Admin UI               │ │
│  │         /data-sources/* endpoints                         │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                                 │
┌─────────────────────────────────────────────────────────────┐
│                    Application Layer                        │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │         SourceManagementService                          │ │
│  │         IngestionSchedulingService                     │ │
│  │         SourceTypeIngestionService (per type)           │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                                 │
┌─────────────────────────────────────────────────────────────┐
│                     Domain Layer                            │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │         UserDataSource • SourceTemplate                 │ │
│  │         SourceType-specific Entities                    │ │
│  │         SourcePluginRegistry • Business Rules           │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                                 │
┌─────────────────────────────────────────────────────────────┐
│                 Infrastructure Layer                        │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │         SourceGateways (per type)                       │ │
│  │         Repositories • Mappers                          │ │
│  │         Validators • Schedulers                          │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Key Principles

1. **Common Core**: All data sources share the same lifecycle, scheduling, quality metrics, and management infrastructure
2. **Source-Specific Extensions**: Each source type can extend with custom validation, gateways, and transformation logic
3. **Plugin Architecture**: Source-specific behavior is encapsulated in plugins that register with the system
4. **Type Safety**: Strict typing throughout, no `Any` types
5. **Separation of Concerns**: Domain logic independent of infrastructure details

### Non-Negotiable Guardrails

**⚠️ CRITICAL**: All data source implementations MUST adhere to these architectural constraints:

1. **Shared Lifecycle**: All sources use the same lifecycle (creation, activation, scheduling, quality assessment, deletion) defined in `UserDataSource` and `SourceManagementService`. Source-specific implementations are **plugins** that extend this shared lifecycle, not replacements.

2. **Clean Architecture Layers**: Strict adherence to the layer separation:
   - **Presentation** → FastAPI routes, Next.js UI
   - **Application** → `SourceManagementService`, `IngestionSchedulingService`, source-specific ingestion services
   - **Domain** → Business logic, entities, plugins, business rules
   - **Infrastructure** → Gateways, repositories, validators, schedulers

3. **Centralized Services**:
   - **Scheduling**: All scheduling flows through `IngestionSchedulingService` (shared service). Source-specific services orchestrate ingestion but **do not** implement their own scheduling.
   - **Quality Metrics**: Quality assessment runs centrally through shared infrastructure. Source-specific services provide data but don't manage quality metrics directly.
   - **Ingestion Jobs**: All ingestion executions create `IngestionJob` records through the shared job system.

4. **Configuration Storage**: Source-specific configuration MUST be stored in `SourceConfiguration.metadata` (JSON). This ensures:
   - Common fields remain in base `SourceConfiguration`
   - Source-specific fields are properly typed via Pydantic value objects
   - Business rules are enforced at the domain layer
   - Configuration is validated through plugins

5. **Type Safety Contract**:
   - **Never use `Any`**: All types must be properly defined using `src/type_definitions/` patterns
   - **TypedDict for configs**: Source-specific configurations use TypedDict or Pydantic models
   - **Protocols for interfaces**: Gateway interfaces use Protocol classes
   - **Generated TypeScript types**: Frontend types must be generated from backend Pydantic models

6. **Testing Requirements**:
   - Every validator, repository, and service MUST ship with typed unit + integration tests
   - Test coverage must exceed the required threshold (>85% for business logic)
   - Use typed fixtures from `tests/test_types/fixtures.py` and `tests/test_types/mocks.py`
   - Follow testing patterns in `docs/type_examples.md`

---

## Common Infrastructure

### 1. Core Domain Entities

**Location**: `src/domain/entities/user_data_source.py`

All data sources share these common entities:

#### `UserDataSource`
- **Common Fields**:
  - Identity: `id`, `owner_id`, `research_space_id`
  - Metadata: `name`, `description`, `tags`, `version`
  - Status: `status` (DRAFT, ACTIVE, INACTIVE, ERROR, etc.)
  - Configuration: `configuration` (SourceConfiguration)
  - Scheduling: `ingestion_schedule` (IngestionSchedule)
  - Quality: `quality_metrics` (QualityMetrics)
  - Timestamps: `created_at`, `updated_at`, `last_ingested_at`

- **Common Methods**:
  - `is_active()`: Check if source is actively ingesting
  - `can_ingest()`: Check if source is eligible for ingestion
  - `update_status()`: Change source status
  - `update_quality_metrics()`: Update quality assessment
  - `record_ingestion()`: Record successful ingestion

#### `SourceConfiguration`
- **Common Fields**:
  - `url`: Source URL (for API/database sources)
  - `file_path`: File path (for file uploads)
  - `format`: Data format (json, csv, xml, etc.)
  - `auth_type`: Authentication method
  - `auth_credentials`: Authentication credentials
  - `requests_per_minute`: Rate limiting
  - `field_mapping`: Field name mappings
  - `metadata`: Source-specific metadata (flexible JSON)

- **Extensibility**: Uses `extra="allow"` to permit source-specific fields

#### `IngestionSchedule`
- **Common Fields**:
  - `enabled`: Whether scheduling is enabled
  - `frequency`: Frequency (manual, hourly, daily, weekly)
  - `start_time`: Scheduled start time
  - `timezone`: Timezone for scheduling

- **Scheduling Support**:
  - Currently supports predefined frequencies: `manual`, `hourly`, `daily`, `weekly`
  - Validation handled by field validator in the entity
  - User preferences flow through shared scheduling service, not ad-hoc workers
  - **Future Enhancement**: Cron expression support planned for advanced scheduling scenarios

#### `QualityMetrics`
- **Common Fields**:
  - `completeness_score`: Data completeness (0-1)
  - `consistency_score`: Data consistency (0-1)
  - `timeliness_score`: Data timeliness (0-1)
  - `overall_score`: Overall quality score (0-1)
  - `last_assessed`: When quality was last assessed
  - `issues_count`: Number of quality issues found

### 2. Application Services

**Location**: `src/application/services/`

#### `SourceManagementService`
- **Common Operations** (all sources):
  - `create_source()`: Create new data source
  - `get_source()`: Retrieve source by ID
  - `update_source()`: Update source configuration
  - `delete_source()`: Delete source
  - `activate_source()` / `deactivate_source()`: Status management
  - `validate_source_configuration()`: Validate configuration
  - `get_user_sources()`: List user's sources
  - `search_sources()`: Search by name
  - `get_statistics()`: Overall statistics

- **Plugin Integration**: Uses `SourcePluginRegistry` to delegate source-specific validation

#### `IngestionSchedulingService` (to be implemented)
- **Common Operations**:
  - `schedule_ingestion()`: Schedule periodic ingestion using predefined frequencies (and, in future, cron expressions)
  - `unschedule_ingestion()`: Remove schedule
  - `execute_scheduled_ingestion()`: Execute scheduled job
  - `get_scheduled_sources()`: List sources with active schedules
  - `pause_schedule()` / `resume_schedule()`: Pause/resume scheduling

- **Centralized Scheduling**:
  - **All scheduling flows through this service**: Source-specific services orchestrate ingestion but do NOT implement their own scheduling logic
  - **Predefined frequencies**: Currently supports `manual`, `hourly`, `daily`, `weekly` schedules; cron will be added via `frequency="cron"` + `cron_expression` once scheduler adapters are wired in
  - **Schedule persistence**: Schedules are persisted in database, not in-memory workers
  - **Integration**: Source-specific ingestion services are called by the scheduling service, not vice versa
  - **Implementation order**: Source-specific ingestion services can still be invoked directly from API routes for manual, one-off ingestions while this service is being implemented; scheduled/recurring ingestion flows MUST go through this service before production use

### 3. Domain Services

**Location**: `src/domain/services/`

#### `SourcePluginRegistry`
- **Purpose**: Registry for source-specific plugins
- **Common Interface**: All plugins implement `SourcePlugin` protocol
- **Registration**: Plugins register by `SourceType`

#### `SourcePlugin` Protocol
```python
class SourcePlugin(ABC):
    """Base class for source-specific plugins."""

    source_type: SourceType

    def __init__(self, *, name: str | None = None, description: str | None = None):
        ...

    @abstractmethod
    def validate_configuration(
        self, configuration: SourceConfiguration
    ) -> SourceConfiguration:
        """Validate and sanitize source-specific configuration."""
        ...

    def activation_metadata(self, configuration: SourceConfiguration) -> JSONObject:
        """Optional metadata emitted when a plugin is activated."""
        return {}
```

### 4. Infrastructure Components

**Location**: `src/infrastructure/`

#### Repositories
- **Common Interface**: `UserDataSourceRepository`
  - `save()`, `find_by_id()`, `find_by_owner()`, `find_by_type()`, `delete()`
  - `record_ingestion()`, `update_quality_metrics()`
  - `get_statistics()`

#### Mappers
- **Common Pattern**: Domain entities ↔ Database models
- **Location**: `src/infrastructure/mappers/user_data_source_mapper.py`

#### Event System
- **Common Events**: All sources emit domain events
  - `SourceCreatedEvent`
  - `SourceUpdatedEvent`
  - `SourceStatusChangedEvent`
  - `IngestionCompletedEvent`

### 5. Database Schema

**Location**: `src/models/database/user_data_source.py`

#### Common Tables
- **`user_data_sources`**: Core source metadata (all sources)
- **`ingestion_jobs`**: Execution history (all sources)
- **`source_templates`**: Reusable configurations (all sources)

#### Common Fields
- Identity, ownership, status, configuration (JSON), scheduling, quality metrics
- Timestamps, relationships

---

## Source-Specific Components

### 1. Source Type Enumeration

**Location**: `src/domain/entities/user_data_source.py`

```python
class SourceType(str, Enum):
    FILE_UPLOAD = "file_upload"
    API = "api"
    DATABASE = "database"
    WEB_SCRAPING = "web_scraping"
    PUBMED = "pubmed"  # Example: PubMed-specific type
```

### 2. Source-Specific Domain Entities

**Pattern**: Extend or compose with `UserDataSource`

**⚠️ CRITICAL**: Source-specific configuration MUST be stored in `SourceConfiguration.metadata` (JSON). This ensures:
- Business rules are enforced at the domain layer (per AGENTS.md mandate)
- Configuration is properly typed via Pydantic value objects
- Common infrastructure remains unchanged
- Type safety is maintained throughout

#### Option A: Composition (Recommended)
```python
class PubMedQueryConfig(BaseModel):
    """PubMed-specific configuration value object."""

    query: str = Field(..., min_length=1, description="PubMed search query")
    date_from: str | None = Field(None, description="Start date (YYYY/MM/DD)")
    date_to: str | None = Field(None, description="End date (YYYY/MM/DD)")
    publication_types: list[str] | None = Field(
        None,
        description="Filter by publication types",
    )
    max_results: int = Field(1000, ge=1, le=10000, description="Maximum results")
    relevance_threshold: int = Field(5, ge=0, le=10, description="Relevance threshold")

    @field_validator("date_from", "date_to")
    @classmethod
    def validate_date_format(cls, v: str | None) -> str | None:
        """Validate date format matches PubMed requirements."""
        if v and not re.match(r"\d{4}/\d{2}/\d{2}", v):
            raise ValueError("Date must be in YYYY/MM/DD format")
        return v

    @field_validator("date_from", "date_to", mode="before")
    @classmethod
    def validate_date_range(cls, v: str | None, info) -> str | None:
        """Validate date_from is before date_to."""
        if info.data.get("date_from") and info.data.get("date_to"):
            if info.data["date_from"] > info.data["date_to"]:
                raise ValueError("date_from must be before date_to")
        return v

# Usage: Store in UserDataSource.configuration.metadata
# The plugin validates and converts to/from this Pydantic model
```

#### Option B: Inheritance (For complex cases)
```python
class PubMedUserDataSource(UserDataSource):
    """Extended entity for PubMed sources."""

    pubmed_config: PubMedQueryConfig

    # Additional PubMed-specific business logic
```

### 3. Source-Specific Gateways

**Location**: `src/infrastructure/data_sources/`

#### Gateway Pattern
Each source type implements a gateway interface:

```python
class SourceGateway(Protocol):
    """Protocol for source-specific data gateways."""

    async def fetch_data(
        self,
        configuration: SourceConfiguration,
        parameters: dict[str, JSONValue] | None = None,
    ) -> list[RawRecord]:
        """Fetch data from the source."""
        ...

    async def test_connection(
        self,
        configuration: SourceConfiguration,
    ) -> ConnectionTestResult:
        """Test connection to the source."""
        ...
```

#### Examples
- **`HttpAPISourceGateway`**: Generic HTTP API gateway
- **`LocalFileUploadGateway`**: File upload gateway
- **`PubMedGateway`**: PubMed-specific gateway (to be implemented)
- **`DatabaseSourceGateway`**: Database connection gateway (to be implemented)

### 4. Source-Specific Validators

**Location**: `src/infrastructure/validation/` or `src/domain/validation/`

Source-specific validators should **not duplicate** business rules already expressed
in domain value objects like `PubMedQueryConfig`. Instead, they act as adapters that:

- Instantiate the domain config model (e.g., `PubMedQueryConfig`) using
  `SourceConfiguration.metadata`
- Translate Pydantic validation errors into a normalized error list for callers

#### Pattern
```python
class PubMedConfigurationValidator:
    """Adapter that bridges SourceConfiguration -> PubMedQueryConfig validation.

    NOTE:
        All PubMed configuration rules (date formats, ranges, limits, etc.)
        live in PubMedQueryConfig at the domain layer. This validator should
        NOT re-implement those rules; it only adapts validation failures into
        a uniform error list for callers.
    """

    def validate(self, config: SourceConfiguration) -> list[str]:
        """Return list of validation error messages."""
        try:
            # Domain-layer validation via Pydantic
            PubMedQueryConfig(**config.metadata)
        except ValidationError as exc:
            return [error["msg"] for error in exc.errors()]
        return []
```

### 5. Source-Specific Repositories

**Pattern**: Extend base repository for source-specific queries

```python
class PubMedArticleRepository:
    """Repository for PubMed articles."""

    def find_by_pmid(self, pmid: str) -> Publication | None:
        """Find publication by PubMed ID."""
        ...

    def find_by_query_id(self, query_id: UUID) -> list[Publication]:
        """Find articles from a specific query."""
        ...

    def find_new_since(self, since: datetime) -> list[Publication]:
        """Find articles added since timestamp."""
        ...
```

### 6. Source-Specific Transformers

**Location**: `src/domain/transform/transformers/`

#### Pattern
```python
class PubMedTransformer:
    """Transform PubMed raw data into domain entities."""

    def transform_publication(
        self,
        raw_record: RawRecord,
    ) -> Publication:
        """Transform raw PubMed record to Publication entity."""
        ...

    def extract_variants(
        self,
        publication: Publication,
    ) -> list[Variant]:
        """Extract variants from publication text."""
        ...

    def extract_phenotypes(
        self,
        publication: Publication,
    ) -> list[Phenotype]:
        """Extract phenotypes and map to HPO terms."""
        ...
```

### 7. Source-Specific Application Services

**Location**: `src/application/services/`

**⚠️ CRITICAL**: Source-specific ingestion services:
- **Orchestrate** plugin validation, gateway fetch, transformation, repository writes
- **Do NOT** implement scheduling logic (that's handled by `IngestionSchedulingService`)
- **Do NOT** manage quality metrics directly (that's handled centrally)
- **Do** update ingestion job records through shared infrastructure
- **Do** emit domain events for ingestion completion

#### Pattern
```python
class PubMedIngestionService:
    """Application service for PubMed ingestion.

    Orchestrates PubMed-specific ingestion while delegating
    scheduling and quality metrics to shared services.
    """

    def __init__(
        self,
        pubmed_gateway: PubMedGateway,
        publication_repository: PublicationRepository,
        pubmed_article_repository: PubMedArticleRepository,
        # Note: scheduling_service is NOT injected here
        # Scheduling is handled by IngestionSchedulingService
    ):
        ...

    async def execute_ingestion(
        self,
        source: UserDataSource,
    ) -> IngestionResult:
        """Execute PubMed ingestion for a source.

        This method is called by IngestionSchedulingService
        when a scheduled job runs, or by API endpoints for
        manual triggers.
        """
        # 1. Validate source type
        if source.source_type != SourceType.PUBMED:
            raise ValueError("Source is not a PubMed source")

        # 2. Extract and validate PubMed config from source.configuration.metadata
        pubmed_config = self._extract_pubmed_config(source.configuration)

        # 3. Call gateway to fetch data
        raw_records = await self.pubmed_gateway.fetch_data(
            source.configuration,
        )

        # 4. Transform raw records to domain entities
        publications = [
            self.transformer.transform_publication(record)
            for record in raw_records
        ]

        # 5. Store in repositories (both normalized and raw JSON)
        for pub in publications:
            self.publication_repository.save(pub)
        self.pubmed_article_repository.save_raw_records(
            source_id=source.id,
            raw_records=raw_records,
        )

        # 6. Update source (record ingestion timestamp)
        updated_source = source.record_ingestion()
        self.source_repository.save(updated_source)

        # 7. Emit domain event for asynchronous subscribers
        #    (metrics, audit logging, downstream pipelines). The scheduler
        #    and other consumers can react to this independently of the
        #    immediate caller.
        self.event_bus.publish(
            IngestionCompletedEvent(
                source_id=source.id,
                records_processed=len(publications),
                status=IngestionStatus.COMPLETED,
            )
        )

        # 8. Return result to the immediate caller (API route or
        #    IngestionSchedulingService) for synchronous feedback and
        #    ingestion job updates. This is the primary request/response
        #    contract for orchestrated ingestion.
        return IngestionResult(
            source_id=source.id,
            records_processed=len(publications),
            status=IngestionStatus.COMPLETED,
        )
```

---

## Implementation Patterns

### Pattern 1: Plugin Registration

**How to register a new source type:**

```python
# In src/domain/services/source_plugins/plugins.py

from src.domain.entities.user_data_source import SourceType
from src.domain.services.source_plugins.base import SourcePlugin
from src.domain.services.source_plugins.registry import default_registry

class PubMedPlugin(SourcePlugin):
    """Plugin for PubMed data sources."""

    source_type = SourceType.PUBMED

    def validate_configuration(
        self,
        configuration: SourceConfiguration,
    ) -> SourceConfiguration:
        # PubMed-specific validation
        if not configuration.metadata.get("query"):
            raise ValueError("PubMed query is required")
        return configuration

# Register plugin with shared registry
default_registry.register(PubMedPlugin())
```

### Pattern 2: Gateway Implementation

**How to implement a source-specific gateway:**

```python
# In src/infrastructure/data_sources/pubmed_gateway.py

class PubMedGateway(SourceGateway):
    """Gateway for PubMed API."""

    def __init__(self, ingestor: PubMedIngestor):
        self.ingestor = ingestor

    async def fetch_data(
        self,
        configuration: SourceConfiguration,
        parameters: dict[str, JSONValue] | None = None,
    ) -> list[RawRecord]:
        # Extract PubMed-specific config
        query = configuration.metadata.get("query", "MED13")
        date_from = configuration.metadata.get("date_from")
        date_to = configuration.metadata.get("date_to")

        # Call ingestor
        return await self.ingestor.fetch_data(
            query=query,
            mindate=date_from,
            maxdate=date_to,
            **(parameters or {}),
        )

    async def test_connection(
        self,
        configuration: SourceConfiguration,
    ) -> ConnectionTestResult:
        # Test PubMed API connection
        ...
```

### Pattern 3: Service Orchestration

**How to orchestrate source-specific ingestion:**

**⚠️ IMPORTANT**: Source-specific ingestion services are **called by** `IngestionSchedulingService`, not the other way around. The scheduling service:
1. Reads schedules from database
2. Determines which sources need ingestion
3. Calls the appropriate source-specific ingestion service
4. Updates `IngestionJob` records
5. Handles retries and error recovery

```python
# In src/application/services/ingestion_scheduling_service.py

class IngestionSchedulingService:
    """Centralized scheduling service for all data sources."""

    async def execute_scheduled_ingestion(
        self,
        source: UserDataSource,
    ) -> IngestionResult:
        """Execute ingestion for a scheduled source.

        This method:
        1. Creates IngestionJob record
        2. Routes to appropriate source-specific service
        3. Updates job status
        4. Handles errors and retries
        """
        # Create job record
        job = IngestionJob.create(
            source_id=source.id,
            trigger=IngestionTrigger.SCHEDULED,
        )
        self.job_repository.save(job)

        try:
            # Route to source-specific service
            if source.source_type == SourceType.PUBMED:
                result = await self.pubmed_ingestion_service.execute_ingestion(source)
            elif source.source_type == SourceType.API:
                result = await self.api_ingestion_service.execute_ingestion(source)
            # ... other source types

            # Update job with result
            job.mark_completed(result)
            self.job_repository.save(job)
            return result

        except Exception as e:
            job.mark_failed(str(e))
            self.job_repository.save(job)
            raise

# In src/application/services/pubmed_ingestion_service.py

class PubMedIngestionService:
    """Orchestrates PubMed ingestion (called by scheduling service)."""

    async def execute_ingestion(
        self,
        source: UserDataSource,
    ) -> IngestionResult:
        # Implementation as shown in Pattern 7 above
        ...
```

### Pattern 4: Configuration Storage

**How to store source-specific configuration:**

```python
# Store in UserDataSource.configuration.metadata

pubmed_source = UserDataSource(
    id=UUID(),
    owner_id=user_id,
    source_type=SourceType.PUBMED,
    configuration=SourceConfiguration(
        url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
        metadata={
            "query": "MED13 AND mutation",
            "date_from": "2020-01-01",
            "date_to": "2024-12-31",
            "publication_types": ["journal_article", "review"],
            "max_results": 1000,
            "relevance_threshold": 5,
        },
        requests_per_minute=10,  # NCBI rate limit
    ),
)
```

---

## Adding New Data Sources

### Step-by-Step Guide

#### Step 1: Define Source Type

**Location**: `src/domain/entities/user_data_source.py`

```python
class SourceType(str, Enum):
    # ... existing types ...
    NEW_SOURCE = "new_source"
```

#### Step 2: Create Domain Entities (if needed)

**Location**: `src/domain/entities/`

```python
class NewSourceConfig(BaseModel):
    """Configuration specific to new source."""

    required_field: str
    optional_field: str | None = None
```

#### Step 3: Implement Source Plugin

**Location**: `src/domain/services/source_plugins/`

```python
class NewSourcePlugin(SourcePlugin):
    """Plugin for new source type."""

    def validate_configuration(
        self,
        configuration: SourceConfiguration,
    ) -> SourceConfiguration:
        # Validation logic
        ...

    def get_required_fields(self) -> list[str]:
        return ["required_field"]

    def get_default_configuration(self) -> SourceConfiguration:
        return SourceConfiguration(
            metadata={"required_field": "default_value"}
        )
```

#### Step 4: Implement Gateway

**Location**: `src/infrastructure/data_sources/new_source_gateway.py`

```python
class NewSourceGateway(SourceGateway):
    """Gateway for new source."""

    async def fetch_data(
        self,
        configuration: SourceConfiguration,
        parameters: dict[str, JSONValue] | None = None,
    ) -> list[RawRecord]:
        # Fetch logic
        ...

    async def test_connection(
        self,
        configuration: SourceConfiguration,
    ) -> ConnectionTestResult:
        # Connection test
        ...
```

#### Step 5: Implement Application Service

**Location**: `src/application/services/new_source_ingestion_service.py`

```python
class NewSourceIngestionService:
    """Service for new source ingestion."""

    async def execute_ingestion(
        self,
        source: UserDataSource,
    ) -> IngestionResult:
        # Orchestration logic
        ...
```

#### Step 6: Register Plugin

**Location**: `src/domain/services/source_plugins/plugins.py`

```python
registry.register(SourceType.NEW_SOURCE, NewSourcePlugin())
```

#### Step 7: Create Database Tables (if needed)

**Location**: `alembic/versions/`

```python
def upgrade() -> None:
    op.create_table(
        "new_source_data",
        sa.Column("id", sa.String(), primary_key=True),
        # ... source-specific fields ...
    )
```

#### Step 8: Add API Routes

**Location**: `src/routes/admin_routes/data_sources/`

**⚠️ CRITICAL**: API routes must:
- Return `ApiResponse[...]` or `PaginatedResponse[...]` from `src/type_definitions/common.py`
- Use generated TypeScript types (via `scripts/generate_ts_types.py`)
- Follow existing route patterns for consistency
- Maintain type safety (no `Any` types)

```python
# In src/routes/admin_routes/data_sources/pubmed.py

from src.type_definitions.common import ApiResponse, PaginatedResponse
from src.shared.types.data_source import DataSource  # Generated TypeScript type

@router.post("/pubmed", response_model=ApiResponse[DataSource])
async def create_pubmed_source(
    request: CreatePubMedSourceRequest,
    current_user: User = Depends(get_current_user),
    service: SourceManagementService = Depends(get_source_management_service),
):
    """Create a new PubMed data source."""
    source = service.create_source(
        CreateSourceRequest(
            owner_id=current_user.id,
            source_type=SourceType.PUBMED,
            configuration=SourceConfiguration(
                url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
                metadata=request.pubmed_config.model_dump(),  # Pydantic to dict
            ),
        )
    )
    return ApiResponse(
        success=True,
        data=source,  # Mapped to DataSource TypeScript type
    )

@router.get("/pubmed/{source_id}/articles", response_model=PaginatedResponse[Publication])
async def get_pubmed_articles(
    source_id: UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """Get articles from a PubMed source."""
    # Implementation with pagination
    ...
```

#### Step 9: Add UI Components (if needed)

**Location**: `src/web/components/data-sources/`

**⚠️ CRITICAL**: UI components must:
- Use generated TypeScript types from backend Pydantic models
- Follow Next.js SSR/React Query architecture (see `docs/frontend/EngenieeringArchitectureNext.md`)
- Maintain type safety throughout
- Use shared types from `src/shared/types/`

```typescript
// In src/web/components/data-sources/PubMedSourceForm.tsx

import { DataSource, DataSourceConfig } from '@/shared/types/data-source' // Generated type
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/lib/api-client'

export function PubMedSourceForm() {
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: async (data: DataSourceConfig) => {
      // Type-safe API call using generated types
      return apiClient.post<ApiResponse<DataSource>>('/data-sources/pubmed', {
        name: data.name,
        configuration: {
          metadata: {
            query: data.metadata?.query,
            date_from: data.metadata?.date_from,
            // ... other fields
          }
        }
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['data-sources'] })
    }
  })

  // Form implementation with type-safe fields
  ...
}
```

---

## Examples

### Example 1: PubMed Data Source

**This example demonstrates the complete implementation following all guardrails.**

#### Domain Layer
- **Entity**: `PubMedQueryConfig` (Pydantic value object)
  - Stored in `UserDataSource.configuration.metadata`
  - Validated by `PubMedPlugin` at domain layer
  - Business rules: Query validation, date range validation, relevance scoring, per-project scoping

- **Plugin**: `PubMedPlugin` (implements `SourcePlugin` protocol)
  - Validates `SourceConfiguration.metadata` against `PubMedQueryConfig`
  - Provides default configuration
  - Enforces required fields (query is mandatory)

- **Business Rules** (enforced at domain layer):
  - Query must be non-empty string
  - Date ranges must be valid (YYYY/MM/DD format)
  - date_from must be before date_to
  - max_results must be between 1 and 10000
  - Relevance threshold must be between 0 and 10

#### Application Layer
- **Service**: `PubMedIngestionService`
  - **Orchestrates**: Plugin validation → Gateway fetch → Transformer → Repository writes
  - **Delegates to shared services**:
    - Scheduling handled by `IngestionSchedulingService` (not implemented here)
    - Quality metrics handled centrally (not managed here)
    - Ingestion job updates handled by scheduling service
  - **Scheduler orchestration implemented**: `IngestionSchedulingService` now registers jobs, tracks `next_run_at`/`last_run_at`, and records `IngestionJob` snapshots for every run
  - **Emits events**: `IngestionCompletedEvent` for downstream processing

#### Infrastructure Layer
- **Gateway**: `PubMedGateway` (implements `SourceGateway` protocol)
  - Wraps: `PubMedIngestor` (existing infrastructure)
  - Uses: `api_response_validator.py` for response validation
  - Handles: API calls, rate limiting (NCBI: 10 req/sec), error handling, retries

- **Repository**: `PubMedArticleRepository`
  - Stores: Publications (normalized), query history, raw JSON snapshots
  - Extends: Base repository pattern for source-specific queries
  - Methods: `find_by_pmid()`, `find_by_query_id()`, `find_new_since()`

- **Transformer**: `PubMedTransformer`
  - Transforms: Raw XML → `Publication` entities
  - Extracts: Variants, phenotypes, evidence (following universal extraction template)
  - Uses: Existing transform infrastructure

#### Database Schema
- **Extends common tables**: Uses `user_data_sources` and `ingestion_jobs` (no new tables needed for basic functionality)
- **Optional source-specific tables**: `pubmed_queries`, `pubmed_articles` (if needed for advanced features)
- **Indexes**: `pmid`, `research_space_id`, `next_run_at` for performance

#### API & UI

- **FastAPI Routes**: `/data-sources/pubmed/*`
  - Returns: `ApiResponse<DataSource>` or `PaginatedResponse<Publication>`
  - Uses: Generated TypeScript types
- **Scheduling & History Routes**: `/admin/data-sources/{source_id}/schedule*`, `/admin/data-sources/{source_id}/ingestion-jobs`
  - Schedule endpoints persist cadence + cron metadata (cron raising `NotImplementedError` until dedicated backend)
  - History endpoint returns recent `IngestionJob` entries for UI detail panels

- **Next.js Components**:
  - Forms for query configuration, schedule selection (Create dialog + PubMed schedule modal)
  - Detail drawer surfaces latest manual run + ingestion job history using the new API
  - Tables for article results (future enhancement) remain on the roadmap
  - Uses: React Query, generated types, SSR architecture

#### Configuration Example
```python
# Domain layer: Pydantic value object
pubmed_config = PubMedQueryConfig(
    query="MED13 AND (mutation OR variant)",
    date_from="2020/01/01",  # PubMed date format
    date_to=None,  # Current date
    publication_types=["journal_article", "review"],
    max_results=1000,
    relevance_threshold=5,
)

# Stored in UserDataSource (via plugin validation)
pubmed_source = UserDataSource(
    source_type=SourceType.PUBMED,
    research_space_id=project_id,  # Per-project scoping
    configuration=SourceConfiguration(
        url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
        metadata=pubmed_config.model_dump(),  # Pydantic → dict
        requests_per_minute=10,  # NCBI rate limit
    ),
    ingestion_schedule=IngestionSchedule(
        enabled=True,
        frequency="daily",  # Currently supports: manual, hourly, daily, weekly
        start_time=datetime(2024, 1, 1, 2, 0, 0),
        timezone="UTC",
    ),
)

# Scheduling flows through IngestionSchedulingService
# PubMedIngestionService.execute_ingestion() is called by scheduler
# Future: Cron expression support planned for advanced scheduling
```

### Example 2: Generic HTTP API Source

#### Domain Layer
- **Plugin**: `APISourcePlugin` (generic validation)
- **Business Rules**: URL validation, auth validation, rate limit validation

#### Application Layer
- **Service**: `APIIngestionService` (generic)
  - Works with: Any HTTP API
  - Handles: Authentication, rate limiting, pagination

#### Infrastructure Layer
- **Gateway**: `HttpAPISourceGateway` (existing)
  - Handles: HTTP requests, auth, retries
  - Supports: Bearer, Basic, API key, OAuth2

#### Configuration Example
```python
api_source = UserDataSource(
    source_type=SourceType.API,
    configuration=SourceConfiguration(
        url="https://api.example.com/data",
        auth_type="bearer",
        auth_credentials={"token": "..."},
        requests_per_minute=60,
        metadata={
            "method": "GET",
            "query_params": {"limit": 100},
        },
    ),
)
```

### Example 3: File Upload Source

#### Domain Layer
- **Plugin**: `FileUploadPlugin`
- **Business Rules**: File format validation, size limits

#### Application Layer
- **Service**: `FileUploadIngestionService`
  - Handles: File parsing, validation, storage

#### Infrastructure Layer
- **Gateway**: `LocalFileUploadGateway` (existing)
  - Handles: File reading, format detection, parsing

#### Configuration Example
```python
file_source = UserDataSource(
    source_type=SourceType.FILE_UPLOAD,
    configuration=SourceConfiguration(
        file_path="/uploads/data.csv",
        format="csv",
        field_mapping={
            "gene": "gene_symbol",
            "variant": "hgvs",
        },
    ),
)
```

---

## Best Practices

### 1. Configuration Storage

- **Common fields**: Store in `SourceConfiguration` base fields
- **Source-specific fields**: Store in `SourceConfiguration.metadata` (JSON)
- **Validation**: Use plugins to validate source-specific fields

### 2. Error Handling

- **Common errors**: Handle in application services
- **Source-specific errors**: Handle in gateways, propagate as domain exceptions
- **Retry logic**: Implement in gateways, not services

### 3. Testing

- **Unit tests**: Test plugins, validators, transformers
- **Integration tests**: Test gateways with real APIs (mocked)
- **E2E tests**: Test full ingestion flow

### 4. Type Safety

**⚠️ CRITICAL - Never-Any Contract**:

- **No `Any` types**: Use proper types from `src/type_definitions/`
  - `JSONObject`, `JSONValue`, `JSONArray` for JSON-compatible data
  - `ApiResponse<T>`, `PaginatedResponse<T>` for API responses
  - TypedDict classes for update operations (`GeneUpdate`, `VariantUpdate`, etc.)
  - Validation results from `src/type_definitions/external_apis.py`

- **TypedDict for configs**: Use TypedDict or Pydantic models for source-specific configurations
  - Store in `SourceConfiguration.metadata` as typed JSON
  - Validate through plugins using Pydantic models

- **Protocols for interfaces**: Use Protocol for gateway interfaces
  - `SourceGateway` protocol for all gateways
  - `SourcePlugin` protocol for all plugins

- **Generated TypeScript types**:
  - Backend Pydantic models → TypeScript interfaces via `scripts/generate_ts_types.py`
  - Frontend must use generated types, not manual definitions
  - Types must stay in sync (regenerate after model changes)

- **Testing with typed fixtures**:
  - Use `tests/test_types/fixtures.py` for typed test data
  - Use `tests/test_types/mocks.py` for typed mocks
  - Follow patterns in `docs/type_examples.md`

### 5. Testing Requirements

**⚠️ MANDATORY**: Every new component must ship with tests:

- **Unit Tests**:
  - Test plugins, validators, transformers in isolation
  - Use typed fixtures and mocks
  - Coverage target: >85% for business logic

- **Integration Tests**:
  - Test gateways with real APIs (mocked)
  - Test repository persistence
  - Test service orchestration

- **Type Tests**:
  - MyPy strict mode must pass
  - No `Any` types allowed
  - All type annotations must be complete

- **Test Location**:
  - Unit tests: `tests/unit/`
  - Integration tests: `tests/integration/`
  - Follow existing test patterns and structure

### 6. Documentation

- **Plugin documentation**: Document required fields, validation rules
- **Gateway documentation**: Document API endpoints, rate limits, error codes
- **Service documentation**: Document orchestration flow, dependencies

---

## Summary

### What's Common to All Sources

1. **Domain Entities**: `UserDataSource`, `SourceConfiguration`, `IngestionSchedule`, `QualityMetrics`
2. **Application Services**: `SourceManagementService`, `IngestionSchedulingService`
3. **Infrastructure**: Repositories, mappers, event system
4. **Database Schema**: Core tables for sources, jobs, templates
5. **Lifecycle**: Creation, activation, scheduling, quality assessment, deletion

### What's Source-Specific

1. **Domain Entities**: Source-specific configuration value objects
2. **Plugins**: Validation, default configuration, required fields
3. **Gateways**: Data fetching, connection testing
4. **Repositories**: Source-specific queries and storage
5. **Transformers**: Raw data → domain entities
6. **Application Services**: Source-specific ingestion orchestration
7. **Database Tables**: Source-specific data storage (if needed)

### Extension Points

1. **Source Type Enum**: Add new `SourceType` value
2. **Plugin Registry**: Register new `SourcePlugin`
3. **Gateway Implementation**: Implement `SourceGateway` protocol
4. **Service Implementation**: Create source-specific ingestion service
5. **Database Schema**: Add source-specific tables (if needed)
6. **API Routes**: Add source-specific endpoints (if needed)
7. **UI Components**: Add source-specific forms (if needed)

---

*This plan ensures that adding new data sources is straightforward while maintaining architectural consistency and type safety throughout the system.*

---

## Appendix: Pluggable Scheduling & Cron Strategy

To keep cron and scheduling **fully pluggable**, the system treats scheduling as a cross‑cutting concern with clear separation of responsibilities:

- **Domain layer**:
  - `IngestionSchedule` is a value object that describes *intent* (logical `frequency`, optional future `cron_expression`, `start_time`, `timezone`) without depending on any specific cron engine or library.
  - Business rules (e.g., “cron requires a non‑empty expression”) are enforced as Pydantic validators, but the cron string itself is opaque to the domain.

- **Application layer**:
  - `IngestionSchedulingService` owns *which* sources run *when*, and coordinates the lifecycle of `IngestionJob` entities.
  - It depends on an abstract scheduler port (e.g., a `SchedulerPort` protocol) that exposes operations like `register_job(source_id, schedule)` and `remove_job(job_id)`.
  - Source-specific ingestion services (e.g., `PubMedIngestionService`) never talk directly to cron libraries; they are invoked by the scheduling service.

- **Infrastructure layer**:
  - Concrete scheduler adapters (e.g., `APSchedulerBackend`, `CeleryBeatBackend`, `CloudSchedulerBackend`) implement the `SchedulerPort` protocol.
  - These adapters map `IngestionSchedule.frequency` + `cron_expression` into the native trigger configuration for the chosen scheduler.
  - Swapping from one scheduler backend to another does not require changes to domain entities or application services—only wiring at the infrastructure/binding layer.

This design ensures that MED13 can introduce cron expressions later, or migrate between different scheduling technologies, without violating Clean Architecture or the type‑safety guarantees defined in `AGENTS.md` and `docs/EngineeringArchitecture.md`.
