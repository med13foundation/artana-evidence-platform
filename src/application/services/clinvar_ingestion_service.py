"""Application service for orchestrating ClinVar ingestion per data source."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.domain.entities import data_source_configs, user_data_source
from src.domain.services import clinvar_ingestion, ingestion

from ._clinvar_ingestion_helpers import ClinVarIngestionServiceHelpers

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.application.services.ports.ingestion_pipeline_port import (
        IngestionPipelinePort,
    )
    from src.application.services.storage_configuration_service import (
        StorageConfigurationService,
    )
    from src.domain.repositories.source_document_repository import (
        SourceDocumentRepository,
    )
    from src.type_definitions.common import JSONObject


class ClinVarIngestionService(ClinVarIngestionServiceHelpers):
    """Coordinate fetching, transforming, and persisting ClinVar data per source."""

    def __init__(
        self,
        gateway: clinvar_ingestion.ClinVarGateway,
        pipeline: IngestionPipelinePort,
        storage_service: StorageConfigurationService | None = None,
        source_document_repository: SourceDocumentRepository | None = None,
    ) -> None:
        self._gateway = gateway
        self._pipeline = pipeline
        self._storage_service = storage_service
        self._source_document_repository = source_document_repository

    async def ingest(
        self,
        source: user_data_source.UserDataSource,
        context: ingestion.IngestionRunContext | None = None,
    ) -> clinvar_ingestion.ClinVarIngestionSummary:
        """Execute ingestion for a ClinVar data source."""
        self._assert_source_type(source)
        config = self._build_config(source.configuration)
        checkpoint_before = (
            dict(context.source_sync_state.checkpoint_payload)
            if context is not None
            else None
        )
        query_signature = (
            context.query_signature
            if context is not None and context.query_signature.strip()
            else self._build_query_signature(
                source_type=source.source_type,
                metadata=config.model_dump(mode="json"),
            )
        )
        pipeline_run_id = (
            context.pipeline_run_id
            if context is not None
            and isinstance(context.pipeline_run_id, str)
            and context.pipeline_run_id.strip()
            else None
        )

        fetch_result = await self._fetch_records_with_checkpoint(
            config=config,
            checkpoint_before=checkpoint_before,
        )
        raw_records_data = fetch_result.records
        dedup_outcome = self._build_ledger_dedup_outcome(
            source=source,
            records=raw_records_data,
            context=context,
        )
        filtered_records = dedup_outcome.filtered_records

        raw_storage_key: str | None = None
        if self._storage_service:
            raw_storage_key = await self._persist_raw_records(raw_records_data, source)
        self._upsert_source_documents(
            records=raw_records_data,
            source=source,
            context=context,
            raw_storage_key=raw_storage_key,
        )

        raw_records = self._to_pipeline_records(
            filtered_records,
            original_source_id=str(source.id),
        )

        observations_created = 0
        if source.research_space_id is not None:
            result = self._pipeline.run(
                raw_records,
                research_space_id=str(source.research_space_id),
                progress_callback=self._build_pipeline_progress_callback(context),
            )
            observations_created = result.observations_created
        else:
            logger.warning(
                "ClinVar source %s has no research_space_id; skipping kernel pipeline",
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

        checkpoint_after_raw = fetch_result.checkpoint_after
        if isinstance(checkpoint_after_raw, dict):
            checkpoint_after_payload: JSONObject = dict(checkpoint_after_raw)
        else:
            checkpoint_after_payload = self._build_fallback_checkpoint(
                fetched_records=fetch_result.fetched_records,
                processed_records=len(filtered_records),
            )

        return clinvar_ingestion.ClinVarIngestionSummary(
            source_id=source.id,
            ingestion_job_id=context.ingestion_job_id if context else None,
            fetched_records=fetch_result.fetched_records,
            parsed_publications=len(raw_records),
            created_publications=observations_created,
            updated_publications=0,
            extraction_targets=self._build_extraction_targets(
                filtered_records,
                source_type=source.source_type,
                pipeline_run_id=pipeline_run_id,
            ),
            executed_query=config.query,
            query_signature=query_signature,
            checkpoint_before=checkpoint_before,
            checkpoint_after=checkpoint_after_payload,
            checkpoint_kind=fetch_result.checkpoint_kind.value,
            new_records=dedup_outcome.new_records,
            updated_records=dedup_outcome.updated_records,
            unchanged_records=dedup_outcome.unchanged_records,
            skipped_records=dedup_outcome.unchanged_records,
        )

    @staticmethod
    def _build_config(
        source_config: user_data_source.SourceConfiguration,
    ) -> data_source_configs.ClinVarQueryConfig:
        metadata = source_config.metadata or {}
        return data_source_configs.ClinVarQueryConfig.model_validate(metadata)

    @staticmethod
    def _assert_source_type(source: user_data_source.UserDataSource) -> None:
        if source.source_type != user_data_source.SourceType.CLINVAR:
            msg = (
                "ClinVar ingestion can only run for ClinVar sources "
                f"(got {source.source_type.value})"
            )
            raise ValueError(msg)
