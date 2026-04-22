"""SQLAlchemy repository for source record idempotency ledgers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select

from src.domain.entities.source_record_ledger import (  # noqa: TC001
    SourceRecordLedgerEntry,
)
from src.domain.repositories.source_record_ledger_repository import (
    SourceRecordLedgerRepository,
)
from src.infrastructure.mappers.source_record_ledger_mapper import (
    SourceRecordLedgerMapper,
)
from src.models.database.source_record_ledger import SourceRecordLedgerModel

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from sqlalchemy.orm import Session


class SqlAlchemySourceRecordLedgerRepository(SourceRecordLedgerRepository):
    """Persist and query source record fingerprint ledgers."""

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

    def get_entry(
        self,
        *,
        source_id: UUID,
        external_record_id: str,
    ) -> SourceRecordLedgerEntry | None:
        model = self.session.get(
            SourceRecordLedgerModel,
            (str(source_id), external_record_id),
        )
        return SourceRecordLedgerMapper.to_domain(model) if model else None

    def get_entries_by_external_ids(
        self,
        *,
        source_id: UUID,
        external_record_ids: list[str],
    ) -> dict[str, SourceRecordLedgerEntry]:
        if not external_record_ids:
            return {}
        stmt = select(SourceRecordLedgerModel).where(
            SourceRecordLedgerModel.source_id == str(source_id),
            SourceRecordLedgerModel.external_record_id.in_(external_record_ids),
        )
        models = self.session.execute(stmt).scalars().all()
        return {
            model.external_record_id: SourceRecordLedgerMapper.to_domain(model)
            for model in models
        }

    def upsert_entries(
        self,
        entries: list[SourceRecordLedgerEntry],
    ) -> list[SourceRecordLedgerEntry]:
        if not entries:
            return []
        merged_models: list[SourceRecordLedgerModel] = []
        for entry in entries:
            model = SourceRecordLedgerMapper.to_model(entry)
            merged = self.session.merge(model)
            merged_models.append(merged)
        self.session.commit()
        for merged in merged_models:
            self.session.refresh(merged)
        return [SourceRecordLedgerMapper.to_domain(model) for model in merged_models]

    def delete_by_source(self, source_id: UUID) -> int:
        stmt = delete(SourceRecordLedgerModel).where(
            SourceRecordLedgerModel.source_id == str(source_id),
        )
        result = self.session.execute(stmt)
        self.session.commit()
        return self._rowcount(result)

    def count_for_source(self, source_id: UUID) -> int:
        stmt = select(func.count()).where(
            SourceRecordLedgerModel.source_id == str(source_id),
        )
        return int(self.session.execute(stmt).scalar_one())

    def delete_entries_older_than(
        self,
        *,
        cutoff: datetime,
        limit: int = 1000,
    ) -> int:
        effective_limit = max(limit, 1)
        candidate_stmt = (
            select(
                SourceRecordLedgerModel.source_id,
                SourceRecordLedgerModel.external_record_id,
            )
            .where(SourceRecordLedgerModel.last_processed_at < cutoff)
            .order_by(SourceRecordLedgerModel.last_processed_at.asc())
            .limit(effective_limit)
        )
        candidate_rows = self.session.execute(candidate_stmt).all()
        if not candidate_rows:
            return 0
        deleted_rows = 0
        for source_id, external_record_id in candidate_rows:
            delete_stmt = delete(SourceRecordLedgerModel).where(
                SourceRecordLedgerModel.source_id == source_id,
                SourceRecordLedgerModel.external_record_id == external_record_id,
            )
            result = self.session.execute(delete_stmt)
            deleted_rows += self._rowcount(result)
        self.session.commit()
        return deleted_rows
