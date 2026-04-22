"""Domain contracts for MARRVEL ingestion orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID  # noqa: TCH003

from src.domain.entities.data_source_configs import MarrvelQueryConfig  # noqa: TCH001
from src.domain.entities.source_sync_state import CheckpointKind  # noqa: TCH001
from src.domain.services.ingestion import IngestionExtractionTarget  # noqa: TCH001
from src.type_definitions.common import JSONObject, RawRecord  # noqa: TCH001


class MarrvelGateway(Protocol):
    """Protocol describing infrastructure responsibilities for MARRVEL ingestion."""

    async def fetch_records(self, config: MarrvelQueryConfig) -> list[RawRecord]:
        """Fetch raw MARRVEL records according to per-source configuration."""


@dataclass(frozen=True)
class MarrvelGatewayFetchResult:
    """Gateway response including records and checkpoint cursor metadata."""

    records: list[RawRecord]
    fetched_records: int
    checkpoint_after: JSONObject | None = None
    checkpoint_kind: CheckpointKind = CheckpointKind.NONE


@runtime_checkable
class MarrvelIncrementalGateway(Protocol):
    """Optional protocol for checkpoint-aware MARRVEL fetching."""

    async def fetch_records_incremental(
        self,
        config: MarrvelQueryConfig,
        *,
        checkpoint: JSONObject | None = None,
    ) -> MarrvelGatewayFetchResult:
        """Fetch MARRVEL records using source checkpoint semantics."""


@dataclass(frozen=True)
class MarrvelIngestionSummary:
    """Aggregate statistics about a MARRVEL ingestion run."""

    source_id: UUID
    fetched_records: int
    parsed_publications: int
    created_publications: int
    updated_publications: int
    extraction_targets: tuple[IngestionExtractionTarget, ...] = ()
    executed_query: str | None = None
    query_signature: str | None = None
    checkpoint_before: JSONObject | None = None
    checkpoint_after: JSONObject | None = None
    checkpoint_kind: str | None = None
    new_records: int = 0
    updated_records: int = 0
    unchanged_records: int = 0
    skipped_records: int = 0
    ingestion_job_id: UUID | None = None
