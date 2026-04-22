"""Shared types for Tier-2 content-enrichment service and helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID


@dataclass(frozen=True)
class ContentEnrichmentDocumentOutcome:
    document_id: UUID
    status: Literal["enriched", "skipped", "failed"]
    execution_mode: Literal["ai", "deterministic"]
    reason: str
    acquisition_method: str | None = None
    content_storage_key: str | None = None
    content_length_chars: int = 0
    run_id: str | None = None
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContentEnrichmentRunSummary:
    requested: int
    processed: int
    enriched: int
    skipped: int
    failed: int
    ai_runs: int
    deterministic_runs: int
    errors: tuple[str, ...]
    started_at: datetime
    completed_at: datetime


__all__ = [
    "ContentEnrichmentDocumentOutcome",
    "ContentEnrichmentRunSummary",
]
