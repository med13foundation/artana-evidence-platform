"""SQLAlchemy repository for source-level ingestion lock leases."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert

from src.domain.entities.ingestion_source_lock import IngestionSourceLock  # noqa: TC001
from src.domain.repositories.ingestion_source_lock_repository import (
    IngestionSourceLockRepository,
)
from src.infrastructure.mappers.ingestion_source_lock_mapper import (
    IngestionSourceLockMapper,
)
from src.models.database.ingestion_source_lock import IngestionSourceLockModel

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session


class SqlAlchemyIngestionSourceLockRepository(IngestionSourceLockRepository):
    """Persist and query source lock leases."""

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

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _is_postgres_backend(self) -> bool:
        bind = self.session.bind
        if bind is None:
            return False
        dialect_name = bind.dialect.name
        return isinstance(dialect_name, str) and dialect_name.lower() == "postgresql"

    def get_by_source(self, source_id: UUID) -> IngestionSourceLock | None:
        model = self.session.get(IngestionSourceLockModel, str(source_id))
        return IngestionSourceLockMapper.to_domain(model) if model else None

    def try_acquire(
        self,
        *,
        source_id: UUID,
        lock_token: str,
        lease_expires_at: datetime,
        heartbeat_at: datetime,
        acquired_by: str | None = None,
    ) -> IngestionSourceLock | None:
        source_id_text = str(source_id)
        lease_expires_at_utc = self._normalize_datetime(lease_expires_at)
        heartbeat_at_utc = self._normalize_datetime(heartbeat_at)

        if self._is_postgres_backend():
            now = heartbeat_at_utc
            stmt = (
                postgresql_insert(IngestionSourceLockModel)
                .values(
                    source_id=source_id_text,
                    lock_token=lock_token,
                    lease_expires_at=lease_expires_at_utc,
                    last_heartbeat_at=heartbeat_at_utc,
                    acquired_by=acquired_by,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_update(
                    index_elements=[IngestionSourceLockModel.source_id],
                    set_={
                        "lock_token": lock_token,
                        "lease_expires_at": lease_expires_at_utc,
                        "last_heartbeat_at": heartbeat_at_utc,
                        "acquired_by": acquired_by,
                        "updated_at": now,
                    },
                    where=or_(
                        IngestionSourceLockModel.lease_expires_at <= heartbeat_at_utc,
                        IngestionSourceLockModel.lock_token == lock_token,
                    ),
                )
            )
            result = self.session.execute(stmt)
            self.session.commit()
            if self._rowcount(result) <= 0:
                return None
            acquired = self.get_by_source(source_id)
            if acquired is None or acquired.lock_token != lock_token:
                return None
            return acquired

        model = self.session.get(IngestionSourceLockModel, source_id_text)
        if model is None:
            model = IngestionSourceLockModel(
                source_id=source_id_text,
                lock_token=lock_token,
                lease_expires_at=lease_expires_at_utc,
                last_heartbeat_at=heartbeat_at_utc,
                acquired_by=acquired_by,
            )
            self.session.add(model)
            self.session.commit()
            self.session.refresh(model)
            return IngestionSourceLockMapper.to_domain(model)

        model_lease_expires_at = self._normalize_datetime(model.lease_expires_at)
        can_takeover = model_lease_expires_at <= heartbeat_at_utc
        same_owner = model.lock_token == lock_token
        if not (can_takeover or same_owner):
            return None

        model.lock_token = lock_token
        model.lease_expires_at = lease_expires_at_utc
        model.last_heartbeat_at = heartbeat_at_utc
        model.acquired_by = acquired_by
        self.session.commit()
        self.session.refresh(model)
        return IngestionSourceLockMapper.to_domain(model)

    def refresh_lease(
        self,
        *,
        source_id: UUID,
        lock_token: str,
        lease_expires_at: datetime,
        heartbeat_at: datetime,
    ) -> IngestionSourceLock | None:
        stmt = (
            update(IngestionSourceLockModel)
            .where(IngestionSourceLockModel.source_id == str(source_id))
            .where(IngestionSourceLockModel.lock_token == lock_token)
            .values(
                lease_expires_at=self._normalize_datetime(lease_expires_at),
                last_heartbeat_at=self._normalize_datetime(heartbeat_at),
                updated_at=self._normalize_datetime(heartbeat_at),
            )
        )
        result = self.session.execute(stmt)
        self.session.commit()
        if self._rowcount(result) <= 0:
            return None
        refreshed = self.get_by_source(source_id)
        if refreshed is None or refreshed.lock_token != lock_token:
            return None
        return refreshed

    def release(
        self,
        *,
        source_id: UUID,
        lock_token: str,
    ) -> bool:
        stmt = (
            delete(IngestionSourceLockModel)
            .where(IngestionSourceLockModel.source_id == str(source_id))
            .where(IngestionSourceLockModel.lock_token == lock_token)
        )
        result = self.session.execute(stmt)
        self.session.commit()
        return self._rowcount(result) > 0

    def upsert(self, lock: IngestionSourceLock) -> IngestionSourceLock:
        model = IngestionSourceLockMapper.to_model(lock)
        merged = self.session.merge(model)
        self.session.commit()
        self.session.refresh(merged)
        return IngestionSourceLockMapper.to_domain(merged)

    def list_expired(
        self,
        *,
        as_of: datetime,
        limit: int = 100,
    ) -> list[IngestionSourceLock]:
        stmt = (
            select(IngestionSourceLockModel)
            .where(IngestionSourceLockModel.lease_expires_at <= as_of)
            .order_by(IngestionSourceLockModel.lease_expires_at.asc())
            .limit(max(limit, 1))
        )
        models = self.session.execute(stmt).scalars().all()
        return [IngestionSourceLockMapper.to_domain(model) for model in models]

    def delete_by_source(self, source_id: UUID) -> bool:
        stmt = delete(IngestionSourceLockModel).where(
            IngestionSourceLockModel.source_id == str(source_id),
        )
        result = self.session.execute(stmt)
        self.session.commit()
        return self._rowcount(result) > 0

    def delete_expired(
        self,
        *,
        as_of: datetime,
        limit: int = 1000,
    ) -> int:
        effective_limit = max(limit, 1)
        candidate_stmt = (
            select(IngestionSourceLockModel.source_id)
            .where(IngestionSourceLockModel.lease_expires_at <= as_of)
            .order_by(IngestionSourceLockModel.lease_expires_at.asc())
            .limit(effective_limit)
        )
        candidate_ids = [row[0] for row in self.session.execute(candidate_stmt).all()]
        if not candidate_ids:
            return 0

        deleted_rows = 0
        for source_id in candidate_ids:
            delete_stmt = delete(IngestionSourceLockModel).where(
                IngestionSourceLockModel.source_id == source_id,
            )
            result = self.session.execute(delete_stmt)
            deleted_rows += self._rowcount(result)
        self.session.commit()
        return deleted_rows
