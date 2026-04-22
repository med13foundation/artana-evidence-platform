"""Domain entity for source-level ingestion lock leases."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field


class IngestionSourceLock(BaseModel):
    """Represents a lease-style source lock used for ingestion coordination."""

    model_config = ConfigDict(frozen=True)

    source_id: UUID
    lock_token: str = Field(..., min_length=1, max_length=64)
    lease_expires_at: datetime
    last_heartbeat_at: datetime
    acquired_by: str | None = Field(default=None, max_length=128)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def is_expired(self, *, as_of: datetime | None = None) -> bool:
        """Return True when the lock lease has expired."""
        reference = as_of or datetime.now(UTC)
        lease_expires_at = self.lease_expires_at
        if lease_expires_at.tzinfo is None:
            lease_expires_at = lease_expires_at.replace(tzinfo=UTC)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=UTC)
        return lease_expires_at <= reference


__all__ = ["IngestionSourceLock"]
