"""Text payload and batch summary helpers for extraction runner orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.application.services.ports.extraction_processor_port import (
    ExtractionTextPayload,
)

if TYPE_CHECKING:
    from src.domain.entities import ExtractionQueueItem


@dataclass(frozen=True)
class ExtractionBatchSummary:
    """Execution summary for one extraction batch."""

    processed: int = 0
    completed: int = 0
    skipped: int = 0
    failed: int = 0


def resolve_document_reference(item: ExtractionQueueItem) -> str | None:
    if item.payload_ref:
        return item.payload_ref
    if item.raw_storage_key:
        return item.raw_storage_key
    document_reference_value = item.metadata.get("document_reference")
    if isinstance(document_reference_value, str):
        return document_reference_value
    return None


def build_payload_from_segments(
    *,
    title: str,
    abstract: str,
    full_text: str,
    document_reference: str | None,
) -> ExtractionTextPayload | None:
    if full_text:
        return ExtractionTextPayload(
            text=full_text,
            text_source="full_text",
            document_reference=document_reference,
        )
    if title and abstract:
        return ExtractionTextPayload(
            text=f"{title} {abstract}",
            text_source="title_abstract",
            document_reference=document_reference,
        )
    if title:
        return ExtractionTextPayload(
            text=title,
            text_source="title",
            document_reference=document_reference,
        )
    if abstract:
        return ExtractionTextPayload(
            text=abstract,
            text_source="abstract",
            document_reference=document_reference,
        )
    return None


def coerce_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, int | float):
        return str(value)
    return ""
