"""Port interface for publication extraction processors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

from src.type_definitions.common import (  # noqa: TC001
    ExtractionFact,
    ExtractionTextSource,
    JSONObject,
)

if TYPE_CHECKING:
    from src.domain.entities.extraction_queue_item import ExtractionQueueItem
    from src.domain.entities.publication import Publication


ExtractionOutcome = Literal["completed", "failed", "skipped"]


@dataclass(frozen=True)
class ExtractionTextPayload:
    """Payload describing the text provided to an extraction processor."""

    text: str
    text_source: ExtractionTextSource
    document_reference: str | None = None


@dataclass(frozen=True)
class ExtractionProcessorResult:
    status: ExtractionOutcome
    facts: list[ExtractionFact]
    metadata: JSONObject
    processor_name: str
    text_source: ExtractionTextSource
    processor_version: str | None = None
    document_reference: str | None = None
    error_message: str | None = None


class ExtractionProcessorPort(Protocol):
    """Port for extracting structured facts from publications."""

    def extract_publication(
        self,
        *,
        queue_item: ExtractionQueueItem,
        publication: Publication | None,
        text_payload: ExtractionTextPayload | None = None,
    ) -> ExtractionProcessorResult:
        """Extract facts for a single publication."""


__all__ = [
    "ExtractionOutcome",
    "ExtractionProcessorPort",
    "ExtractionProcessorResult",
    "ExtractionTextPayload",
]
