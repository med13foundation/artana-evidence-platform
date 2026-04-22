"""
Domain entity for publication extraction queue items.

Tracks extraction status for PubMed publications and provides
state transition helpers for immediate post-ingestion extraction.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field

from src.type_definitions.common import JSONObject  # noqa: TC001

UpdatePayload = dict[str, object]


class ExtractionStatus(StrEnum):
    """Lifecycle status for a publication extraction task."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ExtractionQueueItem(BaseModel):
    """Represents a queued extraction task for a publication."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    publication_id: int | None = None
    pubmed_id: str | None = None
    source_type: str = "pubmed"
    source_record_id: str = "unknown"
    raw_storage_key: str | None = None
    payload_ref: str | None = None
    source_id: UUID
    ingestion_job_id: UUID
    status: ExtractionStatus = Field(default=ExtractionStatus.PENDING)
    attempts: int = 0
    last_error: str | None = None
    extraction_version: int = 1
    metadata: JSONObject = Field(default_factory=dict)
    queued_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def start_processing(self) -> ExtractionQueueItem:
        """Mark the item as processing and increment attempts."""
        now = datetime.now(UTC)
        update_payload: UpdatePayload = {
            "status": ExtractionStatus.PROCESSING,
            "attempts": self.attempts + 1,
            "started_at": now,
            "updated_at": now,
        }
        return self.model_copy(
            update=update_payload,
        )

    def mark_completed(
        self,
        *,
        metadata: JSONObject | None = None,
    ) -> ExtractionQueueItem:
        """Mark the item as completed."""
        now = datetime.now(UTC)
        merged_metadata: JSONObject = dict(self.metadata)
        if metadata:
            merged_metadata.update(metadata)
        update_payload: UpdatePayload = {
            "status": ExtractionStatus.COMPLETED,
            "completed_at": now,
            "updated_at": now,
            "metadata": merged_metadata,
            "last_error": None,
        }
        return self.model_copy(
            update=update_payload,
        )

    def mark_failed(self, error_message: str) -> ExtractionQueueItem:
        """Mark the item as failed with the provided error message."""
        now = datetime.now(UTC)
        update_payload: UpdatePayload = {
            "status": ExtractionStatus.FAILED,
            "completed_at": now,
            "updated_at": now,
            "last_error": error_message,
        }
        return self.model_copy(
            update=update_payload,
        )


__all__ = ["ExtractionQueueItem", "ExtractionStatus"]
