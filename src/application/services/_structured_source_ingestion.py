"""Shared ingestion helpers for structured non-publication source records."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from src.domain.entities import source_document, source_record_ledger
from src.domain.services.ingestion import IngestionExtractionTarget
from src.type_definitions.ingestion import RawRecord

from ._structured_source_ingestion_support import (
    StructuredSourceGateway,
    StructuredSourceIngestionConfig,
    StructuredSourceIngestionSummary,
    checkpoint_payload,
    compute_payload_hash,
    extract_source_updated_at,
    source_type_value,
    to_json_object,
    to_json_value,
)

if TYPE_CHECKING:

    from src.application.services.ports.ingestion_pipeline_port import (
        IngestionPipelinePort,
    )
    from src.domain.entities.user_data_source import UserDataSource
    from src.domain.repositories.source_document_repository import (
        SourceDocumentRepository,
    )
    from src.domain.services.ingestion import (
        IngestionProgressCallback,
        IngestionProgressUpdate,
        IngestionRunContext,
    )
    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _LedgerDedupOutcome:
    """Result of source-record ledger filtering."""

    filtered_records: list[JSONObject]
    entries_to_upsert: list[source_record_ledger.SourceRecordLedgerEntry]
    new_records: int
    updated_records: int
    unchanged_records: int


class StructuredSourceIngestionService:
    """Base service for scheduled structured source ingestion."""

    def __init__(
        self,
        *,
        gateway: StructuredSourceGateway,
        pipeline: IngestionPipelinePort | None = None,
        source_document_repository: SourceDocumentRepository | None = None,
        config: StructuredSourceIngestionConfig,
    ) -> None:
        self._gateway = gateway
        self._pipeline = pipeline
        self._source_document_repository = source_document_repository
        self._config = config

    async def ingest(
        self,
        source: UserDataSource,
        *,
        context: IngestionRunContext | None = None,
    ) -> StructuredSourceIngestionSummary:
        """Run one scheduled ingestion cycle for a structured source."""
        self._assert_source_type(source)
        metadata = self._source_metadata(source)
        query = self._resolve_query(source)
        max_results = self._resolve_max_results(metadata)
        checkpoint_before = (
            dict(context.source_sync_state.checkpoint_payload)
            if context is not None
            else None
        )
        query_signature = (
            context.query_signature
            if context is not None and context.query_signature.strip()
            else self._build_query_signature(metadata=metadata)
        )
        pipeline_run_id = (
            context.pipeline_run_id
            if context is not None
            and isinstance(context.pipeline_run_id, str)
            and context.pipeline_run_id.strip()
            else None
        )

        fetch_result = self._gateway.fetch_records(
            query=query,
            max_results=max_results,
        )
        records = [to_json_object(record) for record in fetch_result.records]
        dedup_outcome = self._build_ledger_dedup_outcome(
            source=source,
            records=records,
            context=context,
        )
        filtered_records = dedup_outcome.filtered_records
        self._upsert_source_documents(
            source=source,
            context=context,
            records=records,
            pipeline_run_id=pipeline_run_id,
        )

        observations_created = 0
        if self._pipeline is not None and source.research_space_id is not None:
            pipeline_result = self._pipeline.run(
                self._to_pipeline_records(
                    filtered_records,
                    original_source_id=str(source.id),
                ),
                research_space_id=str(source.research_space_id),
                progress_callback=self._build_pipeline_progress_callback(context),
            )
            observations_created = pipeline_result.observations_created
        elif self._pipeline is not None and source.research_space_id is None:
            logger.warning(
                "%s source %s has no research_space_id; skipping kernel pipeline",
                self._config.source_label,
                source.id,
            )

        if (
            context is not None
            and context.source_record_ledger_repository is not None
            and dedup_outcome.entries_to_upsert
        ):
            context.source_record_ledger_repository.upsert_entries(
                dedup_outcome.entries_to_upsert,
            )

        return StructuredSourceIngestionSummary(
            source_id=source.id,
            ingestion_job_id=context.ingestion_job_id if context else None,
            fetched_records=fetch_result.fetched_records,
            parsed_publications=len(filtered_records),
            created_publications=observations_created,
            updated_publications=0,
            extraction_targets=self._build_extraction_targets(
                filtered_records,
                pipeline_run_id=pipeline_run_id,
            ),
            executed_query=query or None,
            query_signature=query_signature,
            checkpoint_before=checkpoint_before,
            checkpoint_after=checkpoint_payload(fetch_result.checkpoint_after),
            checkpoint_kind=fetch_result.checkpoint_kind,
            new_records=dedup_outcome.new_records,
            updated_records=dedup_outcome.updated_records,
            unchanged_records=dedup_outcome.unchanged_records,
            skipped_records=dedup_outcome.unchanged_records,
            observations_created=observations_created,
        )

    def _assert_source_type(self, source: UserDataSource) -> None:
        source_type = source_type_value(source.source_type)
        if source_type != self._config.source_type.value:
            msg = (
                f"Expected source_type={self._config.source_type.value}, "
                f"got {source_type}"
            )
            raise ValueError(msg)

    @staticmethod
    def _source_metadata(source: UserDataSource) -> JSONObject:
        metadata = dict(source.configuration.metadata or {})
        if isinstance(source.configuration.query, str) and source.configuration.query:
            metadata.setdefault("query", source.configuration.query)
        return {str(key): to_json_value(value) for key, value in metadata.items()}

    def _resolve_query(self, source: UserDataSource) -> str:
        metadata = self._source_metadata(source)
        for key in self._config.query_keys:
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, int | float):
                return str(value)
        source_name = getattr(source, "name", None)
        if isinstance(source_name, str) and source_name.strip():
            return source_name.strip()
        return ""

    def _resolve_max_results(self, metadata: JSONObject) -> int:
        raw_value = metadata.get("max_results")
        if isinstance(raw_value, int | float):
            return max(1, int(raw_value))
        if isinstance(raw_value, str):
            try:
                return max(1, int(raw_value))
            except ValueError:
                return self._config.default_max_results
        return self._config.default_max_results

    @staticmethod
    def _build_pipeline_progress_callback(
        context: IngestionRunContext | None,
    ) -> IngestionProgressCallback | None:
        if context is None or context.progress_callback is None:
            return None
        progress_callback = context.progress_callback

        def _forward(update: IngestionProgressUpdate) -> None:
            progress_callback(
                replace(
                    update,
                    ingestion_job_id=update.ingestion_job_id
                    or context.ingestion_job_id,
                ),
            )

        return _forward

    def _to_pipeline_records(
        self,
        records: list[JSONObject],
        *,
        original_source_id: str,
    ) -> list[RawRecord]:
        raw_records: list[RawRecord] = []
        for record in records:
            payload = to_json_object(record)
            raw_records.append(
                RawRecord(
                    source_id=self._extract_pipeline_record_id(payload),
                    data=payload,
                    metadata={
                        "original_source_id": original_source_id,
                        "type": self._config.source_type.value,
                        "entity_type": self._config.entity_type,
                    },
                ),
            )
        return raw_records

    def _build_extraction_targets(
        self,
        records: list[JSONObject],
        *,
        pipeline_run_id: str | None,
    ) -> tuple[IngestionExtractionTarget, ...]:
        targets: list[IngestionExtractionTarget] = []
        seen_source_record_ids: set[str] = set()
        for record in records:
            source_record_id = self._extract_external_record_id(record)
            if source_record_id in seen_source_record_ids:
                continue
            seen_source_record_ids.add(source_record_id)
            metadata_payload: JSONObject = {
                "raw_record": to_json_object(record),
                "source_record_id": source_record_id,
                "source_type": self._config.source_type.value,
            }
            if isinstance(pipeline_run_id, str) and pipeline_run_id.strip():
                metadata_payload["pipeline_run_id"] = pipeline_run_id.strip()
            targets.append(
                IngestionExtractionTarget(
                    source_record_id=source_record_id,
                    source_type=self._config.source_type.value,
                    metadata=metadata_payload,
                ),
            )
        return tuple(targets)

    def _build_ledger_dedup_outcome(
        self,
        *,
        source: UserDataSource,
        records: list[JSONObject],
        context: IngestionRunContext | None,
    ) -> _LedgerDedupOutcome:
        if context is None or context.source_record_ledger_repository is None:
            return _LedgerDedupOutcome(
                filtered_records=records,
                entries_to_upsert=[],
                new_records=len(records),
                updated_records=0,
                unchanged_records=0,
            )

        ledger_repository = context.source_record_ledger_repository
        record_pairs = [
            (
                record,
                self._extract_external_record_id(record),
                compute_payload_hash(record),
            )
            for record in records
        ]
        external_ids = [external_id for _, external_id, _ in record_pairs]
        existing_by_external_id = ledger_repository.get_entries_by_external_ids(
            source_id=source.id,
            external_record_ids=list(dict.fromkeys(external_ids)),
        )

        now = datetime.now(UTC)
        current_entries: dict[str, source_record_ledger.SourceRecordLedgerEntry] = dict(
            existing_by_external_id,
        )
        filtered_records: list[JSONObject] = []
        entries_to_upsert: list[source_record_ledger.SourceRecordLedgerEntry] = []
        new_records = 0
        updated_records = 0
        unchanged_records = 0

        for record, external_id, payload_hash in record_pairs:
            existing_entry = current_entries.get(external_id)
            if existing_entry is None:
                new_records += 1
                filtered_records.append(record)
                new_entry = source_record_ledger.SourceRecordLedgerEntry(
                    source_id=source.id,
                    external_record_id=external_id,
                    payload_hash=payload_hash,
                    source_updated_at=extract_source_updated_at(record),
                    first_seen_job_id=context.ingestion_job_id,
                    last_seen_job_id=context.ingestion_job_id,
                    last_changed_job_id=context.ingestion_job_id,
                    last_processed_at=now,
                    created_at=now,
                    updated_at=now,
                )
                entries_to_upsert.append(new_entry)
                current_entries[external_id] = new_entry
                continue

            updated_entry = existing_entry.mark_seen(
                payload_hash=payload_hash,
                seen_job_id=context.ingestion_job_id,
                source_updated_at=extract_source_updated_at(record),
                seen_at=now,
            )
            entries_to_upsert.append(updated_entry)
            current_entries[external_id] = updated_entry
            if existing_entry.payload_hash == payload_hash:
                unchanged_records += 1
                continue
            updated_records += 1
            filtered_records.append(record)

        return _LedgerDedupOutcome(
            filtered_records=filtered_records,
            entries_to_upsert=entries_to_upsert,
            new_records=new_records,
            updated_records=updated_records,
            unchanged_records=unchanged_records,
        )

    def _upsert_source_documents(
        self,
        *,
        source: UserDataSource,
        context: IngestionRunContext | None,
        records: list[JSONObject],
        pipeline_run_id: str | None,
    ) -> None:
        if self._source_document_repository is None or not records:
            return

        seen_external_ids: set[str] = set()
        documents: list[source_document.SourceDocument] = []
        now = datetime.now(UTC)
        for record in records:
            external_record_id = self._extract_external_record_id(record)
            if external_record_id in seen_external_ids:
                continue
            seen_external_ids.add(external_record_id)
            metadata_payload: JSONObject = {"raw_record": to_json_object(record)}
            if isinstance(pipeline_run_id, str) and pipeline_run_id.strip():
                metadata_payload["pipeline_run_id"] = pipeline_run_id.strip()
            serialized = json.dumps(
                record,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
            documents.append(
                source_document.SourceDocument(
                    id=uuid4(),
                    research_space_id=source.research_space_id,
                    source_id=source.id,
                    ingestion_job_id=context.ingestion_job_id if context else None,
                    external_record_id=external_record_id,
                    source_type=self._config.source_type,
                    document_format=source_document.DocumentFormat.JSON,
                    content_hash=compute_payload_hash(record),
                    content_length_chars=len(serialized),
                    enrichment_status=source_document.EnrichmentStatus.PENDING,
                    extraction_status=(
                        source_document.DocumentExtractionStatus.PENDING
                    ),
                    metadata=metadata_payload,
                    created_at=now,
                    updated_at=now,
                ),
            )
        if documents:
            self._source_document_repository.upsert_many(documents)

    def _extract_external_record_id(self, record: JSONObject) -> str:
        for key in self._config.id_keys:
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                return f"{self._config.source_type.value}:{key}:{value.strip()}"
            if isinstance(value, int):
                return f"{self._config.source_type.value}:{key}:{value}"
        return f"{self._config.source_type.value}:hash:{compute_payload_hash(record)}"

    def _extract_pipeline_record_id(self, record: JSONObject) -> str:
        for key in self._config.id_keys:
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, int):
                return str(value)
        return str(uuid4())

    def _build_query_signature(self, *, metadata: JSONObject) -> str:
        canonical_payload = {
            "source_type": self._config.source_type.value,
            "metadata": metadata,
        }
        return compute_payload_hash(canonical_payload)


__all__ = [
    "StructuredSourceGateway",
    "StructuredSourceIngestionConfig",
    "StructuredSourceIngestionService",
    "StructuredSourceIngestionSummary",
]
