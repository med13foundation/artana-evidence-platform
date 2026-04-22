"""
Application service for user data source management.

Orchestrates domain services and repositories to implement
data source management use cases with proper business logic.
"""

from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from src.domain.entities.source_template import SourceTemplate
from src.domain.entities.user_data_source import (
    IngestionSchedule,
    QualityMetrics,
    ScheduleFrequency,
    SourceConfiguration,
    SourceStatus,
    SourceType,
    UserDataSource,
)
from src.domain.events import (
    DomainEvent,
    DomainEventBus,
    SourceCreatedEvent,
    SourceStatusChangedEvent,
    SourceUpdatedEvent,
    domain_event_bus,
)
from src.domain.repositories.source_template_repository import SourceTemplateRepository
from src.domain.repositories.user_data_source_repository import UserDataSourceRepository
from src.domain.services.source_plugins import SourcePluginRegistry, default_registry
from src.type_definitions.common import StatisticsResponse


class CreateSourceRequest(BaseModel):
    """Request model for creating a new data source."""

    owner_id: UUID
    name: str
    source_type: SourceType
    description: str = ""
    template_id: UUID | None = None
    configuration: SourceConfiguration = Field(
        default_factory=lambda: SourceConfiguration(
            url="",
            file_path="",
            format="",
            auth_type=None,
            auth_credentials={},
            requests_per_minute=None,
            field_mapping={},
            metadata={},
        ),
    )
    tags: list[str] = Field(default_factory=list)
    research_space_id: UUID | None = None
    ingestion_schedule: IngestionSchedule | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class UpdateSourceRequest(BaseModel):
    """Request model for updating a data source."""

    name: str | None = None
    description: str | None = None
    status: SourceStatus | None = None
    configuration: SourceConfiguration | None = None
    ingestion_schedule: IngestionSchedule | None = None
    tags: list[str] | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class SourceManagementService:
    """
    Application service for user data source management.

    Orchestrates data source operations including creation, configuration,
    lifecycle management, and quality monitoring.
    """

    def __init__(
        self,
        user_data_source_repository: UserDataSourceRepository,
        source_template_repository: SourceTemplateRepository | None = None,
        plugin_registry: SourcePluginRegistry | None = None,
        event_bus: DomainEventBus | None = None,
    ):
        self._source_repository = user_data_source_repository
        self._template_repository = source_template_repository
        self._plugin_registry = plugin_registry or default_registry
        self._event_bus = event_bus or domain_event_bus

    def _require_template_repository(self) -> SourceTemplateRepository:
        if self._template_repository is None:
            msg = "Source template repository is not configured"
            raise RuntimeError(msg)
        return self._template_repository

    def _apply_plugin_validation(
        self,
        source_type: SourceType,
        configuration: SourceConfiguration,
    ) -> SourceConfiguration:
        plugin = self._plugin_registry.get(source_type)
        if plugin is None:
            return configuration
        return plugin.validate_configuration(configuration)

    def _publish_event(self, event: DomainEvent) -> None:
        self._event_bus.publish(event)

    def _determine_changed_fields(self, request: UpdateSourceRequest) -> list[str]:
        changed: list[str] = []
        if request.name is not None:
            changed.append("name")
        if request.description is not None:
            changed.append("description")
        if request.status is not None:
            changed.append("status")
        if request.configuration is not None:
            changed.append("configuration")
        if request.ingestion_schedule is not None:
            changed.append("ingestion_schedule")
        if request.tags is not None:
            changed.append("tags")
        return changed

    def create_source(self, request: CreateSourceRequest) -> UserDataSource:
        # Validate template if provided
        if request.template_id:
            template_repository = self._require_template_repository()
            template = template_repository.find_by_id(request.template_id)
            if not template:
                msg = f"Template {request.template_id} not found"
                raise ValueError(msg)
            if not template.is_available(request.owner_id):
                msg = f"Template {request.template_id} is not available"
                raise ValueError(msg)

        configuration = self._apply_plugin_validation(
            request.source_type,
            request.configuration,
        )

        # Create the source entity
        source = UserDataSource(
            id=uuid4(),
            owner_id=request.owner_id,
            research_space_id=request.research_space_id,
            name=request.name,
            description=request.description,
            source_type=request.source_type,
            template_id=request.template_id,
            configuration=configuration,
            ingestion_schedule=(
                request.ingestion_schedule
                if request.ingestion_schedule is not None
                else IngestionSchedule(
                    enabled=False,
                    frequency=ScheduleFrequency.MANUAL,
                    start_time=None,
                    timezone="UTC",
                )
            ),
            tags=request.tags,
            last_ingested_at=None,
        )

        # Save to repository
        saved_source = self._source_repository.save(source)
        self._publish_event(SourceCreatedEvent.from_source(saved_source))
        return saved_source

    def get_source(
        self,
        source_id: UUID,
        owner_id: UUID | None = None,
    ) -> UserDataSource | None:
        source = self._source_repository.find_by_id(source_id)
        if source and owner_id and source.owner_id != owner_id:
            return None  # Not owned by this user
        return source

    def get_user_sources(
        self,
        owner_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        return self._source_repository.find_by_owner(owner_id, skip, limit)

    def update_source(  # noqa: C901 - explicit field-by-field updates keep behavior clear
        self,
        source_id: UUID,
        request: UpdateSourceRequest,
        owner_id: UUID | None,
    ) -> UserDataSource | None:
        source = self._source_repository.find_by_id(source_id)
        if not source or (owner_id is not None and source.owner_id != owner_id):
            return None

        if request.status == SourceStatus.ACTIVE:
            effective_schedule = request.ingestion_schedule or source.ingestion_schedule
            if not effective_schedule.requires_scheduler:
                msg = (
                    "Active sources require an enabled ingestion schedule "
                    "with a non-manual frequency"
                )
                raise ValueError(msg)

        # Apply updates
        updated_source = source
        previous_status = source.status
        if request.name is not None:
            updated_source = updated_source.model_copy(
                update={"name": request.name},
            )
        if request.description is not None:
            updated_source = updated_source.model_copy(
                update={"description": request.description},
            )
        if request.status is not None and request.status != updated_source.status:
            updated_source = updated_source.update_status(request.status)
        if request.configuration is not None:
            sanitized_config = self._apply_plugin_validation(
                updated_source.source_type,
                request.configuration,
            )
            updated_source = updated_source.update_configuration(sanitized_config)
        if request.ingestion_schedule is not None:
            updated_source = updated_source.model_copy(
                update={"ingestion_schedule": request.ingestion_schedule},
            )
        if request.tags is not None:
            updated_source = updated_source.model_copy(update={"tags": request.tags})

        saved_source = self._source_repository.save(updated_source)
        changed_fields = self._determine_changed_fields(request)
        if changed_fields:
            self._publish_event(
                SourceUpdatedEvent.from_source(
                    saved_source,
                    changed_fields=changed_fields,
                ),
            )
        if request.status is not None and request.status != previous_status:
            self._publish_event(
                SourceStatusChangedEvent.from_source(
                    saved_source,
                    previous_status=previous_status,
                ),
            )
        return saved_source

    def delete_source(self, source_id: UUID, owner_id: UUID | None) -> bool:
        source = self._source_repository.find_by_id(source_id)
        if not source or (owner_id is not None and source.owner_id != owner_id):
            return False

        return self._source_repository.delete(source_id)

    def activate_source(
        self,
        source_id: UUID,
        owner_id: UUID,
    ) -> UserDataSource | None:
        source = self._source_repository.find_by_id(source_id)
        if not source or source.owner_id != owner_id:
            return None
        if not source.ingestion_schedule.requires_scheduler:
            msg = (
                "Active sources require an enabled ingestion schedule "
                "with a non-manual frequency"
            )
            raise ValueError(msg)

        previous_status = source.status
        activated_source = source.update_status(SourceStatus.ACTIVE)
        saved_source = self._source_repository.save(activated_source)
        self._publish_event(
            SourceStatusChangedEvent.from_source(
                saved_source,
                previous_status=previous_status,
            ),
        )
        return saved_source

    def deactivate_source(
        self,
        source_id: UUID,
        owner_id: UUID,
    ) -> UserDataSource | None:
        source = self._source_repository.find_by_id(source_id)
        if not source or source.owner_id != owner_id:
            return None

        previous_status = source.status
        deactivated_source = source.update_status(SourceStatus.INACTIVE)
        saved_source = self._source_repository.save(deactivated_source)
        self._publish_event(
            SourceStatusChangedEvent.from_source(
                saved_source,
                previous_status=previous_status,
            ),
        )
        return saved_source

    def record_ingestion_success(self, source_id: UUID) -> UserDataSource | None:
        return self._source_repository.record_ingestion(source_id)

    def update_quality_metrics(
        self,
        source_id: UUID,
        metrics: QualityMetrics,
    ) -> UserDataSource | None:
        return self._source_repository.update_quality_metrics(source_id, metrics)

    def get_sources_by_type(
        self,
        source_type: SourceType,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        return self._source_repository.find_by_type(source_type, skip, limit)

    def get_active_sources(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        return self._source_repository.find_active_sources(skip, limit)

    def search_sources(
        self,
        query: str,
        owner_id: UUID | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        return self._source_repository.search_by_name(query, owner_id, skip, limit)

    def get_available_templates(
        self,
        user_id: UUID | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[SourceTemplate]:
        template_repository = self._require_template_repository()
        return template_repository.find_available_for_user(user_id, skip, limit)

    def get_statistics(self) -> StatisticsResponse:
        stats = self._source_repository.get_statistics()
        return {
            "total_sources": stats["total_sources"],
            "status_counts": stats["status_counts"],
            "type_counts": stats["type_counts"],
            "average_quality_score": stats["average_quality_score"],
            "sources_with_quality_metrics": stats["sources_with_quality_metrics"],
        }

    def validate_source_configuration(  # noqa: C901 - validator is intentionally comprehensive
        self,
        source: UserDataSource,
    ) -> list[str]:
        errors = []

        plugin = self._plugin_registry.get(source.source_type)
        if plugin:
            try:
                plugin.validate_configuration(source.configuration)
            except ValueError as exc:  # pragma: no cover - defensive logging path
                errors.append(str(exc))

        # Basic validation
        if not source.name.strip():
            errors.append("Source name cannot be empty")

        name_max_len = 200
        if len(source.name) > name_max_len:
            errors.append("Source name cannot exceed 200 characters")

        # Type-specific validation
        if source.source_type == SourceType.API:
            if not source.configuration.url:
                errors.append("API sources require a URL")
            if (
                source.configuration.requests_per_minute
                and source.configuration.requests_per_minute < 1
            ):
                errors.append("Requests per minute must be at least 1")

        elif source.source_type == SourceType.FILE_UPLOAD:
            if not source.configuration.file_path and not hasattr(
                source.configuration,
                "uploaded_file",
            ):
                errors.append("File upload sources require a file")

        # Template validation
        if source.template_id:
            template_repository = self._require_template_repository()
            template = template_repository.find_by_id(source.template_id)
            if not template:
                errors.append(
                    f"Referenced template {source.template_id} does not exist",
                )
            elif not template.is_available(source.owner_id):
                errors.append(f"Template {source.template_id} is not available")

        return errors
