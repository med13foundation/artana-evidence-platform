"""
Domain models for describing asynchronous discovery search jobs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field

from src.domain.entities.data_discovery_parameters import (
    AdvancedQueryParameters,  # noqa: TC001
)
from src.domain.entities.discovery_preset import DiscoveryProvider  # noqa: TC001
from src.type_definitions.common import JSONObject  # noqa: TC001


class DiscoverySearchStatus(StrEnum):
    """Lifecycle status for a discovery search job."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class DiscoverySearchJob(BaseModel):
    """Represents a persisted PubMed or connector search run."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    owner_id: UUID
    session_id: UUID | None = None
    provider: DiscoveryProvider
    status: DiscoverySearchStatus = Field(default=DiscoverySearchStatus.QUEUED)
    query_preview: str = Field(..., description="Human-readable query string")
    parameters: AdvancedQueryParameters
    total_results: int = Field(default=0, ge=0)
    result_metadata: JSONObject = Field(default_factory=dict)
    error_message: str | None = None
    storage_key: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


__all__ = ["DiscoverySearchJob", "DiscoverySearchStatus"]
