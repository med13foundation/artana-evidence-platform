"""Helper mixin for MARRVEL ingestion orchestration details."""

# mypy: disable-error-code="misc"

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from src import type_definitions
from src.domain.entities import (
    source_document,
    source_record_ledger,
    source_sync_state,
    user_data_source,
)
from src.domain.services import ingestion, marrvel_ingestion
from src.domain.services.marrvel_grounding import (
    attach_marrvel_grounding_context,
)

if TYPE_CHECKING:
    from src.application.services.marrvel_ingestion_service import (
        MarrvelIngestionService,
    )
    from src.domain.entities import data_source_configs
    from src.domain.services.ingestion import (
        IngestionProgressCallback,
        IngestionProgressUpdate,
    )


@dataclass(frozen=True)
class _LedgerDedupOutcome:
    """Result of applying record-ledger deduplication to fetched records."""

    filtered_records: list[type_definitions.common.JSONObject]
    entries_to_upsert: list[source_record_ledger.SourceRecordLedgerEntry]
    new_records: int
    updated_records: int
    unchanged_records: int


class MarrvelIngestionServiceHelpers:
    """Private helpers for MARRVEL ingestion orchestration."""

    @staticmethod
    def _build_pipeline_progress_callback(
        context: ingestion.IngestionRunContext | None,
    ) -> IngestionProgressCallback | None:
        if context is None or context.progress_callback is None:
            return None

        def _forward(update: IngestionProgressUpdate) -> None:
            context.progress_callback(
                replace(
                    update,
                    ingestion_job_id=update.ingestion_job_id
                    or context.ingestion_job_id,
                ),
            )

        return _forward

    def _build_extraction_targets(
        self: MarrvelIngestionService,
        records: list[type_definitions.common.JSONObject],
        *,
        source_type: user_data_source.SourceType,
        pipeline_run_id: str | None = None,
    ) -> tuple[ingestion.IngestionExtractionTarget, ...]:
        targets: list[ingestion.IngestionExtractionTarget] = []
        seen_source_record_ids: set[str] = set()
        for record in records:
            source_record_id = self._extract_external_record_id(record)
            if source_record_id in seen_source_record_ids:
                continue
            seen_source_record_ids.add(source_record_id)
            metadata_payload: type_definitions.common.JSONObject = {
                "raw_record": self._extract_pipeline_payload(record),
                "source_record_id": source_record_id,
                "source_type": source_type.value,
            }
            if isinstance(pipeline_run_id, str) and pipeline_run_id.strip():
                metadata_payload["pipeline_run_id"] = pipeline_run_id.strip()
            targets.append(
                ingestion.IngestionExtractionTarget(
                    source_record_id=source_record_id,
                    source_type=source_type.value,
                    publication_id=None,
                    pubmed_id=None,
                    metadata=metadata_payload,
                ),
            )
        return tuple(targets)

    async def _fetch_records_with_checkpoint(
        self: MarrvelIngestionService,
        *,
        config: data_source_configs.MarrvelQueryConfig,
        checkpoint_before: type_definitions.common.JSONObject | None,
    ) -> marrvel_ingestion.MarrvelGatewayFetchResult:
        if isinstance(self._gateway, marrvel_ingestion.MarrvelIncrementalGateway):
            return await self._gateway.fetch_records_incremental(
                config,
                checkpoint=checkpoint_before,
            )

        records = await self._gateway.fetch_records(config)
        return marrvel_ingestion.MarrvelGatewayFetchResult(
            records=records,
            fetched_records=len(records),
            checkpoint_after=None,
            checkpoint_kind=source_sync_state.CheckpointKind.NONE,
        )

    @staticmethod
    def _build_fallback_checkpoint(
        *,
        fetched_records: int,
        processed_records: int,
    ) -> type_definitions.common.JSONObject:
        return {
            "last_processed_at": datetime.now(UTC).isoformat(),
            "fetched_records": fetched_records,
            "processed_records": processed_records,
        }

    def _to_pipeline_records(
        self: MarrvelIngestionService,
        records: list[type_definitions.common.JSONObject],
        *,
        original_source_id: str,
    ) -> list[type_definitions.ingestion.RawRecord]:
        """Adapt MARRVEL JSON records into the kernel ingestion pipeline format."""
        raw_records: list[type_definitions.ingestion.RawRecord] = []
        for record in records:
            gene_symbol = record.get("gene_symbol")
            record_id = (
                gene_symbol
                if isinstance(gene_symbol, str) and gene_symbol.strip()
                else str(uuid4())
            )
            payload = self._extract_pipeline_payload(record)
            grounded_payload = attach_marrvel_grounding_context(payload)

            raw_records.append(
                type_definitions.ingestion.RawRecord(
                    source_id=record_id,
                    data=grounded_payload,
                    metadata={
                        "original_source_id": original_source_id,
                        "type": "marrvel",
                        "entity_type": "GENE",
                        "gene_symbol": grounded_payload.get("gene_symbol"),
                        "record_type": grounded_payload.get("record_type"),
                    },
                ),
            )

        return raw_records

    def _build_ledger_dedup_outcome(
        self: MarrvelIngestionService,
        *,
        source: user_data_source.UserDataSource,
        records: list[type_definitions.common.JSONObject],
        context: ingestion.IngestionRunContext | None,
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
                self._compute_payload_hash(record),
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
        filtered_records: list[type_definitions.common.JSONObject] = []
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
                    source_updated_at=self._extract_source_updated_at(record),
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
                source_updated_at=self._extract_source_updated_at(record),
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

    @staticmethod
    def _extract_external_record_id(
        record: type_definitions.common.JSONObject,
    ) -> str:
        gene_symbol = record.get("gene_symbol")
        if isinstance(gene_symbol, str) and gene_symbol.strip():
            record_type = record.get("record_type", "gene_aggregate")
            return f"marrvel:{record_type}:{gene_symbol.strip().upper()}"

        payload_hash = MarrvelIngestionServiceHelpers._compute_payload_hash(record)
        return f"marrvel:hash:{payload_hash}"

    @staticmethod
    def _compute_payload_hash(
        record: type_definitions.common.JSONObject,
    ) -> str:
        serialized = json.dumps(
            record,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _extract_source_updated_at(
        record: type_definitions.common.JSONObject,
    ) -> datetime | None:
        for key in ("fetched_at", "updated_at", "last_updated"):
            value = record.get(key)
            if isinstance(value, str):
                try:
                    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if parsed.tzinfo is None:
                    return parsed.replace(tzinfo=UTC)
                return parsed
        return None

    @staticmethod
    def _build_query_signature(
        *,
        source_type: user_data_source.SourceType,
        metadata: object,
    ) -> str:
        canonical_payload = json.dumps(
            {
                "source_type": source_type.value,
                "metadata": metadata,
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _extract_pipeline_payload(
        record: type_definitions.common.JSONObject,
    ) -> type_definitions.common.JSONObject:
        payload: type_definitions.common.JSONObject = {}
        for key in (
            "gene_symbol",
            "taxon_id",
            "record_type",
            "source",
            "fetched_at",
            "gene_info",
            "omim_entries",
            "dbnsfp_variants",
            "clinvar_entries",
        ):
            value = record.get(key)
            if value is not None:
                payload[key] = type_definitions.json_utils.to_json_value(value)

        if payload:
            return payload

        for key, value in record.items():
            payload[str(key)] = type_definitions.json_utils.to_json_value(value)
        return payload

    async def _persist_raw_records(
        self: MarrvelIngestionService,
        records: list[type_definitions.common.JSONObject],
        source: user_data_source.UserDataSource,
    ) -> str | None:
        """Persist raw records to storage if backend is available."""
        if not self._storage_service:
            return None

        backend = self._storage_service.resolve_backend_for_use_case(
            type_definitions.storage.StorageUseCase.RAW_SOURCE,
        )
        if not backend:
            return None

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(list(records), tmp, default=str)
            tmp_path = Path(tmp.name)

        try:
            timestamp = source.updated_at.strftime("%Y%m%d_%H%M%S")
            key = f"marrvel/{source.id}/raw/{timestamp}_{uuid4().hex[:8]}.json"

            operation = await self._storage_service.record_store_operation(
                configuration=backend,
                key=key,
                file_path=tmp_path,
                content_type="application/json",
                user_id=source.owner_id,
                metadata={
                    "source_id": str(source.id),
                    "record_count": len(records),
                },
            )
            return operation.key
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def _upsert_source_documents(
        self: MarrvelIngestionService,
        *,
        records: list[type_definitions.common.JSONObject],
        source: user_data_source.UserDataSource,
        context: ingestion.IngestionRunContext | None,
        raw_storage_key: str | None,
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
            grounded_record = attach_marrvel_grounding_context(
                self._extract_pipeline_payload(record),
            )
            metadata_payload: type_definitions.common.JSONObject = {
                "raw_record": grounded_record,
            }
            if (
                context is not None
                and isinstance(context.pipeline_run_id, str)
                and context.pipeline_run_id.strip()
            ):
                metadata_payload["pipeline_run_id"] = context.pipeline_run_id.strip()
            documents.append(
                source_document.SourceDocument(
                    id=uuid4(),
                    research_space_id=source.research_space_id,
                    source_id=source.id,
                    ingestion_job_id=context.ingestion_job_id if context else None,
                    external_record_id=external_record_id,
                    source_type=source.source_type,
                    document_format=source_document.DocumentFormat.MARRVEL_JSON,
                    raw_storage_key=raw_storage_key,
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
