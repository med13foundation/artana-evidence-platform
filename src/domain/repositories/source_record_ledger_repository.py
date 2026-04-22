"""Repository interface for source record idempotency ledgers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime  # noqa: TC003
from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003

if TYPE_CHECKING:
    from src.domain.entities.source_record_ledger import SourceRecordLedgerEntry


class SourceRecordLedgerRepository(ABC):
    """Abstract persistence contract for source record fingerprint ledgers."""

    @abstractmethod
    def get_entry(
        self,
        *,
        source_id: UUID,
        external_record_id: str,
    ) -> SourceRecordLedgerEntry | None:
        """Fetch a single ledger entry by source and upstream record id."""

    @abstractmethod
    def get_entries_by_external_ids(
        self,
        *,
        source_id: UUID,
        external_record_ids: list[str],
    ) -> dict[str, SourceRecordLedgerEntry]:
        """Return ledger entries indexed by external record id."""

    @abstractmethod
    def upsert_entries(
        self,
        entries: list[SourceRecordLedgerEntry],
    ) -> list[SourceRecordLedgerEntry]:
        """Create or update one or more ledger entries."""

    @abstractmethod
    def delete_by_source(self, source_id: UUID) -> int:
        """Delete all ledger entries for a source and return affected rows."""

    @abstractmethod
    def count_for_source(self, source_id: UUID) -> int:
        """Count ledger entries for a source."""

    @abstractmethod
    def delete_entries_older_than(
        self,
        *,
        cutoff: datetime,
        limit: int = 1000,
    ) -> int:
        """Delete stale ledger entries older than cutoff and return deleted rows."""
