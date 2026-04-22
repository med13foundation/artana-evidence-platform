"""Scheduling helpers for source sync state and query signature management."""

# mypy: disable-error-code="misc"

from __future__ import annotations

import hashlib
import json
import logging
from typing import TYPE_CHECKING

from src.domain.entities import user_data_source
from src.domain.entities.source_sync_state import CheckpointKind, SourceSyncState
from src.domain.services.ingestion import IngestionRunContext, IngestionRunSummary

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.services.ingestion_scheduling_service import (
        IngestionSchedulingService,
    )
    from src.domain.services.ingestion import IngestionProgressCallback


logger = logging.getLogger(__name__)


class _IngestionSchedulingStateHelpers:
    """Helpers for checkpoint lifecycle and run context construction."""

    def _prepare_sync_state_for_attempt(
        self: IngestionSchedulingService,
        source: user_data_source.UserDataSource,
    ) -> SourceSyncState | None:
        repository = self._source_sync_state_repository
        if repository is None:
            return None

        query_signature = self._build_query_signature(source)
        default_checkpoint_kind = self._default_checkpoint_kind(source.source_type)
        existing = repository.get_by_source(source.id)
        if existing is None:
            existing = SourceSyncState(
                source_id=source.id,
                source_type=source.source_type,
                checkpoint_kind=default_checkpoint_kind,
                query_signature=query_signature,
            )
        elif (
            existing.checkpoint_kind == CheckpointKind.NONE
            and default_checkpoint_kind != CheckpointKind.NONE
        ):
            existing = existing.model_copy(
                update={"checkpoint_kind": default_checkpoint_kind},
            )
        if (
            existing.query_signature is not None
            and existing.query_signature != query_signature
        ):
            logger.warning(
                "Source query signature changed; resetting checkpoint payload",
                extra={
                    "source_id": str(source.id),
                    "source_type": source.source_type.value,
                    "previous_signature": existing.query_signature,
                    "new_signature": query_signature,
                },
            )
            existing = existing.model_copy(
                update={
                    "checkpoint_payload": {},
                    "checkpoint_kind": default_checkpoint_kind,
                },
            )
        attempted = existing.mark_attempt().model_copy(
            update={"query_signature": query_signature},
        )
        return repository.upsert(attempted)

    def _build_run_context(
        self: IngestionSchedulingService,
        *,
        source: user_data_source.UserDataSource,
        ingestion_job_id: UUID,
        sync_state: SourceSyncState | None,
        pipeline_run_id: str | None = None,
        progress_callback: IngestionProgressCallback | None = None,
    ) -> IngestionRunContext | None:
        if (
            self._source_sync_state_repository is None
            and self._source_record_ledger_repository is None
            and pipeline_run_id is None
            and progress_callback is None
        ):
            return None

        resolved_state = sync_state or SourceSyncState(
            source_id=source.id,
            source_type=source.source_type,
            query_signature=self._build_query_signature(source),
        )
        query_signature = resolved_state.query_signature or self._build_query_signature(
            source,
        )
        return IngestionRunContext(
            ingestion_job_id=ingestion_job_id,
            source_sync_state=resolved_state,
            query_signature=query_signature,
            pipeline_run_id=pipeline_run_id,
            source_record_ledger_repository=self._source_record_ledger_repository,
            progress_callback=progress_callback,
        )

    def _persist_sync_state_on_success(
        self: IngestionSchedulingService,
        *,
        sync_state: SourceSyncState | None,
        ingestion_job_id: UUID,
        summary: IngestionRunSummary,
    ) -> SourceSyncState | None:
        repository = self._source_sync_state_repository
        if repository is None or sync_state is None:
            return None

        checkpoint_after_raw = getattr(summary, "checkpoint_after", None)
        if isinstance(checkpoint_after_raw, dict):
            checkpoint_after = dict(checkpoint_after_raw)
        else:
            checkpoint_after = dict(sync_state.checkpoint_payload)

        updated = sync_state.mark_success(
            successful_job_id=ingestion_job_id,
            checkpoint_payload=checkpoint_after,
        )
        checkpoint_kind = self._resolve_checkpoint_kind(
            raw_value=getattr(summary, "checkpoint_kind", None),
            fallback=sync_state.checkpoint_kind,
        )
        query_signature = getattr(summary, "query_signature", None)
        update_payload: dict[str, object] = {"checkpoint_kind": checkpoint_kind}
        if isinstance(query_signature, str) and query_signature.strip():
            update_payload["query_signature"] = query_signature
        updated = updated.model_copy(update=update_payload)
        return repository.upsert(updated)

    @staticmethod
    def _resolve_checkpoint_kind(
        *,
        raw_value: object,
        fallback: CheckpointKind,
    ) -> CheckpointKind:
        if isinstance(raw_value, CheckpointKind):
            return raw_value
        if isinstance(raw_value, str):
            normalized = raw_value.strip().lower()
            for kind in CheckpointKind:
                if kind.value == normalized:
                    return kind
        return fallback

    @staticmethod
    def _default_checkpoint_kind(
        source_type: user_data_source.SourceType,
    ) -> CheckpointKind:
        if source_type in (
            user_data_source.SourceType.PUBMED,
            user_data_source.SourceType.CLINVAR,
        ):
            return CheckpointKind.CURSOR
        return CheckpointKind.NONE

    @staticmethod
    def _build_query_signature(
        source: user_data_source.UserDataSource,
    ) -> str:
        canonical_payload = json.dumps(
            {
                "source_type": source.source_type.value,
                "configuration": source.configuration.model_dump(mode="json"),
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
