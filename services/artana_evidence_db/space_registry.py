"""Service-local graph-space registry entity."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from artana_evidence_db.common_types import ResearchSpaceSettings
from pydantic import BaseModel, ConfigDict


class KernelSpaceRegistryEntry(BaseModel):
    """Graph-local representation of one tenant space."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    slug: str
    name: str
    description: str | None = None
    owner_id: UUID
    status: str
    settings: ResearchSpaceSettings
    sync_source: str | None = None
    sync_fingerprint: str | None = None
    source_updated_at: datetime | None = None
    last_synced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


__all__ = ["KernelSpaceRegistryEntry"]
