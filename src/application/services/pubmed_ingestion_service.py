"""Application service for orchestrating PubMed ingestion per data source."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.domain.entities import data_source_configs, user_data_source
from src.domain.services.pubmed_ingestion import (
    PubMedGateway,
    PubMedIngestionSummary,
)
from src.domain.transform.transformers.pubmed_record_transformer import (
    PubMedRecordTransformer,
)

from ._pubmed_ingestion_helpers import PubMedIngestionServiceHelpers
from .query_generation_service import (
    QueryGenerationService,
    QueryGenerationServiceDependencies,
)

if TYPE_CHECKING:
    from src.application.services.ports.ingestion_pipeline_port import (
        IngestionPipelinePort,
    )
    from src.application.services.storage_configuration_service import (
        StorageConfigurationService,
    )
    from src.domain.agents.ports.query_agent_port import QueryAgentPort
    from src.domain.repositories import (
        PublicationRepository,
        ResearchSpaceRepository,
        SourceDocumentRepository,
    )
    from src.domain.services.ingestion import IngestionRunContext
    from src.type_definitions.common import JSONObject, SourceMetadata


@dataclass(frozen=True)
class _LedgerDedupOutcome:
    filtered_records: list[dict[str, object]]
    entries_to_upsert: list[dict[str, object]]
    new_records: int
    updated_records: int
    unchanged_records: int


@dataclass(frozen=True)
class PubMedIngestionDependencies:
    """Optional collaborators for PubMed ingestion orchestration."""

    publication_repository: PublicationRepository | None = None
    transformer: PubMedRecordTransformer | None = None
    storage_service: StorageConfigurationService | None = None
    query_agent: QueryAgentPort | None = None
    research_space_repository: ResearchSpaceRepository | None = None
    source_document_repository: SourceDocumentRepository | None = None
    query_generation_service: QueryGenerationService | None = None


class PubMedIngestionService(PubMedIngestionServiceHelpers):
    """Coordinate fetching, transforming, and persisting PubMed data per source."""

    def __init__(
        self,
        gateway: PubMedGateway,
        pipeline: IngestionPipelinePort,
        dependencies: PubMedIngestionDependencies | None = None,
    ) -> None:
        resolved_dependencies = dependencies or PubMedIngestionDependencies()
        self._gateway = gateway
        self._pipeline = pipeline
        self._publication_repository = resolved_dependencies.publication_repository
        self._transformer = (
            resolved_dependencies.transformer or PubMedRecordTransformer()
        )
        self._storage_service = resolved_dependencies.storage_service
        self._query_agent = resolved_dependencies.query_agent
        self._research_space_repository = (
            resolved_dependencies.research_space_repository
        )
        self._source_document_repository = (
            resolved_dependencies.source_document_repository
        )
        self._query_generation_service = (
            resolved_dependencies.query_generation_service
            or QueryGenerationService(
                dependencies=QueryGenerationServiceDependencies(
                    query_agent=self._query_agent,
                    research_space_repository=self._research_space_repository,
                ),
            )
        )

    async def ingest(
        self,
        source: user_data_source.UserDataSource,
        context: IngestionRunContext | None = None,
    ) -> PubMedIngestionSummary:
        """Execute ingestion for a PubMed data source."""
        self._assert_source_type(source)
        config = self._build_config(source.configuration)
        query_resolution = await self._resolve_query_configuration(
            source=source,
            config=config,
        )
        config = query_resolution.config
        query_generation_decision = query_resolution.query_generation_decision
        query_generation_confidence = query_resolution.query_generation_confidence
        query_generation_run_id = query_resolution.query_generation_run_id
        query_generation_execution_mode = (
            query_resolution.query_generation_execution_mode
        )
        query_generation_fallback_reason = (
            query_resolution.query_generation_fallback_reason
        )
        pipeline_run_id = (
            context.pipeline_run_id
            if context is not None
            and isinstance(context.pipeline_run_id, str)
            and context.pipeline_run_id.strip()
            else None
        )
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
        query_resolved_message = "Resolved PubMed query configuration."
        if query_generation_fallback_reason is not None:
            query_resolved_message = "Fell back to base PubMed query configuration."
        self._emit_progress_update(
            context=context,
            event_type="query_resolved",
            message=query_resolved_message,
            payload={
                "executed_query": config.query,
                "query_signature": query_signature,
                "query_generation_decision": query_generation_decision,
                "query_generation_confidence": query_generation_confidence,
                "query_generation_run_id": query_generation_run_id,
                "query_generation_execution_mode": (query_generation_execution_mode),
                "query_generation_fallback_reason": (query_generation_fallback_reason),
            },
        )

        fetch_result = await self._fetch_records_with_checkpoint(
            config=config,
            checkpoint_before=checkpoint_before,
        )
        raw_records_data = fetch_result.records
        self._emit_progress_update(
            context=context,
            event_type="records_fetched",
            message=(
                "Fetched candidate PubMed records "
                f"({fetch_result.fetched_records} records)."
            ),
            payload={
                "fetched_records": fetch_result.fetched_records,
                "checkpoint_kind": fetch_result.checkpoint_kind.value,
            },
        )
        forced_external_record_ids: set[str] | None = None
        if isinstance(config.pinned_pubmed_id, str) and config.pinned_pubmed_id.strip():
            normalized_pmid = config.pinned_pubmed_id.strip()
            forced_external_record_ids = {
                f"pubmed:pmid:{normalized_pmid}",
                f"pubmed:pubmed_id:{normalized_pmid}",
            }
        dedup_outcome = self._build_ledger_dedup_outcome(
            source=source,
            records=raw_records_data,
            context=context,
            force_external_record_ids=forced_external_record_ids,
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
        self._emit_progress_update(
            context=context,
            event_type="source_documents_upserted",
            message=(
                "Upserted source documents for fetched PubMed records "
                f"({len(raw_records_data)} documents)."
            ),
            payload={
                "document_count": len(raw_records_data),
                "raw_storage_key": raw_storage_key,
                "pipeline_run_id": pipeline_run_id,
            },
        )

        raw_records = self._to_pipeline_records(
            filtered_records,
            original_source_id=str(source.id),
            domain_context=config.domain_context,
        )

        observations_created = 0
        if source.research_space_id is not None:
            self._emit_progress_update(
                context=context,
                event_type="kernel_ingestion_started",
                message="Kernel ingestion pipeline started for filtered PubMed records.",
                payload={
                    "record_count": len(raw_records),
                    "pipeline_run_id": pipeline_run_id,
                },
            )
            result = self._pipeline.run(
                raw_records,
                research_space_id=str(source.research_space_id),
                progress_callback=self._build_pipeline_progress_callback(context),
            )
            observations_created = result.observations_created
            self._emit_progress_update(
                context=context,
                event_type="kernel_ingestion_finished",
                message="Kernel ingestion pipeline finished for PubMed records.",
                payload={
                    "record_count": len(raw_records),
                    "observations_created": observations_created,
                    "error_count": len(result.errors),
                    "pipeline_run_id": pipeline_run_id,
                    "success": result.success,
                },
            )
        else:
            # Keep source-level behavior consistent with legacy implementation
            # without requiring an injected logger.
            pass

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

        return PubMedIngestionSummary(
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
            query_generation_run_id=query_generation_run_id,
            query_generation_model=config.agent_config.model_id,
            query_generation_decision=query_generation_decision,
            query_generation_confidence=query_generation_confidence,
            query_generation_execution_mode=query_generation_execution_mode,
            query_generation_fallback_reason=query_generation_fallback_reason,
            query_generation_downstream_fetched_records=fetch_result.fetched_records,
            query_generation_downstream_processed_records=len(filtered_records),
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
        configuration: user_data_source.SourceConfiguration,
    ) -> data_source_configs.PubMedQueryConfig:
        metadata: SourceMetadata = dict(configuration.metadata or {})
        if configuration.query:
            metadata["query"] = configuration.query
        return data_source_configs.PubMedQueryConfig.model_validate(metadata)

    @staticmethod
    def _assert_source_type(source: user_data_source.UserDataSource) -> None:
        if source.source_type != user_data_source.SourceType.PUBMED:
            message = (
                f"PubMed ingestion can only be executed for PubMed sources "
                f"(got {source.source_type.value})"
            )
            raise ValueError(message)
