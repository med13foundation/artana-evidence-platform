"""Domain contracts for PubMed ingestion orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID  # noqa: TCH003

from src.domain.entities.data_source_configs import PubMedQueryConfig  # noqa: TCH001
from src.domain.entities.source_sync_state import CheckpointKind  # noqa: TCH001
from src.domain.services.ingestion import IngestionExtractionTarget  # noqa: TCH001
from src.type_definitions.common import JSONObject, RawRecord  # noqa: TCH001


class PubMedGateway(Protocol):
    """Protocol describing infrastructure responsibilities for PubMed ingestion."""

    async def fetch_records(self, config: PubMedQueryConfig) -> list[RawRecord]:
        """Fetch raw PubMed records according to per-source configuration."""


@dataclass(frozen=True)
class PubMedQueryValidationResult:
    """Outcome of validating a PubMed query against the upstream API."""

    is_valid: bool
    api_feedback: str | None = None
    translated_query: str | None = None
    result_count: int | None = None


@runtime_checkable
class PubMedQueryValidationGateway(Protocol):
    """Optional protocol for validating source queries before execution."""

    async def validate_query(
        self,
        config: PubMedQueryConfig,
    ) -> PubMedQueryValidationResult:
        """Validate a PubMed query and return structured API feedback."""


@dataclass(frozen=True)
class PubMedGatewayFetchResult:
    """Gateway response including records and checkpoint cursor metadata."""

    records: list[RawRecord]
    fetched_records: int
    checkpoint_after: JSONObject | None = None
    checkpoint_kind: CheckpointKind = CheckpointKind.NONE


@runtime_checkable
class PubMedIncrementalGateway(Protocol):
    """Optional protocol for cursor-aware PubMed fetching."""

    async def fetch_records_incremental(
        self,
        config: PubMedQueryConfig,
        *,
        checkpoint: JSONObject | None = None,
    ) -> PubMedGatewayFetchResult:
        """Fetch PubMed records using source checkpoint semantics."""


@dataclass(frozen=True)
class PubMedIngestionSummary:
    """Aggregate statistics about a PubMed ingestion run."""

    source_id: UUID
    fetched_records: int
    parsed_publications: int
    created_publications: int
    updated_publications: int
    extraction_targets: tuple[IngestionExtractionTarget, ...] = ()
    executed_query: str | None = None
    query_generation_run_id: str | None = None
    query_generation_model: str | None = None
    query_generation_decision: str | None = None
    query_generation_confidence: float | None = None
    query_generation_execution_mode: str | None = None
    query_generation_fallback_reason: str | None = None
    query_generation_downstream_fetched_records: int | None = None
    query_generation_downstream_processed_records: int | None = None
    query_signature: str | None = None
    checkpoint_before: JSONObject | None = None
    checkpoint_after: JSONObject | None = None
    checkpoint_kind: str | None = None
    new_records: int = 0
    updated_records: int = 0
    unchanged_records: int = 0
    skipped_records: int = 0
    ingestion_job_id: UUID | None = None
