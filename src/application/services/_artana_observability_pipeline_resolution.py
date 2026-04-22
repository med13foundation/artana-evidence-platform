"""Pipeline-run resolution helpers for Artana observability."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from src.application.services._artana_observability_models import (
    _DOCUMENT_METADATA_RUN_KEYS,
    _EXTRACTION_METADATA_RUN_KEYS,
)
from src.application.services._artana_observability_support import _append_unique
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
else:
    Session = object


def load_pipeline_job_run_ids(
    session: Session,
    *,
    research_space_id: str,
    pipeline_run_id: str,
) -> list[str]:
    pipeline_jobs = (
        session.execute(
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
    run_ids: list[str] = []
    for job in pipeline_jobs:
        metadata = coerce_json_object(job.job_metadata)
        pipeline_payload = coerce_json_object(metadata.get("pipeline_run"))
        if normalize_optional_string(pipeline_payload.get("run_id")) != pipeline_run_id:
            continue
        query_generation = coerce_json_object(metadata.get("query_generation"))
        _append_unique(run_ids, query_generation.get("run_id"))
    return run_ids


def load_pipeline_document_run_ids(
    session: Session,
    *,
    research_space_id: str,
    pipeline_run_id: str,
) -> tuple[list[str], list[str]]:
    documents = (
        session.execute(
            select(SourceDocumentModel).where(
                SourceDocumentModel.research_space_id == research_space_id,
            ),
        )
        .scalars()
        .all()
    )
    run_ids: list[str] = []
    pipeline_document_ids: list[str] = []
    for document in documents:
        metadata = coerce_json_object(document.metadata_payload)
        if (
            normalize_optional_string(metadata.get("pipeline_run_id"))
            != pipeline_run_id
        ):
            continue
        pipeline_document_ids.append(str(document.id))
        _append_unique(run_ids, document.enrichment_agent_run_id)
        _append_unique(run_ids, document.extraction_agent_run_id)
        for key in _DOCUMENT_METADATA_RUN_KEYS:
            _append_unique(run_ids, metadata.get(key))
    return run_ids, pipeline_document_ids


def load_pipeline_extraction_run_ids(
    session: Session,
    *,
    research_space_id: str,
    pipeline_run_id: str,
) -> list[str]:
    publication_extractions = (
        session.execute(
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
    run_ids: list[str] = []
    for extraction in publication_extractions:
        metadata = coerce_json_object(extraction.metadata_payload)
        if (
            normalize_optional_string(metadata.get("pipeline_run_id"))
            != pipeline_run_id
        ):
            continue
        for key in _EXTRACTION_METADATA_RUN_KEYS:
            _append_unique(run_ids, metadata.get(key))
    return run_ids


def load_relation_evidence_run_ids(
    session: Session,
    *,
    pipeline_document_ids: list[str],
) -> list[str]:
    run_ids: list[str] = []
    for run_id in load_relation_evidence_agent_run_ids_for_document_ids(
        session,
        document_ids=pipeline_document_ids,
    ):
        _append_unique(run_ids, run_id)
    return run_ids


__all__ = [
    "load_pipeline_document_run_ids",
    "load_pipeline_extraction_run_ids",
    "load_pipeline_job_run_ids",
    "load_relation_evidence_run_ids",
]
