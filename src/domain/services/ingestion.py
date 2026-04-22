"""Shared contracts for ingestion scheduling and orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal, Protocol
from uuid import UUID  # noqa: TCH003

from src.type_definitions.common import JSONObject  # noqa: TC001

if TYPE_CHECKING:
    from src.domain.entities.source_sync_state import SourceSyncState
    from src.domain.repositories.source_record_ledger_repository import (
        SourceRecordLedgerRepository,
    )


IngestionProgressEventType = Literal[
    "ingestion_job_started",
    "query_resolved",
    "records_fetched",
    "source_documents_upserted",
    "resolver_warning",
    "kernel_ingestion_started",
    "kernel_ingestion_finished",
    "kernel_ingestion_record_started",
    "kernel_ingestion_record_finished",
    "kernel_ingestion_mapper_started",
    "kernel_ingestion_mapper_finished",
]


@dataclass(frozen=True)
class IngestionProgressUpdate:
    """Incremental progress emitted while a source ingestion run is active."""

    event_type: IngestionProgressEventType
    message: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    ingestion_job_id: UUID | None = None
    payload: JSONObject = field(default_factory=dict)


IngestionProgressCallback = Callable[[IngestionProgressUpdate], None]


@dataclass(frozen=True)
class IngestionRunContext:
    """Context passed by scheduler to source ingestion services."""

    ingestion_job_id: UUID
    source_sync_state: SourceSyncState
    query_signature: str
    pipeline_run_id: str | None = None
    source_record_ledger_repository: SourceRecordLedgerRepository | None = None
    progress_callback: IngestionProgressCallback | None = None


@dataclass(frozen=True)
class IngestionExtractionTarget:
    """Target record to enqueue for post-ingestion extraction."""

    source_record_id: str
    source_type: str
    raw_storage_key: str | None = None
    payload_ref: str | None = None
    publication_id: int | None = None
    pubmed_id: str | None = None
    metadata: JSONObject | None = None


class IngestionRunSummary(Protocol):
    """Protocol describing the summary returned by source ingestion services."""

    @property
    def source_id(self) -> UUID:
        """Source identifier for the ingestion run."""

    @property
    def fetched_records(self) -> int:
        """Number of raw records fetched from upstream."""

    @property
    def parsed_publications(self) -> int:
        """Number of publications parsed by the ingestion pipeline."""

    @property
    def created_publications(self) -> int:
        """Number of publication records created."""

    @property
    def updated_publications(self) -> int:
        """Number of publication records updated."""

    @property
    def extraction_targets(self) -> tuple[IngestionExtractionTarget, ...]:
        """Source records to enqueue for extraction."""

    @property
    def executed_query(self) -> str | None:
        """Source query string when available."""

    @property
    def query_signature(self) -> str | None:
        """Hash of normalized query/config used for this run."""

    @property
    def checkpoint_before(self) -> JSONObject | None:
        """Checkpoint payload before this run started."""

    @property
    def checkpoint_after(self) -> JSONObject | None:
        """Checkpoint payload after this run completed."""

    @property
    def checkpoint_kind(self) -> str | None:
        """Checkpoint mechanism used for this run (cursor/timestamp/etc)."""

    @property
    def new_records(self) -> int:
        """Number of new upstream records this run observed."""

    @property
    def updated_records(self) -> int:
        """Number of changed upstream records this run observed."""

    @property
    def unchanged_records(self) -> int:
        """Number of upstream records skipped as unchanged."""

    @property
    def skipped_records(self) -> int:
        """Number of skipped records for scheduling metrics."""
