"""
Hybrid mapper that combines multiple mapping strategies.
"""

from __future__ import annotations

from time import perf_counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.services.ingestion import IngestionProgressCallback
    from src.infrastructure.ingestion.interfaces import Mapper
    from src.infrastructure.ingestion.types import MappedObservation, RawRecord
    from src.type_definitions.common import JSONObject

from src.domain.services.ingestion import IngestionProgressUpdate
from src.infrastructure.ingestion.interfaces import (
    MapperRunMetricsProvider,
    ProgressAwareMapper,
)


class HybridMapper:
    """
    Hybrid mapper that chains multiple mapping strategies (e.g., Exact -> Vector -> LLM).
    """

    def __init__(self, mappers: list[Mapper]) -> None:
        self.mappers = mappers

    def map(self, record: RawRecord) -> list[MappedObservation]:
        return self.map_with_progress(record)

    def map_with_progress(
        self,
        record: RawRecord,
        *,
        progress_callback: IngestionProgressCallback | None = None,
    ) -> list[MappedObservation]:
        """
        Map a raw record using the configured mappers in sequence.

        Currently implements a simple strategy:
        1. Try the first mapper.
        2. If it produces results, return them.
        3. If not, try the next mapper.

        A more sophisticated strategy might merge results or use confidence scores.
        """
        for mapper in self.mappers:
            mapper_name = mapper.__class__.__name__
            self._emit_progress(
                progress_callback=progress_callback,
                update=IngestionProgressUpdate(
                    event_type="kernel_ingestion_mapper_started",
                    message=f"Mapper {mapper_name} started.",
                    payload={
                        "mapper_name": mapper_name,
                        "source_record_id": record.source_id,
                        "field_count": len(record.data),
                    },
                ),
            )
            mapper_started_at = perf_counter()
            observations = self._map_with_mapper(
                mapper,
                record,
                progress_callback=progress_callback,
            )
            duration_ms = max(
                int((perf_counter() - mapper_started_at) * 1000),
                0,
            )
            mapper_metrics = self._consume_mapper_metrics(mapper)
            message = self._build_mapper_finished_message(
                mapper_name,
                mapper_metrics,
            )
            payload: JSONObject = {
                "mapper_name": mapper_name,
                "source_record_id": record.source_id,
                "field_count": len(record.data),
                "matched_observations": len(observations),
                "selected": bool(observations),
                "duration_ms": duration_ms,
            }
            if mapper_metrics is not None:
                payload.update(mapper_metrics)
            self._emit_progress(
                progress_callback=progress_callback,
                update=IngestionProgressUpdate(
                    event_type="kernel_ingestion_mapper_finished",
                    message=message,
                    payload=payload,
                ),
            )
            if observations:
                return observations

        return []

    @staticmethod
    def _map_with_mapper(
        mapper: Mapper,
        record: RawRecord,
        *,
        progress_callback: IngestionProgressCallback | None,
    ) -> list[MappedObservation]:
        if isinstance(mapper, ProgressAwareMapper):
            return mapper.map_with_progress(
                record,
                progress_callback=progress_callback,
            )
        return mapper.map(record)

    @staticmethod
    def _consume_mapper_metrics(
        mapper: Mapper,
    ) -> JSONObject | None:
        if not isinstance(mapper, MapperRunMetricsProvider):
            return None
        metrics = mapper.consume_run_metrics()
        if metrics is None:
            return None
        return metrics

    @staticmethod
    def _build_mapper_finished_message(
        mapper_name: str,
        mapper_metrics: JSONObject | None,
    ) -> str:
        if mapper_metrics is None:
            return f"Mapper {mapper_name} finished."
        summary_message = mapper_metrics.get("summary_message")
        if not isinstance(summary_message, str) or not summary_message.strip():
            return f"Mapper {mapper_name} finished."
        return f"Mapper {mapper_name} finished. {summary_message.strip()}"

    @staticmethod
    def _emit_progress(
        *,
        progress_callback: IngestionProgressCallback | None,
        update: IngestionProgressUpdate,
    ) -> None:
        if progress_callback is None:
            return
        progress_callback(update)
