"""Run-id loading helpers for pipeline cost attribution."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from sqlalchemy import select

from src.application.services._source_workflow_monitor_shared import (
    coerce_json_object,
    normalize_optional_string,
)
from src.infrastructure.repositories.graph_observability_repository import (
    load_relation_evidence_agent_run_ids_for_document_ids,
)
from src.models.database.ingestion_job import IngestionJobKindEnum, IngestionJobModel
from src.models.database.publication_extraction import PublicationExtractionModel
from src.models.database.source_document import SourceDocumentModel
from src.models.database.user_data_source import UserDataSourceModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class _PipelineRunTraceRunIdLoader:
    """Load linked Artana run ids across pipeline stages."""

    if TYPE_CHECKING:
        _session: Session

    def _load_stage_run_ids(
        self,
        *,
        research_space_id: str,
        pipeline_run_id: str,
    ) -> dict[str, list[str]]:
        stage_run_ids: dict[str, list[str]] = defaultdict(list)
        self._load_job_run_ids(
            research_space_id=research_space_id,
            pipeline_run_id=pipeline_run_id,
            stage_run_ids=stage_run_ids,
        )
        self._load_document_run_ids(
            research_space_id=research_space_id,
            pipeline_run_id=pipeline_run_id,
            stage_run_ids=stage_run_ids,
        )
        self._load_extraction_run_ids(
            research_space_id=research_space_id,
            pipeline_run_id=pipeline_run_id,
            stage_run_ids=stage_run_ids,
        )
        self._load_relation_evidence_run_ids(
            research_space_id=research_space_id,
            pipeline_run_id=pipeline_run_id,
            stage_run_ids=stage_run_ids,
        )
        return stage_run_ids

    def _load_job_run_ids(
        self,
        *,
        research_space_id: str,
        pipeline_run_id: str,
        stage_run_ids: dict[str, list[str]],
    ) -> None:
        jobs = (
            self._session.execute(
                select(IngestionJobModel)
                .join(
                    UserDataSourceModel,
                    UserDataSourceModel.id == IngestionJobModel.source_id,
                )
                .where(UserDataSourceModel.research_space_id == research_space_id)
                .where(
                    IngestionJobModel.job_kind
                    == IngestionJobKindEnum.PIPELINE_ORCHESTRATION,
                ),
            )
            .scalars()
            .all()
        )
        for job in jobs:
            metadata = coerce_json_object(job.job_metadata)
            pipeline_payload = coerce_json_object(metadata.get("pipeline_run"))
            if (
                normalize_optional_string(pipeline_payload.get("run_id"))
                != pipeline_run_id
            ):
                continue
            query_generation = coerce_json_object(metadata.get("query_generation"))
            _append_unique(
                stage_run_ids["query_generation"],
                normalize_optional_string(query_generation.get("run_id")),
            )
            query_progress = coerce_json_object(pipeline_payload.get("query_progress"))
            _append_unique(
                stage_run_ids["query_generation"],
                normalize_optional_string(
                    query_progress.get("query_generation_run_id"),
                ),
            )

    def _load_document_run_ids(
        self,
        *,
        research_space_id: str,
        pipeline_run_id: str,
        stage_run_ids: dict[str, list[str]],
    ) -> None:
        documents = (
            self._session.execute(
                select(SourceDocumentModel).where(
                    SourceDocumentModel.research_space_id == research_space_id,
                ),
            )
            .scalars()
            .all()
        )
        for document in documents:
            metadata = coerce_json_object(document.metadata_payload)
            if (
                normalize_optional_string(metadata.get("pipeline_run_id"))
                != pipeline_run_id
            ):
                continue
            _append_unique(
                stage_run_ids["enrichment"],
                normalize_optional_string(document.enrichment_agent_run_id),
            )
            _append_unique(
                stage_run_ids["enrichment"],
                normalize_optional_string(
                    metadata.get("content_enrichment_agent_run_id"),
                ),
            )
            for key in (
                "entity_recognition_run_id",
                "extraction_stage_run_id",
                "extraction_run_id",
            ):
                _append_unique(
                    stage_run_ids["extraction"],
                    normalize_optional_string(metadata.get(key)),
                )
            _append_unique(
                stage_run_ids["extraction"],
                normalize_optional_string(document.extraction_agent_run_id),
            )
            for key in (
                "graph_agent_run_id",
                "graph_connection_run_id",
                "graph_run_id",
            ):
                _append_unique(
                    stage_run_ids["graph"],
                    normalize_optional_string(metadata.get(key)),
                )

    def _load_extraction_run_ids(
        self,
        *,
        research_space_id: str,
        pipeline_run_id: str,
        stage_run_ids: dict[str, list[str]],
    ) -> None:
        extraction_rows = (
            self._session.execute(
                select(PublicationExtractionModel)
                .join(
                    UserDataSourceModel,
                    UserDataSourceModel.id == PublicationExtractionModel.source_id,
                )
                .where(UserDataSourceModel.research_space_id == research_space_id),
            )
            .scalars()
            .all()
        )
        for extraction in extraction_rows:
            metadata = coerce_json_object(extraction.metadata_payload)
            if (
                normalize_optional_string(metadata.get("pipeline_run_id"))
                != pipeline_run_id
            ):
                continue
            for key in ("agent_run_id", "extraction_run_id"):
                _append_unique(
                    stage_run_ids["extraction"],
                    normalize_optional_string(metadata.get(key)),
                )
            for key in (
                "graph_agent_run_id",
                "graph_connection_run_id",
                "graph_run_id",
            ):
                _append_unique(
                    stage_run_ids["graph"],
                    normalize_optional_string(metadata.get(key)),
                )

    def _load_relation_evidence_run_ids(
        self,
        *,
        research_space_id: str,
        pipeline_run_id: str,
        stage_run_ids: dict[str, list[str]],
    ) -> None:
        document_ids: list[str] = []
        documents = (
            self._session.execute(
                select(SourceDocumentModel).where(
                    SourceDocumentModel.research_space_id == research_space_id,
                ),
            )
            .scalars()
            .all()
        )
        for document in documents:
            metadata = coerce_json_object(document.metadata_payload)
            if (
                normalize_optional_string(metadata.get("pipeline_run_id"))
                != pipeline_run_id
            ):
                continue
            document_ids.append(str(document.id))
        if not document_ids:
            return
        for run_id in load_relation_evidence_agent_run_ids_for_document_ids(
            self._session,
            document_ids=document_ids,
        ):
            _append_unique(
                stage_run_ids["graph"],
                normalize_optional_string(run_id),
            )


def _append_unique(target: list[str], value: str | None) -> None:
    if value is None or value in target:
        return
    target.append(value)


__all__ = ["_PipelineRunTraceRunIdLoader"]
