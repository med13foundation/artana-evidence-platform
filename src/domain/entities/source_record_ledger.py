"""Domain entity for source-level idempotency ledger entries."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field

UpdatePayload = dict[str, object]


class SourceRecordLedgerEntry(BaseModel):
    """Tracks a source record fingerprint to skip unchanged payloads."""

    model_config = ConfigDict(frozen=True)

    source_id: UUID
    external_record_id: str = Field(..., min_length=1, max_length=255)
    payload_hash: str = Field(..., min_length=1, max_length=128)
    source_updated_at: datetime | None = None
    first_seen_job_id: UUID | None = None
    last_seen_job_id: UUID | None = None
    last_changed_job_id: UUID | None = None
    last_processed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def mark_seen(
        self,
        *,
        payload_hash: str,
        seen_job_id: UUID | None,
        source_updated_at: datetime | None = None,
        seen_at: datetime | None = None,
    ) -> SourceRecordLedgerEntry:
        """Return an updated ledger entry for a newly seen upstream record."""
        now = seen_at or datetime.now(UTC)
        changed = payload_hash != self.payload_hash
        update_payload: UpdatePayload = {
            "payload_hash": payload_hash,
            "source_updated_at": source_updated_at,
            "last_seen_job_id": seen_job_id,
            "last_changed_job_id": (
                seen_job_id if changed else self.last_changed_job_id
            ),
            "last_processed_at": now,
            "updated_at": now,
        }
        return self.model_copy(
            update=update_payload,
        )


__all__ = ["SourceRecordLedgerEntry"]
