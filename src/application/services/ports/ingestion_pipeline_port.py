"""Port interface for the kernel ingestion pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.domain.services.ingestion import IngestionProgressCallback
    from src.type_definitions.ingestion import IngestResult, RawRecord


class IngestionPipelinePort(Protocol):
    """Abstraction for running the kernel ingestion pipeline."""

    def run(
        self,
        records: list[RawRecord],
        research_space_id: str,
        *,
        progress_callback: IngestionProgressCallback | None = None,
    ) -> IngestResult:
        """Run ingestion for a batch of raw records into a research space."""


__all__ = ["IngestionPipelinePort"]
