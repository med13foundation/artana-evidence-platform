"""SQLAlchemy repository for source sync checkpoint state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import delete, desc, select

from src.domain.entities.source_sync_state import SourceSyncState  # noqa: TC001
from src.domain.entities.user_data_source import SourceType  # noqa: TC001
from src.domain.repositories.source_sync_state_repository import (
    SourceSyncStateRepository,
)
from src.infrastructure.mappers.source_sync_state_mapper import SourceSyncStateMapper
from src.models.database.source_sync_state import SourceSyncStateModel

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session


class SqlAlchemySourceSyncStateRepository(SourceSyncStateRepository):
    """Persist and query per-source sync checkpoint state."""

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

    def get_by_source(self, source_id: UUID) -> SourceSyncState | None:
        model = self.session.get(SourceSyncStateModel, str(source_id))
        return SourceSyncStateMapper.to_domain(model) if model else None

    def list_by_source_type(
        self,
        source_type: SourceType,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SourceSyncState]:
        stmt = (
            select(SourceSyncStateModel)
            .where(SourceSyncStateModel.source_type == source_type.value)
            .order_by(desc(SourceSyncStateModel.updated_at))
            .offset(offset)
            .limit(limit)
        )
        models = self.session.execute(stmt).scalars().all()
        return [SourceSyncStateMapper.to_domain(model) for model in models]

    def upsert(self, state: SourceSyncState) -> SourceSyncState:
        model = SourceSyncStateMapper.to_model(state)
        merged = self.session.merge(model)
        self.session.commit()
        self.session.refresh(merged)
        return SourceSyncStateMapper.to_domain(merged)

    def delete_by_source(self, source_id: UUID) -> bool:
        stmt = delete(SourceSyncStateModel).where(
            SourceSyncStateModel.source_id == str(source_id),
        )
        result = self.session.execute(stmt)
        self.session.commit()
        return self._rowcount(result) > 0
