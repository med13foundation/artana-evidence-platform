"""
Domain entity for publication extraction outputs.

Stores structured facts extracted from publications along with
traceability metadata and extraction context.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field

from src.type_definitions.common import ExtractionFact, JSONObject  # noqa: TC001


class ExtractionOutcome(StrEnum):
    """Outcome status for an extraction run."""

    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ExtractionTextSource(StrEnum):
    """Text source used for extraction."""

    TITLE_ABSTRACT = "title_abstract"
    TITLE = "title"
    ABSTRACT = "abstract"
    FULL_TEXT = "full_text"


class PublicationExtraction(BaseModel):
    """Represents extracted facts for a publication."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    publication_id: int | None = None
    pubmed_id: str | None = None
    source_id: UUID
    ingestion_job_id: UUID
    queue_item_id: UUID
    status: ExtractionOutcome
    extraction_version: int = 1
    processor_name: str
    processor_version: str | None = None
    text_source: ExtractionTextSource = Field(
        default=ExtractionTextSource.TITLE_ABSTRACT,
    )
    document_reference: str | None = None
    facts: list[ExtractionFact] = Field(default_factory=list)
    metadata: JSONObject = Field(default_factory=dict)
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


__all__ = [
    "ExtractionOutcome",
    "ExtractionTextSource",
    "PublicationExtraction",
]
