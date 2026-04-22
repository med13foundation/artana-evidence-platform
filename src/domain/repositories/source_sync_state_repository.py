"""Repository interface for per-source incremental sync state."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID  # noqa: TC003

from src.domain.entities.source_sync_state import SourceSyncState  # noqa: TC001
from src.domain.entities.user_data_source import SourceType  # noqa: TC001


class SourceSyncStateRepository(ABC):
    """Abstract persistence contract for source sync checkpoints."""

    @abstractmethod
    def get_by_source(self, source_id: UUID) -> SourceSyncState | None:
        """Fetch checkpoint state for a source."""

    @abstractmethod
    def list_by_source_type(
        self,
        source_type: SourceType,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SourceSyncState]:
        """List checkpoint states for a source type."""

    @abstractmethod
    def upsert(self, state: SourceSyncState) -> SourceSyncState:
        """Create or update sync state for a source."""

    @abstractmethod
    def delete_by_source(self, source_id: UUID) -> bool:
        """Delete sync state for a source if present."""
