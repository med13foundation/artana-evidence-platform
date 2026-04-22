"""Mapper utilities for source sync state entities."""

from __future__ import annotations

from uuid import UUID

from src.domain.entities.source_sync_state import CheckpointKind, SourceSyncState
from src.domain.entities.user_data_source import SourceType
from src.models.database.source_sync_state import SourceSyncStateModel
from src.type_definitions.common import JSONObject  # noqa: TC001


class SourceSyncStateMapper:
    """Bidirectional mapper between sync state entities and SQLAlchemy models."""

    @staticmethod
    def to_domain(model: SourceSyncStateModel) -> SourceSyncState:
        payload: JSONObject = dict(model.checkpoint_payload or {})
        return SourceSyncState(
            source_id=UUID(model.source_id),
            source_type=SourceType(model.source_type),
            checkpoint_kind=CheckpointKind(model.checkpoint_kind),
            checkpoint_payload=payload,
            query_signature=model.query_signature,
            last_successful_job_id=(
                UUID(model.last_successful_job_id)
                if model.last_successful_job_id is not None
                else None
            ),
            last_successful_run_at=model.last_successful_run_at,
            last_attempted_run_at=model.last_attempted_run_at,
            upstream_etag=model.upstream_etag,
            upstream_last_modified=model.upstream_last_modified,
            schema_version=model.schema_version,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def to_model(entity: SourceSyncState) -> SourceSyncStateModel:
        return SourceSyncStateModel(
            source_id=str(entity.source_id),
            source_type=entity.source_type.value,
            checkpoint_kind=entity.checkpoint_kind.value,
            checkpoint_payload=dict(entity.checkpoint_payload),
            query_signature=entity.query_signature,
            last_successful_job_id=(
                str(entity.last_successful_job_id)
                if entity.last_successful_job_id is not None
                else None
            ),
            last_successful_run_at=entity.last_successful_run_at,
            last_attempted_run_at=entity.last_attempted_run_at,
            upstream_etag=entity.upstream_etag,
            upstream_last_modified=entity.upstream_last_modified,
            schema_version=entity.schema_version,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
