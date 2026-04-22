"""Typed helper models for PubMed ingestion orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.entities import data_source_configs
    from src.domain.entities.source_record_ledger import SourceRecordLedgerEntry
    from src.type_definitions.common import JSONObject


@dataclass(frozen=True)
class LedgerDedupOutcome:
    """Result of applying record-ledger deduplication to fetched records."""

    filtered_records: list[JSONObject]
    entries_to_upsert: list[SourceRecordLedgerEntry]
    new_records: int
    updated_records: int
    unchanged_records: int


@dataclass(frozen=True)
class QueryResolution:
    """Resolved query configuration and AI generation metadata."""

    config: data_source_configs.PubMedQueryConfig
    query_generation_decision: str
    query_generation_confidence: float
    query_generation_run_id: str | None
    query_generation_execution_mode: str
    query_generation_fallback_reason: str | None


__all__ = ["LedgerDedupOutcome", "QueryResolution"]
