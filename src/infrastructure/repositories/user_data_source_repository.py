"""
SQLAlchemy implementation of User Data Source repository for Artana Resource Library.

Data access layer for user-managed data sources with specialized queries
and efficient database operations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import and_, delete, desc, func, select, update

from src.domain.entities.user_data_source import (
    IngestionSchedule,
    QualityMetrics,
    SourceConfiguration,
    SourceStatus,
    SourceType,
    UserDataSource,
)
from src.domain.repositories.user_data_source_repository import (
    UserDataSourceRepository as UserDataSourceRepositoryInterface,
)
from src.infrastructure.mappers.user_data_source_mapper import UserDataSourceMapper
from src.models.database import UserDataSourceModel

if TYPE_CHECKING:  # pragma: no cover - typing only
    from uuid import UUID

    from sqlalchemy.orm import Session

    from src.type_definitions.common import StatisticsResponse


class SqlAlchemyUserDataSourceRepository(UserDataSourceRepositoryInterface):
    """
    Repository for UserDataSource entities with specialized data source queries.

    Provides data access operations for user-managed data sources including
    ownership-based filtering, status queries, and quality metric tracking.
    """

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        """Get the current database session."""
        if self._session is None:
            message = "Session not provided"
            raise ValueError(message)
        return self._session

    @staticmethod
    def _rowcount(result: object) -> int:
        """Safely extract rowcount information from SQLAlchemy results."""
        count = getattr(result, "rowcount", None)
        return int(count) if isinstance(count, int) else 0

    def save(self, source: UserDataSource) -> UserDataSource:
        """Save a user data source to the repository."""
        model = UserDataSourceMapper.to_model(source)
        model = self.session.merge(model)
        self.session.commit()
        self.session.refresh(model)
        return UserDataSourceMapper.to_domain(model)

    def find_by_id(self, source_id: UUID) -> UserDataSource | None:
        """Find a user data source by its ID."""
        stmt = select(UserDataSourceModel).where(
            UserDataSourceModel.id == str(source_id),
        )
        result = self.session.execute(stmt).scalar_one_or_none()
        return UserDataSourceMapper.to_domain(result) if result else None

    def find_by_owner(
        self,
        owner_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        """Find all data sources owned by a specific user."""
        stmt = (
            select(UserDataSourceModel)
            .where(UserDataSourceModel.owner_id == str(owner_id))
            .order_by(desc(UserDataSourceModel.updated_at))
            .offset(skip)
            .limit(limit)
        )
        results = self.session.execute(stmt).scalars().all()
        return [UserDataSourceMapper.to_domain(model) for model in results]

    def find_by_type(
        self,
        source_type: SourceType,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        """Find all data sources of a specific type."""
        stmt = (
            select(UserDataSourceModel)
            .where(UserDataSourceModel.source_type == source_type.value)
            .order_by(desc(UserDataSourceModel.updated_at))
            .offset(skip)
            .limit(limit)
        )
        results = self.session.execute(stmt).scalars().all()
        return [UserDataSourceMapper.to_domain(model) for model in results]

    def find_by_status(
        self,
        status: SourceStatus,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        """Find all data sources with a specific status."""
        stmt = (
            select(UserDataSourceModel)
            .where(UserDataSourceModel.status == status.value)
            .order_by(desc(UserDataSourceModel.updated_at))
            .offset(skip)
            .limit(limit)
        )
        results = self.session.execute(stmt).scalars().all()
        return [UserDataSourceMapper.to_domain(model) for model in results]

    def find_active_sources(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        """Find all active data sources."""
        stmt = (
            select(UserDataSourceModel)
            .where(UserDataSourceModel.status == SourceStatus.ACTIVE.value)
            .order_by(desc(UserDataSourceModel.last_ingested_at).nulls_last())
            .offset(skip)
            .limit(limit)
        )
        results = self.session.execute(stmt).scalars().all()
        return [UserDataSourceMapper.to_domain(model) for model in results]

    def find_by_tag(
        self,
        tag: str,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        """Find data sources that have a specific tag."""
        # Using JSON containment query for tags array
        stmt = (
            select(UserDataSourceModel)
            .where(func.json_contains(UserDataSourceModel.tags, f'["{tag}"]'))
            .order_by(desc(UserDataSourceModel.updated_at))
            .offset(skip)
            .limit(limit)
        )
        results = self.session.execute(stmt).scalars().all()
        return [UserDataSourceMapper.to_domain(model) for model in results]

    def find_by_research_space(
        self,
        research_space_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        """Find all data sources in a specific research space."""
        stmt = (
            select(UserDataSourceModel)
            .where(UserDataSourceModel.research_space_id == str(research_space_id))
            .order_by(desc(UserDataSourceModel.updated_at))
            .offset(skip)
            .limit(limit)
        )
        results = self.session.execute(stmt).scalars().all()
        return [UserDataSourceMapper.to_domain(model) for model in results]

    def search_by_name(
        self,
        query: str,
        owner_id: UUID | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        """Search data sources by name using fuzzy matching."""
        search_pattern = f"%{query}%"
        stmt = select(UserDataSourceModel).where(
            UserDataSourceModel.name.ilike(search_pattern),
        )

        if owner_id:
            stmt = stmt.where(UserDataSourceModel.owner_id == str(owner_id))

        stmt = (
            stmt.order_by(desc(UserDataSourceModel.updated_at))
            .offset(skip)
            .limit(limit)
        )

        results = self.session.execute(stmt).scalars().all()
        return [UserDataSourceMapper.to_domain(model) for model in results]

    def update_status(
        self,
        source_id: UUID,
        status: SourceStatus,
    ) -> UserDataSource | None:
        """Update the status of a data source."""
        stmt = (
            update(UserDataSourceModel)
            .where(UserDataSourceModel.id == str(source_id))
            .values(status=status.value)
            .returning(UserDataSourceModel)
        )
        result = self.session.execute(stmt).scalar_one_or_none()
        if result:
            self.session.commit()
            return UserDataSourceMapper.to_domain(result)
        return None

    def update_quality_metrics(
        self,
        source_id: UUID,
        metrics: QualityMetrics,
    ) -> UserDataSource | None:
        """Update the quality metrics of a data source."""
        stmt = (
            update(UserDataSourceModel)
            .where(UserDataSourceModel.id == str(source_id))
            .values(quality_metrics=metrics.model_dump())
            .returning(UserDataSourceModel)
        )
        result = self.session.execute(stmt).scalar_one_or_none()
        if result:
            self.session.commit()
            return UserDataSourceMapper.to_domain(result)
        return None

    def update_configuration(
        self,
        source_id: UUID,
        config: SourceConfiguration,
    ) -> UserDataSource | None:
        """Update the configuration of a data source."""
        stmt = (
            update(UserDataSourceModel)
            .where(UserDataSourceModel.id == str(source_id))
            .values(configuration=config.model_dump())
            .returning(UserDataSourceModel)
        )
        result = self.session.execute(stmt).scalar_one_or_none()
        if result:
            self.session.commit()
            return UserDataSourceMapper.to_domain(result)
        return None

    def update_ingestion_schedule(
        self,
        source_id: UUID,
        schedule: IngestionSchedule,
    ) -> UserDataSource | None:
        """Update the ingestion schedule of a data source."""
        stmt = (
            update(UserDataSourceModel)
            .where(UserDataSourceModel.id == str(source_id))
            .values(ingestion_schedule=schedule.model_dump(mode="json"))
            .returning(UserDataSourceModel)
        )
        result = self.session.execute(stmt).scalar_one_or_none()
        if result:
            self.session.commit()
            return UserDataSourceMapper.to_domain(result)
        return None

    def record_ingestion(self, source_id: UUID) -> UserDataSource | None:
        """Record that ingestion has occurred for a data source."""
        now = datetime.now(UTC)
        stmt = (
            update(UserDataSourceModel)
            .where(UserDataSourceModel.id == str(source_id))
            .values(last_ingested_at=now.isoformat(timespec="seconds"))
            .returning(UserDataSourceModel)
        )
        result = self.session.execute(stmt).scalar_one_or_none()
        if result:
            self.session.commit()
            return UserDataSourceMapper.to_domain(result)
        return None

    def delete(self, source_id: UUID) -> bool:
        """Delete a data source from the repository."""
        stmt = delete(UserDataSourceModel).where(
            UserDataSourceModel.id == str(source_id),
        )
        result = self.session.execute(stmt)
        self.session.commit()
        affected = self._rowcount(result)
        return affected > 0

    def count_by_owner(self, owner_id: UUID) -> int:
        """Count the number of data sources owned by a user."""
        stmt = select(func.count()).where(UserDataSourceModel.owner_id == str(owner_id))
        return self.session.execute(stmt).scalar_one()

    def count_by_status(self, status: SourceStatus) -> int:
        """Count the number of data sources with a specific status."""
        stmt = select(func.count()).where(UserDataSourceModel.status == status.value)
        return self.session.execute(stmt).scalar_one()

    def count_by_type(self, source_type: SourceType) -> int:
        """Count the number of data sources of a specific type."""
        stmt = select(func.count()).where(
            UserDataSourceModel.source_type == source_type.value,
        )
        return self.session.execute(stmt).scalar_one()

    def count_by_research_space(self, research_space_id: UUID) -> int:
        """Count the number of data sources in a specific research space."""
        stmt = select(func.count()).where(
            UserDataSourceModel.research_space_id == str(research_space_id),
        )
        return self.session.execute(stmt).scalar_one()

    def exists(self, source_id: UUID) -> bool:
        """Check if a data source exists."""
        stmt = select(func.count()).where(UserDataSourceModel.id == str(source_id))
        return self.session.execute(stmt).scalar_one() > 0

    def get_statistics(self) -> StatisticsResponse:
        """Get overall statistics about data sources."""
        # Get counts by status
        status_counts: dict[str, int] = {}
        for status in SourceStatus:
            count = self.count_by_status(status)
            status_counts[status.value] = count

        # Get counts by type
        type_counts: dict[str, int] = {}
        for source_type in SourceType:
            count = self.count_by_type(source_type)
            type_counts[source_type.value] = count

        # Get quality statistics
        stmt = select(
            func.avg(
                func.json_extract(
                    UserDataSourceModel.quality_metrics,
                    "$.overall_score",
                ),
            ),
            func.count(),
        ).where(
            and_(
                UserDataSourceModel.quality_metrics.isnot(None),
                func.json_extract(
                    UserDataSourceModel.quality_metrics,
                    "$.overall_score",
                ).isnot(None),
            ),
        )
        avg_quality = None
        total_with_quality = 0
        quality_row = self.session.execute(stmt).first()
        if quality_row is not None:
            avg_quality, total_with_quality = quality_row

        # Get total count
        total_count = self.session.execute(
            select(func.count()).select_from(UserDataSourceModel),
        ).scalar_one()

        stats: StatisticsResponse = {
            "total_sources": total_count,
            "status_counts": status_counts,
            "type_counts": type_counts,
            "average_quality_score": (
                float(avg_quality) if avg_quality is not None else None
            ),
            "sources_with_quality_metrics": int(total_with_quality),
        }
        return stats
