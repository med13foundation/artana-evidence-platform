"""
Mapper for UserDataSource entities and database models.

Provides bidirectional mapping between domain entities and database models
for the Data Sources module.
"""

from datetime import UTC, datetime
from uuid import UUID

from src.domain.entities.user_data_source import (
    IngestionSchedule,
    QualityMetrics,
    SourceConfiguration,
    SourceStatus,
    SourceType,
    UserDataSource,
)
from src.models.database.user_data_source import (
    SourceStatusEnum,
    SourceTypeEnum,
    UserDataSourceModel,
)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = value
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=UTC)
    return normalized.astimezone(UTC).isoformat(timespec="seconds")


class UserDataSourceMapper:
    """
    Bidirectional mapper between UserDataSource domain entities and database models.

    Handles conversion between domain objects and database representations,
    ensuring type safety and data integrity.
    """

    @staticmethod
    def to_domain(model: UserDataSourceModel) -> UserDataSource:
        """
        Convert a database model to a domain entity.

        Args:
            model: The UserDataSourceModel to convert

        Returns:
            The corresponding UserDataSource domain entity
        """
        source_type_raw = (
            model.source_type.value
            if isinstance(model.source_type, SourceTypeEnum)
            else str(model.source_type)
        )
        status_raw = (
            model.status.value
            if isinstance(model.status, SourceStatusEnum)
            else str(model.status)
        )

        return UserDataSource(
            id=UUID(str(model.id)),
            owner_id=UUID(str(model.owner_id)),
            research_space_id=(
                UUID(str(model.research_space_id))
                if model.research_space_id is not None
                else None
            ),
            name=model.name,
            description=model.description,
            source_type=SourceType(source_type_raw),
            template_id=UUID(str(model.template_id)) if model.template_id else None,
            configuration=SourceConfiguration.model_validate(model.configuration or {}),
            status=SourceStatus(status_raw),
            ingestion_schedule=IngestionSchedule.model_validate(
                model.ingestion_schedule or {},
            ),
            quality_metrics=QualityMetrics.model_validate(model.quality_metrics or {}),
            created_at=model.created_at,
            updated_at=model.updated_at,
            last_ingested_at=_parse_datetime(model.last_ingested_at),
            tags=model.tags or [],
            version=model.version,
        )

    @staticmethod
    def to_model(entity: UserDataSource) -> UserDataSourceModel:
        """
        Convert a domain entity to a database model.

        Args:
            entity: The UserDataSource entity to convert

        Returns:
            The corresponding UserDataSourceModel
        """
        return UserDataSourceModel(
            id=str(entity.id),
            owner_id=str(entity.owner_id),
            research_space_id=(
                str(entity.research_space_id)
                if entity.research_space_id is not None
                else None
            ),
            name=entity.name,
            description=entity.description,
            source_type=SourceTypeEnum(entity.source_type.value),
            template_id=str(entity.template_id) if entity.template_id else None,
            configuration=entity.configuration.model_dump(mode="json"),
            status=SourceStatusEnum(entity.status.value),
            ingestion_schedule=entity.ingestion_schedule.model_dump(mode="json"),
            quality_metrics=entity.quality_metrics.model_dump(mode="json"),
            last_ingested_at=_format_datetime(entity.last_ingested_at),
            tags=list(entity.tags),
            version=entity.version,
        )
