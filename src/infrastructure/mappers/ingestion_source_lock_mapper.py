"""Mapper utilities for ingestion source lock entities."""

from __future__ import annotations

from uuid import UUID

from src.domain.entities.ingestion_source_lock import IngestionSourceLock
from src.models.database.ingestion_source_lock import IngestionSourceLockModel


class IngestionSourceLockMapper:
    """Bidirectional mapper for source lock lease rows."""

    @staticmethod
    def to_domain(model: IngestionSourceLockModel) -> IngestionSourceLock:
        return IngestionSourceLock(
            source_id=UUID(model.source_id),
            lock_token=model.lock_token,
            lease_expires_at=model.lease_expires_at,
            last_heartbeat_at=model.last_heartbeat_at,
            acquired_by=model.acquired_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def to_model(entity: IngestionSourceLock) -> IngestionSourceLockModel:
        return IngestionSourceLockModel(
            source_id=str(entity.source_id),
            lock_token=entity.lock_token,
            lease_expires_at=entity.lease_expires_at,
            last_heartbeat_at=entity.last_heartbeat_at,
            acquired_by=entity.acquired_by,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
