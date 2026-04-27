"""Source-document extraction orchestration for the observation bridge."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from artana_evidence_api.source_document_entity_extraction import (
    RecognizedEntityCandidate,
    extract_entity_candidates,
    source_document_text,
)
from artana_evidence_api.source_document_graph_writer import SourceDocumentGraphWriter
from artana_evidence_api.source_document_models import (
    DocumentExtractionStatus,
    ObservationBridgeEntityRecognitionServiceProtocol,
    SourceDocument,
    SourceDocumentRepositoryProtocol,
)
from artana_evidence_api.types.common import JSONObject
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class SourceDocumentExtractionSummary:
    """Summary returned by deterministic source-document extraction."""

    derived_graph_seed_entity_ids: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


class ServiceLocalSourceDocumentExtractionService:
    """Coordinate source-document extraction across focused dependencies."""

    def __init__(
        self,
        *,
        session: Session,
        repository: SourceDocumentRepositoryProtocol,
        graph_writer: SourceDocumentGraphWriter | None = None,
    ) -> None:
        self._repository = repository
        self._graph_writer = (
            graph_writer if graph_writer is not None else SourceDocumentGraphWriter(session)
        )

    async def process_pending_documents(
        self,
        *,
        limit: int,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
        source_type: str | None = None,
        pipeline_run_id: str | None = None,
    ) -> SourceDocumentExtractionSummary:
        del pipeline_run_id
        pending_documents = self._repository.list_pending_extraction(
            limit=limit,
            source_id=source_id,
            research_space_id=research_space_id,
            ingestion_job_id=ingestion_job_id,
            source_type=source_type,
        )
        seed_entity_ids: list[str] = []
        run_errors: list[str] = []
        for raw_source_document in pending_documents:
            source_document = SourceDocument.model_validate(raw_source_document)
            result = self._process_document(source_document)
            for seed_entity_id in result.derived_graph_seed_entity_ids:
                if seed_entity_id not in seed_entity_ids:
                    seed_entity_ids.append(seed_entity_id)
            for error in result.errors:
                if error not in run_errors:
                    run_errors.append(error)
        return SourceDocumentExtractionSummary(
            derived_graph_seed_entity_ids=tuple(seed_entity_ids),
            errors=tuple(run_errors),
        )

    def _process_document(
        self,
        source_document: SourceDocument,
    ) -> SourceDocumentExtractionSummary:
        metadata = dict(source_document.metadata)
        candidates = extract_entity_candidates(source_document_text(metadata))
        entity_ids_by_label: dict[str, str] = {}
        graph_write_warning: str | None = None

        if source_document.research_space_id is not None and candidates:
            try:
                entity_ids_by_label = self._graph_writer.persist_candidates(
                    source_document=source_document,
                    candidates=candidates,
                )
            except Exception as exc:  # noqa: BLE001
                graph_write_warning = _graph_write_warning(exc)

        extraction_status = (
            DocumentExtractionStatus.FAILED
            if graph_write_warning is not None
            else DocumentExtractionStatus.EXTRACTED
        )
        updated_document = source_document.model_copy(
            update={
                "extraction_status": extraction_status,
                "extraction_agent_run_id": None,
                "metadata": self._extraction_metadata(
                    metadata=metadata,
                    candidates=candidates,
                    entity_ids_by_label=entity_ids_by_label,
                    graph_write_warning=graph_write_warning,
                ),
                "updated_at": datetime.now(UTC),
            },
        )
        self._repository.upsert(updated_document)
        return SourceDocumentExtractionSummary(
            derived_graph_seed_entity_ids=tuple(entity_ids_by_label.values()),
            errors=(graph_write_warning,) if graph_write_warning is not None else (),
        )

    @staticmethod
    def _extraction_metadata(
        *,
        metadata: JSONObject,
        candidates: list[RecognizedEntityCandidate],
        entity_ids_by_label: dict[str, str],
        graph_write_warning: str | None,
    ) -> JSONObject:
        observations_created = len(entity_ids_by_label)
        detected_entities = [
            {
                "label": candidate.label,
                "entity_type": candidate.entity_type,
                "normalized_label": candidate.normalized_label,
                "graph_entity_id": entity_ids_by_label.get(candidate.label),
            }
            for candidate in candidates
        ]
        ingestion_errors = (
            [graph_write_warning] if graph_write_warning is not None else []
        )
        updated_metadata: JSONObject = {
            **metadata,
            "entity_recognition_decision": "generated",
            "entity_recognition_confidence": 0.72 if detected_entities else 0.0,
            "entity_recognition_rationale": (
                "Service-local deterministic entity mention extraction."
                if detected_entities
                else "No deterministic entity mentions were detected."
            ),
            "entity_recognition_run_id": None,
            "entity_recognition_shadow_mode": False,
            "entity_recognition_requires_review": False,
            "entity_recognition_governance_reason": "service_local_bridge",
            "entity_recognition_wrote_to_kernel": observations_created > 0,
            "entity_recognition_ingestion_success": graph_write_warning is None,
            "entity_recognition_ingestion_entities_created": observations_created,
            "entity_recognition_ingestion_observations_created": observations_created,
            "entity_recognition_ingestion_errors": ingestion_errors,
            "entity_recognition_detected_entities": detected_entities,
            "entity_recognition_processed_at": datetime.now(UTC).isoformat(),
        }
        if graph_write_warning is not None:
            updated_metadata["entity_recognition_graph_write_warning"] = (
                graph_write_warning
            )
        return updated_metadata

    async def close(self) -> None:
        return None


def _graph_write_warning(exc: Exception) -> str:
    message = str(exc).strip()
    if message == "":
        return f"observation_bridge_graph_write_skipped:{type(exc).__name__}"
    return (
        f"observation_bridge_graph_write_skipped:{type(exc).__name__}:"
        f"{message[:240]}"
    )


def create_observation_bridge_entity_recognition_service(
    *,
    session: Session,
    source_document_repository: object,
    pipeline_run_event_repository: object,
) -> ObservationBridgeEntityRecognitionServiceProtocol:
    """Return the service-local deterministic entity-recognition bridge."""

    del pipeline_run_event_repository
    return ServiceLocalSourceDocumentExtractionService(
        session=session,
        repository=cast(
            "SourceDocumentRepositoryProtocol",
            source_document_repository,
        ),
    )


__all__ = [
    "ServiceLocalSourceDocumentExtractionService",
    "SourceDocumentExtractionSummary",
    "create_observation_bridge_entity_recognition_service",
]
