"""
Extraction queue repository interface.

Defines persistence operations for publication extraction queue items.
"""

from __future__ import annotations

from abc import abstractmethod
from uuid import UUID

from src.domain.entities.extraction_queue_item import ExtractionQueueItem
from src.domain.repositories.base import Repository
from src.type_definitions.common import ExtractionQueueUpdate, JSONObject


class ExtractionQueueRepository(
    Repository[ExtractionQueueItem, UUID, ExtractionQueueUpdate],
):
    """Domain repository interface for extraction queue items."""

    @abstractmethod
    def enqueue_many(
        self,
        items: list[ExtractionQueueItem],
    ) -> list[ExtractionQueueItem]:
        """Insert multiple queue items, skipping duplicates."""

    @abstractmethod
    def list_pending(
        self,
        limit: int,
        *,
        source_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
    ) -> list[ExtractionQueueItem]:
        """List pending queue items."""

    @abstractmethod
    def claim_pending(
        self,
        limit: int,
        *,
        source_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
    ) -> list[ExtractionQueueItem]:
        """Atomically claim pending items and mark them as processing."""

    @abstractmethod
    def mark_completed(
        self,
        item_id: UUID,
        *,
        metadata: JSONObject | None = None,
    ) -> ExtractionQueueItem:
        """Mark a queue item as completed."""

    @abstractmethod
    def mark_failed(
        self,
        item_id: UUID,
        *,
        error_message: str,
    ) -> ExtractionQueueItem:
        """Mark a queue item as failed."""


__all__ = ["ExtractionQueueRepository"]
