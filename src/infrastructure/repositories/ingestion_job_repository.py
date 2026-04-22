"""SQLAlchemy repository adapter for ingestion jobs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.repositories.ingestion_job_repository import (
    IngestionJobRepository,
)

from ._ingestion_job_repository_persistence_mixin import (
    SqlAlchemyIngestionJobRepositoryPersistenceMixin,
)
from ._ingestion_job_repository_pipeline_mixin import (
    SqlAlchemyIngestionJobRepositoryPipelineMixin,
)
from ._ingestion_job_repository_query_mixin import (
    SqlAlchemyIngestionJobRepositoryQueryMixin,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class SqlAlchemyIngestionJobRepository(
    SqlAlchemyIngestionJobRepositoryQueryMixin,
    SqlAlchemyIngestionJobRepositoryPipelineMixin,
    SqlAlchemyIngestionJobRepositoryPersistenceMixin,
    IngestionJobRepository,
):
    """Domain-facing repository implementation for ingestion jobs."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            message = "Session not provided"
            raise ValueError(message)
        return self._session
