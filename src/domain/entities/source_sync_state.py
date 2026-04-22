"""Domain entity for per-source incremental sync checkpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field

from src.domain.entities.user_data_source import SourceType  # noqa: TC001
from src.type_definitions.common import JSONObject  # noqa: TC001

UpdatePayload = dict[str, object]


def _empty_checkpoint_payload() -> JSONObject:
    return {}


class CheckpointKind(str, Enum):
    """Supported upstream checkpoint mechanisms."""

    NONE = "none"
    CURSOR = "cursor"
    TIMESTAMP = "timestamp"
    EXTERNAL_ID = "external_id"


class SourceSyncState(BaseModel):
    """Sync state for a single source to support incremental ingestion."""

    model_config = ConfigDict(frozen=True)

    source_id: UUID
    source_type: SourceType
    checkpoint_kind: CheckpointKind = Field(default=CheckpointKind.NONE)
    checkpoint_payload: JSONObject = Field(default_factory=_empty_checkpoint_payload)
    query_signature: str | None = None
    last_successful_job_id: UUID | None = None
    last_successful_run_at: datetime | None = None
    last_attempted_run_at: datetime | None = None
    upstream_etag: str | None = None
    upstream_last_modified: datetime | None = None
    schema_version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def mark_attempt(
        self,
        *,
        attempted_at: datetime | None = None,
    ) -> SourceSyncState:
        """Return an updated state recording an ingestion attempt."""
        now = attempted_at or datetime.now(UTC)
        update_payload: UpdatePayload = {
            "last_attempted_run_at": now,
            "updated_at": now,
        }
        return self.model_copy(
            update=update_payload,
        )

    def mark_success(
        self,
        *,
        successful_job_id: UUID | None,
        checkpoint_payload: JSONObject,
        successful_at: datetime | None = None,
    ) -> SourceSyncState:
        """Return an updated state after a successful ingestion run."""
        now = successful_at or datetime.now(UTC)
        update_payload: UpdatePayload = {
            "last_successful_job_id": successful_job_id,
            "last_successful_run_at": now,
            "last_attempted_run_at": now,
            "checkpoint_payload": checkpoint_payload,
            "updated_at": now,
        }
        return self.model_copy(
            update=update_payload,
        )


__all__ = ["CheckpointKind", "SourceSyncState"]
