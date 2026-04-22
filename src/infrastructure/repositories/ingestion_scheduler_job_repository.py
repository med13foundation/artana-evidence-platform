"""SQLAlchemy repository for durable scheduler job records."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from src.domain.entities.ingestion_scheduler_job import (
    IngestionSchedulerJob,  # noqa: TC001
)
from src.domain.repositories.ingestion_scheduler_job_repository import (
    IngestionSchedulerJobRepository,
)
from src.infrastructure.mappers.ingestion_scheduler_job_mapper import (
    IngestionSchedulerJobMapper,
)
from src.models.database.ingestion_scheduler_job import IngestionSchedulerJobModel

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from sqlalchemy.orm import Session


class SqlAlchemyIngestionSchedulerJobRepository(IngestionSchedulerJobRepository):
    """Persist and query scheduler job rows."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            message = "Session not provided"
            raise ValueError(message)
        return self._session

    @staticmethod
    def _rowcount(result: object) -> int:
        count = getattr(result, "rowcount", None)
        return int(count) if isinstance(count, int) else 0

    def get_by_job_id(self, job_id: str) -> IngestionSchedulerJob | None:
        model = self.session.get(IngestionSchedulerJobModel, job_id)
        return IngestionSchedulerJobMapper.to_domain(model) if model else None

    def get_by_source(self, source_id: UUID) -> IngestionSchedulerJob | None:
        stmt = (
            select(IngestionSchedulerJobModel)
            .where(IngestionSchedulerJobModel.source_id == str(source_id))
            .limit(1)
        )
        model = self.session.execute(stmt).scalars().first()
        return IngestionSchedulerJobMapper.to_domain(model) if model else None

    def upsert(self, job: IngestionSchedulerJob) -> IngestionSchedulerJob:
        model = IngestionSchedulerJobMapper.to_model(job)
        merged = self.session.merge(model)
        self.session.commit()
        self.session.refresh(merged)
        return IngestionSchedulerJobMapper.to_domain(merged)

    def list_due(
        self,
        *,
        as_of: datetime,
        limit: int = 100,
    ) -> list[IngestionSchedulerJob]:
        stmt = (
            select(IngestionSchedulerJobModel)
            .where(IngestionSchedulerJobModel.is_enabled.is_(True))
            .where(IngestionSchedulerJobModel.next_run_at <= as_of)
            .order_by(IngestionSchedulerJobModel.next_run_at.asc())
            .limit(max(limit, 1))
        )
        models = self.session.execute(stmt).scalars().all()
        return [IngestionSchedulerJobMapper.to_domain(model) for model in models]

    def delete_by_job_id(self, job_id: str) -> bool:
        stmt = delete(IngestionSchedulerJobModel).where(
            IngestionSchedulerJobModel.job_id == job_id,
        )
        result = self.session.execute(stmt)
        self.session.commit()
        return self._rowcount(result) > 0

    def delete_by_source(self, source_id: UUID) -> bool:
        stmt = delete(IngestionSchedulerJobModel).where(
            IngestionSchedulerJobModel.source_id == str(source_id),
        )
        result = self.session.execute(stmt)
        self.session.commit()
        return self._rowcount(result) > 0
