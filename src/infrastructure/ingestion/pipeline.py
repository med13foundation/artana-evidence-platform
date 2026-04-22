"""
Orchestrator for the kernel ingestion pipeline.
"""

from __future__ import annotations

import logging
from time import perf_counter
from typing import TYPE_CHECKING

from src.domain.services.domain_context_resolver import DomainContextResolver
from src.domain.services.ingestion import IngestionProgressUpdate
from src.infrastructure.ingestion.interfaces import ProgressAwareMapper
from src.infrastructure.ingestion.types import IngestResult, RawRecord

if TYPE_CHECKING:
    from collections.abc import Callable

    from artana_evidence_db.kernel_services import (
        KernelObservationService,
    )

    from src.domain.services.ingestion import IngestionProgressCallback
    from src.infrastructure.ingestion.interfaces import (
        Mapper,
        Normalizer,
        Resolver,
        Validator,
    )
    from src.infrastructure.ingestion.provenance.tracker import ProvenanceTracker
    from src.infrastructure.ingestion.types import MappedObservation
    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """
    Orchestrates the ingestion process: Map -> Normalize -> Resolve -> Validate.
    """

    def __init__(  # noqa: PLR0913
        self,
        mapper: Mapper,
        normalizer: Normalizer,
        resolver: Resolver,
        validator: Validator,
        observation_service: KernelObservationService,
        provenance_tracker: ProvenanceTracker,
        rollback_on_error: Callable[[], None] | None = None,
    ) -> None:
        self.mapper = mapper
        self.normalizer = normalizer
        self.resolver = resolver
        self.validator = validator
        self.observation_service = observation_service
        self.provenance_tracker = provenance_tracker
        self.rollback_on_error = rollback_on_error

    def run(  # noqa: C901
        self,
        records: list[RawRecord],
        research_space_id: str,
        *,
        progress_callback: IngestionProgressCallback | None = None,
    ) -> IngestResult:
        """
        Run the ingestion pipeline on a batch of records.

        Args:
            records: List of raw records to process.
            research_space_id: The research space ID to ingest data into.

        Returns:
            IngestResult summarizing the outcome.
        """
        result = IngestResult(success=True)

        total_records = len(records)
        for record_index, record in enumerate(records, start=1):
            record_started_at = perf_counter()
            self._emit_progress(
                progress_callback=progress_callback,
                update=IngestionProgressUpdate(
                    event_type="kernel_ingestion_record_started",
                    message=f"Kernel ingestion record {record_index} started.",
                    payload={
                        "record_index": record_index,
                        "total_records": total_records,
                        "source_record_id": record.source_id,
                    },
                ),
            )
            try:
                resolved_record = self._normalize_domain_context_metadata(record)

                # 0. Track Provenance (Source Level)
                # We create a provenance record for this source record
                provenance_id = self.provenance_tracker.track_ingestion(
                    research_space_id=research_space_id,
                    source_type="PIPELINE_INGESTION",  # or from record.metadata
                    source_ref=resolved_record.source_id,
                    raw_input=resolved_record.data,
                    # agent_model, mapping_method could be passed if available
                )

                # 1. Map
                mapped_observations = self._map_with_progress(
                    resolved_record,
                    progress_callback=progress_callback,
                )
                if not mapped_observations:
                    self._emit_record_finished(
                        progress_callback=progress_callback,
                        record=resolved_record,
                        record_index=record_index,
                        total_records=total_records,
                        record_started_at=record_started_at,
                        result=result,
                        mapped_observations_count=0,
                        validation_failures=0,
                        success=True,
                    )
                    continue

                # 2. Resolve subject entity once per source record.
                entity_type = resolved_record.metadata.get("entity_type")
                if not isinstance(entity_type, str) or not entity_type.strip():
                    result.errors.append("Missing entity_type")
                    self._emit_record_finished(
                        progress_callback=progress_callback,
                        record=resolved_record,
                        record_index=record_index,
                        total_records=total_records,
                        record_started_at=record_started_at,
                        result=result,
                        mapped_observations_count=len(mapped_observations),
                        validation_failures=0,
                        success=False,
                        error_message="Missing entity_type",
                    )
                    continue

                subject_anchor = mapped_observations[0].subject_anchor
                if not subject_anchor:
                    result.errors.append("Missing subject anchor")
                    self._emit_record_finished(
                        progress_callback=progress_callback,
                        record=resolved_record,
                        record_index=record_index,
                        total_records=total_records,
                        record_started_at=record_started_at,
                        result=result,
                        mapped_observations_count=len(mapped_observations),
                        validation_failures=0,
                        success=False,
                        error_message="Missing subject anchor",
                    )
                    continue

                resolved_entity = self.resolver.resolve(
                    anchor=subject_anchor,
                    entity_type=entity_type,
                    research_space_id=research_space_id,
                    source_record_id=resolved_record.source_id,
                    progress_callback=progress_callback,
                )
                if resolved_entity.created:
                    result.entities_created += 1
                if resolved_entity.id not in result.entity_ids_touched:
                    result.entity_ids_touched.append(resolved_entity.id)

                validation_failures = 0
                for observation in mapped_observations:
                    # 3. Normalize
                    normalized = self.normalizer.normalize(observation)

                    # 4. Validate
                    validated = self.validator.validate(normalized)
                    if validated is not None:
                        # 5. Persist
                        self.observation_service.record_observation_value(
                            research_space_id=research_space_id,
                            subject_id=resolved_entity.id,
                            variable_id=validated.variable_id,
                            value=validated.value,
                            unit=validated.unit,
                            observed_at=validated.observed_at,
                            provenance_id=provenance_id,
                        )
                        result.observations_created += 1
                    else:
                        validation_failures += 1
                        result.errors.append(
                            f"Validation failed for {normalized.variable_id}",
                        )
                self._emit_record_finished(
                    progress_callback=progress_callback,
                    record=resolved_record,
                    record_index=record_index,
                    total_records=total_records,
                    record_started_at=record_started_at,
                    result=result,
                    mapped_observations_count=len(mapped_observations),
                    validation_failures=validation_failures,
                    success=validation_failures == 0,
                )

            except Exception as e:
                logger.exception("Error processing record %s", record.source_id)
                if self.rollback_on_error is not None:
                    try:
                        self.rollback_on_error()
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "Error rolling back ingestion transaction for %s",
                            record.source_id,
                        )
                result.errors.append(f"Error processing {record.source_id}: {e!s}")
                result.success = False
                self._emit_record_finished(
                    progress_callback=progress_callback,
                    record=record,
                    record_index=record_index,
                    total_records=total_records,
                    record_started_at=record_started_at,
                    result=result,
                    mapped_observations_count=0,
                    validation_failures=0,
                    success=False,
                    error_message=str(e),
                )

        return result

    @staticmethod
    def _normalize_domain_context_metadata(record: RawRecord) -> RawRecord:
        """
        Canonicalize domain metadata without source-specific behavior.

        Source connectors are responsible for enforcing domain requirements.
        """
        explicit_domain_context = DomainContextResolver.from_metadata(record.metadata)
        if explicit_domain_context is None:
            return record

        raw_domain_context = record.metadata.get("domain_context")
        current_domain_context = DomainContextResolver.normalize(
            raw_domain_context if isinstance(raw_domain_context, str) else None,
        )
        if current_domain_context == explicit_domain_context:
            return record

        enriched_metadata = dict(record.metadata)
        enriched_metadata["domain_context"] = explicit_domain_context
        return RawRecord(
            source_id=record.source_id,
            data=record.data,
            metadata=enriched_metadata,
        )

    def _map_with_progress(
        self,
        record: RawRecord,
        *,
        progress_callback: IngestionProgressCallback | None = None,
    ) -> list[MappedObservation]:
        if isinstance(self.mapper, ProgressAwareMapper):
            return self.mapper.map_with_progress(
                record,
                progress_callback=progress_callback,
            )
        return self.mapper.map(record)

    @staticmethod
    def _emit_progress(
        *,
        progress_callback: IngestionProgressCallback | None,
        update: IngestionProgressUpdate,
    ) -> None:
        if progress_callback is None:
            return
        progress_callback(update)

    def _emit_record_finished(  # noqa: PLR0913
        self,
        *,
        progress_callback: IngestionProgressCallback | None,
        record: RawRecord,
        record_index: int,
        total_records: int,
        record_started_at: float,
        result: IngestResult,
        mapped_observations_count: int,
        validation_failures: int,
        success: bool,
        error_message: str | None = None,
    ) -> None:
        duration_ms = max(int((perf_counter() - record_started_at) * 1000), 0)
        payload: JSONObject = {
            "record_index": record_index,
            "total_records": total_records,
            "source_record_id": record.source_id,
            "duration_ms": duration_ms,
            "mapped_observations_count": mapped_observations_count,
            "validation_failures": validation_failures,
            "entities_created_total": result.entities_created,
            "observations_created_total": result.observations_created,
            "errors_total": len(result.errors),
            "success": success,
        }
        if error_message is not None:
            payload["error_message"] = error_message
        self._emit_progress(
            progress_callback=progress_callback,
            update=IngestionProgressUpdate(
                event_type="kernel_ingestion_record_finished",
                message=f"Kernel ingestion record {record_index} finished.",
                payload=payload,
            ),
        )
