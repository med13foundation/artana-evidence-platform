"""Repository interface for source-level ingestion lock leases."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime  # noqa: TC003
from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003

if TYPE_CHECKING:
    from src.domain.entities.ingestion_source_lock import IngestionSourceLock


class IngestionSourceLockRepository(ABC):
    """Abstract persistence contract for source lock leases."""

    @abstractmethod
    def get_by_source(self, source_id: UUID) -> IngestionSourceLock | None:
        """Fetch source lock state for one source if present."""

    @abstractmethod
    def try_acquire(
        self,
        *,
        source_id: UUID,
        lock_token: str,
        lease_expires_at: datetime,
        heartbeat_at: datetime,
        acquired_by: str | None = None,
    ) -> IngestionSourceLock | None:
        """Atomically acquire lock or take over when existing lease is expired."""

    @abstractmethod
    def refresh_lease(
        self,
        *,
        source_id: UUID,
        lock_token: str,
        lease_expires_at: datetime,
        heartbeat_at: datetime,
    ) -> IngestionSourceLock | None:
        """Refresh lease for an already acquired lock token."""

    @abstractmethod
    def release(
        self,
        *,
        source_id: UUID,
        lock_token: str,
    ) -> bool:
        """Release lock only when token ownership matches."""

    @abstractmethod
    def upsert(self, lock: IngestionSourceLock) -> IngestionSourceLock:
        """Create or update lock state for administrative workflows."""

    @abstractmethod
    def list_expired(
        self,
        *,
        as_of: datetime,
        limit: int = 100,
    ) -> list[IngestionSourceLock]:
        """List source lock leases that have expired by the given timestamp."""

    @abstractmethod
    def delete_by_source(self, source_id: UUID) -> bool:
        """Delete lock state for one source."""

    @abstractmethod
    def delete_expired(
        self,
        *,
        as_of: datetime,
        limit: int = 1000,
    ) -> int:
        """Delete expired locks and return affected rows."""
